"""core: runs, registered ETLs, jobs, and the provenance of imported data."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from geoapps_db.models.base import Base, CreatedMixin, IdMixin, Timestamp, _in

JOB_STATES = ("queued", "running", "done", "failed")


class Run(IdMixin, CreatedMixin, Base):
    """One execution with its full version tuple (code versions, wind product, snapshots)."""

    __tablename__ = "run"
    __table_args__ = {"schema": "core"}

    stream: Mapped[str] = mapped_column(String(128), default="nrt", server_default="nrt")
    etl: Mapped[str | None] = mapped_column(String(128))
    versions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


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


class Job(IdMixin, CreatedMixin, Base):
    """One submission of a registered step, claimed by a worker with SKIP LOCKED."""

    __tablename__ = "job"
    __table_args__ = (CheckConstraint(_in("state", JOB_STATES), name="state"), {"schema": "core"})

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
    started_at: Mapped[datetime | None] = mapped_column(Timestamp)
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp)


class Dataset(IdMixin, CreatedMixin, Base):
    """One fetched file, public or private: what it was, where from, under which licence.

    The same bytes fetched twice are one row, so a rerun on an unchanged file is a no-op.
    """

    __tablename__ = "dataset"
    __table_args__ = (UniqueConstraint("name", "sha256"), {"schema": "core"})

    name: Mapped[str] = mapped_column(String(128), index=True)  # "unep-mars-plumes"
    url: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str] = mapped_column(
        String(128), default="unspecified", server_default="unspecified"
    )
    attribution: Mapped[str | None] = mapped_column(Text)  # credit line to show with the data
    sha256: Mapped[str] = mapped_column(String(64))
    n_records: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    run_id: Mapped[int | None] = mapped_column(ForeignKey("core.run.id"))


class Assertion(IdMixin, CreatedMixin, Base):
    """One claim by one provider about one record, and whether we accepted it (framework p. 4)."""

    __tablename__ = "assertion"
    __table_args__ = {"schema": "core"}

    provider: Mapped[str] = mapped_column(
        String(128), index=True
    )  # registry, regulator, analyst, dataset
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("core.dataset.id"), index=True)
    record_id: Mapped[str | None] = mapped_column(String(256))
    claim: Mapped[str] = mapped_column(String(64))  # "plume", "operator", "facility_asset", ...
    accepted: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    asserted_at: Mapped[datetime | None] = mapped_column(Timestamp)  # when the provider said it
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


__all__ = ["JOB_STATES", "Assertion", "Dataset", "Etl", "Job", "Run"]
