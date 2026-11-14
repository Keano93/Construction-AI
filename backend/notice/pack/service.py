"""Commercial pack for one project over a date range.

The latest commercial position, built from the record for a chosen period: what is due, what was notified, what is
new, and the change and claims register with QS estimates. Deadlines come from the deadline engine; no model is
involved. Notice does not keep meeting minutes or actions: the pack is the input to the meeting, not its record.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.base import project_calendar
from ..deadlines import working_days_remaining
from ..models import Claim, ContractRule, Deadline, Document, Event, Project, ReviewItem, RevisionComparison

CATEGORIES = ["change", "delay", "instruction", "disruption"]
MAX_RANGE_DAYS = 366


class PackError(ValueError):
    pass


def _money(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def build_pack(db: Session, project: Project, date_from: date, date_to: date) -> dict:
    if date_from > date_to:
        raise PackError("The start of the period must be on or before its end")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise PackError("The period can be at most a year")
    cal = project_calendar(project)

    def in_range(d: date | None) -> bool:
        return d is not None and date_from <= d <= date_to

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

    # --- notices: position at the end of the period, one row per event ---------------------------
    groups: dict[uuid.UUID, dict] = {}
    for d in sorted(deadlines, key=lambda x: x.due_date):
        e = ev_by_id[d.event_id]
        if d.status != "running" or e.status == "dismissed" or e.trigger_date > date_to:
            continue
        wd = working_days_remaining(d.due_date, date_to, cal)
        if wd > 10:
            continue
        r = rules[d.rule_id]
        g = groups.get(e.id)
        if g is None:
            rid, rstatus = review_by_event.get(e.id, (None, None))
            g = groups[e.id] = {
                "event_id": str(e.id), "event_ref": e.ref, "event_title": e.title, "category": e.category,
                "due_date": d.due_date.isoformat(), "working_days_remaining": wd,
                "bucket": "overdue" if wd < 0 else "next_5" if wd <= 5 else "next_10",
                "condition_precedent": False, "obligations": [],
                "draft_status": {"pending": "draft to review", "approved": "approved, not yet issued"}.get(rstatus or "", rstatus),
                "review_item_id": str(rid) if rid else None,
            }
        g["obligations"].append({"clause_ref": r.clause_ref, "label": d.label, "due_date": d.due_date.isoformat(),
                                 "condition_precedent": r.condition_precedent})
        g["condition_precedent"] = g["condition_precedent"] or r.condition_precedent
    notices = list(groups.values())

    issued = []
    for d in sorted(deadlines, key=lambda x: x.met_at or x.created_at):
        met = d.met_at.date() if d.met_at else None
        if d.status == "met" and in_range(met):
            e = ev_by_id[d.event_id]
            issued.append({"event_id": str(e.id), "event_ref": e.ref, "event_title": e.title, "clause_ref": rules[d.rule_id].clause_ref,
                           "obligation": d.label, "issued_on": met.isoformat(), "due_date": d.due_date.isoformat(),
                           "in_time": met <= d.due_date})

    # --- register at the end of the period -------------------------------------------------------
    claims = [c for c in db.execute(select(Claim).where(Claim.project_id == project.id).order_by(Claim.created_at)).scalars()
              if c.created_at.date() <= date_to]
    claim_of_event: dict[str, str] = {}
    for c in claims:
        for eid in c.event_ids:
            claim_of_event.setdefault(eid, c.ref)

    def notice_state(e: Event) -> tuple[str, str | None]:
        ds = by_event.get(e.id, [])
        if any(d.status == "met" and d.met_at and d.met_at.date() <= date_to for d in ds):
            return "issued", None
        running = sorted((d for d in ds if d.status in ("running", "met")), key=lambda d: d.due_date)
        if not running:
            return "none", None
        return ("overdue" if running[0].due_date < date_to else "open"), running[0].due_date.isoformat()

    def time_bar(e: Event) -> bool:
        return notice_state(e)[0] == "overdue" and any(
            rules[d.rule_id].condition_precedent and d.due_date < date_to for d in by_event.get(e.id, []) if d.status == "running")

    register = []
    for e in events:
        if e.status == "dismissed" or e.trigger_date > date_to:
            continue
        state, next_due = notice_state(e)
        register.append({
            "event_id": str(e.id), "ref": e.ref, "category": e.category, "title": e.title, "trigger_date": e.trigger_date.isoformat(),
            "status": e.status, "notice_state": state, "next_due": next_due, "time_bar_risk": time_bar(e),
            "estimated_value": _money(e.estimated_value), "value_note": e.value_note, "claim_ref": claim_of_event.get(str(e.id)),
            "review_item_id": str(review_by_event[e.id][0]) if e.id in review_by_event else None,
        })

    claims_out = []
    for c in claims:
        evs = [ev_by_id[uuid.UUID(x)] for x in c.event_ids if uuid.UUID(x) in ev_by_id]
        priced = [e.estimated_value for e in evs if e.estimated_value is not None]
        rid = db.execute(select(ReviewItem.id).where(ReviewItem.payload["claim_id"].astext == str(c.id))).scalar()
        claims_out.append({
            "id": str(c.id), "ref": c.ref, "title": c.title, "status": c.status, "created_on": c.created_at.date().isoformat(),
            "new_in_period": in_range(c.created_at.date()), "events": [e.ref for e in evs],
            "time_bar_risk": any(r.get("time_bar_risk") for r in c.notice_compliance),
            "estimated_value": _money(c.estimated_value), "events_estimate": _money(sum(priced, Decimal(0))) if priced else None,
            "review_item_id": str(rid) if rid else None,
        })

    def total(pred=lambda r: True) -> float:
        return round(sum(r["estimated_value"] or 0 for r in register if pred(r)), 2)

    totals = {
        "by_category": {c: total(lambda r, c=c: r["category"] == c) for c in CATEGORIES},
        "all": total(), "notified": total(lambda r: r["notice_state"] == "issued"),
        "not_notified": total(lambda r: r["notice_state"] in ("open", "overdue")),
        "time_bar_risk": total(lambda r: r["time_bar_risk"]),
        "unpriced_events": sum(1 for r in register if r["estimated_value"] is None),
    }
    open_rows = [r for r in register if r["status"] in ("open", "notified")]
    notice_position = {s: sum(1 for r in open_rows if r["notice_state"] == s) for s in ("issued", "open", "overdue", "none")}

    # --- new in the period -----------------------------------------------------------------------
    new_events = [r for r in register if in_range(date.fromisoformat(r["trigger_date"]))]
    new_revisions = []
    for comp in db.execute(select(RevisionComparison).where(RevisionComparison.project_id == project.id)
                           .order_by(RevisionComparison.created_at)).scalars():
        if not in_range(comp.created_at.date()):
            continue
        rev = db.get(Document, comp.revised_document_id)
        rid = db.execute(select(ReviewItem.id).where(ReviewItem.payload["comparison_id"].astext == str(comp.id))).scalar()
        pv = [c for c in comp.changes if (c.get("assessment") or {}).get("potential_variation")]
        new_revisions.append({"id": str(comp.id), "document": rev.filename, "compared_on": comp.created_at.date().isoformat(),
                              "changes": len(comp.changes), "possible_variations": len(pv),
                              "raised": sum(1 for c in pv if c.get("raised")), "understated": bool(comp.flags),
                              "review_item_id": str(rid) if rid else None})

    # events found per week (Monday-starting weeks overlapping the period)
    weekly = []
    wk = date_from - timedelta(days=date_from.weekday())
    while wk <= date_to:
        end = wk + timedelta(days=6)
        rows = [r for r in new_events if wk <= date.fromisoformat(r["trigger_date"]) <= end]
        weekly.append({"week_start": wk.isoformat(), "count": len(rows),
                       "by_category": {c: sum(1 for r in rows if r["category"] == c) for c in CATEGORIES}})
        wk += timedelta(days=7)

    return {
        "project": {"id": str(project.id), "name": project.name, "location": project.location},
        "from": date_from.isoformat(), "to": date_to.isoformat(),
        "summary": {
            "notices_overdue": sum(1 for n in notices if n["bucket"] == "overdue"),
            "notices_next_5": sum(1 for n in notices if n["bucket"] == "next_5"),
            "notices_next_10": sum(1 for n in notices if n["bucket"] == "next_10"),
            "notices_issued": len(issued), "new_events": len(new_events), "new_revisions": len(new_revisions),
            "new_possible_variations": sum(r["possible_variations"] - r["raised"] for r in new_revisions),
            "new_claims": sum(1 for c in claims_out if c["new_in_period"]),
            "open_events": len(open_rows), "estimated_total": totals["all"], "time_bar_risk": totals["time_bar_risk"],
        },
        "notices": notices, "issued": issued, "new_events": new_events, "new_revisions": new_revisions,
        "weekly": weekly, "register": register, "claims": claims_out, "totals": totals, "notice_position": notice_position,
    }
