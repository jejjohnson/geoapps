"""Import the public methane plumes of UNEP IMEO's Eye on Methane (MARS).

The dataset is published as a ZIP of CSV (or of GeoJSON) on the Eye on Methane
download page, under CC BY-NC-SA 4.0. Columns follow the published data
dictionary (https://methanedata.unep.org/dict-mars-plumes):

    id_plume                    unique plume id                → xref (unep-mars, detection)
    source_name                 source id, e.g. country + 3 digits → ref.source via xref
    satellite                   satellite and agency           → ref.sensor
    tile_date                   observation time, ISO 8601     → observed_at
    lat, lon                    source location, WGS84         → point geometry and origin
    ch4_fluxrate(_std)          kg h⁻¹                         → marks.q_kg_h, q_sigma_kg_h
    wind_u, wind_v, wind_speed  m s⁻¹                          → marks.wind_*
    total_emission(_std)        t, transient events only       → marks.total_emission_*
    tile, tile_background       product ids                    → scene_id, attrs
    country, sector             where and what                 → ref.source
    actionable, notified, detection_institution, quantification_institution,
    last_update, insert_date                                   → attrs

Every plume lands as ``predicted`` (E4). MARS analysts have already reviewed
the public plumes; set ``accept_provider_validation`` to record that review as
a label by ``provider:unep-mars`` instead of reviewing each one yourself.
Persistence is not computed from this dataset: it lists plumes, not the clear
looks that found nothing (data model §7).
"""

import csv
import hashlib
import io
import json
import math
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from geoapps_db import repo
from geoapps_workers.registry import StepContext, etl

PROVIDER = "unep-mars"
MARS_CSV_URL = "https://unepazeconomyadlsstorage.blob.core.windows.net/public/unep_methanedata_detected_plumes_csv.zip"
LICENCE = "CC BY-NC-SA 4.0"
ATTRIBUTION = "UNEP International Methane Emissions Observatory, Eye on Methane / MARS"
REQUIRED = ("id_plume", "lat", "lon", "tile_date")


class MarsParams(BaseModel):
    url: str = Field(
        default=MARS_CSV_URL, description="ZIP, CSV or GeoJSON URL of the public plume list"
    )
    path: str | None = Field(default=None, description="Read a local file instead of the URL")
    accept_provider_validation: bool = Field(
        default=False,
        description="Record MARS's own review as a label (analyst provider:unep-mars) so plumes arrive validated",
    )
    p_assumed: float = Field(
        default=0.95, ge=0, le=1, description="Probability used for queue ranking; MARS gives none"
    )
    licence: str = Field(default=LICENCE, description="Licence recorded with the dataset")
    attribution: str = Field(default=ATTRIBUTION, description="Credit line shown with the data")
    limit: int | None = Field(
        default=None, ge=1, description="Import only the first N rows, to try it out"
    )


# ── reading ─────────────────────────────────────────────────────────────────
def _fetch(p: MarsParams) -> tuple[bytes, str]:
    if p.path:
        path = Path(p.path).expanduser()
        return path.read_bytes(), path.name
    resp = httpx.get(p.url, timeout=300, follow_redirects=True)
    resp.raise_for_status()
    return resp.content, p.url.rsplit("/", 1)[-1]


def _norm(key: str) -> str:
    return key.strip().lstrip("﻿").lower().replace(" ", "_")


def _records_from_csv(text: str) -> list[dict[str, Any]]:
    return [
        {_norm(k): v for k, v in row.items() if k is not None}
        for row in csv.DictReader(io.StringIO(text))
    ]


def _records_from_geojson(text: str) -> list[dict[str, Any]]:
    out = []
    for f in json.loads(text).get("features", []):
        rec = {_norm(k): v for k, v in (f.get("properties") or {}).items()}
        g = f.get("geometry") or {}
        if g.get("type") == "Point" and ("lat" not in rec or "lon" not in rec):
            rec["lon"], rec["lat"] = g["coordinates"][:2]
        out.append(rec)
    return out


def read_records(blob: bytes, name: str) -> list[dict[str, Any]]:
    """Plume records from a ZIP, CSV or GeoJSON file; in a ZIP, every member with plume rows."""
    if zipfile.is_zipfile(io.BytesIO(blob)):
        records: list[dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for member in sorted(z.namelist()):
                low = member.lower()
                if member.startswith("__MACOSX") or not low.endswith((".csv", ".geojson", ".json")):
                    continue
                rows = read_records(z.read(member), member)
                if rows and "id_plume" in rows[0]:
                    records.extend(rows)
        return records
    text = blob.decode("utf-8-sig")
    if name.lower().endswith((".geojson", ".json")) or text.lstrip().startswith("{"):
        return _records_from_geojson(text)
    return _records_from_csv(text)


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, int | float):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    s = str(v).strip()
    if s.lower() in ("", "na", "nan", "none", "null", "not available", "-"):
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return None if math.isnan(x) else x


def _time(v: Any) -> datetime | None:
    if v in (None, ""):
        return None
    s = str(v).strip().replace("Z", "+00:00")
    for candidate in (s, s.replace(" ", "T", 1)):
        try:
            t = datetime.fromisoformat(candidate)
            return t if t.tzinfo else t.replace(tzinfo=UTC)
        except ValueError:
            continue
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in ("", "na", "nan", "none", "null") else s


def _bool(v: Any) -> bool | None:
    s = _text(v)
    return None if s is None else s.lower() in ("true", "1", "yes", "y")


def to_detection(rec: dict[str, Any], p_assumed: float) -> dict[str, Any]:
    """One MARS record → the fields of one detection, its source and its sensor."""
    lat, lon = _num(rec.get("lat")), _num(rec.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("missing or invalid lat/lon")
    observed = _time(rec.get("tile_date"))
    if observed is None:
        raise ValueError("missing or invalid tile_date")
    marks = {
        "p": p_assumed,
        "q_kg_h": _num(rec.get("ch4_fluxrate")),
        "q_sigma_kg_h": _num(rec.get("ch4_fluxrate_std")),
        "wind_u_m_s": _num(rec.get("wind_u")),
        "wind_v_m_s": _num(rec.get("wind_v")),
        "wind_speed_m_s": _num(rec.get("wind_speed")),
        "total_emission_t": _num(rec.get("total_emission")),
        "total_emission_sigma_t": _num(rec.get("total_emission_std")),
    }
    attrs = {
        "actionable": _text(rec.get("actionable")),
        "notified": _bool(rec.get("notified")),
        "detection_institution": _text(rec.get("detection_institution")),
        "quantification_institution": _text(rec.get("quantification_institution")),
        "tile_background": _text(rec.get("tile_background")),
        "last_update": _text(rec.get("last_update")),
        "insert_date": _text(rec.get("insert_date")),
    }
    return {
        "record_id": _text(rec.get("id_plume")),
        "source_name": _text(rec.get("source_name")),
        "sensor": _text(rec.get("satellite")) or "unknown",
        "country": _text(rec.get("country")),
        "sector": _text(rec.get("sector")),
        "lon": round(lon, 6),
        "lat": round(lat, 6),
        "observed_at": observed,
        "scene_id": _text(rec.get("tile")),
        "marks": {k: v for k, v in marks.items() if v is not None},
        "attrs": {k: v for k, v in attrs.items() if v is not None},
    }


# ── the step ────────────────────────────────────────────────────────────────
@etl(
    name="import_mars_plumes",
    params=MarsParams,
    writes=(
        "core.dataset",
        "ref.sensor",
        "ref.source",
        "ref.xref",
        "review.detection",
        "monitor.event",
    ),
    version="0.1.0",
)
def import_mars_plumes(p: MarsParams, ctx: StepContext) -> dict:
    """Import the public UNEP IMEO Eye on Methane (MARS) plumes, with sources, sensors and provenance."""
    s = ctx.session
    blob, name = _fetch(p)
    sha = hashlib.sha256(blob).hexdigest()
    records = read_records(blob, name)
    if not records:
        raise ValueError(f"{name}: no plume records found (expected a column named id_plume)")
    missing = [c for c in REQUIRED if c not in records[0]]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}; found {sorted(records[0])}")
    if p.limit:
        records = records[: p.limit]

    dataset, new_file = repo.register_dataset(
        s,
        name="unep-mars-plumes",
        sha256=sha,
        url=None if p.path else p.url,
        licence=p.licence,
        attribution=p.attribution,
        n_records=len(records),
        run_id=ctx.run_id,
    )
    if not new_file:
        ctx.info(f"unchanged: dataset {dataset.id} has the same checksum")
        return {"dataset_id": dataset.id, "unchanged_file": True, "rows": len(records)}

    # what we already hold from this provider, in two queries instead of one per row
    known_det = repo.xref_map(s, PROVIDER, "detection")
    last_update = repo.detection_attr(s, list(known_det.values()), "last_update")
    sensors: dict[str, int] = {}
    n = Counter()
    reasons = Counter()
    touched: set[int] = set()

    for i, rec in enumerate(records):
        try:
            row = to_detection(rec, p.p_assumed)
            if not row["record_id"]:
                raise ValueError("missing id_plume")
        except ValueError as exc:
            reasons[str(exc)] += 1
            continue

        with s.begin_nested():  # one bad record never poisons the rest
            try:
                det_id = known_det.get(row["record_id"])
                if det_id is not None:
                    if last_update.get(det_id) == row["attrs"].get("last_update"):
                        n["unchanged"] += 1
                    elif repo.refresh_imported_detection(
                        s, det_id, marks=row["marks"], attrs=row["attrs"]
                    ):
                        n["updated"] += 1
                    else:
                        n["changed_after_review"] += 1  # never rewritten under a label
                    continue

                if row["sensor"] not in sensors:
                    sensors[row["sensor"]] = repo.upsert_sensor(s, row["sensor"])
                source_id = None
                if row["source_name"]:
                    source_id, created = repo.source_for_record(
                        s,
                        provider=PROVIDER,
                        record_id=row["source_name"],
                        lon=row["lon"],
                        lat=row["lat"],
                        sector=row["sector"],
                        country=row["country"],
                    )
                    n["sources_created"] += created
                    touched.add(source_id)
                point = {"type": "Point", "coordinates": [row["lon"], row["lat"]]}
                det = repo.add_detection(
                    s,
                    kind="ch4_plume",
                    geometry=point,
                    origin=point,
                    marks=row["marks"],
                    attrs=row["attrs"],
                    observed_at=row["observed_at"],
                    scene_id=row["scene_id"],
                    sensor_id=sensors[row["sensor"]],
                    source_id=source_id,
                    dataset_id=dataset.id,
                    run_id=ctx.run_id,
                )
                repo.add_xref(
                    s,
                    provider=PROVIDER,
                    entity="detection",
                    record_id=row["record_id"],
                    entity_id=det.id,
                )
                repo.add_assertion(
                    s,
                    provider=PROVIDER,
                    claim="plume",
                    record_id=row["record_id"],
                    dataset_id=dataset.id,
                    asserted_at=_time(row["attrs"].get("last_update")) or row["observed_at"],
                )
                if p.accept_provider_validation:
                    repo.record_verdict(
                        s,
                        det.id,
                        verdict="confirm",
                        analyst=f"provider:{PROVIDER}",
                        note="published by UNEP IMEO MARS",
                        rechain=False,
                    )
                known_det[row["record_id"]] = det.id
                n["imported"] += 1
            except Exception as exc:
                reasons[str(exc).splitlines()[0][:160]] += 1
        if (i + 1) % 2000 == 0:
            ctx.info(f"{i + 1} of {len(records)} rows")

    for sid in touched:
        repo.rechain_events(s, sid)
    repo.refresh_source_seen(s, sorted(touched))
    result = {
        "dataset_id": dataset.id,
        "licence": p.licence,
        "rows": len(records),
        "imported": n["imported"],
        "unchanged": n["unchanged"],
        "updated": n["updated"],
        "changed_after_review": n["changed_after_review"],
        "sources_created": n["sources_created"],
        "sensors": sorted(sensors),
        "skipped_total": sum(reasons.values()),
        "skipped": dict(reasons.most_common(10)),
        "validated_by_provider": p.accept_provider_validation,
    }
    ctx.info(
        f"imported {n['imported']} plumes at {len(touched)} sources from {len(sensors)} sensors; "
        f"skipped {result['skipped_total']}"
    )
    return result
