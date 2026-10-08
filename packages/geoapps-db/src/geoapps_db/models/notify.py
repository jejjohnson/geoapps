"""notify (app 3): watches, alerts, the delivery outbox, and feedback that becomes labels."""

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from geoapps_db.models.base import Base, CreatedMixin, IdMixin, Timestamp, _in

ALERT_STATES = ("raised", "seen", "kept", "dismissed")
FEEDBACK_ABOUT = ("alert", "detection", "attribution", "facility", "source")


class Watch(IdMixin, CreatedMixin, Base):
    """A watch rule over an area (G3): any validated detection of a kind, optionally above a flux."""

    __tablename__ = "watch"
    __table_args__ = {"schema": "notify"}

    owner: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(256))
    geom = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=True), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(64))
    min_q_kg_h: Mapped[float | None] = mapped_column(Float)


class Alert(IdMixin, CreatedMixin, Base):
    """One alert per (watch, detection) (G5)."""

    __tablename__ = "alert"
    __table_args__ = (
        UniqueConstraint("watch_id", "detection_id"),
        CheckConstraint(_in("state", ALERT_STATES), name="state"),
        {"schema": "notify"},
    )

    watch_id: Mapped[int] = mapped_column(
        ForeignKey("notify.watch.id", ondelete="CASCADE"), index=True
    )
    detection_id: Mapped[int] = mapped_column(ForeignKey("review.detection.id"), index=True)
    state: Mapped[str] = mapped_column(String(16), default="raised", server_default="raised")
    reason: Mapped[str | None] = mapped_column(Text)


class Outbox(IdMixin, CreatedMixin, Base):
    """Delivery queue: a worker sends and marks rows, so a crash never sends twice (G2)."""

    __tablename__ = "outbox"
    __table_args__ = {"schema": "notify"}

    alert_id: Mapped[int] = mapped_column(
        ForeignKey("notify.alert.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(32), default="in_app", server_default="in_app")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sent_at: Mapped[datetime | None] = mapped_column(Timestamp)


class Feedback(IdMixin, CreatedMixin, Base):
    """What a watcher, analyst, operator or government told us; dismissals land here too."""

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(_in("about", FEEDBACK_ABOUT), name="about"),
        {"schema": "notify"},
    )

    author: Mapped[str] = mapped_column(String(128), index=True)
    about: Mapped[str] = mapped_column(String(16))
    about_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(64))  # "not a plume", "wrong source", "repaired", ...
    body: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(String(64))  # what we did with it
