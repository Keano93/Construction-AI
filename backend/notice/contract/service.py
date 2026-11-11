"""Contract model: clause splitting, rule extraction, and the approval workflow."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..agents.base import AgentSpec, run_task
from ..agents.citations import locate_quote
from ..config import get_settings
from ..models import Contract, ContractClause, ContractRule, Document, Project
from ..record import audit, log_project_event
from . import offline  # noqa: F401  (registers offline handler)
from .clauses import split_clauses
from .schemas import ContractExtraction

SPEC = AgentSpec(
    name="contract_extractor",
    version="1.0.0",
    title="Contract model",
    pillar="core",
    description="Extracts notice clauses, time bars, payment, retention, variation and EOT rules from the contract for human approval.",
    inputs=["contract document"],
    outputs=["proposed contract rules with verbatim source quotes"],
    tools=["split_clauses", "llm.structured", "locate_quote"],
)

EDITABLE_FIELDS = {
    "rule_type", "clause_ref", "title", "summary", "trigger_event", "event_categories", "period_value",
    "period_unit", "recipient", "required_form", "condition_precedent", "details",
}


def run_contract_extraction(db: Session, contract_id: uuid.UUID) -> Contract:
    contract = db.get(Contract, contract_id)
    doc = db.get(Document, contract.document_id)
    project = db.get(Project, contract.project_id)

    # 1. clauses (deterministic)
    contract.clauses.clear()
    db.flush()
    spans = split_clauses(doc.text)
    clause_rows = {}
    for pos, c in enumerate(spans):
        row = ContractClause(contract_id=contract.id, project_id=project.id, ref=c.ref, title=c.title, text=c.text,
                             char_start=c.char_start, char_end=c.char_end, position=pos)
        db.add(row)
        clause_rows.setdefault(c.ref, row)
    db.flush()

    # 2. rules (LLM or offline), then verify every quote against the source
    clause_payload = [{"ref": c.ref, "title": c.title, "text": c.text} for c in spans]
    rendered = "\n\n".join(f"[{c.ref}] {c.text}" for c in spans) if spans else doc.text
    try:
        out, run = run_task(
            db, spec=SPEC, project_id=project.id, task="extract_rules", prompt_agent="contract_extraction",
            variables={"contract_form": project.contract_form or "unknown", "clauses": rendered, "_clauses": clause_payload},
            schema=ContractExtraction, inputs={"contract_id": str(contract.id), "document_id": str(doc.id), "clauses": len(spans)},
        )
    except Exception:
        contract.status = "failed"
        raise
    contract.extraction_run_id = run.id
    threshold = get_settings().low_confidence_threshold
    for r in out.rules:
        clause = clause_rows.get(r.clause_ref)
        window = (clause.char_start, clause.char_end) if clause else (0, len(doc.text))
        span = locate_quote(doc.text[window[0]:window[1]], r.source_quote)
        confidence = r.confidence
        verified = span is not None
        if not verified:
            span_any = locate_quote(doc.text, r.source_quote)
            if span_any:
                span, window, verified = span_any, (0, len(doc.text)), True
        if not verified:
            confidence = min(confidence, threshold - 0.2)
        if clause is None:
            confidence = min(confidence, threshold - 0.1)
        details = {"percentage": r.percentage, "day_of_month": r.day_of_month,
                   "quote_verified": verified, "clause_found": clause is not None}
        start = window[0] + span[0] if span else None
        end = window[0] + span[1] if span else None
        row = ContractRule(
            contract_id=contract.id, project_id=project.id, clause_id=clause.id if clause else None,
            rule_type=r.rule_type, clause_ref=r.clause_ref, title=r.title, summary=r.summary,
            trigger_event=r.trigger_event, event_categories=list(r.event_categories), period_value=r.period_value,
            period_unit=r.period_unit, recipient=r.recipient, required_form=r.required_form,
            condition_precedent=r.condition_precedent, details={k: v for k, v in details.items() if v is not None},
            source_quote=doc.text[start:end] if span else r.source_quote, source_char_start=start, source_char_end=end,
            confidence=round(confidence, 3), status="proposed", original=r.model_dump(mode="json"),
        )
        db.add(row)
    contract.status = "pending_review"
    if out.contract_form and not contract.form:
        contract.form = out.contract_form
    db.flush()
    log_project_event(db, project.id, "contract.rules_extracted", actor=f"agent:{SPEC.name}", entity_type="contract",
                      entity_id=contract.id, payload={"rules": len(out.rules), "clauses": len(spans)})
    return contract


def review_rule(db: Session, rule: ContractRule, *, user_id: uuid.UUID, decision: str, edits: dict | None = None) -> ContractRule:
    """decision: approve | reject | reopen. Optional edits are applied before approval and logged."""
    before = {k: getattr(rule, k) for k in EDITABLE_FIELDS}
    if edits:
        unknown = set(edits) - EDITABLE_FIELDS
        if unknown:
            raise ValueError(f"Fields not editable: {sorted(unknown)}")
        for k, v in edits.items():
            setattr(rule, k, v)
    rule.status = {"approve": "approved", "reject": "rejected", "reopen": "proposed"}[decision]
    rule.reviewed_by, rule.reviewed_at = user_id, datetime.now(timezone.utc)
    after = {k: getattr(rule, k) for k in EDITABLE_FIELDS}
    db.flush()
    contract = db.get(Contract, rule.contract_id)
    remaining = sum(1 for r in contract.rules if r.status == "proposed")
    if remaining == 0 and contract.status == "pending_review":
        contract.status = "approved"
    project = db.get(Project, rule.project_id)
    audit(db, action=f"contract_rule.{decision}", actor_type="user", actor_id=str(user_id), org_id=project.org_id,
          project_id=project.id, entity_type="contract_rule", entity_id=rule.id,
          source_refs=[{"document_id": str(contract.document_id), "clause_ref": rule.clause_ref,
                        "char_start": rule.source_char_start, "char_end": rule.source_char_end}],
          details={"edited": bool(edits), "before": before if edits else None, "after": after if edits else None})
    log_project_event(db, project.id, f"contract_rule.{rule.status}", actor=f"user:{user_id}", entity_type="contract_rule",
                      entity_id=rule.id, payload={"clause_ref": rule.clause_ref, "edited": bool(edits)})
    return rule
