"""Locations, observations, events and persistence (data model §6–7)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from geoapps_core import bounds, chain_by_gap, inverse_variance_mean, persistence_posterior
from geoapps_db.models import Detection, Event, Location, LocationStatus, Observation
from geoapps_db.repo._util import geom

EVENT_GAP_DAYS = 30.0


def _days(t: datetime) -> float:
    return t.timestamp() / 86400.0


def _from_days(d: float | None) -> datetime | None:
    return None if d is None else datetime.fromtimestamp(d * 86400.0, tz=UTC)


# ── locations ───────────────────────────────────────────────────────────────
def add_location(
    session: Session,
    *,
    name: str,
    area: dict[str, Any],
    by: str,
    source_id: int | None = None,
    facility_id: int | None = None,
    sensors: list[str] | None = None,
    revisit_days: float | None = None,
    status: str = "candidate",
) -> Location:
    loc = Location(
        name=name,
        area=geom(area),
        status=status,
        source_id=source_id,
        facility_id=facility_id,
        sensors=sensors or [],
        revisit_days=revisit_days,
    )
    session.add(loc)
    session.flush()
    session.add(LocationStatus(location_id=loc.id, status=status, by=by, reason="created"))
    session.flush()
    return loc


def set_location_status(
    session: Session, location_id: int, status: str, *, by: str, reason: str | None = None
) -> None:
    """Every lifecycle transition is a row, so "when did we stop watching?" is a query."""
    loc = session.get(Location, location_id)
    if loc is None:
        raise LookupError(f"location {location_id} not found")
    loc.status = status
    session.add(LocationStatus(location_id=location_id, status=status, by=by, reason=reason))
    session.flush()


def add_observation(
    session: Session,
    *,
    location_id: int,
    observed_at: datetime,
    valid_fraction: float,
    detection_limit: float | None = None,
    pixel_size_m: float | None = None,
    sensor_id: int | None = None,
    scene_id: str | None = None,
    detection_id: int | None = None,
    run_id: int | None = None,
) -> Observation:
    ob = Observation(
        location_id=location_id,
        observed_at=observed_at,
        valid_fraction=valid_fraction,
        detection_limit=detection_limit,
        pixel_size_m=pixel_size_m,
        sensor_id=sensor_id,
        scene_id=scene_id,
        detection_id=detection_id,
        run_id=run_id,
    )
    session.add(ob)
    session.flush()
    return ob


def persistence(
    session: Session,
    location_id: int,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    min_valid_fraction: float = 0.5,
    threshold: float | None = None,
) -> dict[str, Any]:
    """P(q) | data ~ Beta(1 + N_det, 1 + N_valid − N_det), over the looks able to see size q.

    Without a threshold, every valid look counts, which mixes sensors of very different
    sensitivity; with one, a look counts only if its detection limit L ≤ q (in the kind's
    limit mark), so a site watched by a coarse sensor does not look less persistent.
    """
    stmt = select(Observation.detection_id, Observation.detection_limit).where(
        Observation.location_id == location_id, Observation.valid_fraction >= min_valid_fraction
    )
    if start:
        stmt = stmt.where(Observation.observed_at >= start)
    if end:
        stmt = stmt.where(Observation.observed_at < end)
    looks = session.execute(stmt).all()
    if threshold is not None:
        # a look whose detection limit is above the threshold says nothing about snapshots that size
        looks = [
            lk for lk in looks if lk.detection_limit is not None and lk.detection_limit <= threshold
        ]
    n_valid = len(looks)
    n_det = sum(1 for lk in looks if lk.detection_id is not None)
    post = persistence_posterior(n_det, n_valid)
    lo, hi = post.ppf([0.05, 0.95])
    return {
        "location_id": location_id,
        "n_valid": n_valid,
        "n_det": n_det,
        "mean": float(post.mean()),
        "p05": float(lo),
        "p95": float(hi),
        "threshold": threshold,
    }


# ── events ──────────────────────────────────────────────────────────────────
def rechain_events(
    session: Session,
    source_id: int,
    *,
    gap_days: float = EVENT_GAP_DAYS,
    now: datetime | None = None,
) -> list[int]:
    """Rebuild a source's events from its validated detections and clear looks.

    Events are derived rows: rebuilding them from detections and observations is
    always safe, and keeps one rule for live data, imports and reanalysis.
    """
    now = now or datetime.now(UTC)
    dets = session.execute(
        select(Detection.id, Detection.observed_at, Detection.marks, Detection.kind)
        .where(Detection.source_id == source_id, Detection.status == "validated")
        .order_by(Detection.observed_at, Detection.id)
    ).all()
    clear = session.scalars(
        select(Observation.observed_at)
        .join(Location, Location.id == Observation.location_id)
        .where(
            Location.source_id == source_id,
            Observation.detection_id.is_(None),
            Observation.valid_fraction >= 0.5,
        )
    ).all()
    session.execute(delete(Event).where(Event.source_id == source_id))
    session.flush()
    if not dets:
        return []

    t = np.array([_days(d.observed_at) for d in dets])  # (K,) days
    c = np.array([_days(x) for x in clear]) if clear else None  # (C,) days
    idx = chain_by_gap(t, gap_days, c)  # (K,) event index
    ids = []
    for k in range(int(idx.max()) + 1):
        members = [d for d, i in zip(dets, idx, strict=True) if i == k]
        t_b, t_c = members[0].observed_at, members[-1].observed_at
        t_a, t_d = bounds(_days(t_b), _days(t_c), c)
        q = [m.marks.get("q_kg_h", np.nan) for m in members]
        s = [m.marks.get("q_sigma_kg_h", np.nan) for m in members]
        rate = inverse_variance_mean(np.array(q, dtype=float), np.array(s, dtype=float))
        # closed once a clear look follows it, or once the gap has passed with nothing new
        closed = t_d is not None or (now - t_c) > timedelta(days=gap_days)
        ev = Event(
            kind=members[0].kind,
            source_id=source_id,
            t_a=_from_days(t_a),
            t_b=t_b,
            t_c=t_c,
            t_d=_from_days(t_d),
            status="closed" if closed else "open",
            n_detections=len(members),
            q_mean_kg_h=None if rate is None else round(rate.mean, 1),
            q_sigma_kg_h=None if rate is None or rate.sigma is None else round(rate.sigma, 1),
        )
        session.add(ev)
        session.flush()
        session.execute(
            Detection.__table__.update()
            .where(Detection.id.in_([m.id for m in members]))
            .values(event_id=ev.id)
        )
        ids.append(ev.id)
    return ids


def events_for_source(session: Session, source_id: int) -> list[dict[str, Any]]:
    from geoapps_db.repo.ref import event_dict

    return [
        event_dict(e)
        for e in session.scalars(
            select(Event).where(Event.source_id == source_id).order_by(Event.t_b)
        )
    ]


def list_events(
    session: Session, *, status: str | None = None, limit: int = 500
) -> list[dict[str, Any]]:
    from geoapps_db.repo.ref import event_dict

    stmt = select(Event).order_by(Event.t_c.desc()).limit(limit)
    if status:
        stmt = stmt.where(Event.status == status)
    return [
        {**event_dict(e), "source_id": e.source_id, "kind": e.kind} for e in session.scalars(stmt)
    ]
