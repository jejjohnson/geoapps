"""Engine and session handling.

The connection string comes from ``GEOAPPS_DATABASE_URL`` (instance
configuration, ownership rule 16), e.g.
``postgresql+psycopg://geoapps:geoapps@localhost:5432/geoapps``.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg://geoapps:geoapps@localhost:5432/geoapps"


def database_url() -> str:
    return os.environ.get("GEOAPPS_DATABASE_URL", DEFAULT_URL)


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True, future=True)


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    """One transaction: commit on success, roll back on any error."""
    factory = sessionmaker(bind=get_engine(url), expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
