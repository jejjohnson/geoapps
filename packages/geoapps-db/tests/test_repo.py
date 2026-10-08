"""Database gates: E4 (nothing unvalidated downstream), G5 (watch rules fire exactly),
K1 (idempotent jobs), L2 (marks validated) and the SKIP LOCKED job claim."""

from datetime import UTC, datetime, timedelta

import pydantic
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from geoapps_db import repo
from geoapps_db.models import Alert, Detection, Label, Outbox


def square(lon: float, lat: float, half: float = 0.002) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lon - half, lat - half],
                [lon + half, lat - half],
                [lon + half, lat + half],
                [lon - half, lat + half],
                [lon - half, lat - half],
            ]
        ],
    }


NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
MARKS = {"q_kg_h": 850.0, "q_sigma_kg_h": 210.0, "p": 0.92}


def add(session, lon=-103.5, lat=31.9, marks=MARKS, hours_ago=6.0):
    return repo.add_detection(
        session,
        kind="ch4_plume",
        geometry=square(lon, lat),
        marks=marks,
        observed_at=NOW - timedelta(hours=hours_ago),
        scene_id="tanager-demo-001",
        now=NOW,
    )


def test_detection_born_predicted_with_priority(session):
    det = add(session)
    assert det.status == "predicted"
    assert det.priority > 0


def test_l2_bad_marks_refused(session):
    with pytest.raises(pydantic.ValidationError):
        add(session, marks={"q_kg_h": -5, "q_sigma_kg_h": 1, "p": 0.5})
    assert session.scalar(select(func.count(Detection.id))) == 0


def test_queue_orders_by_priority(session):
    small = add(session, marks={**MARKS, "q_kg_h": 50.0})
    large = add(session, lon=-103.4, marks={**MARKS, "q_kg_h": 3000.0})
    ids = [f["id"] for f in repo.queue(session)["features"]]
    assert ids == [large.id, small.id]


def test_e4_only_validated_reaches_alerts(session):
    """E4 + G5: predicted and rejected detections raise 0 alerts; validating one raises exactly 1 per watcher."""
    repo.create_watch(
        session, owner="eman", name="Permian pad", geometry=square(-103.5, 31.9, 0.05)
    )
    repo.create_watch(
        session, owner="colleague", name="Delaware basin", geometry=square(-103.5, 31.9, 0.5)
    )
    a, b = add(session), add(session)
    assert session.scalar(select(func.count(Alert.id))) == 0

    rejected = repo.record_verdict(session, b.id, verdict="reject", analyst="eman")
    assert rejected.status == "rejected" and rejected.alerts_raised == 0

    confirmed = repo.record_verdict(session, a.id, verdict="confirm", analyst="eman")
    assert confirmed.status == "validated"
    assert confirmed.alerts_raised == 2
    assert session.scalar(select(func.count(Alert.id))) == 2
    assert session.scalar(select(func.count(Outbox.id))) == 2
    assert session.scalar(select(func.count(Label.id))) == 2

    with pytest.raises(repo.NotReviewable):
        repo.record_verdict(session, a.id, verdict="confirm", analyst="eman")


def test_watch_flux_threshold_and_kind(session):
    repo.create_watch(
        session, owner="eman", name="big only", geometry=square(-103.5, 31.9, 0.05), min_q_kg_h=1000
    )
    det = add(session)  # 850 kg/h, below the threshold
    assert (
        repo.record_verdict(session, det.id, verdict="confirm", analyst="eman").alerts_raised == 0
    )


def test_redraw_needs_geometry(session):
    det = add(session)
    with pytest.raises(ValueError):
        repo.record_verdict(session, det.id, verdict="redraw", analyst="eman")
    res = repo.record_verdict(
        session, det.id, verdict="redraw", analyst="eman", geometry=square(-103.5, 31.9, 0.001)
    )
    assert res.status == "validated"


def test_would_notify_raises_priority(session):
    plain = add(session)
    repo.create_watch(session, owner="eman", name="pad", geometry=square(-103.2, 31.9, 0.05))
    watched = add(session, lon=-103.2)
    assert watched.priority == pytest.approx(2 * plain.priority)  # (1 + β n_d) with β = 1


def test_k1_idempotent_jobs(session):
    repo.upsert_etl(
        session, name="seed_demo", version="0.0.1", description="", params_schema={}, writes=[]
    )
    j1 = repo.enqueue_job(session, etl="seed_demo", params={}, key="seed_demo:window-1")
    j2 = repo.enqueue_job(session, etl="seed_demo", params={}, key="seed_demo:window-1")
    assert j1.id == j2.id


def test_claim_job_skip_locked(db_url):
    engine = create_engine(db_url)
    with Session(engine) as s:
        repo.upsert_etl(
            s, name="seed_demo", version="0.0.1", description="", params_schema={}, writes=[]
        )
        repo.enqueue_job(s, etl="seed_demo", params={"n": 1})
        repo.enqueue_job(s, etl="seed_demo", params={"n": 2})
        s.commit()
    with Session(engine) as w1, Session(engine) as w2:
        first = repo.claim_job(w1)  # holds its row lock until commit
        second = repo.claim_job(w2)  # must skip the locked row
        assert first is not None and second is not None
        assert first.id != second.id
        w1.commit()
        w2.commit()
    engine.dispose()


def test_a1_migrations_round_trip(db_url):
    """Gate A1: head → base → head on a real database, and the models match head."""
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from geoapps_db.autogen import include_name, include_object
    from geoapps_db.cli import alembic_config
    from geoapps_db.models import Base

    cfg = alembic_config(db_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn,
            opts={
                "include_schemas": True,
                "include_name": include_name,
                "include_object": include_object,
            },
        )
        assert compare_metadata(ctx, Base.metadata) == []
    engine.dispose()
