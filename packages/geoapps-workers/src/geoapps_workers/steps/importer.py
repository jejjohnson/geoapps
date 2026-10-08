"""Bring your own detections: import a GeoJSON FeatureCollection as predicted detections.

This is the first bring-your-own-data path (workstream M2). Each feature needs
a Polygon geometry and properties holding the kind's marks plus an observation
time, for example::

    {"type": "Feature",
     "geometry": {"type": "Polygon", "coordinates": [...]},
     "properties": {"observed_at": "2026-09-30T17:05:00Z", "scene_id": "my-scene-42",
                    "q_kg_h": 850, "q_sigma_kg_h": 210, "p": 0.9}}

Every imported row is born ``predicted`` and goes to app 1's queue: an import
never skips validation (E4).
"""

import json
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from geoapps_core import get_kind
from geoapps_db import repo
from geoapps_workers.registry import StepContext, etl


class ImportParams(BaseModel):
    source: str = Field(description="Path or http(s) URL of a GeoJSON FeatureCollection")
    kind: str = Field(default="ch4_plume", description="Event kind of every feature")
    scene_prefix: str = Field(default="import", description="Prefix for scene ids that are missing")


def _load(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        resp = httpx.get(source, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    return json.loads(Path(source).expanduser().read_text())


@etl(name="import_detections", params=ImportParams, writes=("review.detection",))
def import_detections(p: ImportParams, ctx: StepContext) -> dict:
    """Import a GeoJSON FeatureCollection of detections as predicted rows."""
    kind = get_kind(p.kind)
    data = _load(p.source)
    marks_fields = set(kind.marks.model_fields)
    imported, skipped = 0, []
    for i, feat in enumerate(data.get("features", [])):
        props = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        if geom.get("type") != kind.geometry:
            skipped.append(
                {"index": i, "reason": f"geometry {geom.get('type')} is not {kind.geometry}"}
            )
            continue
        try:
            observed = datetime.fromisoformat(str(props["observed_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            skipped.append({"index": i, "reason": "missing or invalid observed_at"})
            continue
        with ctx.session.begin_nested():  # one bad feature never poisons the rest
            try:
                repo.add_detection(
                    ctx.session,
                    kind=kind.name,
                    geometry=geom,
                    marks={k: v for k, v in props.items() if k in marks_fields},
                    observed_at=observed,
                    scene_id=props.get("scene_id") or f"{p.scene_prefix}-{i:05d}",
                    run_id=ctx.run_id,
                )
                imported += 1
            except Exception as exc:  # marks failing the kind's schema (L2), bad geometry...
                skipped.append({"index": i, "reason": str(exc).splitlines()[0][:200]})
    ctx.info(f"imported {imported}, skipped {len(skipped)}")
    return {"imported": imported, "skipped": skipped[:50], "skipped_total": len(skipped)}
