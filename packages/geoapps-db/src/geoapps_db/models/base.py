"""Declarative base, naming convention and shared column types."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import TSTZRANGE, Range
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SCHEMAS = ("core", "ref", "review", "attribution", "monitor", "notify")

Timestamp = DateTime(timezone=True)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class CreatedMixin:
    """When we recorded the row: the second clock (data model §3)."""

    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class ValidMixin:
    """When the fact was true in the world: [from, to), open-ended by default."""

    valid: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, nullable=False, server_default="(,)")
