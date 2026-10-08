"""Registry and runner tests; the database ones need GEOAPPS_TEST_DATABASE_URL."""

import json
import os

import pytest
from sqlalchemy import create_engine, text

from geoapps_workers import runner  # noqa: F401  (registers steps)
from geoapps_workers.registry import REGISTRY
from geoapps_workers.steps.demo import plume_polygon

URL = os.environ.get("GEOAPPS_TEST_DATABASE_URL")


def test_registry_has_steps_with_schemas():
    assert {"seed_demo", "import_detections"} <= set(REGISTRY)
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
    engine = create_engine(URL)
    with engine.begin() as conn:
        for schema in ("notify", "review", "ref", "core"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    engine.dispose()
    from alembic import command

    from geoapps_db.cli import alembic_config

    command.upgrade(alembic_config(URL), "head")
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
