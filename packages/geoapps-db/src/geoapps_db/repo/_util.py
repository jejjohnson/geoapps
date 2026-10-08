"""Geometry and serialization helpers shared by the repository modules."""

import json
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import functions as gf
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSON


def geom(geojson: dict[str, Any]):
    """GeoJSON dict (EPSG:4326) → a PostGIS geometry expression."""
    return gf.ST_SetSRID(gf.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)


def as_geojson(column):
    # ST_AsGeoJSON returns text; cast to json so the driver hands back a dict.
    return func.ST_AsGeoJSON(column, 6).cast(JSON)


def point(lon: float, lat: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [float(lon), float(lat)]}


def iso(t: datetime | None) -> str | None:
    # always UTC on the wire, whatever the database session's time zone is
    return t.astimezone(UTC).isoformat() if t else None


def collection(features) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}
