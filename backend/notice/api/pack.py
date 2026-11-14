"""Commercial pack (latest position over a date range) and QS estimates."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Claim, Event, Project, User
from ..pack import export
from ..pack.service import PackError, build_pack
from ..record import audit
from .deps import current_user, owned, project_for

router = APIRouter(tags=["pack"])


def _pack(db: Session, project: Project, date_from: date | None, date_to: date | None) -> dict:
    to = date_to or date.today()
    try:
        return build_pack(db, project, date_from or to - timedelta(days=6), to)
    except PackError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/projects/{project_id}/pack")
def commercial_pack(project_id: uuid.UUID, date_from: date | None = Query(None, alias="from"),
                    date_to: date | None = Query(None, alias="to"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Defaults to the 7 days ending today."""
    return _pack(db, project_for(project_id, user, db), date_from, date_to)


@router.get("/projects/{project_id}/pack/export")
def commercial_pack_export(project_id: uuid.UUID, format: str = "pdf", date_from: date | None = Query(None, alias="from"),
                           date_to: date | None = Query(None, alias="to"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    if format not in ("pdf", "docx"):
        raise HTTPException(422, "format must be pdf or docx")
    pack = _pack(db, p, date_from, date_to)
    data = export.to_pdf(pack) if format == "pdf" else export.to_docx(pack)
    mime = "application/pdf" if format == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    audit(db, action="pack.export", actor_type="user", actor_id=str(user.id), org_id=p.org_id, project_id=p.id,
          entity_type="project", entity_id=p.id, details={"format": format, "from": pack["from"], "to": pack["to"]})
    db.commit()
    name = f"Commercial pack {p.name} {pack['from']} to {pack['to']}.{format}"
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- estimates --------------------------------------------------------------

class EstimateIn(BaseModel):
    estimated_value: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    value_note: str | None = Field(default=None, max_length=500)


def _set_estimate(db: Session, user: User, project: Project, entity, kind: str, body: EstimateIn) -> dict:
    before = {"estimated_value": str(entity.estimated_value) if entity.estimated_value is not None else None}
    entity.estimated_value = body.estimated_value
    if kind == "event" and "value_note" in body.model_fields_set:
        before["value_note"] = entity.value_note
        entity.value_note = body.value_note
    audit(db, action=f"{kind}.estimate", actor_type="user", actor_id=str(user.id), org_id=project.org_id, project_id=project.id,
          entity_type=kind, entity_id=entity.id, details={"before": before, "after": body.model_dump(mode="json", exclude_unset=True)})
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
