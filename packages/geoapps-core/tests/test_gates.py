"""Closed-form gates from docs/design/01-design-plan.md, "Testing and validation gates"."""

import math

import numpy as np
import pydantic
import pytest

from geoapps_core import (
    CH4_PLUME,
    Status,
    Verdict,
    alert_mask,
    bearing_deg,
    candidate_probabilities,
    haversine_m,
    iou,
    label_carries_over,
    overpasses_needed,
    persistence_posterior,
    priority,
    prob_persistence_above,
    status_after,
)
from geoapps_core.attribution import candidate_weights


def test_e1_label_carry_over():
    """E1: identical masks carry; a 1-pixel shift of a 20 × 20 mask has IoU 380/420 and carries at τ = 0.5."""
    m = np.zeros((40, 40), bool)
    m[10:30, 10:30] = True
    shifted = np.roll(m, 1, axis=1)
    assert iou(m, m) == 1.0
    assert iou(m, shifted) == pytest.approx(380 / 420)
    assert label_carries_over(m, shifted, tau=0.5)
    assert not label_carries_over(m, np.zeros_like(m), tau=0.5)


def test_e4_verdicts_set_status():
    """E4: only a person's verdict moves a detection out of `predicted`."""
    assert status_after(Verdict.CONFIRM) is Status.VALIDATED
    assert status_after(Verdict.REDRAW) is Status.VALIDATED
    assert status_after(Verdict.REJECT) is Status.REJECTED


def test_e5_priority_window_decay():
    """E5: two detections equal except for ages τ and τ + λ have priority ratio e⁻¹."""
    tau, lam = 72.0, 48.0
    pri = priority(
        [0.8, 0.8], [1.0, 1.0], [500.0, 500.0], [1, 1], [tau, tau + lam], tau=tau, lam=lam
    )
    assert pri[1] / pri[0] == pytest.approx(math.exp(-1), abs=1e-6)


def test_e5_window_closing_alerts_none_missed():
    """E5: every queued item with n_d = 1 and τ − a_d ≤ δ raises an alert (0 missed of 1,000)."""
    rng = np.random.default_rng(0)
    n = 1000
    tau, lam, delta = 72.0, 48.0, 12.0
    p, v = rng.uniform(0, 1, n), rng.uniform(0, 1, n)
    q = rng.uniform(0, 2000, n)
    notify = rng.integers(0, 2, n)
    age = rng.uniform(0, 120, n)
    pri = priority(p, v, q, notify, age, tau=tau, lam=lam)
    alerts = alert_mask(
        pri, notify, age, pi0=10.0, tau=tau, delta=delta
    )  # π₀ high: only window alerts
    closing = (notify == 1) & (tau - age >= 0) & (tau - age <= delta)
    assert closing.sum() > 0
    assert np.all(alerts[closing])


def test_f1_scoring_oracle():
    """F1: with ℓ = 500 m and κ = 4, a downwind candidate gets w = 0; upwind at 500 m vs 1,000 m gives e^1.5."""
    wind_to = 90.0  # wind blows toward the east
    # bearing from source to origin = 90° means the source is upwind (west) of the plume
    w = candidate_weights(
        [500.0, 1000.0, 500.0], [90.0, 90.0, 270.0], wind_to, ell=500.0, kappa=4.0
    )
    assert w[2] == 0.0
    assert w[0] / w[1] == pytest.approx(math.exp(1.5), abs=1e-6)
    p = candidate_probabilities([500.0, 1000.0], [90.0, 90.0], wind_to, w0=0.0)
    assert p.sum() == pytest.approx(1.0)


def test_geodesy_helpers():
    assert haversine_m(0, 0, 0, 1) == pytest.approx(111_195, rel=1e-3)
    assert bearing_deg(0, 0, 1, 0) == pytest.approx(90.0)
    assert bearing_deg(0, 0, 0, 1) == pytest.approx(0.0)


def test_g3_verification_arithmetic():
    """G3: overpasses needed are 5 for (P̂ = 0.5, α = 0.05) and 14 for (P̂ = 0.2, α = 0.05)."""
    assert overpasses_needed(0.5, 0.05) == 5
    assert overpasses_needed(0.2, 0.05) == 14


def test_h5_gain_oracle():
    """H5: posterior sd of P is 0.1387 for (5, 10) and 0.1043 for (10, 20)."""
    assert persistence_posterior(5, 10).std() == pytest.approx(0.1387, abs=1e-4)
    assert persistence_posterior(10, 20).std() == pytest.approx(0.1043, abs=1e-4)


def test_stage4_persistence_rule():
    # 9 of 10 valid overpasses with a plume: P is very likely above 0.5
    assert prob_persistence_above(9, 10, 0.5) > 0.99
    assert prob_persistence_above(0, 10, 0.5) < 0.01
    with pytest.raises(ValueError):
        persistence_posterior(3, 2)


def test_l2_marks_validated():
    """L2: marks that fail their kind's schema are refused."""
    ok = CH4_PLUME.validate_marks({"q_kg_h": 850, "q_sigma_kg_h": 210, "p": 0.9})
    assert ok["viability"] == 1.0
    for bad in (
        {"q_kg_h": -1, "q_sigma_kg_h": 1, "p": 0.5},
        {"q_kg_h": 1, "q_sigma_kg_h": 1, "p": 1.5},
        {},
    ):
        with pytest.raises(pydantic.ValidationError):
            CH4_PLUME.validate_marks(bad)
