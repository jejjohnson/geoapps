"""App 1: detections, the validation queue, verdicts and frozen label sets."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import functions as gf
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from geoapps_core import Status, Verdict, get_kind, priority, status_after
from geoapps_db.models import (
    Alert,
    Detection,
    Label,
    LabelSet,
    LabelSetMember,
    Outbox,
    Sensor,
    Watch,
)
from geoapps_db.repo._util import as_geojson, collection, geom, iso

# Queue settings (E5). Hours; tuned per instance later through configuration.
TAU_HOURS = 72.0
LAMBDA_HOURS = 48.0
BETA = 1.0
Q_REF_KG_H = 100.0


def _would_notify(session: Session, kind: str, geom_expr, q: float | None) -> bool:
    """n_d: would validating this detection fire at least one watch rule?"""
    stmt = select(func.count(Watch.id)).where(
        gf.ST_Intersects(Watch.geom, geom_expr),
        or_(Watch.kind.is_(None), Watch.kind == kind),
        or_(Watch.min_q_kg_h.is_(None), Watch.min_q_kg_h <= (q or 0.0)),
    )
    return session.scalar(stmt) > 0


def queue_priority(marks: dict[str, Any], age_h: float, would_notify: bool) -> float:
    # π_d = p_d · v_d · g(Q̂_d) · (1 + β n_d) · u(a_d); an unquantified plume ranks as Q̂ = Q_ref
    q = marks.get("q_kg_h")
    return float(
        priority(
            [marks.get("p", 1.0)],
            [marks.get("viability", 1.0)],
            [Q_REF_KG_H if q is None else q],
            [int(would_notify)],
            [age_h],
            tau=TAU_HOURS,
            lam=LAMBDA_HOURS,
            beta=BETA,
            q_ref=Q_REF_KG_H,
        )[0]
    )


def add_detection(
    session: Session,
    *,
    kind: str,
    geometry: dict[str, Any],
    marks: dict[str, Any],
    observed_at: datetime,
    scene_id: str | None = None,
    origin: dict[str, Any] | None = None,
    sensor_id: int | None = None,
    source_id: int | None = None,
    dataset_id: int | None = None,
    attrs: dict[str, Any] | None = None,
    supersedes_id: int | None = None,
    run_id: int | None = None,
    now: datetime | None = None,
) -> Detection:
    """Store a detection as ``predicted`` with its queue priority π_d (E4, E5).

    Marks are validated against the kind's schema first; a bad row is refused (L2).
    The geometry is the kind's outline, or a point when only the location is known.
    """
    event_kind = get_kind(kind)
    if not event_kind.accepts_geometry(geometry.get("type", "")):
        raise ValueError(
            f"{kind} detections are {event_kind.geometry} or Point, not {geometry.get('type')}"
        )
    marks = event_kind.validate_marks(marks)
    geom_expr = geom(geometry)
    if geometry.get("type") in ("Polygon", "MultiPolygon"):
        # provider outlines can self-intersect; keep only the repaired polygonal part
        geom_expr = gf.ST_Multi(gf.ST_CollectionExtract(gf.ST_MakeValid(geom_expr), 3))
    now = now or datetime.now(UTC)
    age_h = max((now - observed_at).total_seconds() / 3600.0, 0.0)
    n_d = _would_notify(session, kind, geom_expr, marks.get("q_kg_h"))
    det = Detection(
        kind=kind,
        status=Status.PREDICTED.value,
        scene_id=scene_id,
        observed_at=observed_at,
        geom=geom_expr,
        origin=geom(origin) if origin else None,
        marks=marks,
        attrs=attrs or {},
        priority=queue_priority(marks, age_h, n_d),
        sensor_id=sensor_id,
        source_id=source_id,
        dataset_id=dataset_id,
        supersedes_id=supersedes_id,
        run_id=run_id,
    )
    session.add(det)
    session.flush()
    return det


def _detection_feature(d: Detection, g: dict, sensor: str | None) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": d.id,
        "geometry": g,
        "properties": {
            "kind": d.kind,
            "status": d.status,
            "scene_id": d.scene_id,
            "observed_at": iso(d.observed_at),
            "priority": round(d.priority, 6),
            "sensor": sensor,
            "source_id": d.source_id,
            "event_id": d.event_id,
            "dataset_id": d.dataset_id,
            **d.marks,
        },
    }


def _select_features():
    return select(Detection, as_geojson(Detection.geom), Sensor.name).outerjoin(
        Sensor, Sensor.id == Detection.sensor_id
    )


def detections_geojson(
    session: Session,
    *,
    status: str | None = None,
    kind: str | None = None,
    source_id: int | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 20000,
) -> dict[str, Any]:
    stmt = _select_features().order_by(Detection.observed_at.desc())
    if status:
        stmt = stmt.where(Detection.status == status)
    if kind:
        stmt = stmt.where(Detection.kind == kind)
    if source_id is not None:
        stmt = stmt.where(Detection.source_id == source_id)
    if bbox:
        stmt = stmt.where(gf.ST_Intersects(Detection.geom, gf.ST_MakeEnvelope(*bbox, 4326)))
    return collection(_detection_feature(*r) for r in session.execute(stmt.limit(limit)).all())


def queue(session: Session, *, kind: str | None = None, limit: int = 50) -> dict[str, Any]:
    """The validation queue: predicted detections, highest priority first, newest on ties."""
    stmt = (
        _select_features()
        .where(Detection.status == Status.PREDICTED.value)
        .order_by(Detection.priority.desc(), Detection.observed_at.desc(), Detection.id)
    )
    if kind:
        stmt = stmt.where(Detection.kind == kind)
    return collection(_detection_feature(*r) for r in session.execute(stmt.limit(limit)).all())


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
    rechain: bool = True,
) -> VerdictResult:
    """A verdict: label, new status, the source's events and any watch alerts, in one transaction (E4, G3, G4).

    ``rechain=False`` lets a bulk import rebuild each source's events once at the end.
    """
    verdict = Verdict(verdict)
    det = session.scalar(select(Detection).where(Detection.id == detection_id).with_for_update())
    if det is None:
        raise LookupError(f"detection {detection_id} not found")
    if det.status != Status.PREDICTED.value:
        raise NotReviewable(f"detection {detection_id} is already {det.status}")
    if verdict is Verdict.REDRAW and geometry is None:
        raise ValueError("a redraw needs the corrected geometry")

    label = Label(
        detection_id=det.id,
        scene_id=det.scene_id,
        geom=geom(geometry) if geometry else det.geom,
        verdict=verdict.value,
        analyst=analyst,
        note=note,
    )
    session.add(label)
    new_status = status_after(verdict)
    det.status = new_status.value
    session.flush()

    if rechain and det.source_id is not None:
        from geoapps_db.repo.monitor import rechain_events
        from geoapps_db.repo.ref import refresh_source_seen

        rechain_events(session, det.source_id)
        refresh_source_seen(session, [det.source_id])

    raised = _raise_alerts(session, det) if new_status is Status.VALIDATED else 0
    return VerdictResult(label_id=label.id, status=new_status.value, alerts_raised=raised)


def _raise_alerts(session: Session, det: Detection) -> int:
    """Evaluate watch rules on a validated detection; one alert per (watch, detection) (G5)."""
    q = (det.marks or {}).get("q_kg_h")
    watch_ids = session.scalars(
        select(Watch.id).where(
            gf.ST_Intersects(
                Watch.geom, select(Detection.geom).where(Detection.id == det.id).scalar_subquery()
            ),
            or_(Watch.kind.is_(None), Watch.kind == det.kind),
            or_(Watch.min_q_kg_h.is_(None), Watch.min_q_kg_h <= (q or 0.0)),
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


def freeze_label_set(
    session: Session,
    name: str,
    *,
    analyst_prefix: str | None = None,
    before: datetime | None = None,
) -> LabelSet:
    """𝓛ₖ = freeze(labels where t ≤ tₖ), optionally only one analyst group (e.g. "provider:")."""
    before = before or datetime.now(UTC)
    stmt = select(Label.id).where(Label.created_at <= before)
    if analyst_prefix:
        stmt = stmt.where(Label.analyst.startswith(analyst_prefix))
    ids = session.scalars(stmt).all()
    ls = LabelSet(
        name=name,
        frozen_at=before,
        filter={"analyst_prefix": analyst_prefix, "before": before.isoformat()},
        n_labels=len(ids),
    )
    session.add(ls)
    session.flush()
    if ids:
        session.execute(
            pg_insert(LabelSetMember), [{"label_set_id": ls.id, "label_id": i} for i in ids]
        )
    return ls


def refresh_imported_detection(
    session: Session,
    detection_id: int,
    *,
    marks: dict[str, Any],
    attrs: dict[str, Any],
    now: datetime | None = None,
) -> bool:
    """A provider revised a record: update a still-predicted detection; returns False once reviewed.

    A reviewed detection is never changed underneath its label; the caller reports it instead.
    """
    det = session.scalar(select(Detection).where(Detection.id == detection_id).with_for_update())
    if det is None:
        raise LookupError(f"detection {detection_id} not found")
    if det.status != Status.PREDICTED.value:
        return False
    det.marks = get_kind(det.kind).validate_marks(marks)
    det.attrs = attrs
    age_h = max(((now or datetime.now(UTC)) - det.observed_at).total_seconds() / 3600.0, 0.0)
    det.priority = queue_priority(
        det.marks, age_h, _would_notify(session, det.kind, det.geom, det.marks.get("q_kg_h"))
    )
    session.flush()
    return True


def detection_attr(session: Session, ids: list[int], key: str) -> dict[int, str | None]:
    """One attribute of many detections, e.g. the provider's ``last_update`` for re-imports."""
    if not ids:
        return {}
    return dict(
        session.execute(
            select(Detection.id, Detection.attrs[key].astext).where(Detection.id.in_(ids))
        ).all()
    )
