import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import jobs
from ..agents.base import project_calendar
from ..agents.registry import AGENTS
from ..config import get_settings
from ..contract.service import review_rule
from ..db import get_db
from ..deadlines import DeadlineRule, PeriodUnit, compute_deadline, deadline_status, working_days_remaining
from ..ingestion.extractors import ExtractionError
from ..ingestion.service import ingest_file
from ..llm import get_provider
from ..models import (
    AgentRun,
    AuditLog,
    Contract,
    ContractRule,
    Deadline,
    Document,
    Event,
    Item,
    Job,
    Party,
    Project,
    ProjectLog,
    ProjectShutdown,
    ReviewItem,
    User,
)
from ..record import audit, verify_audit_chain
from ..retrieval import search
from . import serializers as S
from .deps import current_user, owned, project_for

router = APIRouter(tags=["projects"])
MAX_UPLOAD = 50 * 1024 * 1024


# --- projects ------------------------------------------------------------

class ProjectIn(BaseModel):
    name: str
    code: str | None = None
    location: str | None = None
    contract_form: str | None = None
    holiday_region: str = "IE"
    start_date: date | None = None


class ShutdownIn(BaseModel):
    name: str
    start: date
    end: date


class PartyIn(BaseModel):
    name: str
    organisation: str | None = None
    role: str
    email: str | None = None


@router.get("/system")
def system_info():
    p = get_provider()
    return {"llm_provider": p.name, "model": p.model, "low_confidence_threshold": get_settings().low_confidence_threshold}


@router.get("/agents")
def list_agents():
    return [a.__dict__ for a in AGENTS]


@router.get("/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Project).where(Project.org_id == user.org_id).order_by(Project.created_at)).scalars()
    return [S.project(p) for p in rows]


@router.post("/projects")
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(org_id=user.org_id, **body.model_dump())
    project_calendar(p)  # validates region
    db.add(p)
    db.flush()
    audit(db, action="project.create", actor_type="user", actor_id=str(user.id), org_id=user.org_id, project_id=p.id,
          entity_type="project", entity_id=p.id)
    db.commit()
    return S.project(p)


@router.get("/projects/{project_id}")
def get_project(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    today = date.today()
    cal = project_calendar(p)

    def count(model, *where):
        return db.execute(select(func.count()).select_from(model).where(model.project_id == p.id, *where)).scalar_one()

    running = list(db.execute(select(Deadline).where(Deadline.project_id == p.id, Deadline.status == "running")).scalars())
    overdue = sum(1 for d in running if d.due_date < today)
    due_5 = sum(1 for d in running if d.due_date >= today and working_days_remaining(d.due_date, today, cal) <= 5)
    return {
        **S.project(p),
        "stats": {
            "documents": count(Document), "items": count(Item), "events_open": count(Event, Event.status == "open"),
            "review_pending": count(ReviewItem, ReviewItem.status == "pending"),
            "review_low_confidence": count(ReviewItem, ReviewItem.status == "pending", ReviewItem.low_confidence.is_(True)),
            "rules_proposed": count(ContractRule, ContractRule.status == "proposed"),
            "rules_approved": count(ContractRule, ContractRule.status == "approved"),
            "deadlines_running": len(running), "deadlines_overdue": overdue, "deadlines_due_5wd": due_5,
            "jobs_queued": count(Job, Job.status.in_(["queued", "running"])),
        },
    }


@router.post("/projects/{project_id}/shutdowns")
def add_shutdown(project_id: uuid.UUID, body: ShutdownIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    if body.end < body.start:
        raise HTTPException(422, "Shutdown ends before it starts")
    s = ProjectShutdown(project_id=p.id, **body.model_dump())
    db.add(s)
    db.flush()
    audit(db, action="project.shutdown.add", actor_type="user", actor_id=str(user.id), org_id=p.org_id, project_id=p.id,
          entity_type="project_shutdown", entity_id=s.id, details=body.model_dump(mode="json"))
    db.commit()
    db.refresh(p)
    return S.project(p)


@router.post("/projects/{project_id}/parties")
def add_party(project_id: uuid.UUID, body: PartyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    db.add(Party(project_id=p.id, **body.model_dump()))
    db.commit()
    db.refresh(p)
    return S.project(p)


# --- documents -----------------------------------------------------------

@router.get("/projects/{project_id}/documents")
def list_documents(project_id: uuid.UUID, kind: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    q = select(Document).where(Document.project_id == p.id).order_by(Document.doc_timestamp.desc().nullslast(), Document.created_at.desc())
    if kind:
        q = q.where(Document.kind == kind)
    return [S.document(d) for d in db.execute(q).scalars()]


@router.post("/projects/{project_id}/documents")
async def upload_document(project_id: uuid.UUID, file: UploadFile = File(...), kind: str | None = Form(None),
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (50MB max)")
    try:
        res = ingest_file(db, p, file.filename or "upload", data, kind=kind or None, uploaded_by=user.id)
    except ExtractionError as e:
        raise HTTPException(422, str(e)) from e
    db.commit()
    if get_settings().jobs_inline:
        jobs.drain()
    return {"document": S.document(res.document), "created": res.created}


@router.get("/documents/{document_id}")
def get_document(document_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return S.document(owned(db.get(Document, document_id), user, db), with_text=True)


@router.get("/documents/{document_id}/file")
def download_document(document_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = owned(db.get(Document, document_id), user, db)
    return FileResponse(d.storage_path, media_type=d.mime, filename=d.filename)


@router.get("/items/{item_id}")
def get_item(item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return S.item(owned(db.get(Item, item_id), user, db))


@router.get("/projects/{project_id}/search")
def search_project(project_id: uuid.UUID, q: str, k: int = 10, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    return [h.__dict__ | {"chunk_id": str(h.chunk_id), "document_id": str(h.document_id), "item_id": str(h.item_id) if h.item_id else None}
            for h in search(db, p.id, q, k=min(k, 50))]


# --- contract model ------------------------------------------------------

class RuleReviewIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject|reopen)$")
    edits: dict | None = None


@router.get("/projects/{project_id}/contract")
def get_contract(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    return [S.contract(c) for c in db.execute(select(Contract).where(Contract.project_id == p.id).order_by(Contract.created_at)).scalars()]


@router.post("/rules/{rule_id}/review")
def review_contract_rule(rule_id: uuid.UUID, body: RuleReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = owned(db.get(ContractRule, rule_id), user, db)
    edits = body.edits
    if edits and "period_unit" in edits and edits["period_unit"] is not None:
        PeriodUnit(edits["period_unit"])  # validate
    try:
        review_rule(db, r, user_id=user.id, decision=body.decision, edits=edits)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    db.commit()
    return S.rule(r)


@router.post("/contracts/{contract_id}/reextract")
def reextract(contract_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = owned(db.get(Contract, contract_id), user, db)
    if any(r.status == "approved" for r in c.rules):
        raise HTTPException(409, "Contract has approved rules; re-extraction would discard reviewed work")
    for r in list(c.rules):
        db.delete(r)
    c.status = "extracting"
    jobs.enqueue(db, "contract.extract", {"contract_id": c.id}, c.project_id)
    db.commit()
    if get_settings().jobs_inline:
        jobs.drain()
    return {"status": "queued"}


# --- events / deadlines --------------------------------------------------

@router.get("/projects/{project_id}/events")
def list_events(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    events = db.execute(select(Event).where(Event.project_id == p.id).order_by(Event.trigger_date.desc())).scalars()
    return [S.event(e) | {"deadlines": [S.deadline(d) for d in e.deadlines]} for e in events]


@router.get("/projects/{project_id}/deadlines")
def list_deadlines(project_id: uuid.UUID, include_closed: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    cal, today = project_calendar(p), date.today()
    q = select(Deadline).where(Deadline.project_id == p.id).order_by(Deadline.due_date)
    if not include_closed:
        q = q.where(Deadline.status == "running")
    out = []
    for d in db.execute(q).scalars():
        row = S.deadline(d, remaining=working_days_remaining(d.due_date, today, cal))
        row["urgency"] = deadline_status(d.due_date, today).value if d.status == "running" else d.status
        row["event"] = {"ref": d.event.ref, "title": d.event.title, "category": d.event.category}
        row["condition_precedent"] = d.rule.condition_precedent
        ri = db.execute(select(ReviewItem.id).where(ReviewItem.event_id == d.event_id)).scalar()
        row["review_item_id"] = str(ri) if ri else None
        out.append(row)
    return out


class CalcIn(BaseModel):
    trigger_date: date
    period: int = Field(ge=0, le=2000)
    unit: PeriodUnit
    roll_forward: bool = True


@router.post("/projects/{project_id}/deadline-calculator")
def deadline_calculator(project_id: uuid.UUID, body: CalcIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    return compute_deadline(body.trigger_date, DeadlineRule(body.period, body.unit, body.roll_forward), project_calendar(p)).to_trace()


# --- record / audit ------------------------------------------------------

@router.get("/projects/{project_id}/log")
def project_log(project_id: uuid.UUID, limit: int = 200, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    rows = db.execute(select(ProjectLog).where(ProjectLog.project_id == p.id).order_by(ProjectLog.id.desc()).limit(min(limit, 1000))).scalars()
    return [{"id": r.id, "type": r.type, "entity_type": r.entity_type, "entity_id": str(r.entity_id) if r.entity_id else None,
             "payload": r.payload, "actor": r.actor, "created_at": S.iso(r.created_at)} for r in rows]


@router.get("/projects/{project_id}/audit")
def project_audit(project_id: uuid.UUID, limit: int = 200, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = project_for(project_id, user, db)
    rows = db.execute(select(AuditLog).where(AuditLog.project_id == p.id).order_by(AuditLog.id.desc()).limit(min(limit, 1000))).scalars()
    names = {str(u.id): u.name for u in db.execute(select(User).where(User.org_id == p.org_id)).scalars()}
    return [{"id": r.id, "actor_type": r.actor_type, "actor_id": r.actor_id, "actor_name": names.get(r.actor_id, r.actor_id),
             "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id, "source_refs": r.source_refs,
             "details": r.details, "hash": r.hash, "prev_hash": r.prev_hash, "created_at": S.iso(r.created_at)} for r in rows]


@router.get("/audit/verify")
def audit_verify(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ok, bad = verify_audit_chain(db)
    return {"ok": ok, "first_bad_id": bad}


@router.get("/agent-runs/{run_id}")
def get_run(run_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = owned(db.get(AgentRun, run_id), user, db)
    return {"id": str(r.id), "agent": r.agent, "agent_version": r.agent_version, "task": r.task, "prompt_id": r.prompt_id,
            "provider": r.provider, "model": r.model, "inputs": r.inputs, "output": r.output, "status": r.status,
            "error": r.error, "usage": r.usage, "started_at": S.iso(r.started_at), "finished_at": S.iso(r.finished_at)}

