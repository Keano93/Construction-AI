"""Notice agent pipeline: message -> classification -> clause link -> deadline -> draft notice -> review queue."""

from __future__ import annotations

import logging
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Contract, ContractClause, ContractRule, Deadline, Document, Draft, Event, Item, Party, Project
from ...record import log_project_event
from ..base import (
    AgentSpec,
    run_task,
    tool_approved_rules,
    tool_compute_deadline,
    tool_create_review_item,
    tool_retrieve,
)
from ..citations import cite
from . import offline  # noqa: F401  (registers offline handlers)
from .core import EventView, MessageView, RuleView, classify_variables, verify_classification
from .schemas import Classification, NoticeDraftOut

log = logging.getLogger(__name__)

SPEC = AgentSpec(
    name="notice_agent",
    version="1.0.0",
    title="Notice agent",
    pillar="protect_the_money",
    description="Monitors emails, WhatsApp exports and site diaries; flags changes, delays, instructions and disruption; "
                "links the contract clause, starts the deadline clock and drafts the notice.",
    inputs=["email", "whatsapp", "diary"],
    outputs=["event register entry", "deadline", "draft notice", "review item with citations"],
    tools=["approved_rules", "open_events", "retrieve", "compute_deadline (deterministic)", "create_draft", "create_review_item"],
)
MESSAGE_KINDS = {"email", "whatsapp", "diary", "letter"}


# --- context builders ----------------------------------------------------

def rule_view(r: ContractRule) -> RuleView:
    return RuleView(id=str(r.id), clause_ref=r.clause_ref, title=r.title, rule_type=r.rule_type,
                    event_categories=list(r.event_categories or []), period_value=r.period_value,
                    period_unit=r.period_unit, summary=r.summary, condition_precedent=r.condition_precedent)


def author_role(parties: list[Party], author: str | None) -> tuple[str, Party | None]:
    if not author:
        return "unknown", None
    a = author.lower()
    for p in parties:
        if (p.email and p.email.lower() in a) or p.name.lower() in a:
            return p.role, p
    return "unknown", None


def parties_block(parties: list[Party]) -> str:
    return "\n".join(f"- {p.name} ({p.organisation or '-'}) <{p.email or '-'}>: {p.role}" for p in parties) or "(none recorded)"


def project_block(project: Project) -> str:
    return f"{project.name}, {project.location or ''}. Contract form: {project.contract_form or 'unknown'}. We are the {project.our_role.replace('_', ' ')}."


def _next_event_ref(db: Session, project_id: uuid.UUID) -> str:
    n = db.execute(select(func.count()).select_from(Event).where(Event.project_id == project_id)).scalar_one()
    return f"PE-{n + 1:03d}"


def _signatory(parties: list[Party]) -> str:
    ours = [p for p in parties if p.role == "contractor"]
    if not ours:
        return "[Name], for and on behalf of the Contractor"
    p = ours[0]
    return f"{p.name}\nfor and on behalf of {p.organisation or 'the Contractor'}"


def _recipient(parties: list[Party], rule: ContractRule) -> str:
    er = next((p for p in parties if p.role == "employers_representative"), None)
    if er:
        return f"{er.name}, Employer's Representative ({er.organisation}) <{er.email}>"
    return rule.recipient or "The Employer's Representative"


# --- pipeline ------------------------------------------------------------

def run_notice_agent_for_item(db: Session, item_id: uuid.UUID) -> dict:
    item = db.get(Item, item_id)
    if item is None or item.kind not in MESSAGE_KINDS:
        return {"skipped": True}
    doc = db.get(Document, item.document_id)
    project = db.get(Project, item.project_id)
    parties = list(project.parties)
    rules = tool_approved_rules(db, project.id)
    rviews = [rule_view(r) for r in rules]
    open_events = list(db.execute(select(Event).where(Event.project_id == project.id, Event.status.in_(["open", "notified"]))
                                  .order_by(Event.created_at)).scalars())
    eviews = [EventView(e.ref, e.category, e.title, e.trigger_date.isoformat(), e.description[:200]) for e in open_events]
    role, _party = author_role(parties, item.author)
    msg = MessageView(text=item.text, channel=item.kind, timestamp=item.timestamp, author=item.author, author_role=role,
                      subject=item.subject)

    raw, run = run_task(
        db, spec=SPEC, project_id=project.id, task="classify", prompt_agent="notice_agent",
        variables=classify_variables(project_block(project), parties_block(parties), rviews, eviews, msg),
        schema=Classification, inputs={"item_id": str(item.id), "document_id": str(doc.id), "rules": len(rviews)},
        max_tokens=4000,
    )
    v = verify_classification(raw, msg, rviews)
    run.output = {**run.output, "_verification": {"confidence": v.confidence, "issues": v.issues, "auto_linked": v.auto_linked}}

    msg_citations = []
    for s, e, why in v.evidence_spans:
        c = cite(doc.id, doc.text, item.text[s:e], item_id=item.id, label="Triggering message",
                 window=(item.char_start, item.char_end))
        if c:
            msg_citations.append(c.to_dict())

    if v.category == "noise":
        if v.low_confidence:
            tool_create_review_item(
                db, project_id=project.id, spec=SPEC, run=run, kind="possible_event", category="noise",
                title=f"Check: possibly notifiable - {raw.title[:120]}",
                summary="Classified as noise with low confidence. Confirm nothing needs notifying.",
                confidence=v.confidence, citations=msg_citations, payload={"classification": raw.model_dump(), "issues": v.issues},
                source_item_id=item.id,
            )
        return {"category": "noise", "confidence": v.confidence}

    # Existing event: attach evidence, no new clock (the clock runs from first awareness)
    if raw.related_event_ref:
        ev = next((e for e in open_events if e.ref == raw.related_event_ref), None)
        if ev is not None:
            ev.related_item_ids = [*ev.related_item_ids, str(item.id)]
            log_project_event(db, project.id, "event.evidence_added", actor=f"agent:{SPEC.name}", entity_type="event",
                              entity_id=ev.id, payload={"item_id": str(item.id), "category": v.category})
            return {"category": v.category, "related_event": ev.ref}

    event = Event(project_id=project.id, ref=_next_event_ref(db, project.id), category=v.category, title=raw.title[:300],
                  description=raw.summary, trigger_date=v.trigger_date, source_item_id=item.id, agent_run_id=run.id,
                  related_item_ids=[str(item.id)])
    db.add(event)
    db.flush()
    log_project_event(db, project.id, "event.created", actor=f"agent:{SPEC.name}", entity_type="event", entity_id=event.id,
                      payload={"ref": event.ref, "category": event.category, "trigger_date": event.trigger_date})

    rule_rows = {str(r.id): r for r in rules}
    deadlines: list[Deadline] = []
    clause_citations = []
    contract_doc_cache: dict[uuid.UUID, Document] = {}
    for rv in v.rules:
        r = rule_rows[rv.id]
        trace = tool_compute_deadline(project, r, v.trigger_date)
        if trace:
            d = Deadline(project_id=project.id, event_id=event.id, rule_id=r.id,
                         label=f"Clause {r.clause_ref} {r.title}", trigger_date=v.trigger_date,
                         due_date=date.fromisoformat(trace["due_date"]), trace=trace)
            db.add(d)
            deadlines.append(d)
        contract = db.get(Contract, r.contract_id)
        cdoc = contract_doc_cache.setdefault(contract.document_id, db.get(Document, contract.document_id))
        if r.source_char_start is not None:
            clause_citations.append({"document_id": str(cdoc.id), "quote": r.source_quote, "char_start": r.source_char_start,
                                     "char_end": r.source_char_end, "item_id": None, "clause_ref": r.clause_ref,
                                     "label": f"Clause {r.clause_ref}", "verified": True})
    db.flush()
    for d in deadlines:
        log_project_event(db, project.id, "deadline.started", actor="system:deadline_engine", entity_type="deadline",
                          entity_id=d.id, payload={"event": event.ref, "due_date": d.due_date, "rule": d.label})

    draft = None
    primary = v.primary_rule
    draft_issues: list[str] = []
    if primary is not None:
        draft, draft_issues = _draft_notice(db, project, parties, item, doc, event, rule_rows[primary.id], v,
                                            next((d for d in deadlines if str(d.rule_id) == primary.id), None))

    earliest = min((d.due_date for d in deadlines), default=None)
    title_prefix = {"change": "Potential change", "delay": "Delay", "instruction": "Instruction", "disruption": "Disruption"}[v.category]
    summary = raw.summary
    if not v.rules:
        summary += " No approved contract rule is linked - approve the contract rules or link one manually."
    review = tool_create_review_item(
        db, project_id=project.id, spec=SPEC, run=run, kind="notice_flag", category=v.category,
        title=f"{title_prefix}: {raw.title[:200]}", summary=summary, confidence=v.confidence,
        citations=msg_citations + clause_citations,
        payload={
            "classification": raw.model_dump(),
            "verification": {"issues": v.issues + draft_issues, "auto_linked": v.auto_linked},
            "trigger_date": v.trigger_date.isoformat() if v.trigger_date else None,
            "rules": [{"id": rv.id, "clause_ref": rv.clause_ref, "title": rv.title, "condition_precedent": rv.condition_precedent} for rv in v.rules],
            "deadlines": [{"id": str(d.id), "label": d.label, "due_date": str(d.due_date), "trace": d.trace} for d in deadlines],
            "event_ref": event.ref,
            "source": {"item_id": str(item.id), "document_id": str(doc.id), "filename": doc.filename, "channel": item.kind,
                       "author": item.author, "timestamp": item.timestamp.isoformat() if item.timestamp else None},
        },
        event_id=event.id, draft_id=draft.id if draft else None, source_item_id=item.id, priority_date=earliest,
    )
    return {"category": v.category, "event": event.ref, "review_item": str(review.id), "deadlines": [str(d.due_date) for d in deadlines]}


def _draft_notice(db: Session, project: Project, parties: list[Party], item: Item, doc: Document, event: Event,
                  rule: ContractRule, v, deadline: Deadline | None) -> tuple[Draft, list[str]]:
    contract = db.get(Contract, rule.contract_id)
    cdoc = db.get(Document, contract.document_id)
    clause = db.get(ContractClause, rule.clause_id) if rule.clause_id else None
    clause_text = clause.text if clause else rule.source_quote
    form_hits = tool_retrieve(db, project.id, "form of notices in writing email subject line CONTRACT NOTICE addresses Employer's Representative",
                              k=2, kinds=["contract"])
    form_text = "\n...\n".join(h.text for h in form_hits) or "(not found)"
    evidence_quote = item.text[v.evidence_spans[0][0]:v.evidence_spans[0][1]] if v.evidence_spans else None
    period = f"{rule.period_value} {(rule.period_unit or '').replace('_', ' ')}" if rule.period_value is not None else "no fixed period"
    variables = {
        "project": project_block(project), "project_name": project.name, "signatory": _signatory(parties),
        "category": v.category, "title": event.title, "summary": event.description,
        "trigger_date": event.trigger_date.isoformat(), "period": period,
        "due_date": deadline.due_date.isoformat() if deadline else "no fixed period",
        "clause_ref": rule.clause_ref, "clause_title": rule.title, "clause_text": clause_text,
        "form_of_notice": form_text, "channel": item.kind, "timestamp": item.timestamp.isoformat() if item.timestamp else "",
        "author": item.author or "unknown", "text": item.text,
        "_evidence_quote": evidence_quote, "_clause_quote": rule.source_quote, "_recipient": _recipient(parties, rule),
    }
    out, run = run_task(db, spec=SPEC, project_id=project.id, task="draft_notice", prompt_agent="notice_agent",
                        variables=variables, schema=NoticeDraftOut,
                        inputs={"event_id": str(event.id), "rule_id": str(rule.id), "item_id": str(item.id)})
    issues = []
    verified = []
    for c in out.citations:
        if c.source == "message":
            cit = cite(doc.id, doc.text, c.quote, item_id=item.id, label="Triggering message", window=(item.char_start, item.char_end))
        else:
            win = (clause.char_start, clause.char_end) if clause else None
            cit = cite(cdoc.id, cdoc.text, c.quote, clause_ref=rule.clause_ref, label=f"Clause {rule.clause_ref}", window=win)
        if cit:
            verified.append(cit.to_dict())
        else:
            issues.append(f"draft citation not found in {c.source}: {c.quote[:60]!r}")
    run.output = {**run.output, "_verified_citations": verified, "_issues": issues}
    draft = Draft(project_id=project.id, kind="notice", event_id=event.id, rule_id=rule.id, subject=out.subject[:400],
                  recipient=out.recipient[:400], body=out.body)
    db.add(draft)
    db.flush()
    log_project_event(db, project.id, "draft.created", actor=f"agent:{SPEC.name}", entity_type="draft", entity_id=draft.id,
                      payload={"event": event.ref, "clause": rule.clause_ref, "assumptions": out.assumptions,
                               "citations": verified})
    return draft, issues
