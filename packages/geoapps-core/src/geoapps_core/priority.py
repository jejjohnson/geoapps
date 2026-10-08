"""Validation-queue priority and analyst alerts (sub-decision E5).

    π_d = p_d · v_d · g(Q̂_d) · (1 + β n_d) · u(a_d)
    g(Q) = log(1 + Q / Q_ref)
    u(a) = 1 if a ≤ τ else exp(−(a − τ) / λ)

p_d   calibrated probability that detection d is a real plume, in [0, 1]
v_d   viability of its scene (clear, in swath, retrieval passed), in [0, 1]
Q̂_d   predicted flux, kg h⁻¹; Q_ref a reference flux
n_d   1 if validating d would fire a watch or notification rule
a_d   time since the overpass; τ the notification window; λ the decay after it

Ages and windows share one unit (hours by convention).
"""

import numpy as np
from numpy.typing import ArrayLike, NDArray


def urgency(age: ArrayLike, tau: float, lam: float) -> NDArray[np.float64]:
    # u(a) = 1 for a ≤ τ, exp(−(a − τ)/λ) afterwards
    a = np.asarray(age, dtype=float)  # (D,)
    return np.where(a <= tau, 1.0, np.exp(-(a - tau) / lam))  # (D,) → (D,)


def priority(
    p: ArrayLike,
    v: ArrayLike,
    q_hat: ArrayLike,
    would_notify: ArrayLike,
    age: ArrayLike,
    *,
    tau: float,
    lam: float,
    beta: float = 1.0,
    q_ref: float = 100.0,
) -> NDArray[np.float64]:
    """Priority π_d for D queued detections; every input broadcasts to (D,)."""
    p, v, q_hat = (np.asarray(x, dtype=float) for x in (p, v, q_hat))  # (D,) each
    n = np.asarray(would_notify, dtype=float)  # (D,) in {0, 1}
    # g(Q̂) = log(1 + Q̂ / Q_ref)
    g = np.log1p(np.clip(q_hat, 0.0, None) / q_ref)  # (D,) → (D,)
    # π = p · v · g · (1 + β n) · u(a)
    return p * v * g * (1.0 + beta * n) * urgency(age, tau, lam)  # (D,) → (D,)


def alert_mask(
    pri: ArrayLike,
    would_notify: ArrayLike,
    age: ArrayLike,
    *,
    pi0: float,
    tau: float,
    delta: float,
) -> NDArray[np.bool_]:
    """Alert ⇔ π_d ≥ π₀  ∨  (n_d = 1 ∧ 0 ≤ τ − a_d ≤ δ), the window about to close."""
    pri = np.asarray(pri, dtype=float)  # (D,)
    n = np.asarray(would_notify, dtype=bool)  # (D,)
    left = tau - np.asarray(age, dtype=float)  # (D,) time left in window
    return (pri >= pi0) | (n & (left >= 0.0) & (left <= delta))  # (D,) → (D,) bool
