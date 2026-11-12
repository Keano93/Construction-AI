import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.base import project_calendar
from ..db import get_db
from ..deadlines import working_days_remaining
from ..export.drafts import to_docx, to_pdf
from ..models import Claim, Deadline, Draft, Event, Item, Project, ReviewAction, ReviewItem, RevisionComparison, User
from ..record import audit
from ..review import service
from . import serializers as S
from .deps import current_user, owned, project_for

router = APIRouter(tags=["review"])


@router.get("/projects/{project_id}/review")
def list_review(project_id: uuid.UUID, status: str | None = "pending", category: str | None = None, agent: str | None = None,
                low_confidence: bool | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    q = select(ReviewItem).where(ReviewItem.project_id == p.id)
    if status and status != "all":
        q = q.where(ReviewItem.status == status)
    if category:
        q = q.where(ReviewItem.category == category)
    if agent:
        q = q.where(ReviewItem.agent == agent)
    if low_confidence is not None:
        q = q.where(ReviewItem.low_confidence.is_(low_confidence))
    q = q.order_by(ReviewItem.priority_date.asc().nullslast(), ReviewItem.created_at.desc())
    cal, today = project_calendar(p), date.today()
    return [_with_remaining(S.review_item(r), r, cal, today) for r in db.execute(q).scalars()]


def _with_remaining(out: dict, r: ReviewItem, cal, today: date) -> dict:
    """Working days left to the earliest notice deadline (computed by the deadline engine, negative when overdue)."""
    out["working_days_remaining"] = working_days_remaining(r.priority_date, today, cal) if r.priority_date else None
    return out


@router.get("/review/{review_id}")
def get_review(review_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = owned(db.get(ReviewItem, review_id), user, db)
    out = _with_remaining(S.review_item(r), r, project_calendar(db.get(Project, r.project_id)), date.today())
    if r.draft_id:
        out["draft"] = S.draft(db.get(Draft, r.draft_id))
    if r.event_id:
        e = db.get(Event, r.event_id)
        out["event"] = S.event(e)
        out["deadlines"] = [S.deadline(d) for d in db.execute(select(Deadline).where(Deadline.event_id == e.id)).scalars()]
        out["related_items"] = [S.item(i) for i in db.execute(select(Item).where(Item.id.in_([uuid.UUID(x) for x in e.related_item_ids]))).scalars()]
    if r.source_item_id:
        out["source_item"] = S.item(db.get(Item, r.source_item_id))
    if r.kind == "revision_comparison" and r.payload.get("comparison_id"):
        from .phase2 import comparison_out

        out["comparison"] = comparison_out(db, db.get(RevisionComparison, uuid.UUID(r.payload["comparison_id"])))
    if r.kind == "claim_draft" and r.payload.get("claim_id"):
        from .phase2 import claim_out

        out["claim"] = claim_out(db.get(Claim, uuid.UUID(r.payload["claim_id"])))
    out["actions"] = [{"action": a.action, "user_id": str(a.user_id), "comment": a.comment, "created_at": S.iso(a.created_at)}
                      for a in db.execute(select(ReviewAction).where(ReviewAction.review_item_id == r.id).order_by(ReviewAction.created_at)).scalars()]
    return out


class EditIn(BaseModel):
    subject: str | None = None
    body: str | None = None
    recipient: str | None = None
    trigger_date: date | None = None
    category: str | None = None
    comment: str | None = None


class DecisionIn(BaseModel):
    comment: str | None = None


class IssuedIn(BaseModel):
    issued_on: date
    comment: str | None = None


def _act(fn, review_id, user, db, **kw):
    r = owned(db.get(ReviewItem, review_id), user, db)
    try:
        fn(db, r, user.id, **kw)
    except service.ReviewError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return get_review(review_id, user, db)


@router.post("/review/{review_id}/edit")
def edit_review(review_id: uuid.UUID, body: EditIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.category and body.category not in ("change", "delay", "instruction", "disruption", "noise"):
        raise HTTPException(422, "Invalid category")
    return _act(service.edit, review_id, user, db, **body.model_dump())


@router.post("/review/{review_id}/approve")
def approve_review(review_id: uuid.UUID, body: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _act(service.approve, review_id, user, db, comment=body.comment)


@router.post("/review/{review_id}/dismiss")
def dismiss_review(review_id: uuid.UUID, body: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _act(service.dismiss, review_id, user, db, comment=body.comment)


@router.post("/review/{review_id}/reopen")
def reopen_review(review_id: uuid.UUID, body: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _act(service.reopen, review_id, user, db, comment=body.comment)


@router.post("/review/{review_id}/mark-issued")
def mark_issued(review_id: uuid.UUID, body: IssuedIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _act(service.mark_issued, review_id, user, db, issued_on=body.issued_on, comment=body.comment)


@router.get("/drafts/{draft_id}/export")
def export_draft(draft_id: uuid.UUID, format: str = "docx", user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = owned(db.get(Draft, draft_id), user, db)
    if d.status != "approved":
        raise HTTPException(409, "Only approved drafts can be exported")
    project = db.get(Project, d.project_id)
    if format == "docx":
        data, mime = to_docx(d, project), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif format == "pdf":
        data, mime = to_pdf(d, project), "application/pdf"
    else:
        raise HTTPException(422, "format must be docx or pdf")
    audit(db, action="draft.export", actor_type="user", actor_id=str(user.id), org_id=project.org_id, project_id=project.id,
          entity_type="draft", entity_id=d.id, details={"format": format, "version": d.version})
    db.commit()
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in d.subject)[:80].strip()
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{safe}.{format}"'})
