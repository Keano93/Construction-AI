"""Plain-dict serialisers for API responses."""

from __future__ import annotations

from datetime import date

from ..models import (
    Contract,
    ContractClause,
    ContractRule,
    Deadline,
    Document,
    Draft,
    Event,
    Item,
    Project,
    ReviewItem,
)


def iso(v):
    return v.isoformat() if v is not None else None


def project(p: Project) -> dict:
    return {
        "id": str(p.id), "name": p.name, "code": p.code, "location": p.location, "contract_form": p.contract_form,
        "our_role": p.our_role, "holiday_region": p.holiday_region, "working_weekdays": p.working_weekdays,
        "start_date": iso(p.start_date),
        "shutdowns": [{"id": str(s.id), "name": s.name, "start": iso(s.start), "end": iso(s.end)} for s in p.shutdowns],
        "parties": [{"id": str(x.id), "name": x.name, "organisation": x.organisation, "role": x.role, "email": x.email} for x in p.parties],
    }


def document(d: Document, with_text: bool = False) -> dict:
    out = {
        "id": str(d.id), "kind": d.kind, "source": d.source, "filename": d.filename, "mime": d.mime, "author": d.author,
        "doc_timestamp": iso(d.doc_timestamp), "sha256": d.sha256, "size_bytes": d.size_bytes,
        "extraction_method": d.extraction_method, "meta": d.meta, "created_at": iso(d.created_at), "items": len(d.items),
    }
    if with_text:
        out["text"] = d.text
        out["item_list"] = [item(i) for i in d.items]
    return out


def item(i: Item) -> dict:
    return {"id": str(i.id), "document_id": str(i.document_id), "seq": i.seq, "kind": i.kind, "author": i.author,
            "recipients": i.recipients, "subject": i.subject, "timestamp": iso(i.timestamp), "text": i.text,
            "char_start": i.char_start, "char_end": i.char_end, "sha256": i.sha256}


def rule(r: ContractRule) -> dict:
    return {
        "id": str(r.id), "contract_id": str(r.contract_id), "clause_id": str(r.clause_id) if r.clause_id else None,
        "rule_type": r.rule_type, "clause_ref": r.clause_ref, "title": r.title, "summary": r.summary,
        "trigger_event": r.trigger_event, "event_categories": r.event_categories, "period_value": r.period_value,
        "period_unit": r.period_unit, "recipient": r.recipient, "required_form": r.required_form,
        "condition_precedent": r.condition_precedent, "details": r.details, "source_quote": r.source_quote,
        "source_char_start": r.source_char_start, "source_char_end": r.source_char_end, "confidence": r.confidence,
        "status": r.status, "reviewed_at": iso(r.reviewed_at), "edited": r.original is not None and _edited(r),
    }


def _edited(r: ContractRule) -> bool:
    o = r.original or {}
    return any(o.get(k) != getattr(r, k) for k in ("clause_ref", "period_value", "period_unit", "rule_type", "condition_precedent") if k in o)


def clause(c: ContractClause) -> dict:
    return {"id": str(c.id), "ref": c.ref, "title": c.title, "text": c.text, "char_start": c.char_start, "char_end": c.char_end}


def contract(c: Contract, full: bool = True) -> dict:
    out = {"id": str(c.id), "document_id": str(c.document_id), "form": c.form, "title": c.title, "status": c.status,
           "created_at": iso(c.created_at)}
    if full:
        out["clauses"] = [clause(x) for x in c.clauses]
        out["rules"] = [rule(x) for x in sorted(c.rules, key=lambda r: ([int(p) for p in r.clause_ref.split(".") if p.isdigit()], r.title))]
    return out


def deadline(d: Deadline, today: date | None = None, remaining: int | None = None) -> dict:
    out = {"id": str(d.id), "event_id": str(d.event_id), "rule_id": str(d.rule_id), "label": d.label,
           "trigger_date": iso(d.trigger_date), "due_date": iso(d.due_date), "trace": d.trace, "status": d.status,
           "met_at": iso(d.met_at)}
    if remaining is not None:
        out["working_days_remaining"] = remaining
    return out


def event(e: Event) -> dict:
    return {"id": str(e.id), "ref": e.ref, "category": e.category, "title": e.title, "description": e.description,
            "trigger_date": iso(e.trigger_date), "status": e.status, "source_item_id": str(e.source_item_id) if e.source_item_id else None,
            "related_item_ids": e.related_item_ids, "created_at": iso(e.created_at)}


def draft(d: Draft) -> dict:
    return {"id": str(d.id), "kind": d.kind, "subject": d.subject, "recipient": d.recipient, "body": d.body,
            "version": d.version, "status": d.status, "approved_at": iso(d.approved_at)}


def review_item(r: ReviewItem) -> dict:
    return {
        "id": str(r.id), "agent": r.agent, "kind": r.kind, "category": r.category, "title": r.title, "summary": r.summary,
        "confidence": r.confidence, "low_confidence": r.low_confidence, "status": r.status, "priority_date": iso(r.priority_date),
        "event_id": str(r.event_id) if r.event_id else None, "draft_id": str(r.draft_id) if r.draft_id else None,
        "source_item_id": str(r.source_item_id) if r.source_item_id else None, "citations": r.citations,
        "payload": r.payload, "created_at": iso(r.created_at), "decided_at": iso(r.decided_at),
    }
