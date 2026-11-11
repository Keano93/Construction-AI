"""Pure parts of the Claims agent: evidence blocks, notice compliance, timeline verification, document assembly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..citations import locate_quote
from .schemas import ClaimNarrative, TimelineOut


@dataclass
class Evidence:
    id: str  # E1
    item_id: str
    document_id: str
    filename: str
    channel: str
    author: str | None
    timestamp: datetime | None
    text: str
    doc_offset: int  # item start offset in the document text
    linked: bool  # directly linked to a selected event


def evidence_block(ev: list[Evidence], max_chars: int = 1500) -> str:
    out = []
    for e in ev:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M") if e.timestamp else "undated"
        text = e.text if len(e.text) <= max_chars else e.text[:max_chars] + " [...]"
        out.append(f"[{e.id}] {ts} | {e.channel} | {e.author or 'unknown'} | {e.filename}"
                   f"{' | linked to event' if e.linked else ''}\n{text}")
    return "\n\n".join(out)


# --- notice compliance (deterministic) -----------------------------------------

def notice_compliance(rows: list[dict], today: date) -> list[dict]:
    """rows: {event_ref, clause_ref, title, condition_precedent, trigger_date, due_date, status, met_on}."""
    out = []
    for r in rows:
        due = r["due_date"]
        if r["status"] == "cancelled":
            state, text = "cancelled", "clock cancelled (event dismissed)"
        elif r.get("met_on"):
            state = "given_in_time" if r["met_on"] <= due else "given_late"
            text = f"notice given {r['met_on'].isoformat()} ({'in time' if state == 'given_in_time' else f'LATE, due {due.isoformat()}'})"
        elif due < today:
            state, text = "not_given_overdue", f"NOT GIVEN - was due {due.isoformat()}"
        else:
            state, text = "not_given_open", f"not yet given - due {due.isoformat()}"
        risk = r["condition_precedent"] and state in ("not_given_overdue", "given_late")
        out.append({**{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()}, "state": state, "text": text,
                    "time_bar_risk": risk})
    return out


def compliance_block(rows: list[dict]) -> str:
    if not rows:
        return "(no notice obligations linked to these events)"
    return "\n".join(
        f"- {r['event_ref']} clause {r['clause_ref']} {r['title']}{' [CONDITION PRECEDENT]' if r['condition_precedent'] else ''}: "
        f"aware {r['trigger_date']}; {r['text']}" for r in rows)


# --- verification ----------------------------------------------------------

def verify_timeline(out: TimelineOut, evidence: list[Evidence]) -> tuple[list[dict], list[str]]:
    by_id = {e.id: e for e in evidence}
    rows, issues = [], []
    for t in out.entries:
        e = by_id.get(t.evidence_id)
        if e is None:
            issues.append(f"timeline entry cites unknown evidence {t.evidence_id}; dropped")
            continue
        span = locate_quote(e.text, t.quote, min_len=4)
        if span is None:
            issues.append(f"{t.evidence_id}: quote not found in the record; entry dropped ({t.quote[:50]!r})")
            continue
        rows.append({
            "evidence_id": e.id, "item_id": e.item_id, "document_id": e.document_id, "filename": e.filename,
            "channel": e.channel, "author": e.author, "date": e.timestamp.isoformat() if e.timestamp else None,
            "description": t.description, "significance": t.significance,
            "quote": e.text[span[0]:span[1]], "char_start": e.doc_offset + span[0], "char_end": e.doc_offset + span[1],
        })
    rows.sort(key=lambda r: (r["date"] or "9999", r["evidence_id"]))
    return rows, issues


def verify_narrative_citations(n: ClaimNarrative, evidence: list[Evidence], clauses: dict[str, tuple[str, str, int]]) -> tuple[list[dict], list[str]]:
    """clauses: clause_ref -> (document_id, clause text, clause start offset)."""
    by_id = {e.id: e for e in evidence}
    cites, issues = [], []
    for c in n.citations:
        src = c.source.strip()
        e = by_id.get(src.upper())
        if e is not None:
            span = locate_quote(e.text, c.quote, min_len=4)
            if span:
                cites.append({"document_id": e.document_id, "item_id": e.item_id, "clause_ref": None,
                              "char_start": e.doc_offset + span[0], "char_end": e.doc_offset + span[1],
                              "quote": e.text[span[0]:span[1]], "label": f"{e.id} {e.filename}", "verified": True})
                continue
        ref = src.lower().replace("clause", "").strip()
        if ref in clauses:
            doc_id, text, start = clauses[ref]
            span = locate_quote(text, c.quote, min_len=4)
            if span:
                cites.append({"document_id": doc_id, "item_id": None, "clause_ref": ref, "char_start": start + span[0],
                              "char_end": start + span[1], "quote": text[span[0]:span[1]], "label": f"Clause {ref}", "verified": True})
                continue
        issues.append(f"narrative citation not verified ({src}): {c.quote[:50]!r}")
    return cites, issues


# --- assembly ----------------------------------------------------------------

def _fmt(d: str | None) -> str:
    if not d:
        return "undated"
    return datetime.fromisoformat(d).strftime("%d %b %Y")


def assemble_body(ref: str, project: str, events: list[dict], n: ClaimNarrative, compliance: list[dict],
                  timeline: list[dict], gaps: list[str]) -> str:
    parts = [
        f"{n.title}",
        f"Project: {project}  |  Claim {ref}  |  Events: {', '.join(e['ref'] for e in events)}",
        "DRAFT FOR INTERNAL REVIEW - not issued",
        "1. Executive summary\n" + n.executive_summary,
        "2. Entitlement\n" + n.entitlement,
        "3. Notice position\n" + n.notice_position + "\n" + "\n".join(
            f"   - {r['event_ref']} clause {r['clause_ref']} {r['title']}"
            f"{' (condition precedent)' if r['condition_precedent'] else ''}: {r['text']}" for r in compliance),
        "4. Cause\n" + n.cause,
        "5. Effect\n" + n.effect,
        "6. Chronology\n" + "\n".join(
            f"   {_fmt(t['date'])}  [{t['significance']}]  {t['description']}  ({t['evidence_id']}: {t['channel']}, {t['author'] or 'unknown'}; \"{' '.join(t['quote'].split())}\")"
            for t in timeline),
        "7. Quantum\n" + "\n".join(
            f"   7.{i} {q.head}: EUR [to be quantified]. Basis: {q.basis}. Records: {', '.join(q.records_needed) or '-'}."
            for i, q in enumerate(n.quantum_heads, 1)),
        "8. Risks\n" + "\n".join(f"   - {r}" for r in n.risks),
        "9. Records still required\n" + ("\n".join(f"   - {g}" for g in gaps) if gaps else "   - none identified"),
    ]
    return "\n\n".join(parts)
