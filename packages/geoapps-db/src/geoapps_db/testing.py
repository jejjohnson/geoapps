"""Helpers for test suites that run against a throwaway PostGIS database."""

from sqlalchemy import create_engine, text

from geoapps_db.models import SCHEMAS


def reset_database(url: str) -> None:
    """Drop every geoapps schema and replay the migrations, so tests exercise Alembic too."""
    engine = create_engine(url)
    with engine.begin() as conn:
        for schema in reversed(SCHEMAS):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    engine.dispose()
    from alembic import command

    from geoapps_db.cli import alembic_config

    command.upgrade(alembic_config(url), "head")
