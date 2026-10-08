"""Chaining validated detections at one source into events (data model §6).

An event's start lies in [t_a, t_b] and its end in [t_c, t_d]:

    t_a  last valid look without a plume before it
    t_b  first look with a plume
    t_c  last look with a plume
    t_d  first valid look without a plume after it

With observations, a clear look between two detections closes the event.
Without them (a detections-only dataset), a gap longer than G days does.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray


def chain_by_gap(
    t_det: ArrayLike, gap: float, t_clear: ArrayLike | None = None
) -> NDArray[np.int64]:
    """Event index for each of K detection times (sorted ascending), in the same units as gap.

    new event at k  ⇔  t_k − t_{k−1} > G  ∨  a clear look lies in (t_{k−1}, t_k)
    """
    t = np.asarray(t_det, dtype=float)  # (K,)
    if t.size == 0:
        return np.zeros(0, dtype=np.int64)
    if np.any(np.diff(t) < 0):
        raise ValueError("detection times must be sorted")
    breaks = np.diff(t) > gap  # (K−1,)
    if t_clear is not None and len(t_clear):
        c = np.sort(np.asarray(t_clear, dtype=float))  # (C,)
        # number of clear looks strictly between consecutive detections
        between = np.searchsorted(c, t[1:], side="left") - np.searchsorted(c, t[:-1], side="right")
        breaks |= between > 0  # (K−1,)
    return np.concatenate([[0], np.cumsum(breaks)]).astype(np.int64)  # (K,) → (K,)


def bounds(
    t_first: float, t_last: float, t_clear: ArrayLike | None
) -> tuple[float | None, float | None]:
    """(t_a, t_d): the nearest clear looks before t_b and after t_c, or None when unobserved."""
    if t_clear is None or not len(t_clear):
        return None, None
    c = np.sort(np.asarray(t_clear, dtype=float))  # (C,)
    before, after = c[c < t_first], c[c > t_last]
    return (float(before[-1]) if before.size else None, float(after[0]) if after.size else None)


@dataclass(frozen=True)
class RateEstimate:
    mean: float
    sigma: float | None


def inverse_variance_mean(q: ArrayLike, sigma: ArrayLike | None = None) -> RateEstimate | None:
    """Rate when emitting, Q̄ = ∑ wₖ Qₖ / ∑ wₖ with wₖ = 1/σₖ²; a plain mean where σ is missing."""
    q = np.asarray(q, dtype=float)  # (K,)
    ok = np.isfinite(q)
    if not ok.any():
        return None
    s = None if sigma is None else np.asarray(sigma, dtype=float)  # (K,)
    if s is not None and np.all(np.isfinite(s[ok]) & (s[ok] > 0)):
        w = 1.0 / s[ok] ** 2  # (K,)
        # Q̄ = ∑ w Q / ∑ w,   σ_Q̄ = (∑ w)^(−1/2)
        return RateEstimate(float((w * q[ok]).sum() / w.sum()), float(w.sum() ** -0.5))
    return RateEstimate(float(q[ok].mean()), None)
