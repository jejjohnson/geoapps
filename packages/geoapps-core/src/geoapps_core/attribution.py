"""Candidate-source scoring (running-example stage 3).

    w_j = exp(−d_j² / 2ℓ²) · ((1 + cos(θ_j − φ)) / 2)^κ
    p(j | plume) = w_j / (w_0 + Σ_k w_k)

d_j   haversine distance from candidate source j to the plume origin, m
θ_j   bearing from source j to the origin, degrees from north
φ     bearing the wind blows toward, degrees from north
ℓ     length scale, m;  κ sharpness of the alignment penalty
w_0   weight of the "unknown source" option
"""

import numpy as np
from numpy.typing import ArrayLike, NDArray

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lon1: ArrayLike, lat1: ArrayLike, lon2: ArrayLike, lat2: ArrayLike) -> NDArray:
    """Great-circle distance in metres; inputs in degrees, broadcast together."""
    lon1, lat1, lon2, lat2 = (
        np.radians(np.asarray(x, dtype=float)) for x in (lon1, lat1, lon2, lat2)
    )
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def bearing_deg(lon1: ArrayLike, lat1: ArrayLike, lon2: ArrayLike, lat2: ArrayLike) -> NDArray:
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    lon1, lat1, lon2, lat2 = (
        np.radians(np.asarray(x, dtype=float)) for x in (lon1, lat1, lon2, lat2)
    )
    y = np.sin(lon2 - lon1) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(lon2 - lon1)
    return np.degrees(np.arctan2(y, x)) % 360.0


def wind_to_deg(u: ArrayLike, v: ArrayLike) -> NDArray:
    """Bearing the wind blows toward, degrees clockwise from north, from (u east, v north)."""
    # φ = atan2(u, v) mod 360
    return np.degrees(np.arctan2(np.asarray(u, dtype=float), np.asarray(v, dtype=float))) % 360.0


def candidate_weights(
    distance_m: ArrayLike,
    bearing_to_origin_deg: ArrayLike,
    wind_to_deg: float,
    *,
    ell: float,
    kappa: float,
) -> NDArray[np.float64]:
    d = np.asarray(distance_m, dtype=float)  # (K,)
    dtheta = np.radians(np.asarray(bearing_to_origin_deg, dtype=float) - wind_to_deg)  # (K,)
    # exp(−d²/2ℓ²) · ((1 + cos Δθ)/2)^κ
    align = np.clip((1.0 + np.cos(dtheta)) / 2.0, 0.0, 1.0)  # (K,)
    return np.exp(-(d**2) / (2 * ell**2)) * align**kappa  # (K,) → (K,)


def candidate_probabilities(
    distance_m: ArrayLike,
    bearing_to_origin_deg: ArrayLike,
    wind_to_deg: float,
    *,
    ell: float = 500.0,
    kappa: float = 4.0,
    w0: float = 0.05,
) -> NDArray[np.float64]:
    """p(j | plume) for K candidates; the remainder 1 − Σ p_j is the unknown-source share."""
    w = candidate_weights(distance_m, bearing_to_origin_deg, wind_to_deg, ell=ell, kappa=kappa)
    return w / (w0 + w.sum())  # (K,) → (K,)
