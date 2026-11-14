"""Commercial pack export (PDF and Word) from the same data the pack page shows."""

from __future__ import annotations

import io
from datetime import date

CAT = {"change": "Change", "delay": "Delay", "instruction": "Instruction", "disruption": "Disruption"}
STATE = {"issued": "Notified", "overdue": "Notice overdue", "open": "Notice due", "none": "No notice clock"}
INK, MUTED, BAR, URGENT = "#171717", "#737373", "#525252", "#dc2626"


def _d(s: str | None) -> str:
    return date.fromisoformat(s[:10]).strftime("%d %b %Y") if s else "-"


def _eur(v: float | None) -> str:
    return f"EUR {v:,.0f}" if v is not None else "-"


def _due(n: dict) -> str:
    wd = n["working_days_remaining"]
    return f"overdue {-wd} WD" if wd < 0 else "due today" if wd == 0 else f"{wd} WD left"


def headline(p: dict) -> list[tuple[str, str]]:
    s = p["summary"]
    return [("Notices overdue", str(s["notices_overdue"])), ("Due in 10 working days", str(s["notices_next_5"] + s["notices_next_10"])),
            ("Notices issued", str(s["notices_issued"])), ("New events", str(s["new_events"])),
            ("Estimated value", _eur(s["estimated_total"])), ("At time-bar risk", _eur(s["time_bar_risk"]))]


def sections(p: dict) -> list[tuple[str, str | None, list[str], list[list[str]]]]:
    """(heading, intro, table header, rows) for each section; shared by both formats."""
    s, t = p["summary"], p["totals"]
    out = [
        ("1. Notices", f"Position at {_d(p['to'])}: {s['notices_overdue']} overdue, {s['notices_next_5']} due within 5 working days, "
         f"{s['notices_next_10']} due within 10.",
         ["Due", "Status", "Event", "Clauses", "Draft"],
         [[_d(n["due_date"]), _due(n), f"{n['event_ref']} {n['event_title']}",
           ", ".join(o["clause_ref"] + (" (CP)" if o["condition_precedent"] else "") for o in n["obligations"]), n["draft_status"] or "-"]
          for n in p["notices"]]),
        ("2. Notices issued in the period", None, ["Issued", "Event", "Clause", "Due", "In time"],
         [[_d(i["issued_on"]), f"{i['event_ref']} {i['event_title']}", i["clause_ref"], _d(i["due_date"]), "yes" if i["in_time"] else "LATE"]
          for i in p["issued"]]),
        ("3. New in the period", f"{s['new_events']} event(s), {s['new_revisions']} revision(s), {s['new_claims']} claim(s).",
         ["Date", "Ref", "Item", "Type", "Position"],
         [[_d(e["trigger_date"]), e["ref"], e["title"], CAT.get(e["category"], e["category"]), STATE[e["notice_state"]]] for e in p["new_events"]]
         + [[_d(r["compared_on"]), "Revision", r["document"], f"{r['possible_variations']} possible variation(s)", f"{r['raised']} raised"] for r in p["new_revisions"]]
         + [[_d(c["created_on"]), c["ref"], c["title"], "Claim", "time-bar risk" if c["time_bar_risk"] else c["status"]] for c in p["claims"] if c["new_in_period"]]),
        ("4. Change and claims register",
         f"At {_d(p['to'])}: estimated {_eur(t['all'])} - notified {_eur(t['notified'])}, not yet notified {_eur(t['not_notified'])}, "
         f"at time-bar risk {_eur(t['time_bar_risk'])}. {t['unpriced_events']} event(s) not yet estimated. QS estimates, excl. VAT.",
         ["Ref", "Event", "Type", "Notice", "Estimate"],
         [[r["ref"], r["title"] + (f" [{r['claim_ref']}]" if r["claim_ref"] else ""), CAT.get(r["category"], r["category"]),
           STATE[r["notice_state"]] + (" - TIME-BAR RISK" if r["time_bar_risk"] else ""), _eur(r["estimated_value"])] for r in p["register"]]
         + [[c["ref"], c["title"], "Claim", c["status"] + (" - TIME-BAR RISK" if c["time_bar_risk"] else ""),
             _eur(c["estimated_value"] if c["estimated_value"] is not None else c["events_estimate"])] for c in p["claims"]]),
    ]
    return out


WEIGHT = {"Event": 4.0, "Item": 4.0, "Clauses": 1.6, "Notice": 1.8, "Draft": 1.6, "Status": 1.2, "Type": 1.4, "Position": 1.4}


def _widths(head: list[str], total: float) -> list[float]:
    w = [WEIGHT.get(h, 1.0) for h in head]
    return [total * x / sum(w) for x in w]


def _charts(p: dict, width: float):
    """Two small charts: events found per week (columns) and estimated value by type (bars). Single hue, no legend."""
    from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors

    half = width / 2 - 10
    d = Drawing(width, 150)
    weeks = p["weekly"]
    vc = VerticalBarChart()
    vc.x, vc.y, vc.width, vc.height = 30, 20, half - 40, 100
    vc.data = [[w["count"] for w in weeks] or [0]]
    vc.categoryAxis.categoryNames = [date.fromisoformat(w["week_start"]).strftime("%d %b") for w in weeks] or [""]
    vc.categoryAxis.labels.fontSize = 7
    vc.categoryAxis.labels.fillColor = colors.HexColor(MUTED)
    vc.valueAxis.valueMin = 0
    vc.valueAxis.valueMax = max([w["count"] for w in weeks] + [1])
    vc.valueAxis.valueStep = max(1, vc.valueAxis.valueMax // 4)
    vc.valueAxis.labels.fontSize = 7
    vc.valueAxis.labels.fillColor = colors.HexColor(MUTED)
    vc.valueAxis.strokeColor = vc.categoryAxis.strokeColor = colors.HexColor("#d4d4d4")
    vc.bars[0].fillColor = colors.HexColor(BAR)
    vc.bars.strokeColor = None
    vc.barWidth, vc.groupSpacing = 1, 2.2  # columns about a third of each week's slot (stays under ~24pt)
    d.add(vc)
    d.add(String(30, 135, "Events found per week", fontSize=9, fillColor=colors.HexColor(INK)))

    cats = sorted(p["totals"]["by_category"].items(), key=lambda kv: -kv[1])
    hc = HorizontalBarChart()
    hc.x, hc.y, hc.width, hc.height = half + 90, 20, half - 110, 100
    hc.data = [[v for _, v in reversed(cats)]]
    hc.categoryAxis.categoryNames = [CAT[c] for c, _ in reversed(cats)]
    hc.categoryAxis.labels.fontSize = 8
    hc.categoryAxis.labels.fillColor = colors.HexColor(MUTED)
    hc.valueAxis.valueMin = 0
    hc.valueAxis.visible = False
    hc.categoryAxis.strokeColor = colors.HexColor("#d4d4d4")
    hc.bars[0].fillColor = colors.HexColor(BAR)
    hc.bars.strokeColor = None
    hc.barWidth, hc.groupSpacing = 1, 1.6  # thin bars, air between them
    hc.barLabelFormat = lambda v: f"EUR {v:,.0f}" if v else "-"
    hc.barLabels.fontSize = 7.5
    hc.barLabels.fillColor = colors.HexColor(INK)
    hc.barLabels.boxAnchor = "w"
    hc.barLabels.dx = 3
    d.add(hc)
    d.add(String(half + 20, 135, "Estimated value by type (EUR, QS estimates)", fontSize=9, fillColor=colors.HexColor(INK)))
    return d


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
                            title=f"Commercial pack {p['from']} to {p['to']}")

    def esc(x: str) -> str:
        return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    flow = [Paragraph(f"Commercial pack - {esc(p['project']['name'])}", st["Title"]),
            Paragraph(f"{_d(p['from'])} to {_d(p['to'])} &nbsp;·&nbsp; {esc(p['project']['location'] or '')} &nbsp;·&nbsp; "
                      "prepared by Notice from the project record", st["Normal"]), Spacer(1, 8)]
    head = headline(p)
    kpi = Table([[Paragraph(f"<font size=8 color='{MUTED}'>{esc(k)}</font>", cell) for k, _ in head],
                 [Paragraph(f"<font size=14 color='{URGENT if (k in ('Notices overdue', 'At time-bar risk') and v not in ('0', 'EUR 0')) else INK}'><b>{esc(v)}</b></font>", cell) for k, v in head]],
                hAlign="LEFT", colWidths=[doc.width / len(head)] * len(head))
    flow += [kpi, Spacer(1, 6), _charts(p, doc.width), Spacer(1, 6)]
    for heading, intro, thead, rows in sections(p):
        flow.append(Paragraph(esc(heading), st["Heading2"]))
        if intro:
            flow.append(Paragraph(esc(intro), st["Normal"]))
        if rows:
            data = [[Paragraph(f"<b>{esc(h)}</b>", cell) for h in thead]] + [[Paragraph(esc(c), cell) for c in r] for r in rows]
            tbl = Table(data, repeatRows=1, hAlign="LEFT", colWidths=_widths(thead, doc.width))
            tbl.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                                     ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
                                     ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            flow += [Spacer(1, 4), tbl]
        else:
            flow.append(Paragraph("None in this period.", st["Normal"]))
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
    d.add_heading(f"Commercial pack - {p['project']['name']}", 0)
    d.add_paragraph(f"{_d(p['from'])} to {_d(p['to'])} · {p['project']['location'] or ''} · prepared by Notice from the project record")
    kpi = d.add_table(rows=2, cols=len(headline(p)))
    kpi.style = "Light List"
    for i, (k, v) in enumerate(headline(p)):
        kpi.rows[0].cells[i].text, kpi.rows[1].cells[i].text = k, v
    d.add_heading("Estimated value by type", 3)
    for c, v in sorted(p["totals"]["by_category"].items(), key=lambda kv: -kv[1]):
        d.add_paragraph(f"{CAT[c]}: {_eur(v)}", style="List Bullet")
    for heading, intro, thead, rows in sections(p):
        d.add_heading(heading, 2)
        if intro:
            d.add_paragraph(intro)
        if not rows:
            d.add_paragraph("None in this period.")
            continue
        t = d.add_table(rows=1, cols=len(thead))
        t.style = "Light List"
        for i, h in enumerate(thead):
            t.rows[0].cells[i].text = h
        for r in rows:
            cells = t.add_row().cells
            for i, c in enumerate(r):
                cells[i].text = str(c)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
