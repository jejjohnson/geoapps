"""Query and write functions: the only write path into the database.

Each function takes an open ``Session`` and leaves committing to the caller
(``session_scope``), so one API request or one job step is one transaction (G4).
Geometries cross this boundary as GeoJSON dicts in EPSG:4326.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import functions as gf
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from geoapps_core import Status, Verdict, get_kind, priority, status_after
from geoapps_db.models import Alert, Detection, Etl, Job, Label, Outbox, Run, Source, Watch

# Queue settings (E5). Hours; tuned per instance later through configuration.
TAU_HOURS = 72.0
LAMBDA_HOURS = 48.0
BETA = 1.0
Q_REF_KG_H = 100.0


def _geom(geojson: dict[str, Any]):
    return gf.ST_SetSRID(gf.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)


def _as_geojson(column):
    # ST_AsGeoJSON returns text; cast to json so the driver hands back a dict.
    return func.ST_AsGeoJSON(column, 6).cast(JSON)


# ── runs ────────────────────────────────────────────────────────────────────
def start_run(session: Session, etl: str, versions: dict[str, Any], stream: str = "nrt") -> Run:
    run = Run(etl=etl, versions=versions, stream=stream)
    session.add(run)
    session.flush()
    return run


# ── sources ─────────────────────────────────────────────────────────────────
def add_source(
    session: Session, name: str, lon: float, lat: float, kind: str = "unknown", **attrs
) -> Source:
    src = Source(name=name, kind=kind, geom=f"SRID=4326;POINT({lon} {lat})", attrs=attrs)
    session.add(src)
    session.flush()
    return src


def sources_geojson(session: Session, limit: int = 5000) -> dict[str, Any]:
    rows = session.execute(
        select(Source.id, Source.name, Source.kind, _as_geojson(Source.geom)).limit(limit)
    ).all()
    return _collection(
        {
            "type": "Feature",
            "id": r.id,
            "geometry": r[3],
            "properties": {"name": r.name, "kind": r.kind},
        }
        for r in rows
    )


# ── detections (app 1) ──────────────────────────────────────────────────────
def _would_notify(session: Session, kind: str, geom_expr, q: float | None) -> bool:
    """n_d: would validating this detection fire at least one watch rule?"""
    stmt = select(func.count(Watch.id)).where(
        gf.ST_Intersects(Watch.geom, geom_expr),
        or_(Watch.kind.is_(None), Watch.kind == kind),
        or_(Watch.min_q_kg_h.is_(None), Watch.min_q_kg_h <= (q or 0.0)),
    )
    return session.scalar(stmt) > 0


def add_detection(
    session: Session,
    *,
    kind: str,
    geometry: dict[str, Any],
    marks: dict[str, Any],
    observed_at: datetime,
    scene_id: str | None = None,
    origin: dict[str, Any] | None = None,
    run_id: int | None = None,
    now: datetime | None = None,
) -> Detection:
    """Store a machine detection as ``predicted`` with its queue priority π_d (E4, E5).

    Marks are validated against the kind's schema first; a bad row is refused (L2).
    """
    event_kind = get_kind(kind)
    marks = event_kind.validate_marks(marks)
    geom_expr = _geom(geometry)
    now = now or datetime.now(UTC)
    age_h = max((now - observed_at).total_seconds() / 3600.0, 0.0)
    q = marks.get("q_kg_h")
    n_d = _would_notify(session, kind, geom_expr, q)
    # π_d = p_d · v_d · g(Q̂_d) · (1 + β n_d) · u(a_d)
    pi = float(
        priority(
            [marks.get("p", 1.0)],
            [marks.get("viability", 1.0)],
            [q or 0.0],
            [int(n_d)],
            [age_h],
            tau=TAU_HOURS,
            lam=LAMBDA_HOURS,
            beta=BETA,
            q_ref=Q_REF_KG_H,
        )[0]
    )
    det = Detection(
        kind=kind,
        status=Status.PREDICTED.value,
        scene_id=scene_id,
        observed_at=observed_at,
        geom=geom_expr,
        origin=_geom(origin) if origin else None,
        marks=marks,
        priority=pi,
        run_id=run_id,
    )
    session.add(det)
    session.flush()
    return det


def _detection_feature(row) -> dict[str, Any]:
    d = row[0]
    return {
        "type": "Feature",
        "id": d.id,
        "geometry": row[1],
        "properties": {
            "kind": d.kind,
            "status": d.status,
            "scene_id": d.scene_id,
            "observed_at": d.observed_at.isoformat(),
            "priority": round(d.priority, 6),
            **d.marks,
        },
    }


def detections_geojson(
    session: Session,
    *,
    status: str | None = None,
    kind: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 5000,
) -> dict[str, Any]:
    stmt = select(Detection, _as_geojson(Detection.geom)).order_by(Detection.observed_at.desc())
    if status:
        stmt = stmt.where(Detection.status == status)
    if kind:
        stmt = stmt.where(Detection.kind == kind)
    if bbox:
        stmt = stmt.where(gf.ST_Intersects(Detection.geom, gf.ST_MakeEnvelope(*bbox, 4326)))
    return _collection(_detection_feature(r) for r in session.execute(stmt.limit(limit)).all())


def queue(session: Session, *, kind: str | None = None, limit: int = 50) -> dict[str, Any]:
    """The validation queue: predicted detections, highest priority first."""
    stmt = (
        select(Detection, _as_geojson(Detection.geom))
        .where(Detection.status == Status.PREDICTED.value)
        .order_by(Detection.priority.desc(), Detection.id)
    )
    if kind:
        stmt = stmt.where(Detection.kind == kind)
    return _collection(_detection_feature(r) for r in session.execute(stmt.limit(limit)).all())


@dataclass
class VerdictResult:
    label_id: int
    status: str
    alerts_raised: int


class NotReviewable(ValueError):
    pass


def record_verdict(
    session: Session,
    detection_id: int,
    *,
    verdict: Verdict | str,
    analyst: str,
    geometry: dict[str, Any] | None = None,
    note: str | None = None,
) -> VerdictResult:
    """A person's verdict: label, new status and any watch alerts, in one transaction (E4, G3, G4)."""
    verdict = Verdict(verdict)
    det = session.scalar(select(Detection).where(Detection.id == detection_id).with_for_update())
    if det is None:
        raise LookupError(f"detection {detection_id} not found")
    if det.status != Status.PREDICTED.value:
        raise NotReviewable(f"detection {detection_id} is already {det.status}")
    if verdict is Verdict.REDRAW and geometry is None:
        raise ValueError("a redraw needs the corrected geometry")

    label_geom = _geom(geometry) if geometry else det.geom
    label = Label(
        detection_id=det.id,
        scene_id=det.scene_id,
        geom=label_geom,
        verdict=verdict.value,
        analyst=analyst,
        note=note,
    )
    session.add(label)
    new_status = status_after(verdict)
    det.status = new_status.value
    session.flush()

    raised = 0
    if new_status is Status.VALIDATED:
        raised = _raise_alerts(session, det)
    return VerdictResult(label_id=label.id, status=new_status.value, alerts_raised=raised)


def _raise_alerts(session: Session, det: Detection) -> int:
    """Evaluate watch rules on a validated detection; one alert per (watch, detection) (G5)."""
    q = (det.marks or {}).get("q_kg_h", 0.0)
    watch_ids = session.scalars(
        select(Watch.id).where(
            gf.ST_Intersects(
                Watch.geom, select(Detection.geom).where(Detection.id == det.id).scalar_subquery()
            ),
            or_(Watch.kind.is_(None), Watch.kind == det.kind),
            or_(Watch.min_q_kg_h.is_(None), Watch.min_q_kg_h <= q),
        )
    ).all()
    raised = 0
    for wid in watch_ids:
        alert_id = session.scalar(
            pg_insert(Alert)
            .values(watch_id=wid, detection_id=det.id)
            .on_conflict_do_nothing(index_elements=["watch_id", "detection_id"])
            .returning(Alert.id)
        )
        if alert_id is not None:
            session.add(
                Outbox(
                    alert_id=alert_id,
                    channel="in_app",
                    payload={"detection_id": det.id, "watch_id": wid},
                )
            )
            raised += 1
    session.flush()
    return raised


# ── watches and alerts (app 3) ──────────────────────────────────────────────
def create_watch(
    session: Session,
    *,
    owner: str,
    name: str,
    geometry: dict[str, Any],
    kind: str | None = None,
    min_q_kg_h: float | None = None,
) -> Watch:
    if kind is not None:
        get_kind(kind)
    watch = Watch(owner=owner, name=name, geom=_geom(geometry), kind=kind, min_q_kg_h=min_q_kg_h)
    session.add(watch)
    session.flush()
    return watch


def watches_geojson(session: Session, owner: str | None = None) -> dict[str, Any]:
    stmt = select(Watch, _as_geojson(Watch.geom))
    if owner:
        stmt = stmt.where(Watch.owner == owner)
    rows = session.execute(stmt).all()
    return _collection(
        {
            "type": "Feature",
            "id": w.id,
            "geometry": g,
            "properties": {
                "owner": w.owner,
                "name": w.name,
                "kind": w.kind,
                "min_q_kg_h": w.min_q_kg_h,
            },
        }
        for w, g in rows
    )


def list_alerts(
    session: Session, owner: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    stmt = (
        select(
            Alert, Watch.name, Watch.owner, Detection.kind, Detection.marks, Detection.observed_at
        )
        .join(Watch, Watch.id == Alert.watch_id)
        .join(Detection, Detection.id == Alert.detection_id)
        .order_by(Alert.created_at.desc())
        .limit(limit)
    )
    if owner:
        stmt = stmt.where(Watch.owner == owner)
    return [
        {
            "id": a.id,
            "state": a.state,
            "reason": a.reason,
            "created_at": a.created_at.isoformat(),
            "watch": {"id": a.watch_id, "name": wname, "owner": wowner},
            "detection": {
                "id": a.detection_id,
                "kind": kind,
                "observed_at": obs.isoformat(),
                **(marks or {}),
            },
        }
        for a, wname, wowner, kind, marks, obs in session.execute(stmt).all()
    ]


def set_alert_state(
    session: Session, alert_id: int, state: str, reason: str | None = None
) -> Alert:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise LookupError(f"alert {alert_id} not found")
    alert.state = state
    alert.reason = reason
    session.flush()
    return alert


# ── registry and jobs (workstreams H and K) ─────────────────────────────────
def upsert_etl(
    session: Session,
    *,
    name: str,
    version: str,
    description: str,
    params_schema: dict[str, Any],
    writes: list[str],
) -> None:
    stmt = pg_insert(Etl).values(
        name=name,
        version=version,
        description=description,
        params_schema=params_schema,
        writes=writes,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Etl.name],
        set_={
            "version": stmt.excluded.version,
            "description": stmt.excluded.description,
            "params_schema": stmt.excluded.params_schema,
            "writes": stmt.excluded.writes,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)


def list_etls(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "name": e.name,
            "version": e.version,
            "description": e.description,
            "params_schema": e.params_schema,
            "writes": e.writes,
        }
        for e in session.scalars(select(Etl).order_by(Etl.name))
    ]


def get_etl(session: Session, name: str) -> Etl | None:
    return session.get(Etl, name)


def enqueue_job(
    session: Session,
    *,
    etl: str,
    params: dict[str, Any],
    submitted_by: str = "system",
    key: str | None = None,
) -> Job:
    """Queue a job; a repeated idempotency key returns the existing job instead of a duplicate (K1)."""
    if key is not None:
        existing = session.scalar(select(Job).where(Job.key == key))
        if existing is not None:
            return existing
    job = Job(etl=etl, params=params, submitted_by=submitted_by, key=key)
    session.add(job)
    session.flush()
    return job


def claim_job(session: Session) -> Job | None:
    """Take the oldest queued job; concurrent workers never claim the same one."""
    job = session.scalar(
        select(Job)
        .where(Job.state == "queued")
        .order_by(Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is not None:
        job.state = "running"
        job.started_at = datetime.now(UTC)
        session.flush()
    return job


def finish_job(
    session: Session,
    job_id: int,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    run_id: int | None = None,
) -> None:
    session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            state="failed" if error else "done",
            result=result,
            error=error,
            run_id=run_id,
            finished_at=datetime.now(UTC),
        )
    )


def get_job(session: Session, job_id: int) -> dict[str, Any] | None:
    j = session.get(Job, job_id)
    if j is None:
        return None
    return {
        "id": j.id,
        "etl": j.etl,
        "params": j.params,
        "state": j.state,
        "result": j.result,
        "error": j.error,
        "run_id": j.run_id,
        "submitted_by": j.submitted_by,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


def counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(Detection.status, func.count()).group_by(Detection.status)).all()
    out = {s: 0 for s in ("predicted", "validated", "rejected")}
    out.update({s: n for s, n in rows})
    out["alerts"] = session.scalar(select(func.count(Alert.id))) or 0
    out["queued_jobs"] = (
        session.scalar(select(func.count(Job.id)).where(and_(Job.state == "queued"))) or 0
    )
    return out


def _collection(features) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}
