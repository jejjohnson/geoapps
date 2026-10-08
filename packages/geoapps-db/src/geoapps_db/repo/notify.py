"""App 3: watches, alerts and the feedback that flows back into labels."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from geoapps_core import get_kind
from geoapps_db.models import Alert, Detection, Feedback, Watch
from geoapps_db.repo._util import as_geojson, collection, geom, iso


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
    watch = Watch(owner=owner, name=name, geom=geom(geometry), kind=kind, min_q_kg_h=min_q_kg_h)
    session.add(watch)
    session.flush()
    return watch


def watches_geojson(session: Session, owner: str | None = None) -> dict[str, Any]:
    stmt = select(Watch, as_geojson(Watch.geom))
    if owner:
        stmt = stmt.where(Watch.owner == owner)
    return collection(
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
        for w, g in session.execute(stmt).all()
    )


def list_alerts(
    session: Session, owner: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    stmt = (
        select(
            Alert,
            Watch.name,
            Watch.owner,
            Detection.kind,
            Detection.marks,
            Detection.observed_at,
            Detection.source_id,
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
            "created_at": iso(a.created_at),
            "watch": {"id": a.watch_id, "name": wname, "owner": wowner},
            "detection": {
                "id": a.detection_id,
                "kind": kind,
                "observed_at": iso(obs),
                "source_id": source_id,
                **(marks or {}),
            },
        }
        for a, wname, wowner, kind, marks, obs, source_id in session.execute(stmt).all()
    ]


def add_feedback(
    session: Session,
    *,
    author: str,
    about: str,
    about_id: int,
    kind: str,
    body: str | None = None,
    action: str | None = None,
) -> Feedback:
    fb = Feedback(
        author=author, about=about, about_id=about_id, kind=kind, body=body, action=action
    )
    session.add(fb)
    session.flush()
    return fb


def set_alert_state(
    session: Session, alert_id: int, state: str, reason: str | None = None, *, by: str = "system"
) -> Alert:
    """Change an alert's state; a dismissal also becomes feedback, so it can turn into a label."""
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise LookupError(f"alert {alert_id} not found")
    alert.state = state
    alert.reason = reason
    if state == "dismissed":
        add_feedback(
            session,
            author=by,
            about="alert",
            about_id=alert_id,
            kind=reason or "dismissed",
            action="review",
        )
    session.flush()
    return alert


def list_feedback(session: Session, limit: int = 200) -> list[dict[str, Any]]:
    return [
        {
            "id": f.id,
            "author": f.author,
            "about": f.about,
            "about_id": f.about_id,
            "kind": f.kind,
            "body": f.body,
            "action": f.action,
            "created_at": iso(f.created_at),
        }
        for f in session.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(limit))
    ]
