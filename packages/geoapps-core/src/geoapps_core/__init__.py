"""Kind-agnostic domain rules shared by every geoapps service.

Nothing here touches a database, a network or GeoStack. Each function maps
directly onto a rule or gate in docs/design/01-design-plan.md.
"""

from geoapps_core.attribution import (
    bearing_deg,
    candidate_probabilities,
    haversine_m,
    wind_to_deg,
)
from geoapps_core.events import RateEstimate, bounds, chain_by_gap, inverse_variance_mean
from geoapps_core.kinds import CH4_PLUME, EventKind, PlumeMarks, get_kind, kinds, register_kind
from geoapps_core.masks import iou, label_carries_over
from geoapps_core.persistence import (
    overpasses_needed,
    persistence_posterior,
    prob_persistence_above,
)
from geoapps_core.priority import alert_mask, priority
from geoapps_core.status import Status, Verdict, status_after

__all__ = [
    "CH4_PLUME",
    "EventKind",
    "PlumeMarks",
    "RateEstimate",
    "Status",
    "Verdict",
    "alert_mask",
    "bearing_deg",
    "bounds",
    "candidate_probabilities",
    "chain_by_gap",
    "get_kind",
    "haversine_m",
    "inverse_variance_mean",
    "iou",
    "kinds",
    "label_carries_over",
    "overpasses_needed",
    "persistence_posterior",
    "priority",
    "prob_persistence_above",
    "register_kind",
    "status_after",
    "wind_to_deg",
]
