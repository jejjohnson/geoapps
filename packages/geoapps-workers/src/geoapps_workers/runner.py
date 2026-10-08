"""The job runner (workstream K, executor ``local``).

A worker loop claims one queued job at a time with ``FOR UPDATE SKIP LOCKED``,
runs the registered step inside one transaction, and records the result. A
failed step rolls back everything it wrote and marks the job failed.
"""

import logging
import time
import traceback

from geoapps_db import repo, session_scope
from geoapps_workers import steps  # noqa: F401  (registers every step)
from geoapps_workers.registry import REGISTRY, StepContext, sync_registry

log = logging.getLogger("geoapps.worker")


def run_once() -> int | None:
    """Claim and run one job; returns its id, or None when the queue is empty."""
    with session_scope() as session:
        job = repo.claim_job(session)
        if job is None:
            return None
        job_id, etl_name, params, submitted_by = job.id, job.etl, dict(job.params), job.submitted_by

    step = REGISTRY.get(etl_name)
    if step is None:
        with session_scope() as session:
            repo.finish_job(
                session, job_id, error=f"step {etl_name!r} is not registered on this worker"
            )
        return job_id

    try:
        with session_scope() as session:
            run = repo.start_run(session, etl=step.name, versions={step.name: step.version})
            ctx = StepContext(session=session, run_id=run.id, submitted_by=submitted_by)
            result = step.run(params, ctx)
            result = {**result, "log": ctx.log}
            repo.finish_job(session, job_id, result=result, run_id=run.id)
        log.info("job %s (%s) done", job_id, etl_name)
    except Exception as exc:
        log.warning("job %s (%s) failed: %s", job_id, etl_name, exc)
        with session_scope() as session:
            repo.finish_job(
                session, job_id, error="".join(traceback.format_exception_only(exc)).strip()
            )
    return job_id


def run_forever(poll_seconds: float = 2.0) -> None:
    with session_scope() as session:
        n = sync_registry(session)
    log.info("registered %d steps: %s", n, ", ".join(sorted(REGISTRY)))
    while True:
        if run_once() is None:
            time.sleep(poll_seconds)
