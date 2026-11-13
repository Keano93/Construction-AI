"""Weekly commercial meeting pack for one project.

Everything here is computed from the record: deadlines come from the deadline engine, notice status from the
deadline rows, values from QS-entered estimates. No model is involved.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agents.base import project_calendar
from ..deadlines import working_days_remaining
from ..models import Claim, ContractRule, Deadline, Document, Event, MeetingItem, Project, ReviewItem, RevisionComparison

CATEGORIES = ["change", "delay", "instruction", "disruption"]


def _money(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def week_bounds(d: date) -> tuple[date, date, date]:
    """(Monday of this week, Sunday of this week, Sunday of next week)."""
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6), monday + timedelta(days=13)


def previous_meeting(db: Session, project_id: uuid.UUID, meeting_date: date) -> date | None:
    return db.execute(select(func.max(MeetingItem.meeting_date)).where(
        MeetingItem.project_id == project_id, MeetingItem.meeting_date < meeting_date)).scalar()


def _item(m: MeetingItem) -> dict:
    return {"id": str(m.id), "kind": m.kind, "text": m.text, "owner": m.owner, "due_date": m.due_date.isoformat() if m.due_date else None,
            "status": m.status, "meeting_date": m.meeting_date.isoformat(), "closed_on": m.closed_on.isoformat() if m.closed_on else None,
            "event_id": str(m.event_id) if m.event_id else None, "claim_id": str(m.claim_id) if m.claim_id else None}


def build_pack(db: Session, project: Project, meeting_date: date) -> dict:
    cal = project_calendar(project)
    prev = previous_meeting(db, project.id, meeting_date)
    since = prev or meeting_date - timedelta(days=7)
    _, end_this_week, end_next_week = week_bounds(meeting_date)

    events = list(db.execute(select(Event).where(Event.project_id == project.id).order_by(Event.trigger_date)).scalars())
    ev_by_id = {e.id: e for e in events}
    review_by_event = {eid: (rid, st) for eid, rid, st in db.execute(
        select(ReviewItem.event_id, ReviewItem.id, ReviewItem.status)
        .where(ReviewItem.project_id == project.id, ReviewItem.kind == "notice_flag"))}
    deadlines = list(db.execute(select(Deadline).where(Deadline.project_id == project.id)).scalars())
    rules = {r.id: r for r in db.execute(select(ContractRule).where(ContractRule.project_id == project.id)).scalars()}
    by_event: dict[uuid.UUID, list[Deadline]] = {}
    for d in deadlines:
        by_event.setdefault(d.event_id, []).append(d)

    # 1. notices: one row per event with running clocks that are overdue or due by the end of next week
    groups: dict[uuid.UUID, dict] = {}
    for d in sorted(deadlines, key=lambda x: x.due_date):
        e = ev_by_id[d.event_id]
        if d.status != "running" or e.status == "dismissed" or d.due_date > end_next_week:
            continue
        r = rules[d.rule_id]
        g = groups.get(e.id)
        if g is None:
            rid, rstatus = review_by_event.get(e.id, (None, None))
            bucket = "overdue" if d.due_date < meeting_date else "this_week" if d.due_date <= end_this_week else "next_week"
            g = groups[e.id] = {
                "event_id": str(e.id), "event_ref": e.ref, "event_title": e.title, "category": e.category,
                "due_date": d.due_date.isoformat(), "working_days_remaining": working_days_remaining(d.due_date, meeting_date, cal),
                "bucket": bucket, "condition_precedent": False, "obligations": [],
                "draft_status": {"pending": "draft to review", "approved": "approved, not yet issued"}.get(rstatus or "", rstatus),
                "review_item_id": str(rid) if rid else None,
            }
        g["obligations"].append({"clause_ref": r.clause_ref, "label": d.label, "due_date": d.due_date.isoformat(),
                                 "condition_precedent": r.condition_precedent})
        g["condition_precedent"] = g["condition_precedent"] or r.condition_precedent
    notices = list(groups.values())

    # 3. register (computed first: section 2 reuses notice state)
    claims = list(db.execute(select(Claim).where(Claim.project_id == project.id).order_by(Claim.created_at)).scalars())
    claim_of_event: dict[str, str] = {}
    for c in claims:
        for eid in c.event_ids:
            claim_of_event.setdefault(eid, c.ref)

    def notice_state(e: Event) -> tuple[str, str | None]:
        ds = by_event.get(e.id, [])
        if any(d.status == "met" for d in ds):
            return "issued", None
        running = sorted((d for d in ds if d.status == "running"), key=lambda d: d.due_date)
        if not running:
            return "none", None
        return ("overdue" if running[0].due_date < meeting_date else "open"), running[0].due_date.isoformat()

    def time_bar(e: Event) -> bool:
        return any(d.status == "running" and d.due_date < meeting_date and rules[d.rule_id].condition_precedent
                   for d in by_event.get(e.id, []))

    register = []
    for e in events:
        if e.status == "dismissed":
            continue
        state, next_due = notice_state(e)
        register.append({
            "event_id": str(e.id), "ref": e.ref, "category": e.category, "title": e.title, "trigger_date": e.trigger_date.isoformat(),
            "status": e.status, "notice_state": state, "next_due": next_due, "time_bar_risk": time_bar(e),
            "estimated_value": _money(e.estimated_value), "value_note": e.value_note,
            "claim_ref": claim_of_event.get(str(e.id)),
            "review_item_id": str(review_by_event[e.id][0]) if e.id in review_by_event else None,
        })

    claims_out = []
    for c in claims:
        evs = [ev_by_id[uuid.UUID(x)] for x in c.event_ids if uuid.UUID(x) in ev_by_id]
        events_sum = sum((e.estimated_value for e in evs if e.estimated_value is not None), Decimal(0))
        rid = db.execute(select(ReviewItem.id).where(ReviewItem.payload["claim_id"].astext == str(c.id))).scalar()
        claims_out.append({
            "id": str(c.id), "ref": c.ref, "title": c.title, "status": c.status,
            "events": [e.ref for e in evs], "time_bar_risk": any(r.get("time_bar_risk") for r in c.notice_compliance),
            "estimated_value": _money(c.estimated_value), "events_estimate": _money(events_sum) if any(e.estimated_value is not None for e in evs) else None,
            "review_item_id": str(rid) if rid else None,
        })

    def total(rows, pred=lambda r: True) -> float:
        return round(sum(r["estimated_value"] or 0 for r in rows if pred(r)), 2)

    totals = {
        "by_category": {c: total(register, lambda r, c=c: r["category"] == c) for c in CATEGORIES},
        "all": total(register),
        "notified": total(register, lambda r: r["notice_state"] == "issued"),
        "not_notified": total(register, lambda r: r["notice_state"] in ("open", "overdue")),
        "time_bar_risk": total(register, lambda r: r["time_bar_risk"]),
        "unpriced_events": sum(1 for r in register if r["estimated_value"] is None),
    }

    # 2. new since last meeting
    new_events = [r for r in register if since < date.fromisoformat(r["trigger_date"]) <= meeting_date]
    new_revisions = []
    for comp in db.execute(select(RevisionComparison).where(RevisionComparison.project_id == project.id)
                           .order_by(RevisionComparison.created_at)).scalars():
        if not (since < comp.created_at.date() <= meeting_date):
            continue
        rev = db.get(Document, comp.revised_document_id)
        rid = db.execute(select(ReviewItem.id).where(ReviewItem.payload["comparison_id"].astext == str(comp.id))).scalar()
        pv = [c for c in comp.changes if (c.get("assessment") or {}).get("potential_variation")]
        new_revisions.append({"id": str(comp.id), "document": rev.filename, "changes": len(comp.changes), "possible_variations": len(pv),
                              "raised": sum(1 for c in pv if c.get("raised")), "understated": bool(comp.flags),
                              "review_item_id": str(rid) if rid else None})

    # 4. decisions and actions
    items = list(db.execute(select(MeetingItem).where(MeetingItem.project_id == project.id)
                            .order_by(MeetingItem.meeting_date, MeetingItem.created_at)).scalars())
    actions_open = [_item(m) for m in items if m.kind == "action" and m.status == "open" and m.meeting_date <= meeting_date]
    actions_closed = [_item(m) for m in items if m.kind == "action" and m.status in ("done", "cancelled")
                      and m.closed_on and since < m.closed_on <= meeting_date]
    decisions_now = [_item(m) for m in items if m.kind == "decision" and m.meeting_date == meeting_date]
    decisions_prev = [_item(m) for m in items if m.kind == "decision" and prev and m.meeting_date == prev]
    for a in actions_open:
        a["overdue"] = bool(a["due_date"] and a["due_date"] < meeting_date.isoformat())

    return {
        "project": {"id": str(project.id), "name": project.name, "location": project.location},
        "meeting_date": meeting_date.isoformat(), "since": since.isoformat(), "previous_meeting": prev.isoformat() if prev else None,
        "summary": {
            "notices_overdue": sum(1 for n in notices if n["bucket"] == "overdue"),
            "notices_this_week": sum(1 for n in notices if n["bucket"] == "this_week"),
            "notices_next_week": sum(1 for n in notices if n["bucket"] == "next_week"),
            "new_events": len(new_events), "new_possible_variations": sum(r["possible_variations"] - r["raised"] for r in new_revisions),
            "open_events": sum(1 for r in register if r["status"] == "open"), "claims": len(claims_out),
            "actions_open": len(actions_open), "actions_overdue": sum(1 for a in actions_open if a["overdue"]),
        },
        "notices": notices, "new_events": new_events, "new_revisions": new_revisions,
        "register": register, "claims": claims_out, "totals": totals,
        "actions_open": actions_open, "actions_closed": actions_closed,
        "decisions": decisions_now, "previous_decisions": decisions_prev,
    }
