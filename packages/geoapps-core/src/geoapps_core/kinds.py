"""Event kinds (workstream L).

The core stores detections, events and labels without knowing what they
measure. Each phenomenon plugs in as an ``EventKind``: its marks schema, how
detections join into events, which entities it may be attributed to, and its
publication policy. Core tables and apps never branch on a kind's name.

Science (retrieval, detection, quantification) lives in the kind's registered
steps in geoapps-workers, not here.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Geometry = Literal["Point", "Polygon"]
Linker = Literal["same_source", "overlap", "overlap_drift", "contiguous", "tracker"]
Validation = Literal["per_snapshot", "per_event", "trusted_source"]


class PlumeMarks(BaseModel):
    """What one trace-gas plume detection measures.

    A plume can be detected before it is quantified, so the flux is optional;
    an unquantified plume ranks as if Q̂ = Q_ref in the queue.
    """

    q_kg_h: float | None = Field(default=None, ge=0, description="Flux estimate Q̂, kg h⁻¹")
    q_sigma_kg_h: float | None = Field(
        default=None, ge=0, description="Flux uncertainty σ_Q, kg h⁻¹"
    )
    p: float = Field(ge=0, le=1, description="Calibrated probability the plume is real")
    viability: float = Field(default=1.0, ge=0, le=1, description="Scene viability v_d")
    wind_u_m_s: float | None = Field(default=None, description="Eastward wind u₁₀, m s⁻¹")
    wind_v_m_s: float | None = Field(default=None, description="Northward wind v₁₀, m s⁻¹")
    wind_speed_m_s: float | None = Field(default=None, ge=0, description="Wind speed |u₁₀|, m s⁻¹")
    total_emission_t: float | None = Field(
        default=None, ge=0, description="Total mass of a transient event, t"
    )
    total_emission_sigma_t: float | None = Field(
        default=None, ge=0, description="Its uncertainty, t"
    )


@dataclass(frozen=True)
class PublishPolicy:
    allowed: bool = False  # exports are off unless the instance enables them
    delay_hours: float = 0.0  # embargo before a validated event may be exported
    grid_deg: float | None = None  # coarsen exported coordinates to this grid, if set


@dataclass(frozen=True)
class EventKind:
    name: str  # "ch4_plume", "oil_spill", ...
    title: str
    geometry: Geometry  # one snapshot's geometry
    marks: type[BaseModel]  # validated before a detection is stored (gate L2)
    link: Linker  # detections → events
    entities: tuple[str, ...]  # node types it may be attributed to
    validation: Validation = "per_snapshot"
    publish: PublishPolicy = field(default_factory=PublishPolicy)

    def validate_marks(self, marks: dict) -> dict:
        """Raise pydantic.ValidationError if the marks do not fit this kind; drop unset fields."""
        return self.marks.model_validate(marks).model_dump(exclude_none=True)

    def accepts_geometry(self, geometry_type: str) -> bool:
        """A snapshot is stored as the kind's outline, or as a point when only its location is known."""
        allowed = (
            {"Point", "MultiPoint"} if self.geometry == "Point" else {"Polygon", "MultiPolygon"}
        )
        return geometry_type in allowed | {"Point"}


_REGISTRY: dict[str, EventKind] = {}


def register_kind(kind: EventKind) -> EventKind:
    if kind.name in _REGISTRY and _REGISTRY[kind.name] is not kind:
        raise ValueError(f"event kind {kind.name!r} is already registered")
    _REGISTRY[kind.name] = kind
    return kind


def get_kind(name: str) -> EventKind:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown event kind {name!r}; known: {sorted(_REGISTRY)}") from None


def kinds() -> list[EventKind]:
    return list(_REGISTRY.values())


CH4_PLUME = register_kind(
    EventKind(
        name="ch4_plume",
        title="Methane plume",
        geometry="Polygon",
        marks=PlumeMarks,
        link="same_source",
        entities=("source", "facility", "asset", "operator", "government"),
    )
)
