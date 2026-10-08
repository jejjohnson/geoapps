"""API tests. The full loop (seed → verdict → alert) needs GEOAPPS_TEST_DATABASE_URL."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from geoapps_api.main import app

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
    ):
        assert p in paths


@pytest.fixture()
def client(monkeypatch, tmp_path):
    if not URL:
        pytest.skip("set GEOAPPS_TEST_DATABASE_URL to run database tests")
    engine = create_engine(URL)
    with engine.begin() as conn:
        for schema in ("notify", "review", "ref", "core"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    engine.dispose()
    from alembic import command

    from geoapps_db.cli import alembic_config
    from geoapps_db.session import get_engine

    command.upgrade(alembic_config(URL), "head")
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
        "alerts": 1,
        "queued_jobs": 0,
    }
    validated = client.get("/api/detections", params={"status": "validated"}).json()["features"]
    assert [f["id"] for f in validated] == [top]
    assert client.get("/api/sources").json()["features"]
    assert client.get("/api/kinds").json()[0]["name"] == "ch4_plume"
