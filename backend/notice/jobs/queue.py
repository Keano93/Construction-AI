"""Postgres-backed job queue (no Redis needed).

Workers claim jobs with SELECT ... FOR UPDATE SKIP LOCKED, so several workers
can run safely. With NOTICE_JOBS_INLINE=true (tests, seed) jobs run
synchronously in the caller's process after commit via `drain()`.
"""

from __future__ import annotations

import logging
import traceback
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import Job

log = logging.getLogger(__name__)
Handler = Callable[[Session, dict], None]
_HANDLERS: dict[str, Handler] = {}
MAX_ATTEMPTS = 3


def job_handler(type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[type] = fn
        return fn

    return deco


def enqueue(db: Session, type: str, payload: dict, project_id: uuid.UUID | None = None) -> Job:
    job = Job(type=type, payload={k: str(v) if isinstance(v, uuid.UUID) else v for k, v in payload.items()}, project_id=project_id)
    db.add(job)
    return job


def _claim(db: Session) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.status == "queued", Job.run_after <= datetime.now(timezone.utc))
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.execute(stmt).scalar_one_or_none()
    if job:
        job.status = "running"
        job.attempts += 1
    return job


def run_one() -> bool:
    """Claim and run one job. Returns False if the queue is empty."""
    from . import handlers  # noqa: F401  (registers handlers)

    with session_scope() as db:
        job = _claim(db)
        if job is None:
            return False
        job_id, job_type, payload = job.id, job.type, dict(job.payload)

    try:
        with session_scope() as db:
            handler = _HANDLERS.get(job_type)
            if handler is None:
                raise RuntimeError(f"No handler for job type {job_type}")
            handler(db, payload)
        with session_scope() as db:
            j = db.get(Job, job_id)
            j.status, j.finished_at = "done", datetime.now(timezone.utc)
    except Exception as e:  # noqa: BLE001 - record any failure on the job
        log.exception("job %s (%s) failed", job_id, job_type)
        with session_scope() as db:
            j = db.get(Job, job_id)
            j.error = f"{e}\n{traceback.format_exc()[-2000:]}"
            if j.attempts >= MAX_ATTEMPTS:
                j.status = "failed"
            else:
                j.status = "queued"
                j.run_after = datetime.now(timezone.utc) + timedelta(seconds=10 * 2 ** j.attempts)
    return True


def drain(max_jobs: int = 10_000) -> int:
    """Run queued jobs until the queue is empty (used inline / in seed / tests)."""
    n = 0
    while n < max_jobs and run_one():
        n += 1
    return n
