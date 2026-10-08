"""review (app 1): detections, the labels people give them, and frozen label sets.

- a detection is born ``predicted``; only a label changes it (E4)
- labels are append-only and anchored to scene + geometry, not only to a detection id (E1)
"""

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from geoapps_db.models.base import Base, CreatedMixin, IdMixin, Timestamp, _in

STATUSES = ("predicted", "validated", "rejected")
VERDICTS = ("confirm", "redraw", "reject")
RELATIONS = ("same_moment", "contains", "duplicate")


class Detection(IdMixin, CreatedMixin, Base):
    """One snapshot of an event: an outline, or a point when only its location is known."""

    __tablename__ = "detection"
    __table_args__ = (CheckConstraint(_in("status", STATUSES), name="status"), {"schema": "review"})

    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="predicted", server_default="predicted", index=True
    )
    sensor_id: Mapped[int | None] = mapped_column(ForeignKey("ref.sensor.id"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("ref.source.id"), index=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitor.event.id", ondelete="SET NULL"), index=True
    )
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("core.dataset.id"), index=True)
    scene_id: Mapped[str | None] = mapped_column(String(256))
    observed_at: Mapped[datetime] = mapped_column(Timestamp, index=True)
    geom = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=True), nullable=False)
    origin = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=True)
    marks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    priority: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", index=True)
    pixel_size_m: Mapped[float | None] = mapped_column(Float)  # the scale it was seen at
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("review.detection.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("core.run.id"))

    labels: Mapped[list["Label"]] = relationship(back_populates="detection")


class Label(IdMixin, CreatedMixin, Base):
    """A verdict by a person, or by a provider whose review the instance chose to accept."""

    __tablename__ = "label"
    __table_args__ = (
        CheckConstraint(_in("verdict", VERDICTS), name="verdict"),
        {"schema": "review"},
    )

    detection_id: Mapped[int | None] = mapped_column(ForeignKey("review.detection.id"), index=True)
    scene_id: Mapped[str | None] = mapped_column(String(256))
    geom = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=True)
    verdict: Mapped[str] = mapped_column(String(16))
    analyst: Mapped[str] = mapped_column(String(128), index=True)  # a user, or "provider:<name>"
    note: Mapped[str | None] = mapped_column(Text)

    detection: Mapped[Detection | None] = relationship(back_populates="labels")


class DetectionRelation(IdMixin, CreatedMixin, Base):
    """Two detections of one thing at different scales or by different sensors, kept apart.

    same_moment  one look seen by two sensors minutes apart (an observation group)
    contains     a coarse detection (a) holds a finer one (b): TROPOMI blob → EMIT plume
    duplicate    the same snapshot from two providers
    """

    __tablename__ = "detection_relation"
    __table_args__ = (
        CheckConstraint(_in("relation", RELATIONS), name="relation"),
        CheckConstraint("a_id <> b_id", name="distinct"),
        UniqueConstraint("a_id", "b_id", "relation"),
        {"schema": "review"},
    )

    a_id: Mapped[int] = mapped_column(
        ForeignKey("review.detection.id", ondelete="CASCADE"), index=True
    )
    b_id: Mapped[int] = mapped_column(
        ForeignKey("review.detection.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(16))
    method: Mapped[str] = mapped_column(String(64))  # "overlap", "analyst", "provider", ...
    score: Mapped[float | None] = mapped_column(Float)
    decided_by: Mapped[str | None] = mapped_column(String(128))


class LabelSet(IdMixin, CreatedMixin, Base):
    """Labels frozen at a moment, so a model comparison is reproducible (stage 2, 𝓛ₖ)."""

    __tablename__ = "label_set"
    __table_args__ = {"schema": "review"}

    name: Mapped[str] = mapped_column(String(128), unique=True)
    frozen_at: Mapped[datetime] = mapped_column(Timestamp)
    filter: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    n_labels: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class LabelSetMember(Base):
    __tablename__ = "label_set_member"
    __table_args__ = {"schema": "review"}

    label_set_id: Mapped[int] = mapped_column(
        ForeignKey("review.label_set.id", ondelete="CASCADE"), primary_key=True
    )
    label_id: Mapped[int] = mapped_column(ForeignKey("review.label.id"), primary_key=True)
