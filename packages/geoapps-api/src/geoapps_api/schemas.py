"""Request and response bodies. The OpenAPI schema generated from these is the
contract the TypeScript client is generated from (gate D1)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int | str | None = None
    geometry: dict[str, Any] | None
    properties: dict[str, Any] = Field(default_factory=dict)


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]


class VerdictIn(BaseModel):
    verdict: Literal["confirm", "redraw", "reject"]
    geometry: dict[str, Any] | None = Field(default=None, description="Required for a redraw")
    note: str | None = None


class VerdictOut(BaseModel):
    label_id: int
    status: Literal["predicted", "validated", "rejected"]
    alerts_raised: int


class WatchIn(BaseModel):
    name: str
    geometry: dict[str, Any] = Field(description="Polygon in EPSG:4326")
    kind: str | None = None
    min_q_kg_h: float | None = Field(default=None, ge=0)


class WatchOut(BaseModel):
    id: int


class AlertPatch(BaseModel):
    state: Literal["seen", "kept", "dismissed"]
    reason: str | None = Field(default=None, description='e.g. "not a plume", "wrong source"')


class AlertOut(BaseModel):
    id: int
    state: str
    reason: str | None
    created_at: str
    watch: dict[str, Any]
    detection: dict[str, Any]


class EtlOut(BaseModel):
    name: str
    version: str
    description: str
    params_schema: dict[str, Any]
    writes: list[str]


class JobIn(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class JobOut(BaseModel):
    id: int
    etl: str
    params: dict[str, Any]
    state: Literal["queued", "running", "done", "failed"]
    result: dict[str, Any] | None = None
    error: str | None = None
    run_id: int | None = None
    submitted_by: str
    created_at: str | None = None
    finished_at: str | None = None


class KindOut(BaseModel):
    name: str
    title: str
    geometry: str
    validation: str
    entities: list[str]
    marks_schema: dict[str, Any]


class CatalogSource(BaseModel):
    name: str
    kind: str
    url: str
    collections: list[str]
    mirror: str
    licence: str
    description: str


class ClientConfig(BaseModel):
    name: str
    titiler_url: str
    auth_enabled: bool
    sources: list[CatalogSource]


class Stats(BaseModel):
    predicted: int
    validated: int
    rejected: int
    sources: int
    alerts: int
    queued_jobs: int


class DatasetOut(BaseModel):
    id: int
    name: str
    url: str | None
    licence: str
    attribution: str | None
    sha256: str
    n_records: int | None
    n_detections: int
    fetched_at: str | None


class SensorOut(BaseModel):
    id: int
    name: str
    platform: str | None
    agency: str | None
    sensor_type: str | None
    n_detections: int


class EventOut(BaseModel):
    id: int
    status: Literal["open", "closed"]
    t_a: str | None = Field(description="Last clear look before the event, if observed")
    t_b: str = Field(description="First detection")
    t_c: str = Field(description="Last detection")
    t_d: str | None = Field(description="First clear look after the event, if observed")
    n_detections: int
    q_mean_kg_h: float | None
    q_sigma_kg_h: float | None
    source_id: int | None = None
    kind: str | None = None


class SourceDetection(BaseModel):
    id: int
    status: str
    observed_at: str
    q_kg_h: float | None
    q_sigma_kg_h: float | None
    sensor_id: int | None
    event_id: int | None


class Xref(BaseModel):
    provider: str
    record_id: str
    match_score: float | None


class AttributionLink(BaseModel):
    id: int
    facility_id: int
    facility: str
    score: float | None
    method: str
    status: str
    valid_from: str | None
    valid_to: str | None
    decided_by: str | None


class Who(BaseModel):
    at: str
    facility: dict[str, Any]
    asset: dict[str, Any] | None
    operator: dict[str, Any] | None
    owners: list[dict[str, Any]]
    governments: list[dict[str, Any]]


class SourceDetail(BaseModel):
    id: int
    geometry: dict[str, Any]
    name: str
    source_type: str
    sector: str | None
    country: str | None
    status: str
    first_seen: str | None
    last_seen: str | None
    attrs: dict[str, Any]
    xrefs: list[Xref]
    detections: list[SourceDetection]
    events: list[EventOut]
    attributions: list[AttributionLink]
    who: Who | None


class Proposal(BaseModel):
    id: int
    facility_id: int
    score: float
    distance_m: float


class DecisionIn(BaseModel):
    confirm: bool
    valid_from: datetime | None = Field(
        default=None, description="When the link starts; open-ended"
    )


class FeedbackOut(BaseModel):
    id: int
    author: str
    about: str
    about_id: int
    kind: str
    body: str | None
    action: str | None
    created_at: str | None
