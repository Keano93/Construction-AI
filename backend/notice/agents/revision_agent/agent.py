"""Revision agent: compare two revisions, assess each change, hand potential variations to the Notice agent."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ContractRule, Document, Event, Item, Project, RevisionComparison
from ...record import audit, log_project_event
from ..base import AgentSpec, run_task, tool_approved_rules, tool_create_review_item
from ..citations import locate_quote
from ...retrieval import get_embedder
from ..identifiers import identifiers
from . import offline  # noqa: F401  (registers offline handler)
from .diff import diff_documents, revision_key
from .schemas import ChangeAssessment, RevisionAssessment

SPEC = AgentSpec(
    name="revision_agent",
    version="1.0.0",
    title="Revision agent",
    pillar="protect_the_money",
    description="Compares two revisions of a drawing register, specification or drawing; lists every change (by code), "
                "assesses scope/cost/time impact, and hands potential variations to the Notice agent.",
    inputs=["drawing_register", "spec", "drawing"],
    outputs=["change list with old/new passages", "impact assessment", "potential variation hand-off"],
    tools=["deterministic diff", "cross-reference events & documents", "llm.structured", "locate_quote", "raise_variation → Notice agent"],
)
REVISION_KINDS = {"drawing_register", "spec", "drawing"}


class RevisionError(ValueError):
    pass


# --- pairing -------------------------------------------------------------

def find_base_document(db: Session, doc: Document) -> Document | None:
    """Most recent earlier document of the same kind whose filename matches once revision markers are removed."""
    key = revision_key(doc.filename)
    if not key:
        return None
    rows = db.execute(select(Document).where(Document.project_id == doc.project_id, Document.kind == doc.kind,
                                             Document.id != doc.id, Document.created_at <= doc.created_at)
                      .order_by(Document.created_at.desc())).scalars()
    return next((d for d in rows if revision_key(d.filename) == key), None)


def candidate_pairs(db: Session, project_id: uuid.UUID) -> list[tuple[Document, Document]]:
    docs = list(db.execute(select(Document).where(Document.project_id == project_id, Document.kind.in_(REVISION_KINDS))
                           .order_by(Document.created_at)).scalars())
    by_key: dict[tuple[str, str], list[Document]] = {}
    for d in docs:
        by_key.setdefault((d.kind, revision_key(d.filename)), []).append(d)
    return [(a, b) for group in by_key.values() for a, b in zip(group, group[1:])]


# --- cross references ----------------------------------------------------

SIMILAR = 0.35  # lexical similarity above which a change and an event are shown as possibly the same matter


def _event_index(db: Session, project_id: uuid.UUID) -> list[tuple[Event, set[str], str]]:
    events = list(db.execute(select(Event).where(Event.project_id == project_id, Event.status.in_(["open", "notified"]))).scalars())
    out = []
    for e in events:
        text = f"{e.title} {e.description}"
        ids = identifiers(text)
        if e.related_item_ids:
            for it in db.execute(select(Item.text).where(Item.id.in_([uuid.UUID(x) for x in e.related_item_ids]))).scalars():
                ids |= identifiers(it)
                text += " " + it
        out.append((e, ids, text))
    return out


def _cross_refs(db: Session, project_id: uuid.UUID, change: dict, events, exclude: set[uuid.UUID]) -> dict:
    ids = set(change["identifiers"])
    emb = get_embedder()
    cvec = emb.embed(f"{change['label']} {change['new_text'] or change['old_text']}")
    evs = []
    for e, eids, etext in events:
        if ids & eids:
            evs.append({"ref": e.ref, "title": e.title, "status": e.status, "id": str(e.id), "match": "identifier",
                        "on": sorted(ids & eids)})
        else:
            sim = sum(a * b for a, b in zip(cvec, emb.embed(etext)))
            if sim >= SIMILAR:
                evs.append({"ref": e.ref, "title": e.title, "status": e.status, "id": str(e.id), "match": "similar",
                            "similarity": round(sim, 2)})
    docs = []
    if ids:
        for d in db.execute(select(Document.id, Document.filename).where(Document.project_id == project_id)).all():
            if d.id not in exclude and any(i in d.filename.upper() for i in ids if "-" in i):
                docs.append({"id": str(d.id), "filename": d.filename})
    return {"events": evs, "documents": docs}


# --- compare -------------------------------------------------------------

def _changes_block(changes: list[dict]) -> str:
    lines = []
    for c in changes:
        lines.append(f"[{c['id']}] {c['kind'].upper()} {c['label']}")
        if c["fields"]:
            lines.append("  fields: " + "; ".join(f"{k}: '{v[0]}' -> '{v[1]}'" for k, v in c["fields"].items()))
        else:
            if c["old_text"]:
                lines.append(f"  OLD: {c['old_text']}")
            if c["new_text"]:
                lines.append(f"  NEW: {c['new_text']}")
        if c["cross_refs"]["events"]:
            lines.append("  already on the event register: " + ", ".join(f"{e['ref']} {e['title']}" for e in c["cross_refs"]["events"]))
    return "\n".join(lines)


def run_revision_compare(db: Session, base_id: uuid.UUID, revised_id: uuid.UUID, user_id: uuid.UUID | None = None) -> RevisionComparison:
    base, revised = db.get(Document, base_id), db.get(Document, revised_id)
    if base is None or revised is None or base.project_id != revised.project_id:
        raise RevisionError("Both documents must exist in the same project")
    if base.id == revised.id or base.sha256 == revised.sha256:
        raise RevisionError("Choose two different revisions")
    project = db.get(Project, base.project_id)
    method, diff = diff_documents(base.text, revised.text)
    changes = [c.to_dict() for c in diff]
    events = _event_index(db, project.id)
    for c in changes:
        c["cross_refs"] = _cross_refs(db, project.id, c, events, {base.id, revised.id})
        c["raised"] = None

    comparison = RevisionComparison(project_id=project.id, base_document_id=base.id, revised_document_id=revised.id,
                                    method=method, created_by=user_id)
    db.add(comparison)
    db.flush()
    if not changes:
        comparison.summary = "No differences found."
        log_project_event(db, project.id, "revision.compared", actor=f"agent:{SPEC.name}", entity_type="revision_comparison",
                          entity_id=comparison.id, payload={"changes": 0})
        return comparison

    out, run = run_task(
        db, spec=SPEC, project_id=project.id, task="assess_changes", prompt_agent="revision_agent",
        variables={"project": f"{project.name}, {project.location or ''}", "base_filename": base.filename,
                   "revised_filename": revised.filename, "method": method, "changes": _changes_block(changes), "_changes": changes},
        schema=RevisionAssessment, inputs={"base_document_id": str(base.id), "revised_document_id": str(revised.id), "changes": len(changes)},
    )
    comparison.agent_run_id = run.id
    by_id = {a.change_id: a for a in out.assessments}
    issues = []
    citations = []
    for c in changes:
        a: ChangeAssessment | None = by_id.get(c["id"])
        if a is None:
            issues.append(f"{c['id']}: no assessment returned; marked unclear")
            a = ChangeAssessment(change_id=c["id"], summary=c["label"], change_type="unclear", cost_impact="unknown",
                                 time_impact="unknown", affected_packages=[], potential_variation=True,
                                 rationale="Not assessed - review manually.", evidence_quote_old=None, evidence_quote_new=None,
                                 confidence=0.3)
        ad = a.model_dump()
        ad["quote_issues"] = []
        for side, doc, span_key, text_key in (("old", base, "old_span", "old_text"), ("new", revised, "new_span", "new_text")):
            q = ad[f"evidence_quote_{side}"]
            span = c[span_key]
            if not span:
                continue
            local = locate_quote(c[text_key], q, min_len=1) if q else None
            if q and local is None:
                ad["quote_issues"].append(f"{side} quote not found: {q[:50]!r}")
                ad["confidence"] = round(ad["confidence"] * 0.8, 3)
            s, e = (span[0] + local[0], span[0] + local[1]) if local else (span[0], span[1])
            if a.potential_variation:
                citations.append({"document_id": str(doc.id), "item_id": None, "clause_ref": None, "char_start": s, "char_end": e,
                                  "quote": doc.text[s:e], "label": f"{c['id']} {'previous' if side == 'old' else 'revised'}: {doc.filename}",
                                  "verified": True})
        c["assessment"] = ad
    comparison.changes = changes
    comparison.summary = out.overall_summary
    comparison.flags = out.downplaying_flags
    db.flush()

    pv = [c for c in changes if c["assessment"]["potential_variation"]]
    confs = [c["assessment"]["confidence"] for c in (pv or changes)]
    conf = sum(confs) / len(confs)
    new_unflagged = [c for c in pv if not c["cross_refs"]["events"]]
    title = (f"Revision: {base.filename} → {revised.filename} — {len(changes)} change(s), {len(pv)} potential variation(s)"
             + (f", {len(new_unflagged)} not yet on the register" if pv else ""))
    tool_create_review_item(
        db, project_id=project.id, spec=SPEC, run=run, kind="revision_comparison", category="change" if pv else None,
        title=title[:400], summary=out.overall_summary, confidence=conf, citations=citations,
        payload={"comparison_id": str(comparison.id), "method": method, "flags": out.downplaying_flags, "issues": issues,
                 "base": {"id": str(base.id), "filename": base.filename}, "revised": {"id": str(revised.id), "filename": revised.filename},
                 "counts": {"changes": len(changes), "potential_variations": len(pv), "not_on_register": len(new_unflagged)}},
    )
    log_project_event(db, project.id, "revision.compared", actor=f"agent:{SPEC.name}", entity_type="revision_comparison",
                      entity_id=comparison.id, payload={"changes": len(changes), "potential_variations": len(pv)})
    return comparison


# --- hand-off to the Notice agent -------------------------------------------

def _change_rules(db: Session, project_id: uuid.UUID) -> list[ContractRule]:
    rules = [r for r in tool_approved_rules(db, project_id, ["change"]) if r.rule_type in ("notice", "time_bar")]
    special = ("site conditions", "discrepanc", "ambiguit", "oral", "other than")
    general = [r for r in rules if not any(s in r.title.lower() for s in special)]
    general.sort(key=lambda r: (0 if "change" in r.title.lower() else 1, "claim" in r.title.lower(), r.period_value or 99))
    return general[:2]


def raise_variation(db: Session, comparison_id: uuid.UUID, change_id: str, user_id: uuid.UUID, *,
                    force_new: bool = False, trigger_date: date | None = None) -> dict:
    from ..notice_agent.agent import open_event  # avoid import cycle

    comp = db.get(RevisionComparison, comparison_id)
    if comp is None:
        raise RevisionError("Comparison not found")
    changes = [dict(c) for c in comp.changes]
    change = next((c for c in changes if c["id"] == change_id), None)
    if change is None:
        raise RevisionError(f"Unknown change {change_id}")
    if change.get("raised"):
        raise RevisionError(f"Already handled: {change['raised']}")
    project = db.get(Project, comp.project_id)
    base, revised = db.get(Document, comp.base_document_id), db.get(Document, comp.revised_document_id)
    item = revised.items[0]
    a = change.get("assessment") or {}

    if not force_new:
        events = _event_index(db, project.id)
        # attach automatically only on a shared identifier (drawing no., grid ref, RFI); similarity is only a hint
        match = next((e for e, ids, _ in events if set(change["identifiers"]) & ids), None)
        if match is not None:
            if str(item.id) not in match.related_item_ids:
                match.related_item_ids = [*match.related_item_ids, str(item.id)]
            change["raised"] = {"mode": "attached", "event_ref": match.ref, "event_id": str(match.id)}
            comp.changes = changes
            log_project_event(db, project.id, "event.evidence_added", actor=f"user:{user_id}", entity_type="event",
                              entity_id=match.id, payload={"from_revision": str(comp.id), "change": change_id})
            audit(db, action="revision.attach_to_event", actor_type="user", actor_id=str(user_id), org_id=project.org_id,
                  project_id=project.id, entity_type="event", entity_id=match.id,
                  source_refs=[{"document_id": str(revised.id), "char_start": (change["new_span"] or [None])[0]}],
                  details={"comparison": str(comp.id), "change": change_id})
            return change["raised"]

    if trigger_date is None:
        if change.get("issue_date"):
            try:
                trigger_date = date.fromisoformat(change["issue_date"][:10])
            except ValueError:
                trigger_date = None
        trigger_date = trigger_date or (revised.doc_timestamp or revised.created_at).date()

    evidence = []
    for side, doc, span in (("new", revised, change["new_span"]), ("old", base, change["old_span"])):
        if span:
            evidence.append({"document_id": str(doc.id), "item_id": str(doc.items[0].id) if doc.items else None, "clause_ref": None,
                             "char_start": span[0], "char_end": span[1], "quote": doc.text[span[0]:span[1]],
                             "label": f"{'Revised' if side == 'new' else 'Previous'}: {doc.filename}", "verified": True})
    summary = f"{a.get('summary', change['label'])} {a.get('rationale', '')}".strip()
    title = f"{change['label']} ({base.filename} → {revised.filename})"
    result = open_event(
        db, project=project, parties=list(project.parties), item=item, doc=revised, run=None, category="change",
        title=title, summary=summary, trigger_date=trigger_date, rules=_change_rules(db, project.id),
        confidence=float(a.get("confidence", 0.5)), evidence_citations=evidence,
        evidence_quote=change["new_text"] or change["label"], issues=[],
        payload_extra={"origin": {"agent": SPEC.name, "comparison_id": str(comp.id), "change_id": change_id,
                                  "trigger_basis": "drawing issue date" if change.get("issue_date") else "revision received"}},
        actor=f"user:{user_id}",
    )
    similar = [x["ref"] for x in change.get("cross_refs", {}).get("events", []) if x.get("match") == "similar"]
    change["raised"] = {"mode": "new_event", "event_ref": result["event"], "event_id": result["event_id"],
                        "review_item": result["review_item"], "possibly_related": similar}
    comp.changes = changes
    audit(db, action="revision.raise_variation", actor_type="user", actor_id=str(user_id), org_id=project.org_id,
          project_id=project.id, entity_type="event", entity_id=result["event_id"],
          source_refs=[{"document_id": e["document_id"], "char_start": e["char_start"], "char_end": e["char_end"]} for e in evidence],
          details={"comparison": str(comp.id), "change": change_id})
    return change["raised"]
