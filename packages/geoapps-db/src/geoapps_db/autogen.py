"""Filters shared by Alembic autogenerate and the A1 drift test.

Only the geoapps schemas are compared, and GeoAlchemy2's helper keeps the
spatial indexes it manages out of the diff.
"""

from geoalchemy2 import alembic_helpers

from geoapps_db.models import SCHEMAS


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name in SCHEMAS
    return True


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name == "alembic_version":
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)
