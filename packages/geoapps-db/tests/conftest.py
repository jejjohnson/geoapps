"""Database tests run against a real PostGIS when GEOAPPS_TEST_DATABASE_URL is set.

Each test gets a freshly migrated database: the schema is dropped and the
migration replayed, so tests also exercise the Alembic path.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

URL = os.environ.get("GEOAPPS_TEST_DATABASE_URL")


def _reset(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        for schema in ("notify", "review", "ref", "core"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    engine.dispose()
    from alembic import command

    from geoapps_db.cli import alembic_config

    command.upgrade(alembic_config(url), "head")


@pytest.fixture()
def db_url():
    if not URL:
        pytest.skip("set GEOAPPS_TEST_DATABASE_URL to run database tests")
    _reset(URL)
    return URL


@pytest.fixture()
def session(db_url):
    engine = create_engine(db_url)
    with Session(engine, expire_on_commit=False) as s:
        yield s
        s.rollback()
    engine.dispose()
