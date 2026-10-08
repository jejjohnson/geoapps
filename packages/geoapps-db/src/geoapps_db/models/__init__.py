"""geoapps tables, one module per Postgres schema (docs/design/03-data-model.md).

core         runs, ETLs, jobs, datasets, assertions
ref          sensors, sources, facilities, external ids
review       detections, labels, label sets               (app 1)
attribution  source → facility links, assets, orgs, roles  (app 2)
monitor      locations, observations, events               (apps 3, 4)
notify       watches, alerts, outbox, feedback             (app 3)
"""

from geoapps_db.models.attribution import (
    ROLES,
    Asset,
    FacilityAsset,
    FacilityGovernment,
    Org,
    OrgAsset,
    OrgRelation,
    SourceFacility,
)
from geoapps_db.models.base import NAMING, SCHEMAS, Base
from geoapps_db.models.core import JOB_STATES, Assertion, Dataset, Etl, Job, Run
from geoapps_db.models.monitor import Event, Location, LocationStatus, Observation
from geoapps_db.models.notify import ALERT_STATES, Alert, Feedback, Outbox, Watch
from geoapps_db.models.ref import Facility, Sensor, Source, Xref
from geoapps_db.models.review import (
    RELATIONS,
    STATUSES,
    VERDICTS,
    Detection,
    DetectionRelation,
    Label,
    LabelSet,
    LabelSetMember,
)

__all__ = [
    "ALERT_STATES",
    "JOB_STATES",
    "NAMING",
    "RELATIONS",
    "ROLES",
    "SCHEMAS",
    "STATUSES",
    "VERDICTS",
    "Alert",
    "Assertion",
    "Asset",
    "Base",
    "Dataset",
    "Detection",
    "DetectionRelation",
    "Etl",
    "Event",
    "Facility",
    "FacilityAsset",
    "FacilityGovernment",
    "Feedback",
    "Job",
    "Label",
    "LabelSet",
    "LabelSetMember",
    "Location",
    "LocationStatus",
    "Observation",
    "Org",
    "OrgAsset",
    "OrgRelation",
    "Outbox",
    "Run",
    "Sensor",
    "Source",
    "SourceFacility",
    "Watch",
    "Xref",
]
