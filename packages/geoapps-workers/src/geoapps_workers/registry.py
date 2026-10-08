"""The step registry (workstream H1).

An ETL is a function with a Pydantic parameter model. ``@etl`` records its
name, version and what it writes; the registry is mirrored into ``core.etl``
so the API can list steps and the shell can render a form from each JSON
schema. Nothing unregistered can run.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from geoapps_db import repo


@dataclass
class StepContext:
    """What a running step may touch: its session (one transaction) and its run."""

    session: Session
    run_id: int
    submitted_by: str = "system"
    log: list[str] = field(default_factory=list)

    def info(self, msg: str) -> None:
        self.log.append(msg)


@dataclass(frozen=True)
class Step:
    name: str
    version: str
    params: type[BaseModel]
    writes: tuple[str, ...]
    fn: Callable[[BaseModel, StepContext], dict[str, Any]]
    description: str = ""

    def run(self, raw_params: dict[str, Any], ctx: StepContext) -> dict[str, Any]:
        params = self.params.model_validate(raw_params)
        return self.fn(params, ctx)


REGISTRY: dict[str, Step] = {}


def etl(
    *, name: str, params: type[BaseModel], writes: tuple[str, ...] = (), version: str = "0.0.1"
):
    """Register a step: ``@etl(name="seed_demo", params=SeedParams, writes=("review.detection",))``."""

    def wrap(fn: Callable[[Any, StepContext], dict[str, Any]]):
        if name in REGISTRY:
            raise ValueError(f"step {name!r} registered twice")
        REGISTRY[name] = Step(
            name=name,
            version=version,
            params=params,
            writes=tuple(writes),
            fn=fn,
            description=(fn.__doc__ or "").strip().split("\n")[0],
        )
        return fn

    return wrap


def sync_registry(session: Session) -> int:
    """Mirror registered steps into core.etl so the API and shell can list them."""
    for step in REGISTRY.values():
        repo.upsert_etl(
            session,
            name=step.name,
            version=step.version,
            description=step.description,
            params_schema=step.params.model_json_schema(),
            writes=list(step.writes),
        )
    return len(REGISTRY)
