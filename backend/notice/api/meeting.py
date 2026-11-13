"""Weekly commercial meeting: pack, estimates, decisions and actions."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..meeting import export
from ..meeting.service import build_pack
from ..models import Claim, Event, MeetingItem, Project, User
from ..record import audit, log_project_event
from .deps import current_user, owned, project_for

router = APIRouter(tags=["meeting"])


@router.get("/projects/{project_id}/meeting")
def meeting_pack(project_id: uuid.UUID, date_: date | None = Query(None, alias="date"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    return build_pack(db, p, date_ or date.today())


@router.get("/projects/{project_id}/meeting/export")
def meeting_export(project_id: uuid.UUID, format: str = "pdf", date_: date | None = Query(None, alias="date"),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    pack = build_pack(db, p, date_ or date.today())
    if format == "pdf":
        data, mime = export.to_pdf(pack), "application/pdf"
    elif format == "docx":
        data, mime = export.to_docx(pack), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise HTTPException(422, "format must be pdf or docx")
    audit(db, action="meeting.export", actor_type="user", actor_id=str(user.id), org_id=p.org_id, project_id=p.id,
          entity_type="project", entity_id=p.id, details={"format": format, "meeting_date": pack["meeting_date"]})
    db.commit()
    name = f"Commercial meeting {p.name} {pack['meeting_date']}.{format}"
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- estimates --------------------------------------------------------------

class EstimateIn(BaseModel):
    estimated_value: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    value_note: str | None = Field(default=None, max_length=500)


def _set_estimate(db: Session, user: User, project: Project, entity, kind: str, body: EstimateIn) -> dict:
    before = {"estimated_value": str(entity.estimated_value) if entity.estimated_value is not None else None}
    entity.estimated_value = body.estimated_value
    if kind == "event":
        before["value_note"] = entity.value_note
        entity.value_note = body.value_note
    audit(db, action=f"{kind}.estimate", actor_type="user", actor_id=str(user.id), org_id=project.org_id, project_id=project.id,
          entity_type=kind, entity_id=entity.id, details={"before": before, "after": body.model_dump(mode="json")})
    db.commit()
    return {"id": str(entity.id), "estimated_value": float(entity.estimated_value) if entity.estimated_value is not None else None}


@router.patch("/events/{event_id}/estimate")
def estimate_event(event_id: uuid.UUID, body: EstimateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = owned(db.get(Event, event_id), user, db)
    return _set_estimate(db, user, db.get(Project, e.project_id), e, "event", body)


@router.patch("/claims/{claim_id}/estimate")
def estimate_claim(claim_id: uuid.UUID, body: EstimateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = owned(db.get(Claim, claim_id), user, db)
    return _set_estimate(db, user, db.get(Project, c.project_id), c, "claim", body)


# --- decisions and actions ---------------------------------------------------

class ItemIn(BaseModel):
    kind: Literal["decision", "action"]
    text: str = Field(min_length=2, max_length=2000)
    owner: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    meeting_date: date | None = None
    event_id: uuid.UUID | None = None


class ItemPatch(BaseModel):
    text: str | None = Field(default=None, min_length=2, max_length=2000)
    owner: str | None = None
    due_date: date | None = None
    status: Literal["open", "done", "cancelled"] | None = None
    closed_on: date | None = None


@router.post("/projects/{project_id}/meeting-items")
def add_item(project_id: uuid.UUID, body: ItemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    if body.event_id:
        ev = db.get(Event, body.event_id)
        if ev is None or ev.project_id != p.id:
            raise HTTPException(404, "Event not found in this project")
    m = MeetingItem(project_id=p.id, kind=body.kind, text=body.text, owner=body.owner,
                    due_date=body.due_date if body.kind == "action" else None, meeting_date=body.meeting_date or date.today(),
                    status="open" if body.kind == "action" else "recorded", event_id=body.event_id, created_by=user.id)
    db.add(m)
    db.flush()
    audit(db, action=f"meeting.{body.kind}.add", actor_type="user", actor_id=str(user.id), org_id=p.org_id, project_id=p.id,
          entity_type="meeting_item", entity_id=m.id, details=body.model_dump(mode="json"))
    log_project_event(db, p.id, f"meeting.{body.kind}", actor=f"user:{user.id}", entity_type="meeting_item", entity_id=m.id,
                      payload={"text": body.text, "owner": body.owner})
    db.commit()
    return {"id": str(m.id)}


@router.patch("/meeting-items/{item_id}")
def update_item(item_id: uuid.UUID, body: ItemPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = owned(db.get(MeetingItem, item_id), user, db)
    before = {"text": m.text, "owner": m.owner, "due_date": str(m.due_date) if m.due_date else None, "status": m.status}
    changes = body.model_dump(exclude_unset=True, mode="json")
    if "status" in changes and m.kind == "decision":
        raise HTTPException(422, "Decisions have no status; record a new decision instead")
    for k in ("text", "owner", "due_date"):
        if k in changes:
            setattr(m, k, getattr(body, k))
    if body.status:
        m.status = body.status
        m.closed_on = (body.closed_on or date.today()) if body.status in ("done", "cancelled") else None
    p = db.get(Project, m.project_id)
    audit(db, action="meeting.item.update", actor_type="user", actor_id=str(user.id), org_id=p.org_id, project_id=p.id,
          entity_type="meeting_item", entity_id=m.id, details={"before": before, "after": changes})
    db.commit()
    return {"id": str(m.id), "status": m.status}
