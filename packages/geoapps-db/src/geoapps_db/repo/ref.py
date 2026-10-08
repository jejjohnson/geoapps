"""Sensors, sources and facilities: the slowly changing things in the world."""

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from geoapps_db.models import Detection, Event, Facility, Sensor, Source
from geoapps_db.repo._util import as_geojson, collection, geom, iso, point
from geoapps_db.repo.core import add_xref, xref_lookup


# ── sensors ─────────────────────────────────────────────────────────────────
def upsert_sensor(session: Session, name: str, **fields: Any) -> int:
    """The sensor's id, creating it on first sight; fields only fill what is still empty."""
    stmt = pg_insert(Sensor).values(name=name, **fields)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Sensor.name],
        set_={k: func.coalesce(getattr(Sensor, k), stmt.excluded[k]) for k in fields}
        or {"name": stmt.excluded.name},
    ).returning(Sensor.id)
    return session.scalar(stmt)


def list_sensors(session: Session) -> list[dict[str, Any]]:
    n = (
        select(Detection.sensor_id, func.count().label("n"))
        .group_by(Detection.sensor_id)
        .subquery()
    )
    rows = session.execute(
        select(Sensor, func.coalesce(n.c.n, 0))
        .outerjoin(n, n.c.sensor_id == Sensor.id)
        .order_by(Sensor.name)
    ).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "platform": s.platform,
            "agency": s.agency,
            "sensor_type": s.sensor_type,
            "gsd_m": s.gsd_m,
            "revisit_days": s.revisit_days,
            "overpass_local_time": s.overpass_local_time,
            "n_bands": s.n_bands,
            "detection_limits": s.detection_limits,
            "n_detections": int(k),
        }
        for s, k in rows
    ]


# ── sources ─────────────────────────────────────────────────────────────────
def add_source(
    session: Session,
    name: str,
    lon: float,
    lat: float,
    *,
    source_type: str = "unknown",
    event_kind: str = "ch4_plume",
    sector: str | None = None,
    country: str | None = None,
    status: str = "active",
    **attrs: Any,
) -> Source:
    src = Source(
        name=name,
        source_type=source_type,
        event_kind=event_kind,
        sector=sector,
        country=country,
        status=status,
        geom=f"SRID=4326;POINT({lon} {lat})",
        attrs=attrs,
    )
    session.add(src)
    session.flush()
    return src


def source_for_record(
    session: Session, *, provider: str, record_id: str, lon: float, lat: float, **fields: Any
) -> tuple[int, bool]:
    """Our source for a provider's source id, created and cross-referenced on first sight."""
    sid = xref_lookup(session, provider, "source", record_id)
    if sid is not None:
        return sid, False
    src = add_source(session, fields.pop("name", record_id), lon, lat, **fields)
    add_xref(session, provider=provider, entity="source", record_id=record_id, entity_id=src.id)
    return src.id, True


def refresh_source_seen(session: Session, source_ids: list[int] | None = None) -> None:
    """first_seen / last_seen from the source's detections that were not rejected."""
    agg = (
        select(
            Detection.source_id,
            func.min(Detection.observed_at).label("first"),
            func.max(Detection.observed_at).label("last"),
        )
        .where(Detection.status != "rejected", Detection.source_id.is_not(None))
        .group_by(Detection.source_id)
    )
    if source_ids is not None:
        agg = agg.where(Detection.source_id.in_(source_ids))
    agg = agg.subquery()
    session.execute(
        update(Source)
        .where(Source.id == agg.c.source_id)
        .values(first_seen=agg.c.first, last_seen=agg.c.last)
    )


def _source_stats():
    return (
        select(
            Detection.source_id,
            func.count().label("n"),
            func.count().filter(Detection.status == "validated").label("n_validated"),
            func.count().filter(Detection.status == "predicted").label("n_predicted"),
            func.max(
                case((Detection.status != "rejected", (Detection.marks["q_kg_h"].as_float())))
            ).label("q_max"),
        )
        .where(Detection.source_id.is_not(None))
        .group_by(Detection.source_id)
        .subquery()
    )


def sources_geojson(session: Session, limit: int = 20000) -> dict[str, Any]:
    st = _source_stats()
    rows = session.execute(
        select(
            Source, as_geojson(Source.geom), st.c.n, st.c.n_validated, st.c.n_predicted, st.c.q_max
        )
        .outerjoin(st, st.c.source_id == Source.id)
        .order_by(Source.id)
        .limit(limit)
    ).all()
    return collection(
        {
            "type": "Feature",
            "id": s.id,
            "geometry": g,
            "properties": {
                "name": s.name,
                "source_type": s.source_type,
                "sector": s.sector,
                "country": s.country,
                "status": s.status,
                "first_seen": iso(s.first_seen),
                "last_seen": iso(s.last_seen),
                "n_detections": n or 0,
                "n_validated": nv or 0,
                "n_predicted": npd or 0,
                "q_max_kg_h": q,
            },
        }
        for s, g, n, nv, npd, q in rows
    )


def get_source(session: Session, source_id: int) -> Source | None:
    return session.get(Source, source_id)


def source_detail(session: Session, source_id: int) -> dict[str, Any] | None:
    """Everything app 2 and app 4 show for one source: its history, events and who is behind it."""
    from geoapps_db.repo.attribution import links_for_source, who_for_source
    from geoapps_db.repo.core import xrefs_for

    row = session.execute(
        select(Source, as_geojson(Source.geom)).where(Source.id == source_id)
    ).first()
    if row is None:
        return None
    s, g = row
    dets = session.execute(
        select(
            Detection.id,
            Detection.status,
            Detection.observed_at,
            Detection.marks,
            Detection.sensor_id,
            Detection.event_id,
        )
        .where(Detection.source_id == source_id)
        .order_by(Detection.observed_at)
    ).all()
    events = session.scalars(
        select(Event).where(Event.source_id == source_id).order_by(Event.t_b)
    ).all()
    return {
        "id": s.id,
        "geometry": g,
        "name": s.name,
        "source_type": s.source_type,
        "sector": s.sector,
        "country": s.country,
        "status": s.status,
        "first_seen": iso(s.first_seen),
        "last_seen": iso(s.last_seen),
        "attrs": s.attrs,
        "xrefs": xrefs_for(session, "source", s.id),
        "detections": [
            {
                "id": d.id,
                "status": d.status,
                "observed_at": iso(d.observed_at),
                "q_kg_h": (d.marks or {}).get("q_kg_h"),
                "q_sigma_kg_h": (d.marks or {}).get("q_sigma_kg_h"),
                "sensor_id": d.sensor_id,
                "event_id": d.event_id,
            }
            for d in dets
        ],
        "events": [event_dict(e) for e in events],
        "attributions": links_for_source(session, source_id),
        "who": who_for_source(session, source_id),
    }


def event_dict(e: Event) -> dict[str, Any]:
    return {
        "id": e.id,
        "status": e.status,
        "t_a": iso(e.t_a),
        "t_b": iso(e.t_b),
        "t_c": iso(e.t_c),
        "t_d": iso(e.t_d),
        "n_detections": e.n_detections,
        "q_mean_kg_h": e.q_mean_kg_h,
        "q_sigma_kg_h": e.q_sigma_kg_h,
    }


# ── facilities ──────────────────────────────────────────────────────────────
def add_facility(
    session: Session,
    *,
    name: str,
    geometry: dict[str, Any] | None = None,
    lon: float | None = None,
    lat: float | None = None,
    facility_type: str | None = None,
    sector: str | None = None,
    country: str | None = None,
    valid_from: datetime | None = None,
    **attrs: Any,
) -> Facility:
    if geometry is None:
        if lon is None or lat is None:
            raise ValueError("a facility needs a geometry or lon/lat")
        geometry = point(lon, lat)
    fac = Facility(
        name=name,
        geom=geom(geometry),
        facility_type=facility_type,
        sector=sector,
        country=country,
        attrs=attrs,
    )
    if valid_from is not None:
        fac.valid = Range(valid_from, None, bounds="[)")
    session.add(fac)
    session.flush()
    return fac


def facilities_geojson(session: Session, limit: int = 20000) -> dict[str, Any]:
    rows = session.execute(
        select(Facility, as_geojson(Facility.geom)).order_by(Facility.id).limit(limit)
    ).all()
    return collection(
        {
            "type": "Feature",
            "id": f.id,
            "geometry": g,
            "properties": {
                "name": f.name,
                "facility_type": f.facility_type,
                "sector": f.sector,
                "country": f.country,
                "status": f.status,
            },
        }
        for f, g in rows
    )
