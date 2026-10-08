"""Registry and runner tests; the database ones need GEOAPPS_TEST_DATABASE_URL."""

import json
import os

import pytest

from geoapps_db.testing import reset_database
from geoapps_workers import runner  # noqa: F401  (registers steps)
from geoapps_workers.registry import REGISTRY
from geoapps_workers.steps.demo import plume_polygon

URL = os.environ.get("GEOAPPS_TEST_DATABASE_URL")


def test_registry_has_steps_with_schemas():
    assert {"seed_demo", "import_detections", "import_mars_plumes"} <= set(REGISTRY)
    for step in REGISTRY.values():
        schema = step.params.model_json_schema()
        assert schema["type"] == "object"


def test_plume_polygon_is_closed_ring():
    ring = plume_polygon(-103.5, 31.9, 45.0, 1000.0)["coordinates"][0]
    assert ring[0] == ring[-1]
    assert len(ring) > 10


@pytest.fixture()
def db(monkeypatch):
    if not URL:
        pytest.skip("set GEOAPPS_TEST_DATABASE_URL to run database tests")
    reset_database(URL)
    monkeypatch.setenv("GEOAPPS_DATABASE_URL", URL)
    from geoapps_db.session import get_engine

    get_engine.cache_clear()
    yield URL
    get_engine.cache_clear()


def test_seed_then_import_through_queue(db, tmp_path):
    from geoapps_db import repo, session_scope
    from geoapps_workers.cli import main

    main(["submit", "seed_demo", '{"n": 5, "seed": 1}'])
    assert runner.run_once() is not None
    assert runner.run_once() is None  # queue drained

    good = {
        "type": "Feature",
        "geometry": plume_polygon(-103.4, 31.9, 90, 800),
        "properties": {
            "observed_at": "2026-09-30T17:05:00Z",
            "q_kg_h": 400,
            "q_sigma_kg_h": 90,
            "p": 0.8,
        },
    }
    bad_marks = {**good, "properties": {**good["properties"], "p": 7}}
    no_time = {**good, "properties": {"q_kg_h": 1, "q_sigma_kg_h": 1, "p": 0.5}}
    path = tmp_path / "mine.geojson"
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": [good, bad_marks, no_time]})
    )

    main(["submit", "import_detections", json.dumps({"source": str(path)})])
    job_id = runner.run_once()
    with session_scope() as s:
        job = repo.get_job(s, job_id)
        assert job["state"] == "done", job
        assert job["result"]["imported"] == 1
        assert job["result"]["skipped_total"] == 2
        assert repo.counts(s)["predicted"] == 6


def test_failed_step_rolls_back(db):
    from geoapps_db import repo, session_scope
    from geoapps_workers.cli import main

    main(["submit", "import_detections", json.dumps({"source": "/nonexistent.geojson"})])
    job_id = runner.run_once()
    with session_scope() as s:
        job = repo.get_job(s, job_id)
        assert job["state"] == "failed"
        assert "nonexistent" in job["error"]
        assert repo.counts(s)["predicted"] == 0


FIXTURE = __import__("pathlib").Path(__file__).parent / "data" / "mars_fixture.csv"


def _run(step: str, params: dict) -> dict:
    from geoapps_db import repo, session_scope
    from geoapps_workers.cli import main

    main(["submit", step, json.dumps(params)])
    job_id = runner.run_once()
    with session_scope() as s:
        job = repo.get_job(s, job_id)
    assert job["state"] == "done", job["error"]
    return job["result"]


def test_mars_import_then_reimport(db, tmp_path):
    from geoapps_db import repo, session_scope

    first = _run("import_mars_plumes", {"path": str(FIXTURE)})
    assert (first["rows"], first["imported"], first["skipped_total"]) == (6, 4, 2)
    assert first["sources_created"] == 2
    assert first["sensors"] == ["EMIT (NASA)", "Sentinel-2 (ESA)"]
    assert first["licence"] == "CC BY-NC-SA 4.0"
    with session_scope() as s:
        assert repo.counts(s)["predicted"] == 4  # an import never skips review (E4)
        (ds,) = repo.list_datasets(s)
        assert ds["n_detections"] == 4 and ds["attribution"].startswith("UNEP")
        sources = repo.sources_geojson(s)["features"]
        assert sorted(f["properties"]["n_detections"] for f in sources) == [1, 3]

    # the same bytes again: nothing to do
    assert _run("import_mars_plumes", {"path": str(FIXTURE)})["unchanged_file"] is True

    # the provider revises one plume and adds one
    text = FIXTURE.read_text(encoding="utf-8-sig").splitlines()
    text[1] = (
        text[1]
        .replace(",1200,400,", ",1300,380,")
        .replace("2025-05-20T09:00:00Z", "2025-06-01T09:00:00Z")
    )
    text.append(text[2].replace("fixture-0002", "fixture-0007").replace("2025-05-10", "2025-05-12"))
    revised = tmp_path / "revised.csv"
    revised.write_text("\n".join(text) + "\n")
    again = _run("import_mars_plumes", {"path": str(revised)})
    assert (again["imported"], again["updated"], again["unchanged"]) == (1, 1, 3)
    with session_scope() as s:
        q = [f["properties"].get("q_kg_h") for f in repo.detections_geojson(s)["features"]]
        assert 1300.0 in q and 1200.0 not in q


def test_mars_accept_provider_validation_builds_events(db):
    from geoapps_db import repo, session_scope

    out = _run("import_mars_plumes", {"path": str(FIXTURE), "accept_provider_validation": True})
    assert out["imported"] == 4 and out["validated_by_provider"]
    with session_scope() as s:
        assert repo.counts(s)["validated"] == 4
        tst001 = repo.xref_lookup(s, "unep-mars", "source", "TST001")
        detail = repo.source_detail(s, tst001)
        # 1 and 10 May chain into one event; 1 August is more than 30 days later
        assert [e["n_detections"] for e in detail["events"]] == [2, 1]
        assert detail["first_seen"].startswith("2025-05-01")
        assert detail["xrefs"] == [
            {"provider": "unep-mars", "record_id": "TST001", "match_score": None}
        ]
        ls = repo.freeze_label_set(s, "mars", analyst_prefix="provider:unep-mars")
        assert ls.n_labels == 4
