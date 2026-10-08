"""Event chaining, bounds and rates (data model §6)."""

import numpy as np
import pytest

from geoapps_core import CH4_PLUME, bounds, chain_by_gap, inverse_variance_mean, wind_to_deg


def test_gap_rule_splits_events():
    # days: 0, 5, 9 | 60, 62 | 200
    idx = chain_by_gap([0, 5, 9, 60, 62, 200], gap=30)
    assert idx.tolist() == [0, 0, 0, 1, 1, 2]


def test_clear_look_between_detections_closes_event():
    # a clear look on day 7 splits detections on days 5 and 9 even inside the gap
    assert chain_by_gap([0, 5, 9], gap=30, t_clear=[7]).tolist() == [0, 0, 1]
    # a clear look outside every interval changes nothing
    assert chain_by_gap([0, 5, 9], gap=30, t_clear=[-3, 12]).tolist() == [0, 0, 0]


def test_unsorted_times_refused():
    with pytest.raises(ValueError):
        chain_by_gap([5, 0], gap=30)


def test_bounds_from_clear_looks():
    assert bounds(10, 20, [2, 8, 25, 30]) == (8.0, 25.0)
    assert bounds(10, 20, None) == (None, None)  # detections-only: unknown, not zero
    assert bounds(10, 20, [15]) == (None, None)


def test_inverse_variance_mean_matches_framework_example():
    # framework page 6: 980 ± 310 and 1400 ± 600 combine to ≈ 1070 ± 275
    r = inverse_variance_mean([980, 1400], [310, 600])
    assert r.mean == pytest.approx(1069, abs=2)
    assert r.sigma == pytest.approx(275, abs=2)
    # σ missing on any detection: a plain mean, no false precision
    r = inverse_variance_mean([980, 1400], [310, np.nan])
    assert r.mean == pytest.approx(1190) and r.sigma is None


def test_wind_to_deg():
    # u east, v north; blowing toward
    assert wind_to_deg(0, 1) == pytest.approx(0)
    assert wind_to_deg(1, 0) == pytest.approx(90)
    assert wind_to_deg(0, -1) == pytest.approx(180)
    assert wind_to_deg(-1, 0) == pytest.approx(270)


def test_unquantified_plume_and_point_geometry_allowed():
    marks = CH4_PLUME.validate_marks({"p": 0.9})
    assert marks == {"p": 0.9, "viability": 1.0}
    assert CH4_PLUME.accepts_geometry("Point")
    assert CH4_PLUME.accepts_geometry("MultiPolygon")
    assert not CH4_PLUME.accepts_geometry("LineString")
