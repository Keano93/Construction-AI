"""Project record: append-only project log + hash-chained audit log."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import AuditLog, ProjectLog


def _jsonable(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str))


def log_project_event(
    db: Session,
    project_id: uuid.UUID,
    type: str,
    *,
    actor: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    payload: dict | None = None,
) -> ProjectLog:
    row = ProjectLog(
        project_id=project_id,
        type=type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=_jsonable(payload or {}),
        actor=actor,
    )
    db.add(row)
    return row


def audit(
    db: Session,
    *,
    action: str,
    actor_type: str,
    actor_id: str,
    org_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: Any = None,
    source_refs: list | None = None,
    details: dict | None = None,
) -> AuditLog:
    """Append an audit entry whose hash chains to the previous entry.

    A transaction-level advisory lock serialises writers so the chain has no forks.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(424242)"))
    db.flush()
    prev = db.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar()
    created_at = datetime.now(timezone.utc)
    body = {
        "action": action,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "org_id": str(org_id) if org_id else None,
        "project_id": str(project_id) if project_id else None,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "source_refs": _jsonable(source_refs or []),
        "details": _jsonable(details or {}),
        "created_at": created_at.isoformat(),
        "prev_hash": prev,
    }
    h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    row = AuditLog(
        org_id=org_id,
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=body["entity_id"],
        source_refs=body["source_refs"],
        details=body["details"],
        prev_hash=prev,
        hash=h,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def verify_audit_chain(db: Session) -> tuple[bool, int | None]:
    """Recompute every hash. Returns (ok, first_bad_id)."""
    prev = None
    for row in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars():
        body = {
            "action": row.action,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "org_id": str(row.org_id) if row.org_id else None,
            "project_id": str(row.project_id) if row.project_id else None,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "source_refs": row.source_refs,
            "details": row.details,
            "created_at": row.created_at.astimezone(timezone.utc).isoformat(),
            "prev_hash": prev,
        }
        if row.prev_hash != prev or hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != row.hash:
            return False, row.id
        prev = row.hash
    return True, None
