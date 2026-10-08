"""Synthetic plumes for trying the platform with no data at all.

The plumes sit around a handful of made-up well pads in the Permian Basin,
the design doc's running example. Scene ids start with ``synthetic-`` so they
are never mistaken for observations. They exist only so a fresh install has
something to validate, watch and alert on.
"""

import math
from datetime import UTC, datetime, timedelta

import numpy as np
from pydantic import BaseModel, Field

from geoapps_db import repo
from geoapps_workers.registry import StepContext, etl

PERMIAN_PADS = [  # (name, lon, lat), synthetic
    ("Demo pad A", -103.62, 31.94),
    ("Demo pad B", -103.48, 31.87),
    ("Demo pad C", -103.35, 32.02),
    ("Demo pad D", -103.71, 32.10),
    ("Demo pad E", -103.20, 31.78),
]


class SeedParams(BaseModel):
    n: int = Field(default=12, ge=1, le=500, description="Number of synthetic plumes")
    seed: int = Field(default=0, description="Random seed, so a rerun is reproducible")
    days: int = Field(
        default=10, ge=1, le=365, description="Spread observations over the last N days"
    )


def plume_polygon(lon: float, lat: float, wind_to_deg: float, length_m: float, n: int = 16) -> dict:
    """A teardrop polygon that starts at the origin and widens downwind.

    Along-wind distance s ∈ [0, L]; half-width w(s) = 0.25 L sin(π s / L) √(s / L).
    """
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat))
    th = math.radians(wind_to_deg)
    ux, uy = math.sin(th), math.cos(th)  # unit vector the wind blows toward (east, north)
    px, py = -uy, ux  # unit vector to its left

    def point(s: float, side: float) -> list[float]:
        w = 0.25 * length_m * math.sin(math.pi * s / length_m) * math.sqrt(s / length_m)
        x, y = s * ux + side * w * px, s * uy + side * w * py
        return [round(lon + x / m_per_deg_lon, 6), round(lat + y / m_per_deg_lat, 6)]

    stations = [length_m * k / n for k in range(n + 1)]
    ring = [point(s, +1) for s in stations] + [point(s, -1) for s in reversed(stations[1:-1])]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


@etl(name="seed_demo", params=SeedParams, writes=("ref.source", "review.detection"))
def seed_demo(p: SeedParams, ctx: StepContext) -> dict:
    """Create synthetic Permian well pads and predicted methane plumes to try the platform."""
    rng = np.random.default_rng(p.seed)
    now = datetime.now(UTC)
    for name, lon, lat in PERMIAN_PADS:
        repo.add_source(ctx.session, name, lon, lat, kind="well_pad", synthetic=True)
    for i in range(p.n):
        _, lon, lat = PERMIAN_PADS[i % len(PERMIAN_PADS)]
        q = float(rng.lognormal(mean=math.log(600), sigma=0.8))
        repo.add_detection(
            ctx.session,
            kind="ch4_plume",
            geometry=plume_polygon(
                lon, lat, float(rng.uniform(0, 360)), float(rng.uniform(400, 1500))
            ),
            origin={"type": "Point", "coordinates": [lon, lat]},
            marks={
                "q_kg_h": round(q, 1),
                "q_sigma_kg_h": round(q * float(rng.uniform(0.2, 0.45)), 1),
                "p": round(float(rng.uniform(0.35, 0.99)), 3),
                "viability": round(float(rng.uniform(0.6, 1.0)), 3),
            },
            observed_at=now - timedelta(hours=float(rng.uniform(0, 24 * p.days))),
            scene_id=f"synthetic-{p.seed}-{i:03d}",
            run_id=ctx.run_id,
        )
    ctx.info(f"created {p.n} synthetic plumes and {len(PERMIAN_PADS)} sources")
    return {"detections": p.n, "sources": len(PERMIAN_PADS)}
