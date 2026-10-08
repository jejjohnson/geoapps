"""geoapps-db: the only package allowed to write to the geoapps database.

Ownership rule 3 (docs/design/01-design-plan.md): it owns the ORM models,
Alembic migrations and query functions, and never imports FastAPI or JAX.
"""

from geoapps_db.models import (
    Alert,
    Base,
    Detection,
    Etl,
    Job,
    Label,
    Outbox,
    Run,
    Source,
    Watch,
)
from geoapps_db.session import get_engine, session_scope

__all__ = [
    "Alert",
    "Base",
    "Detection",
    "Etl",
    "Job",
    "Label",
    "Outbox",
    "Run",
    "Source",
    "Watch",
    "get_engine",
    "session_scope",
]
