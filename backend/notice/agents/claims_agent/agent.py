"""Claims agent: evidence timeline + notice compliance + claim narrative for selected events."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Claim, Contract, ContractClause, ContractRule, Deadline, Document, Draft, Event, Item, Project
from ...record import log_project_event
from ..base import AgentSpec, run_task, tool_create_review_item, tool_retrieve
from ..identifiers import identifiers
from . import offline  # noqa: F401  (registers offline handlers)
from .core import (
    Evidence,
    assemble_body,
    compliance_block,
    evidence_block,
    notice_compliance,
    verify_narrative_citations,
    verify_timeline,
)
from .schemas import ClaimNarrative, TimelineOut

SPEC = AgentSpec(
    name="claims_agent",
    version="1.0.0",
    title="Claims agent",
    pillar="protect_the_money",
    description="For selected events, assembles a chronological evidence timeline from the project record, checks notice "
                "compliance (by code) and drafts the claim narrative with quantum placeholders.",
    inputs=["events", "project record"],
    outputs=["evidence timeline", "notice compliance", "claim narrative draft"],
    tools=["gather evidence (links, retrieval, identifiers)", "notice compliance (deterministic)", "llm.structured", "locate_quote"],
)
MESSAGE_KINDS = ("email", "whatsapp", "diary", "letter")
MAX_EVIDENCE = 40


class ClaimError(ValueError):
    pass


def next_claim_ref(db: Session, project_id: uuid.UUID) -> str:
    n = db.execute(select(func.count()).select_from(Claim).where(Claim.project_id == project_id)).scalar_one()
    return f"CL-{n + 1:03d}"


def create_claim(db: Session, project: Project, event_ids: list[uuid.UUID], user_id: uuid.UUID | None, title: str | None = None) -> Claim:
    events = list(db.execute(select(Event).where(Event.id.in_(event_ids), Event.project_id == project.id)).scalars())
    if not events or len(events) != len(set(event_ids)):
        raise ClaimError("Select one or more events from this project")
    claim = Claim(project_id=project.id, ref=next_claim_ref(db, project.id), event_ids=[str(e.id) for e in events],
                  title=title or "; ".join(e.title for e in events)[:400], status="drafting", created_by=user_id)
    db.add(claim)
    db.flush()
    return claim


def gather_evidence(db: Session, project: Project, events: list[Event], today: date) -> list[Evidence]:
    linked_ids = {uuid.UUID(i) for e in events for i in e.related_item_ids}
    start = min(e.trigger_date for e in events) - timedelta(days=21)
    scores: dict[uuid.UUID, float] = {i: 10.0 for i in linked_ids}
    for e in events:
        for h in tool_retrieve(db, project.id, f"{e.title} {e.description}", k=30, kinds=list(MESSAGE_KINDS)):
            if h.item_id:
                scores[h.item_id] = max(scores.get(h.item_id, 0.0), h.score)
    ev_ids = set().union(*(identifiers(f"{e.title} {e.description}") for e in events))
    if ev_ids:
        for it in db.execute(select(Item).where(Item.project_id == project.id, Item.kind.in_(MESSAGE_KINDS))).scalars():
            if ev_ids & identifiers(it.text):
                scores[it.id] = max(scores.get(it.id, 0.0), 1.0)
    items = list(db.execute(select(Item).where(Item.id.in_(list(scores)))).scalars())
    items = [i for i in items if i.id in linked_ids or (i.timestamp and start <= i.timestamp.date() <= today)]
    items.sort(key=lambda i: -scores[i.id])
    items = items[:MAX_EVIDENCE]
    items.sort(key=lambda i: (i.timestamp is None, i.timestamp))
    docs = {d.id: d for d in db.execute(select(Document).where(Document.id.in_({i.document_id for i in items}))).scalars()}
    return [Evidence(id=f"E{n}", item_id=str(i.id), document_id=str(i.document_id), filename=docs[i.document_id].filename,
                     channel=i.kind, author=i.author, timestamp=i.timestamp, text=i.text, doc_offset=i.char_start,
                     linked=i.id in linked_ids) for n, i in enumerate(items, 1)]


def _compliance_rows(db: Session, events: list[Event]) -> list[dict]:
    rows = []
    for e in events:
        for d in db.execute(select(Deadline).where(Deadline.event_id == e.id).order_by(Deadline.due_date)).scalars():
            r = db.get(ContractRule, d.rule_id)
            rows.append({"event_ref": e.ref, "clause_ref": r.clause_ref, "title": r.title, "condition_precedent": r.condition_precedent,
                         "trigger_date": d.trigger_date, "due_date": d.due_date, "status": d.status,
                         "met_on": d.met_at.date() if d.met_at else None})
    return rows


def run_claims_agent(db: Session, claim_id: uuid.UUID, today: date | None = None) -> Claim:
    today = today or date.today()
    claim = db.get(Claim, claim_id)
    project = db.get(Project, claim.project_id)
    events = list(db.execute(select(Event).where(Event.id.in_([uuid.UUID(x) for x in claim.event_ids]))
                             .order_by(Event.trigger_date)).scalars())
    events_text = "\n".join(f"- {e.ref} [{e.category}] aware {e.trigger_date}: {e.title}. {e.description}" for e in events)
    project_text = f"{project.name}, {project.location or ''}. Contract: {project.contract_form or 'unknown'}."

    # 1. evidence + timeline
    evidence = gather_evidence(db, project, events, today)
    t_out, t_run = run_task(
        db, spec=SPEC, project_id=project.id, task="timeline", prompt_agent="claims_agent",
        variables={"project": project_text, "events": events_text, "evidence": evidence_block(evidence),
                   "_evidence": evidence, "_event_text": " ".join(f"{e.title} {e.description}" for e in events)},
        schema=TimelineOut, inputs={"claim_id": str(claim.id), "events": claim.event_ids, "evidence_items": len(evidence)},
    )
    timeline, issues = verify_timeline(t_out, evidence)

    # 2. notice compliance (code)
    compliance = notice_compliance(_compliance_rows(db, events), today)

    # 3. narrative
    rules = {}
    for e in events:
        for d in e.deadlines:
            r = db.get(ContractRule, d.rule_id)
            rules[r.clause_ref] = r
    clause_texts: dict[str, tuple[str, str, int]] = {}
    for ref, r in rules.items():
        contract = db.get(Contract, r.contract_id)
        if r.clause_id:
            c = db.get(ContractClause, r.clause_id)
            clause_texts[ref] = (str(contract.document_id), c.text, c.char_start)
    extracts = tool_retrieve(db, project.id, "Compensation Events Delay Events extension of time adjustment of the Contract Sum claim particulars",
                             k=3, kinds=["contract"])
    timeline_text = "\n".join(f"- {t['date'][:10] if t['date'] else 'undated'} {t['evidence_id']} [{t['significance']}] "
                              f"{t['description']} (\"{t['quote']}\")" for t in timeline) or "(no verified entries)"
    n_out, n_run = run_task(
        db, spec=SPEC, project_id=project.id, task="narrative", prompt_agent="claims_agent",
        variables={"project": project_text, "title": claim.title, "events": events_text,
                   "clauses": "\n\n".join(f"[{ref}] {t[1]}" for ref, t in clause_texts.items()) or "(none linked)",
                   "contract_extracts": "\n...\n".join(h.text for h in extracts) or "(none)",
                   "compliance": compliance_block(compliance), "timeline": timeline_text,
                   "gaps": "\n".join(f"- {g}" for g in t_out.gaps) or "(none)",
                   "_events": [{"ref": e.ref, "title": e.title, "category": e.category} for e in events],
                   "_timeline": timeline, "_compliance": compliance,
                   "_clause_refs": [(ref, r.source_quote) for ref, r in rules.items()]},
        schema=ClaimNarrative, inputs={"claim_id": str(claim.id), "timeline_entries": len(timeline)},
    )
    n_cites, n_issues = verify_narrative_citations(n_out, evidence, clause_texts)
    issues += n_issues

    # 4. assemble draft + review item
    body = assemble_body(claim.ref, project.name, [{"ref": e.ref} for e in events], n_out, compliance, timeline, t_out.gaps)
    draft = Draft(project_id=project.id, kind="claim", event_id=events[0].id, subject=f"{claim.ref} {n_out.title}"[:400],
                  recipient="Employer's Representative", body=body)
    db.add(draft)
    db.flush()
    claim.title = n_out.title[:400]
    claim.timeline, claim.notice_compliance, claim.gaps = timeline, compliance, t_out.gaps
    claim.narrative = n_out.model_dump(mode="json")
    claim.draft_id, claim.agent_run_ids, claim.status = draft.id, [str(t_run.id), str(n_run.id)], "ready"

    verified_ratio = len(timeline) / max(len(t_out.entries), 1)
    confidence = round(min(n_out.confidence, 0.95) * (0.5 + 0.5 * verified_ratio), 3)
    if len(timeline) < 2:
        confidence = min(confidence, 0.5)
        issues.append("fewer than two verified timeline entries")
    time_bar = [r for r in compliance if r["time_bar_risk"]]
    citations = [{"document_id": t["document_id"], "item_id": t["item_id"], "clause_ref": None, "char_start": t["char_start"],
                  "char_end": t["char_end"], "quote": t["quote"], "label": f"{t['evidence_id']} {t['filename']}", "verified": True}
                 for t in timeline]
    citations += [c for c in n_cites if c["clause_ref"]]
    tool_create_review_item(
        db, project_id=project.id, spec=SPEC, run=n_run, kind="claim_draft", category=events[0].category,
        title=f"Claim {claim.ref}: {n_out.title}"[:400], summary=n_out.executive_summary, confidence=confidence,
        citations=citations,
        payload={"claim_id": str(claim.id), "claim_ref": claim.ref, "events": [{"ref": e.ref, "title": e.title, "id": str(e.id)} for e in events],
                 "timeline": timeline, "compliance": compliance, "gaps": t_out.gaps, "risks": n_out.risks,
                 "quantum_heads": [q.model_dump() for q in n_out.quantum_heads], "issues": issues,
                 "time_bar_risk": bool(time_bar), "evidence_considered": len(evidence)},
        draft_id=draft.id, event_id=events[0].id,
    )
    log_project_event(db, project.id, "claim.drafted", actor=f"agent:{SPEC.name}", entity_type="claim", entity_id=claim.id,
                      payload={"ref": claim.ref, "timeline": len(timeline), "time_bar_risk": bool(time_bar)})
    return claim
