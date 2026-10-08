"""Tables of the walking skeleton.

Schemas follow docs/design/01-design-plan.md, "Data placement":

    core     runs, registered ETLs, jobs
    ref      reference layers (sources); facilities and assets come with app 2
    review   detections and analyst labels (app 1)
    notify   watches, alerts and the outbox (app 3)

Rules carried into the schema:
- a detection is born ``predicted``; only a verdict changes it (E4)
- labels are append-only and anchored to scene + geometry, not only to a detection id (E1)
- one alert per (watch, detection), so a watcher is never alerted twice (G5)
"""

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SCHEMAS = ("core", "ref", "review", "notify")
STATUSES = ("predicted", "validated", "rejected")
VERDICTS = ("confirm", "redraw", "reject")
JOB_STATES = ("queued", "running", "done", "failed")
ALERT_STATES = ("raised", "seen", "kept", "dismissed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


Timestamp = DateTime(timezone=True)


# ── core ────────────────────────────────────────────────────────────────────
class Run(Base):
    """One execution with its full version tuple (code versions, wind product, snapshots)."""

    __tablename__ = "run"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stream: Mapped[str] = mapped_column(String(128), default="nrt", server_default="nrt")
    etl: Mapped[str | None] = mapped_column(String(128))
    versions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class Etl(Base):
    """A registered step users and schedules may run (workstream H1)."""

    __tablename__ = "etl"
    __table_args__ = {"schema": "core"}

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    params_schema: Mapped[dict[str, Any]] = mapped_column(JSONB)
    writes: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, server_default=func.now(), onupdate=func.now()
    )


class Job(Base):
    """One submission of a registered step, claimed by a worker with SKIP LOCKED."""

    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint(_in("state", JOB_STATES), name="state"),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    etl: Mapped[str] = mapped_column(ForeignKey("core.etl.name"), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    state: Mapped[str] = mapped_column(
        String(16), default="queued", server_default="queued", index=True
    )
    key: Mapped[str | None] = mapped_column(
        String(256), unique=True
    )  # (step, input, version tuple)
    submitted_by: Mapped[str] = mapped_column(
        String(128), default="system", server_default="system"
    )
    run_id: Mapped[int | None] = mapped_column(ForeignKey("core.run.id"))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(Timestamp)
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp)


# ── ref ─────────────────────────────────────────────────────────────────────
class Source(Base):
    """A candidate emitter (well pad, compressor, landfill...). Facilities and assets arrive with app 2."""

    __tablename__ = "source"
    __table_args__ = {"schema": "ref"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(64), default="unknown", server_default="unknown")
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=True), nullable=False)
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


# ── review ──────────────────────────────────────────────────────────────────
class Detection(Base):
    """One snapshot of an event, born predicted (E4)."""

    __tablename__ = "detection"
    __table_args__ = (
        CheckConstraint(_in("status", STATUSES), name="status"),
        {"schema": "review"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="predicted", server_default="predicted", index=True
    )
    scene_id: Mapped[str | None] = mapped_column(String(256))
    observed_at: Mapped[datetime] = mapped_column(Timestamp)
    geom = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=True), nullable=False)
    origin = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=True)
    marks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    priority: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("core.run.id"))
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())

    labels: Mapped[list["Label"]] = relationship(back_populates="detection")


class Label(Base):
    """An analyst verdict, anchored to scene + geometry so it survives reprocessing (E1). Append-only."""

    __tablename__ = "label"
    __table_args__ = (
        CheckConstraint(_in("verdict", VERDICTS), name="verdict"),
        {"schema": "review"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    detection_id: Mapped[int | None] = mapped_column(ForeignKey("review.detection.id"), index=True)
    scene_id: Mapped[str | None] = mapped_column(String(256))
    geom = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=False), nullable=True)
    verdict: Mapped[str] = mapped_column(String(16))
    analyst: Mapped[str] = mapped_column(String(128))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())

    detection: Mapped[Detection | None] = relationship(back_populates="labels")


# ── notify ──────────────────────────────────────────────────────────────────
class Watch(Base):
    """A watch rule over an area (G3): any validated detection of a kind, optionally above a flux."""

    __tablename__ = "watch"
    __table_args__ = {"schema": "notify"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(256))
    geom = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=True), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(64))
    min_q_kg_h: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class Alert(Base):
    """One alert per (watch, detection) (G5)."""

    __tablename__ = "alert"
    __table_args__ = (
        UniqueConstraint("watch_id", "detection_id"),
        CheckConstraint(_in("state", ALERT_STATES), name="state"),
        {"schema": "notify"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    watch_id: Mapped[int] = mapped_column(
        ForeignKey("notify.watch.id", ondelete="CASCADE"), index=True
    )
    detection_id: Mapped[int] = mapped_column(ForeignKey("review.detection.id"), index=True)
    state: Mapped[str] = mapped_column(String(16), default="raised", server_default="raised")
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class Outbox(Base):
    """Delivery queue: a worker sends and marks rows, so a crash never sends twice (G2)."""

    __tablename__ = "outbox"
    __table_args__ = {"schema": "notify"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("notify.alert.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(32), default="in_app", server_default="in_app")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sent_at: Mapped[datetime | None] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
