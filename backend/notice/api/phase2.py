"""Revision agent and Claims agent routes."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import jobs
from ..agents.claims_agent.agent import ClaimError, create_claim
from ..agents.revision_agent.agent import RevisionError, candidate_pairs, raise_variation
from ..config import get_settings
from ..db import get_db
from ..models import Claim, Document, ReviewItem, RevisionComparison, User
from ..record import audit
from . import serializers as S
from .deps import current_user, owned, project_for

router = APIRouter(tags=["revisions", "claims"])


def comparison_out(db: Session, c: RevisionComparison, full: bool = True) -> dict:
    base, rev = db.get(Document, c.base_document_id), db.get(Document, c.revised_document_id)
    ri = db.execute(select(ReviewItem.id).where(ReviewItem.payload["comparison_id"].astext == str(c.id))).scalar()
    pv = sum(1 for ch in c.changes if (ch.get("assessment") or {}).get("potential_variation"))
    out = {"id": str(c.id), "method": c.method, "summary": c.summary, "flags": c.flags, "created_at": S.iso(c.created_at),
           "base": {"id": str(base.id), "filename": base.filename}, "revised": {"id": str(rev.id), "filename": rev.filename},
           "counts": {"changes": len(c.changes), "potential_variations": pv,
                      "raised": sum(1 for ch in c.changes if ch.get("raised"))},
           "review_item_id": str(ri) if ri else None}
    if full:
        out["changes"] = c.changes
    return out


def claim_out(c: Claim, full: bool = True) -> dict:
    out = {"id": str(c.id), "ref": c.ref, "title": c.title, "status": c.status, "event_ids": c.event_ids,
           "draft_id": str(c.draft_id) if c.draft_id else None, "created_at": S.iso(c.created_at),
           "time_bar_risk": any(r.get("time_bar_risk") for r in c.notice_compliance)}
    if full:
        out |= {"timeline": c.timeline, "notice_compliance": c.notice_compliance, "narrative": c.narrative, "gaps": c.gaps}
    return out


def _run_inline():
    if get_settings().jobs_inline:
        jobs.drain()


# --- revisions ----------------------------------------------------------

class CompareIn(BaseModel):
    base_document_id: uuid.UUID
    revised_document_id: uuid.UUID


class RaiseIn(BaseModel):
    force_new: bool = False
    trigger_date: date | None = None


@router.get("/projects/{project_id}/revisions")
def list_revisions(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    rows = db.execute(select(RevisionComparison).where(RevisionComparison.project_id == p.id)
                      .order_by(RevisionComparison.created_at.desc())).scalars()
    return [comparison_out(db, c, full=False) for c in rows]


@router.get("/projects/{project_id}/revisions/candidates")
def revision_candidates(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    done = {(c.base_document_id, c.revised_document_id) for c in
            db.execute(select(RevisionComparison).where(RevisionComparison.project_id == p.id)).scalars()}
    return [{"base": {"id": str(a.id), "filename": a.filename}, "revised": {"id": str(b.id), "filename": b.filename},
             "kind": b.kind, "compared": (a.id, b.id) in done} for a, b in candidate_pairs(db, p.id)]


@router.post("/projects/{project_id}/revisions")
def compare_revisions(project_id: uuid.UUID, body: CompareIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    for doc_id in (body.base_document_id, body.revised_document_id):
        d = db.get(Document, doc_id)
        if d is None or d.project_id != p.id:
            raise HTTPException(404, "Document not found in this project")
    if body.base_document_id == body.revised_document_id:
        raise HTTPException(422, "Choose two different documents")
    jobs.enqueue(db, "revision_agent.compare", {"base_id": body.base_document_id, "revised_id": body.revised_document_id,
                                                "user_id": user.id}, p.id)
    db.commit()
    _run_inline()
    return {"status": "queued"}


@router.get("/revisions/{comparison_id}")
def get_revision(comparison_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return comparison_out(db, owned(db.get(RevisionComparison, comparison_id), user, db))


@router.post("/revisions/{comparison_id}/changes/{change_id}/raise")
def raise_change(comparison_id: uuid.UUID, change_id: str, body: RaiseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned(db.get(RevisionComparison, comparison_id), user, db)
    try:
        result = raise_variation(db, comparison_id, change_id, user.id, force_new=body.force_new, trigger_date=body.trigger_date)
    except RevisionError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return result


# --- claims ---------------------------------------------------------------

class ClaimIn(BaseModel):
    event_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    title: str | None = None


@router.post("/projects/{project_id}/claims")
def start_claim(project_id: uuid.UUID, body: ClaimIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    try:
        claim = create_claim(db, p, body.event_ids, user.id, body.title)
    except ClaimError as e:
        raise HTTPException(422, str(e)) from e
    jobs.enqueue(db, "claims_agent.draft", {"claim_id": claim.id}, p.id)
    audit(db, action="claim.start", actor_type="user", actor_id=str(user.id), org_id=p.org_id, project_id=p.id,
          entity_type="claim", entity_id=claim.id, details={"events": claim.event_ids})
    db.commit()
    _run_inline()
    db.refresh(claim)
    return claim_out(claim)


@router.get("/projects/{project_id}/claims")
def list_claims(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    rows = db.execute(select(Claim).where(Claim.project_id == p.id).order_by(Claim.created_at.desc())).scalars()
    out = []
    for c in rows:
        ri = db.execute(select(ReviewItem.id).where(ReviewItem.payload["claim_id"].astext == str(c.id))).scalar()
        out.append(claim_out(c, full=False) | {"review_item_id": str(ri) if ri else None})
    return out


@router.get("/claims/{claim_id}")
def get_claim(claim_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return claim_out(owned(db.get(Claim, claim_id), user, db))
