"""Runs, provenance (datasets, assertions, external ids), the ETL registry and jobs."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from geoapps_db.models import Alert, Assertion, Dataset, Detection, Etl, Job, Run, Source, Xref
from geoapps_db.repo._util import iso


# ── runs ────────────────────────────────────────────────────────────────────
def start_run(session: Session, etl: str, versions: dict[str, Any], stream: str = "nrt") -> Run:
    run = Run(etl=etl, versions=versions, stream=stream)
    session.add(run)
    session.flush()
    return run


# ── provenance ──────────────────────────────────────────────────────────────
def register_dataset(
    session: Session,
    *,
    name: str,
    sha256: str,
    url: str | None = None,
    licence: str = "unspecified",
    attribution: str | None = None,
    n_records: int | None = None,
    run_id: int | None = None,
) -> tuple[Dataset, bool]:
    """Record one fetched file; returns (dataset, created). The same bytes twice are one row."""
    existing = session.scalar(select(Dataset).where(Dataset.name == name, Dataset.sha256 == sha256))
    if existing is not None:
        return existing, False
    ds = Dataset(
        name=name,
        sha256=sha256,
        url=url,
        licence=licence,
        attribution=attribution,
        n_records=n_records,
        run_id=run_id,
    )
    session.add(ds)
    session.flush()
    return ds, True


def list_datasets(session: Session) -> list[dict[str, Any]]:
    """Every dataset with how many detections it contributed: the credits for the map."""
    n = (
        select(Detection.dataset_id, func.count().label("n"))
        .group_by(Detection.dataset_id)
        .subquery()
    )
    rows = session.execute(
        select(Dataset, func.coalesce(n.c.n, 0))
        .outerjoin(n, n.c.dataset_id == Dataset.id)
        .order_by(Dataset.fetched_at.desc())
    ).all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "url": d.url,
            "licence": d.licence,
            "attribution": d.attribution,
            "sha256": d.sha256,
            "n_records": d.n_records,
            "n_detections": int(k),
            "fetched_at": iso(d.fetched_at),
        }
        for d, k in rows
    ]


def add_assertion(
    session: Session,
    *,
    provider: str,
    claim: str,
    record_id: str | None = None,
    dataset_id: int | None = None,
    asserted_at: datetime | None = None,
    accepted: bool = True,
    payload: dict[str, Any] | None = None,
) -> Assertion:
    a = Assertion(
        provider=provider,
        claim=claim,
        record_id=record_id,
        dataset_id=dataset_id,
        asserted_at=asserted_at,
        accepted=accepted,
        payload=payload or {},
    )
    session.add(a)
    session.flush()
    return a


def xref_lookup(session: Session, provider: str, entity: str, record_id: str) -> int | None:
    return session.scalar(
        select(Xref.entity_id).where(
            Xref.provider == provider, Xref.entity == entity, Xref.record_id == record_id
        )
    )


def add_xref(
    session: Session,
    *,
    provider: str,
    entity: str,
    record_id: str,
    entity_id: int,
    match_score: float | None = None,
) -> None:
    session.execute(
        pg_insert(Xref)
        .values(
            provider=provider,
            entity=entity,
            record_id=record_id,
            entity_id=entity_id,
            match_score=match_score,
        )
        .on_conflict_do_nothing(index_elements=["provider", "entity", "record_id"])
    )


def xrefs_for(session: Session, entity: str, entity_id: int) -> list[dict[str, Any]]:
    return [
        {"provider": x.provider, "record_id": x.record_id, "match_score": x.match_score}
        for x in session.scalars(
            select(Xref).where(Xref.entity == entity, Xref.entity_id == entity_id)
        )
    ]


# ── registry and jobs (workstreams H and K) ─────────────────────────────────
def upsert_etl(
    session: Session,
    *,
    name: str,
    version: str,
    description: str,
    params_schema: dict[str, Any],
    writes: list[str],
) -> None:
    stmt = pg_insert(Etl).values(
        name=name,
        version=version,
        description=description,
        params_schema=params_schema,
        writes=writes,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Etl.name],
        set_={
            "version": stmt.excluded.version,
            "description": stmt.excluded.description,
            "params_schema": stmt.excluded.params_schema,
            "writes": stmt.excluded.writes,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)


def list_etls(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "name": e.name,
            "version": e.version,
            "description": e.description,
            "params_schema": e.params_schema,
            "writes": e.writes,
        }
        for e in session.scalars(select(Etl).order_by(Etl.name))
    ]


def get_etl(session: Session, name: str) -> Etl | None:
    return session.get(Etl, name)


def enqueue_job(
    session: Session,
    *,
    etl: str,
    params: dict[str, Any],
    submitted_by: str = "system",
    key: str | None = None,
) -> Job:
    """Queue a job; a repeated idempotency key returns the existing job instead of a duplicate (K1)."""
    if key is not None:
        existing = session.scalar(select(Job).where(Job.key == key))
        if existing is not None:
            return existing
    job = Job(etl=etl, params=params, submitted_by=submitted_by, key=key)
    session.add(job)
    session.flush()
    return job


def claim_job(session: Session) -> Job | None:
    """Take the oldest queued job; concurrent workers never claim the same one."""
    job = session.scalar(
        select(Job)
        .where(Job.state == "queued")
        .order_by(Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is not None:
        job.state = "running"
        job.started_at = datetime.now(UTC)
        session.flush()
    return job


def finish_job(
    session: Session,
    job_id: int,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    run_id: int | None = None,
) -> None:
    session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            state="failed" if error else "done",
            result=result,
            error=error,
            run_id=run_id,
            finished_at=datetime.now(UTC),
        )
    )


def get_job(session: Session, job_id: int) -> dict[str, Any] | None:
    j = session.get(Job, job_id)
    if j is None:
        return None
    return {
        "id": j.id,
        "etl": j.etl,
        "params": j.params,
        "state": j.state,
        "result": j.result,
        "error": j.error,
        "run_id": j.run_id,
        "submitted_by": j.submitted_by,
        "created_at": iso(j.created_at),
        "finished_at": iso(j.finished_at),
    }


def counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(Detection.status, func.count()).group_by(Detection.status)).all()
    out = {s: 0 for s in ("predicted", "validated", "rejected")}
    out.update({s: n for s, n in rows})
    out["sources"] = session.scalar(select(func.count(Source.id))) or 0
    out["alerts"] = session.scalar(select(func.count(Alert.id))) or 0
    out["queued_jobs"] = (
        session.scalar(select(func.count(Job.id)).where(Job.state == "queued")) or 0
    )
    return out


def xref_map(session: Session, provider: str, entity: str) -> dict[str, int]:
    """Every record id this provider has for one entity type, mapped to our ids."""
    return dict(
        session.execute(
            select(Xref.record_id, Xref.entity_id).where(
                Xref.provider == provider, Xref.entity == entity
            )
        ).all()
    )
