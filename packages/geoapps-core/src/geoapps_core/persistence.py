"""Site persistence and repair verification (running-example stages 4 and 5).

N_valid   overpasses where the site was observable (clear, in swath, above detection limit)
N_det     those with a validated plume
P         chance that a valid overpass shows a plume

With a flat prior:  P | data ~ Beta(1 + N_det, 1 + N_valid − N_det)
"""

import math

from scipy import stats


def persistence_posterior(n_det: int, n_valid: int) -> stats.rv_continuous:
    """Frozen Beta posterior of P; requires 0 ≤ N_det ≤ N_valid."""
    if not 0 <= n_det <= n_valid:
        raise ValueError(f"need 0 <= n_det <= n_valid, got {n_det=}, {n_valid=}")
    # Beta(a, b), a = 1 + N_det, b = 1 + N_valid − N_det
    return stats.beta(1 + n_det, 1 + n_valid - n_det)


def prob_persistence_above(n_det: int, n_valid: int, p0: float) -> float:
    """Pr(P > p₀ | data), the persistence half of the alert rule."""
    return float(persistence_posterior(n_det, n_valid).sf(p0))


def overpasses_needed(p_hat: float, alpha: float) -> int:
    """Clear overpasses with no plume needed to accept a claimed repair.

    verified ⇔ (1 − P̂)^N′_valid ≤ α  ⇔  N′_valid ≥ log α / log(1 − P̂)
    """
    if not (0.0 < p_hat < 1.0 and 0.0 < alpha < 1.0):
        raise ValueError("p_hat and alpha must lie strictly between 0 and 1")
    # small tolerance so exact powers (e.g. 0.5**5 vs 0.03125) are not rounded up
    return math.ceil(math.log(alpha) / math.log(1.0 - p_hat) - 1e-12)
