"""Request and response bodies. The OpenAPI schema generated from these is the
contract the TypeScript client is generated from (gate D1)."""

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
    alerts: int
    queued_jobs: int
