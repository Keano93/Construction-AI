"""Meeting pack export (PDF and Word) from the same data the meeting page shows."""

from __future__ import annotations

import io
from datetime import date

CAT = {"change": "Change", "delay": "Delay", "instruction": "Instruction", "disruption": "Disruption"}
STATE = {"issued": "Notified", "overdue": "Notice overdue", "open": "Notice due", "none": "No notice clock"}


def _d(s: str | None) -> str:
    return date.fromisoformat(s[:10]).strftime("%d %b %Y") if s else "-"


def _eur(v: float | None) -> str:
    return f"EUR {v:,.0f}" if v is not None else "-"


def _due(n: dict) -> str:
    wd = n["working_days_remaining"]
    return f"overdue {-wd} WD" if wd < 0 else "due today" if wd == 0 else f"{wd} WD left"


def sections(p: dict) -> list[tuple[str, str | None, list[str], list[list[str]]]]:
    """(heading, intro, table header, rows) for each agenda item; shared by both formats."""
    s = p["summary"]
    t = p["totals"]
    since = f"since the last meeting on {_d(p['previous_meeting'])}" if p["previous_meeting"] else f"since {_d(p['since'])}"
    out = [
        ("1. Notices", f"{s['notices_overdue']} overdue, {s['notices_this_week']} due this week, {s['notices_next_week']} due next week.",
         ["Due", "Status", "Event", "Clauses", "Draft"],
         [[_d(n["due_date"]), _due(n), f"{n['event_ref']} {n['event_title']}",
           ", ".join(o["clause_ref"] + (" (CP)" if o["condition_precedent"] else "") for o in n["obligations"]), n["draft_status"] or "-"]
          for n in p["notices"]]),
        ("2. New " + since, f"{s['new_events']} new event(s); {len(p['new_revisions'])} drawing/specification revision(s).",
         ["Aware", "Ref", "Event", "Type", "Notice"],
         [[_d(e["trigger_date"]), e["ref"], e["title"], CAT.get(e["category"], e["category"]), STATE[e["notice_state"]]] for e in p["new_events"]]
         + [["-", "Revision", r["document"], f"{r['possible_variations']} possible variation(s)", f"{r['raised']} raised"] for r in p["new_revisions"]]),
        ("3. Change and claims register",
         f"Estimated total {_eur(t['all'])}: notified {_eur(t['notified'])}, not yet notified {_eur(t['not_notified'])}, "
         f"at time-bar risk {_eur(t['time_bar_risk'])}. {t['unpriced_events']} event(s) not yet estimated. Estimates are QS figures, excl. VAT.",
         ["Ref", "Event", "Type", "Notice", "Estimate"],
         [[r["ref"], r["title"] + (f" [{r['claim_ref']}]" if r["claim_ref"] else ""), CAT.get(r["category"], r["category"]),
           STATE[r["notice_state"]] + (" - TIME-BAR RISK" if r["time_bar_risk"] else ""), _eur(r["estimated_value"])] for r in p["register"]]
         + [[c["ref"], c["title"], "Claim", c["status"] + (" - TIME-BAR RISK" if c["time_bar_risk"] else ""),
             _eur(c["estimated_value"] if c["estimated_value"] is not None else c["events_estimate"])] for c in p["claims"]]),
        ("4. Actions carried forward", f"{s['actions_open']} open, {s['actions_overdue']} overdue.",
         ["Action", "Owner", "Due", "Raised"],
         [[a["text"], a["owner"] or "-", _d(a["due_date"]) + (" (overdue)" if a.get("overdue") else ""), _d(a["meeting_date"])] for a in p["actions_open"]]),
        ("5. Decisions", None, ["Decision", "Recorded"], [[d["text"], _d(d["meeting_date"])] for d in p["decisions"]]),
    ]
    if p["actions_closed"]:
        out.insert(4, ("Actions closed " + since, None, ["Action", "Owner", "Closed"],
                       [[a["text"], a["owner"] or "-", _d(a["closed_on"])] for a in p["actions_closed"]]))
    return out


WEIGHT = {"Event": 4.0, "Action": 5.0, "Decision": 8.0, "Clauses": 1.6, "Notice": 1.8, "Draft": 1.6, "Status": 1.2, "Type": 1.4}


def _widths(head: list[str], total: float) -> list[float]:
    w = [WEIGHT.get(h, 1.0) for h in head]
    return [total * x / sum(w) for x in w]


def to_pdf(p: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    st = getSampleStyleSheet()
    cell = st["BodyText"].clone("cell", fontSize=8.5, leading=10.5)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Commercial meeting {p['meeting_date']}")

    def esc(x: str) -> str:
        return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    flow = [Paragraph(f"Commercial meeting - {esc(p['project']['name'])}", st["Title"]),
            Paragraph(f"{_d(p['meeting_date'])} &nbsp;·&nbsp; {esc(p['project']['location'] or '')} &nbsp;·&nbsp; prepared by Notice from the project record", st["Normal"]),
            Spacer(1, 8)]
    for heading, intro, head, rows in sections(p):
        flow.append(Paragraph(esc(heading), st["Heading2"]))
        if intro:
            flow.append(Paragraph(esc(intro), st["Normal"]))
        if rows:
            data = [[Paragraph(f"<b>{esc(h)}</b>", cell) for h in head]] + [[Paragraph(esc(c), cell) for c in r] for r in rows]
            tbl = Table(data, repeatRows=1, hAlign="LEFT", colWidths=_widths(head, doc.width))
            tbl.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                                     ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
                                     ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            flow.append(Spacer(1, 4))
            flow.append(tbl)
        else:
            flow.append(Paragraph("None.", st["Normal"]))
        flow.append(Spacer(1, 8))
    doc.build(flow)
    return buf.getvalue()


def to_docx(p: dict) -> bytes:
    import docx
    from docx.enum.section import WD_ORIENT
    from docx.shared import Pt

    d = docx.Document()
    sec = d.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10)
    d.add_heading(f"Commercial meeting - {p['project']['name']}", 0)
    d.add_paragraph(f"{_d(p['meeting_date'])} · {p['project']['location'] or ''} · prepared by Notice from the project record")
    for heading, intro, head, rows in sections(p):
        d.add_heading(heading, 2)
        if intro:
            d.add_paragraph(intro)
        if not rows:
            d.add_paragraph("None.")
            continue
        t = d.add_table(rows=1, cols=len(head))
        t.style = "Light List"
        for i, h in enumerate(head):
            t.rows[0].cells[i].text = h
        for r in rows:
            cells = t.add_row().cells
            for i, c in enumerate(r):
                cells[i].text = str(c)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
