"""API tests. The full loop (seed → verdict → alert) needs GEOAPPS_TEST_DATABASE_URL."""

import os

import pytest
from fastapi.testclient import TestClient

from geoapps_api.main import app
from geoapps_db.testing import reset_database

URL = os.environ.get("GEOAPPS_TEST_DATABASE_URL")


def test_openapi_contract_lists_routes():
    spec = app.openapi()
    paths = set(spec["paths"])
    for p in (
        "/api/queue",
        "/api/detections/{detection_id}/verdict",
        "/api/watches",
        "/api/alerts",
        "/api/etl/{name}/jobs",
        "/api/explore/search",
        "/api/sources/{source_id}",
        "/api/events",
        "/api/datasets",
        "/api/attributions/{link_id}",
        "/api/detections/{detection_id}/relations",
    ):
        assert p in paths


@pytest.fixture()
def client(monkeypatch, tmp_path):
    if not URL:
        pytest.skip("set GEOAPPS_TEST_DATABASE_URL to run database tests")
    reset_database(URL)
    from geoapps_db.session import get_engine

    monkeypatch.setenv("GEOAPPS_DATABASE_URL", URL)
    monkeypatch.setenv("GEOAPPS_CONFIG", str(tmp_path / "missing.toml"))
    get_engine.cache_clear()
    with TestClient(app) as c:
        yield c
    get_engine.cache_clear()


def test_full_loop(client):
    from geoapps_db import session_scope
    from geoapps_workers import runner
    from geoapps_workers.registry import sync_registry

    with session_scope() as s:
        sync_registry(s)

    # H1: invalid parameters never create a job
    r = client.post("/api/etl/seed_demo/jobs", json={"params": {"n": -3}})
    assert r.status_code == 422
    assert client.get("/api/stats").json()["queued_jobs"] == 0

    r = client.post("/api/etl/seed_demo/jobs", json={"params": {"n": 6, "seed": 2}})
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert runner.run_once() == job_id
    assert client.get(f"/api/jobs/{job_id}").json()["state"] == "done"

    queue = client.get("/api/queue").json()["features"]
    assert len(queue) == 6
    pri = [f["properties"]["priority"] for f in queue]
    assert pri == sorted(pri, reverse=True)

    # a watch around the whole demo basin, owned by "eman"
    area = {
        "type": "Polygon",
        "coordinates": [[[-104, 31.5], [-103, 31.5], [-103, 32.5], [-104, 32.5], [-104, 31.5]]],
    }
    hdr = {"X-Geoapps-User": "eman"}
    assert (
        client.post(
            "/api/watches", json={"name": "Permian demo", "geometry": area}, headers=hdr
        ).status_code
        == 201
    )

    top, second = queue[0]["id"], queue[1]["id"]
    r = client.post(f"/api/detections/{second}/verdict", json={"verdict": "reject"}, headers=hdr)
    assert r.json() == {"label_id": r.json()["label_id"], "status": "rejected", "alerts_raised": 0}
    r = client.post(f"/api/detections/{top}/verdict", json={"verdict": "confirm"}, headers=hdr)
    assert r.json()["status"] == "validated" and r.json()["alerts_raised"] == 1
    assert (
        client.post(f"/api/detections/{top}/verdict", json={"verdict": "confirm"}).status_code
        == 409
    )
    assert (
        client.post("/api/detections/999999/verdict", json={"verdict": "confirm"}).status_code
        == 404
    )

    alerts = client.get("/api/alerts", headers=hdr).json()
    assert len(alerts) == 1 and alerts[0]["detection"]["id"] == top
    r = client.patch(
        f"/api/alerts/{alerts[0]['id']}",
        json={"state": "dismissed", "reason": "not a plume"},
        headers=hdr,
    )
    assert r.json()["state"] == "dismissed"

    assert client.get("/api/stats").json() == {
        "predicted": 4,
        "validated": 1,
        "rejected": 1,
        "sources": 5,
        "alerts": 1,
        "queued_jobs": 0,
    }
    validated = client.get("/api/detections", params={"status": "validated"}).json()["features"]
    assert [f["id"] for f in validated] == [top]
    assert client.get("/api/sources").json()["features"]
    assert client.get("/api/kinds").json()[0]["name"] == "ch4_plume"

    # the dismissal came back as feedback, and the confirmed plume opened an event at its source
    fb = client.get("/api/feedback").json()
    assert [(f["about"], f["kind"], f["author"]) for f in fb] == [("alert", "not a plume", "eman")]
    src_id = validated[0]["properties"]["source_id"]
    detail = client.get(f"/api/sources/{src_id}").json()
    assert detail["events"][0]["n_detections"] == 1 and detail["who"] is None
    assert client.get("/api/sources/999999").status_code == 404
    assert client.get("/api/events", params={"status": "open"}).json()[0]["source_id"] == src_id


def test_attribution_through_the_api(client):
    from datetime import UTC, datetime

    from geoapps_db import repo, session_scope

    with session_scope() as s:
        src = repo.add_source(s, "S-1", -103.48, 31.87)
        repo.add_facility(s, name="Well Pad 17-B", lon=-103.481, lat=31.871)
        repo.add_detection(
            s,
            kind="ch4_plume",
            geometry={"type": "Point", "coordinates": [-103.48, 31.87]},
            marks={"p": 0.9, "q_kg_h": 900},
            observed_at=datetime(2026, 9, 14, tzinfo=UTC),
            source_id=src.id,
        )
        src_id = src.id
    props = client.post(f"/api/sources/{src_id}/propose").json()
    assert len(props) == 1 and props[0]["score"] > 0.5
    r = client.post(
        f"/api/attributions/{props[0]['id']}",
        json={"confirm": True, "valid_from": "2026-09-01T00:00:00Z"},
        headers={"X-Geoapps-User": "eman"},
    )
    assert (
        r.status_code == 200
        and r.json()["status"] == "confirmed"
        and r.json()["decided_by"] == "eman"
    )
    assert (
        client.post(f"/api/attributions/{props[0]['id']}", json={"confirm": True}).status_code
        == 409
    )
    who = client.get(f"/api/sources/{src_id}").json()["who"]
    assert who["facility"]["name"] == "Well Pad 17-B" and who["operator"] is None


def test_mars_import_through_the_api(client):
    from pathlib import Path

    from geoapps_db import session_scope
    from geoapps_workers import runner
    from geoapps_workers.registry import sync_registry

    with session_scope() as s:
        sync_registry(s)
    fixture = Path(__file__).parents[2] / "geoapps-workers" / "tests" / "data" / "mars_fixture.csv"
    r = client.post("/api/etl/import_mars_plumes/jobs", json={"params": {"path": str(fixture)}})
    assert r.status_code == 202
    runner.run_once()
    (ds,) = client.get("/api/datasets").json()
    assert ds["licence"] == "CC BY-NC-SA 4.0" and ds["n_detections"] == 4
    assert {s["name"] for s in client.get("/api/sensors").json()} == {
        "EMIT (NASA)",
        "Sentinel-2 (ESA)",
    }
    feats = client.get("/api/detections").json()["features"]
    assert {f["geometry"]["type"] for f in feats} == {"Point"}
    assert {f["properties"]["sensor"] for f in feats} == {"EMIT (NASA)", "Sentinel-2 (ESA)"}
