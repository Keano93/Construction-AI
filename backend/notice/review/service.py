"""Review queue: edit / approve / dismiss / reopen / mark issued. Every action is logged with before/after."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.base import project_calendar
from ..deadlines import DeadlineRule, compute_deadline
from ..models import ContractRule, Deadline, Draft, Event, Project, ReviewAction, ReviewItem
from ..record import audit, log_project_event


class ReviewError(ValueError):
    pass


def _snapshot(db: Session, ri: ReviewItem) -> dict:
    snap: dict = {"status": ri.status, "category": ri.category, "title": ri.title}
    if ri.draft_id:
        d = db.get(Draft, ri.draft_id)
        snap["draft"] = {"subject": d.subject, "recipient": d.recipient, "body": d.body, "version": d.version, "status": d.status}
    if ri.event_id:
        e = db.get(Event, ri.event_id)
        snap["event"] = {"trigger_date": e.trigger_date.isoformat(), "category": e.category, "status": e.status}
    return snap


def _record(db: Session, ri: ReviewItem, user_id: uuid.UUID, action: str, before: dict, comment: str | None = None) -> None:
    after = _snapshot(db, ri)
    db.add(ReviewAction(review_item_id=ri.id, project_id=ri.project_id, user_id=user_id, action=action,
                        before=before, after=after, comment=comment))
    project = db.get(Project, ri.project_id)
    refs = [{k: c.get(k) for k in ("document_id", "item_id", "clause_ref", "char_start", "char_end")} for c in ri.citations]
    audit(db, action=f"review.{action}", actor_type="user", actor_id=str(user_id), org_id=project.org_id,
          project_id=project.id, entity_type="review_item", entity_id=ri.id, source_refs=refs,
          details={"comment": comment, "agent": ri.agent, "kind": ri.kind})
    log_project_event(db, project.id, f"review.{action}", actor=f"user:{user_id}", entity_type="review_item",
                      entity_id=ri.id, payload={"title": ri.title})


def _recompute_deadlines(db: Session, event: Event) -> list[dict]:
    project = db.get(Project, event.project_id)
    cal = project_calendar(project)
    out = []
    for d in db.execute(select(Deadline).where(Deadline.event_id == event.id, Deadline.status == "running")).scalars():
        rule = db.get(ContractRule, d.rule_id)
        res = compute_deadline(event.trigger_date, DeadlineRule(rule.period_value, rule.period_unit), cal)
        d.trigger_date, d.due_date, d.trace = event.trigger_date, res.due_date, res.to_trace()
        out.append({"id": str(d.id), "label": d.label, "due_date": str(d.due_date), "trace": d.trace})
    return out


def edit(db: Session, ri: ReviewItem, user_id: uuid.UUID, *, subject: str | None = None, body: str | None = None,
         recipient: str | None = None, trigger_date: date | None = None, category: str | None = None,
         comment: str | None = None) -> ReviewItem:
    if ri.status != "pending":
        raise ReviewError("Only pending items can be edited; reopen it first")
    before = _snapshot(db, ri)
    if ri.draft_id and any(x is not None for x in (subject, body, recipient)):
        d = db.get(Draft, ri.draft_id)
        if subject is not None:
            d.subject = subject
        if body is not None:
            d.body = body
        if recipient is not None:
            d.recipient = recipient
        d.version += 1
    if ri.event_id and (trigger_date is not None or category is not None):
        e = db.get(Event, ri.event_id)
        if category is not None:
            e.category = ri.category = category
        if trigger_date is not None and trigger_date != e.trigger_date:
            e.trigger_date = trigger_date
            deadlines = _recompute_deadlines(db, e)
            ri.payload = {**ri.payload, "trigger_date": trigger_date.isoformat(), "deadlines": deadlines}
            ri.priority_date = min((date.fromisoformat(x["due_date"]) for x in deadlines), default=None)
    db.flush()
    _record(db, ri, user_id, "edit", before, comment)
    return ri


def approve(db: Session, ri: ReviewItem, user_id: uuid.UUID, comment: str | None = None) -> ReviewItem:
    if ri.status != "pending":
        raise ReviewError(f"Item is already {ri.status}")
    before = _snapshot(db, ri)
    now = datetime.now(timezone.utc)
    ri.status, ri.decided_by, ri.decided_at = "approved", user_id, now
    if ri.draft_id:
        d = db.get(Draft, ri.draft_id)
        d.status, d.approved_by, d.approved_at = "approved", user_id, now
    db.flush()
    _record(db, ri, user_id, "approve", before, comment)
    return ri


def dismiss(db: Session, ri: ReviewItem, user_id: uuid.UUID, comment: str | None = None) -> ReviewItem:
    if ri.status != "pending":
        raise ReviewError(f"Item is already {ri.status}")
    before = _snapshot(db, ri)
    ri.status, ri.decided_by, ri.decided_at = "dismissed", user_id, datetime.now(timezone.utc)
    if ri.draft_id:
        db.get(Draft, ri.draft_id).status = "dismissed"
    if ri.event_id:
        db.get(Event, ri.event_id).status = "dismissed"
        for d in db.execute(select(Deadline).where(Deadline.event_id == ri.event_id)).scalars():
            d.status = "cancelled"
    db.flush()
    _record(db, ri, user_id, "dismiss", before, comment)
    return ri


def reopen(db: Session, ri: ReviewItem, user_id: uuid.UUID, comment: str | None = None) -> ReviewItem:
    if ri.status == "pending":
        raise ReviewError("Item is already pending")
    before = _snapshot(db, ri)
    ri.status, ri.decided_by, ri.decided_at = "pending", None, None
    if ri.draft_id:
        d = db.get(Draft, ri.draft_id)
        d.status, d.approved_by, d.approved_at = "draft", None, None
    if ri.event_id:
        e = db.get(Event, ri.event_id)
        if e.status == "dismissed":
            e.status = "open"
            for d in db.execute(select(Deadline).where(Deadline.event_id == e.id, Deadline.status == "cancelled")).scalars():
                d.status = "running"
    db.flush()
    _record(db, ri, user_id, "reopen", before, comment)
    return ri


def mark_issued(db: Session, ri: ReviewItem, user_id: uuid.UUID, issued_on: date, comment: str | None = None) -> ReviewItem:
    """The user confirms they sent the approved notice themselves (Notice never sends anything)."""
    if ri.status != "approved" or not ri.draft_id:
        raise ReviewError("Only approved drafts can be marked as issued")
    before = _snapshot(db, ri)
    if ri.event_id:
        e = db.get(Event, ri.event_id)
        e.status = "notified"
        draft = db.get(Draft, ri.draft_id)
        for d in db.execute(select(Deadline).where(Deadline.event_id == e.id, Deadline.rule_id == draft.rule_id)).scalars():
            d.status, d.met_at = "met", datetime.combine(issued_on, datetime.min.time(), tzinfo=timezone.utc)
    ri.payload = {**ri.payload, "issued_on": issued_on.isoformat()}
    db.flush()
    _record(db, ri, user_id, "mark_issued", before, comment)
    return ri
