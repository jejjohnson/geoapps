"""monitor: where we look, every look (with or without a plume), and the events they bound.

Persistence needs the looks that found nothing, so observations are first-class rows.
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from geoapps_db.models.base import Base, CreatedMixin, IdMixin, Timestamp, _in

LOCATION_STATUSES = ("candidate", "monitored", "paused", "retired")
EVENT_STATUSES = ("open", "closed")


class Location(IdMixin, CreatedMixin, Base):
    """An area of interest around a source or facility: a monitoring decision."""

    __tablename__ = "location"
    __table_args__ = (
        CheckConstraint(_in("status", LOCATION_STATUSES), name="status"),
        {"schema": "monitor"},
    )

    name: Mapped[str] = mapped_column(String(256))
    area = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="candidate", server_default="candidate")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("ref.source.id"), index=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("ref.facility.id"), index=True)
    sensors: Mapped[list[str]] = mapped_column(
        ARRAY(String(128)), default=list, server_default="{}"
    )
    revisit_days: Mapped[float | None] = mapped_column(Float)


class LocationStatus(IdMixin, CreatedMixin, Base):
    """One row per lifecycle transition: candidate → monitored → paused → retired."""

    __tablename__ = "location_status"
    __table_args__ = (
        CheckConstraint(_in("status", LOCATION_STATUSES), name="status"),
        {"schema": "monitor"},
    )

    location_id: Mapped[int] = mapped_column(
        ForeignKey("monitor.location.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    by: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text)


class Observation(IdMixin, CreatedMixin, Base):
    """One look at one location: how much was valid and the smallest plume it could see."""

    __tablename__ = "observation"
    __table_args__ = (
        CheckConstraint("valid_fraction >= 0 AND valid_fraction <= 1", name="valid_fraction"),
        {"schema": "monitor"},
    )

    location_id: Mapped[int] = mapped_column(
        ForeignKey("monitor.location.id", ondelete="CASCADE"), index=True
    )
    sensor_id: Mapped[int | None] = mapped_column(ForeignKey("ref.sensor.id"))
    scene_id: Mapped[str | None] = mapped_column(String(256))
    observed_at: Mapped[datetime] = mapped_column(Timestamp, index=True)
    valid_fraction: Mapped[float] = mapped_column(Float)
    detection_limit_kg_h: Mapped[float | None] = mapped_column(Float)
    detection_id: Mapped[int | None] = mapped_column(ForeignKey("review.detection.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("core.run.id"))


class Event(IdMixin, CreatedMixin, Base):
    """One episode at one source; start in [t_a, t_b], end in [t_c, t_d] (data model §6)."""

    __tablename__ = "event"
    __table_args__ = (
        CheckConstraint(_in("status", EVENT_STATUSES), name="status"),
        CheckConstraint("t_b <= t_c", name="order"),
        {"schema": "monitor"},
    )

    kind: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("ref.source.id", ondelete="CASCADE"), index=True
    )
    location_id: Mapped[int | None] = mapped_column(ForeignKey("monitor.location.id"))
    t_a: Mapped[datetime | None] = mapped_column(Timestamp)  # last clear look before
    t_b: Mapped[datetime] = mapped_column(Timestamp)  # first detection
    t_c: Mapped[datetime] = mapped_column(Timestamp)  # last detection
    t_d: Mapped[datetime | None] = mapped_column(Timestamp)  # first clear look after
    status: Mapped[str] = mapped_column(String(8), default="open", server_default="open")
    n_detections: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    q_mean_kg_h: Mapped[float | None] = mapped_column(Float)  # rate when emitting, Q̄
    q_sigma_kg_h: Mapped[float | None] = mapped_column(Float)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("core.run.id"))
