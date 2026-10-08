"""Database tests run against a real PostGIS when GEOAPPS_TEST_DATABASE_URL is set.

Each test gets a freshly migrated database: the schema is dropped and the
migration replayed, so tests also exercise the Alembic path.
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from geoapps_db.testing import reset_database

URL = os.environ.get("GEOAPPS_TEST_DATABASE_URL")


@pytest.fixture()
def db_url():
    if not URL:
        pytest.skip("set GEOAPPS_TEST_DATABASE_URL to run database tests")
    reset_database(URL)
    return URL


@pytest.fixture()
def session(db_url):
    engine = create_engine(db_url)
    with Session(engine, expire_on_commit=False) as s:
        yield s
        s.rollback()
    engine.dispose()
