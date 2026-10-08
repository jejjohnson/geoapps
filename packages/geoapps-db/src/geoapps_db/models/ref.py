"""ref: things in the world we observe or that registries list."""

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, CheckConstraint, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from geoapps_db.models.base import Base, CreatedMixin, IdMixin, Timestamp, ValidMixin, _in

SOURCE_STATUSES = ("candidate", "active", "inactive", "retired")
ENTITIES = ("source", "facility", "asset", "org", "detection", "sensor", "location")


class Sensor(IdMixin, CreatedMixin, Base):
    """A satellite instrument; detection limits and priorities vary by sensor."""

    __tablename__ = "sensor"
    __table_args__ = {"schema": "ref"}

    name: Mapped[str] = mapped_column(String(128), unique=True)  # as the provider names it
    platform: Mapped[str | None] = mapped_column(String(128))
    agency: Mapped[str | None] = mapped_column(String(128))
    sensor_type: Mapped[str | None] = mapped_column(String(64))  # hyperspectral, multispectral, ...
    gsd_m: Mapped[float | None] = mapped_column(Float)


class Source(IdMixin, CreatedMixin, Base):
    """One emission point: it exists because detections came from there (framework p. 4)."""

    __tablename__ = "source"
    __table_args__ = (
        CheckConstraint(_in("status", SOURCE_STATUSES), name="status"),
        {"schema": "ref"},
    )

    name: Mapped[str] = mapped_column(String(256))
    event_kind: Mapped[str] = mapped_column(
        String(64), default="ch4_plume", server_default="ch4_plume", index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(64), default="unknown", server_default="unknown"
    )  # vent, flare, landfill
    sector: Mapped[str | None] = mapped_column(String(128), index=True)
    country: Mapped[str | None] = mapped_column(String(128), index=True)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    first_seen: Mapped[datetime | None] = mapped_column(Timestamp)
    last_seen: Mapped[datetime | None] = mapped_column(Timestamp)
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class Facility(IdMixin, CreatedMixin, ValidMixin, Base):
    """A site that a registry or an analyst says exists; it groups the sources on it."""

    __tablename__ = "facility"
    __table_args__ = {"schema": "ref"}

    name: Mapped[str] = mapped_column(String(256))
    facility_type: Mapped[str | None] = mapped_column(
        String(64)
    )  # well pad, compressor, landfill, mine
    sector: Mapped[str | None] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(128))
    geom = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class Xref(IdMixin, CreatedMixin, Base):
    """A provider's record id mapped onto our entity, so three registries can name one facility."""

    __tablename__ = "xref"
    __table_args__ = (
        UniqueConstraint("provider", "entity", "record_id"),
        CheckConstraint(_in("entity", ENTITIES), name="entity"),
        Index(None, "entity", "entity_id"),
        {"schema": "ref"},
    )

    entity: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[int] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(String(128))
    record_id: Mapped[str] = mapped_column(String(256))
    match_score: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text)
