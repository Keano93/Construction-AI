"""Generate the synthetic Riverside Apartments project files.

    python demo_data/generate.py

Writes demo_data/riverside/ (the files a contractor would upload) and
evals/notice_agent/dataset.jsonl (the same messages with ground-truth labels).
Deterministic: re-running produces identical files (fixed timestamps).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from riverside_contract import CONTRACT_TEXT, CONTRACT_TITLE  # noqa: E402
from riverside_messages import DIARY, MESSAGES, P  # noqa: E402

TZ = ZoneInfo("Europe/Dublin")
OUT = HERE / "riverside"
EVAL_OUT = HERE.parent / "evals" / "notice_agent" / "dataset.jsonl"
FIXED = datetime(2026, 11, 6, 12, 0)


def _dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def _addr(k: str) -> str:
    name, email = P[k]
    return f"{name} <{email}>"


# --- PDFs ----------------------------------------------------------------

def write_pdf(path: Path, title: str, text: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=title, author="Notice demo generator",
                            creator="Notice demo generator", invariant=1)
    flow = []
    for block in text.strip().split("\n"):
        if not block.strip():
            flow.append(Spacer(1, 6))
            continue
        esc = block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        flow.append(Paragraph(esc, styles["Normal"]))
    doc.build(flow)


# --- emails / WhatsApp / diary --------------------------------------------

def write_emails() -> list[dict]:
    d = OUT / "correspondence" / "emails"
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for msg in [x for x in MESSAGES if x["channel"] == "email"]:
        em = EmailMessage()
        em["From"] = _addr(msg["frm"])
        em["To"] = ", ".join(_addr(k) for k in msg["to"])
        if msg["cc"]:
            em["Cc"] = ", ".join(_addr(k) for k in msg["cc"])
        em["Date"] = format_datetime(_dt(msg["dt"]))
        em["Subject"] = msg["subject"]
        em["Message-ID"] = make_msgid(idstring=msg["key"], domain="riverside.example")
        em.set_content(msg["body"] + "\n")
        slug = "".join(c if c.isalnum() else "_" for c in msg["subject"])[:50].strip("_")
        (d / f"{msg['key']}_{slug}.eml").write_bytes(bytes(em))
        rows.append(msg)
    return rows


def write_whatsapp() -> None:
    d = OUT / "correspondence" / "whatsapp"
    d.mkdir(parents=True, exist_ok=True)
    for chan, fname in (("wa_site", "WhatsApp Chat with Riverside Site Team.txt"),
                        ("wa_design", "WhatsApp Chat with Riverside Design Team.txt")):
        lines = []
        for msg in sorted((x for x in MESSAGES if x["channel"] == chan), key=lambda x: x["dt"]):
            dt = _dt(msg["dt"])
            lines.append(f"{dt:%d/%m/%Y}, {dt:%H:%M} - {P[msg['frm']][0]}: {msg['body']}")
        (d / fname).write_text("\n".join(lines) + "\n")


def write_diaries() -> None:
    d = OUT / "site_diary"
    d.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, list[str]] = {}
    for date_s, who, body, _ in DIARY:
        by_month.setdefault(date_s[:7], []).append(f"SITE DIARY — {date_s} — {P[who][0]}\n{body.strip()}\n")
    for month, entries in by_month.items():
        (d / f"Site Diary {month}.txt").write_text("\n".join(entries))


# --- drawings / spec -----------------------------------------------------

REGISTER_A = [
    ("RA-ARC-201", "Block A - Ground floor GA", "P2", "2026-06-12"),
    ("RA-ARC-202", "Block A - Level 1-4 GA", "P2", "2026-06-12"),
    ("RA-ARC-203", "Block B - Ground floor GA", "P2", "2026-06-12"),
    ("RA-ARC-204", "Block A - Elevations", "P2", "2026-06-12"),
    ("RA-ARC-205", "Block B - Elevations", "P2", "2026-06-12"),
    ("RA-ARC-206", "Window schedule", "P2", "2026-06-12"),
    ("RA-STR-110", "Block B - Foundation layout", "B", "2026-06-20"),
    ("RA-STR-205", "Block A - Core walls GA", "A", "2026-06-20"),
    ("RA-STR-230", "Block A - Lintel schedule", "A", "2026-06-20"),
    ("RA-CIV-300", "External drainage layout", "C", "2026-06-25"),
    ("RA-MEP-401", "Block A - Basement plant rooms", "P1", "2026-06-25"),
]
REGISTER_B = [
    ("RA-ARC-201", "Block A - Ground floor GA", "P3", "2026-09-16"),
    ("RA-ARC-202", "Block A - Level 1-4 GA", "P3", "2026-09-16"),
    ("RA-ARC-203", "Block B - Ground floor GA", "P3", "2026-09-16"),
    ("RA-ARC-204", "Block A - Elevations", "P3", "2026-09-16"),
    ("RA-ARC-205", "Block B - Elevations", "P3", "2026-09-16"),
    ("RA-ARC-206", "Window schedule", "P3", "2026-09-16"),
    ("RA-ARC-212", "Block B - L1 accessible units layout", "P1", "2026-10-07"),
    ("RA-STR-110", "Block B - Foundation layout", "C", "2026-08-18"),
    ("RA-STR-205", "Block A - Core walls GA and embeds", "B", "2026-09-11"),
    ("RA-STR-230", "Block A - Lintel schedule", "A", "2026-06-20"),
    ("RA-CIV-300", "External drainage layout", "C", "2026-06-25"),
    ("RA-MEP-401", "Block A - Basement plant rooms", "P2", "2026-09-24"),
    ("SK-S-031", "Block B lift pit - deepened", "-", "2026-10-09"),
]

SPEC_R1 = """RIVERSIDE APARTMENTS - M&E SPECIFICATION
Section 5: Sprinkler Installation - Revision 01 (12 June 2026)
5.1 Scope: Residential sprinkler system to BS 9251 Category 2 serving Blocks A and B.
5.2 Water supply: Sprinkler storage tank 72 m3 net capacity, sectional GRP, located in Block A basement tank room (4.5m x 6.0m).
5.3 Pumps: Single electric duty pump with jockey pump, controller to BS EN 12845.
5.4 Alarm: Flow switches per floor connected to the fire alarm panel.
5.5 Testing: Hydrostatic test at 1.5 x working pressure for 2 hours.
"""
SPEC_R2 = """RIVERSIDE APARTMENTS - M&E SPECIFICATION
Section 5: Sprinkler Installation - Revision 02 (24 September 2026)
5.1 Scope: Residential sprinkler system to BS 9251 Category 3 serving Blocks A and B, including basement car park to BS EN 12845 OH1.
5.2 Water supply: Sprinkler storage tank 110 m3 net capacity, sectional steel, located in Block A basement tank room (6.0m x 7.0m).
5.3 Pumps: Duty and standby diesel pumpsets with jockey pump, controller to BS EN 12845, fuel tank 8 hours.
5.4 Alarm: Flow switches per floor connected to the fire alarm panel and remote monitoring.
5.5 Testing: Hydrostatic test at 1.5 x working pressure for 2 hours. Witnessed by the fire engineer.
"""

DRAWING_P2 = """TITLE BLOCK: Riverside Apartments | RA-ARC-204 | Block A - Elevations | Rev P2 | 12/06/2026 | Fennessy Moran Architects
NOTES:
1. Window type W07 (east elevation, 22 no.): double glazed, Ug 1.1, Rw 32 dB.
2. Window openings east elevation: 1500 wide x 1350 high.
3. Facing brick: red multi stock, stretcher bond.
4. Balcony upstand: 150mm.
"""
DRAWING_P3 = """TITLE BLOCK: Riverside Apartments | RA-ARC-204 | Block A - Elevations | Rev P3 | 16/09/2026 | Fennessy Moran Architects
NOTES:
1. Window type W07 (east elevation, 22 no.): triple glazed, Ug 0.6, Rw 40 dB (acoustic).
2. Window openings east elevation: 1800 wide x 1350 high.
3. Facing brick: red multi stock, stretcher bond.
4. Balcony upstand: 150mm.
REVISION P3: coordination update - door numbering, window schedule.
"""


def write_drawings() -> None:
    import openpyxl

    d = OUT / "drawings"
    d.mkdir(parents=True, exist_ok=True)
    for name, rows in (("Drawing Register Rev A.xlsx", REGISTER_A), ("Drawing Register Rev B.xlsx", REGISTER_B)):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Register"
        ws.append(["Drawing No", "Title", "Revision", "Date", "Status"])
        for r in rows:
            ws.append([*r, "For Construction"])
        wb.properties.created = wb.properties.modified = FIXED
        wb.save(d / name)
    write_pdf(d / "M&E Spec Section 5 Rev 01.pdf", "M&E Spec 5 Rev 01", SPEC_R1)
    write_pdf(d / "M&E Spec Section 5 Rev 02.pdf", "M&E Spec 5 Rev 02", SPEC_R2)
    write_pdf(d / "RA-ARC-204 Rev P2.pdf", "RA-ARC-204 P2", DRAWING_P2)
    write_pdf(d / "RA-ARC-204 Rev P3.pdf", "RA-ARC-204 P3", DRAWING_P3)


# --- M&E quotes ----------------------------------------------------------

def write_quotes() -> None:
    import docx
    import openpyxl

    d = OUT / "tender" / "M&E package quotes"
    d.mkdir(parents=True, exist_ok=True)
    write_pdf(d / "Brightwater M&E - Quote RA-ME-01.pdf", "Brightwater quote", """BRIGHTWATER M&E LTD - QUOTATION RA-ME-01
To: Brennock Construction Ltd. Project: Riverside Apartments, Co. Cork. Package: Mechanical and Electrical Services, Blocks A and B.
Date: 14 May 2026. Validity: 90 days.
Mechanical services (heating, ventilation MVHR, domestic water, soil and waste): EUR 1,184,000
Electrical services (LV distribution, small power, lighting, fire alarm, data): EUR 902,500
Sprinkler installation per Section 5 Rev 01: EUR 214,000
Builder's work in connection: EXCLUDED
BMS and controls: EXCLUDED - by others
Testing and commissioning: Included
Total: EUR 2,300,500 excl. VAT
Assumptions: Programme of 58 weeks. Working hours 08:00-17:00 Mon-Fri. Free access to all areas. Scaffold by main contractor.
Exclusions: Builder's work, BMS, ESB connection charges, out-of-hours working, temporary building supplies.
""")
    doc = docx.Document()
    doc.core_properties.created = doc.core_properties.modified = FIXED
    doc.add_heading("Kestrel Building Services Ltd - Tender Return", 1)
    for line in [
        "Project: Riverside Apartments, Co. Cork - M&E Package. Date: 16 May 2026.",
        "Mechanical installation (heating, MVHR, plumbing, drainage above ground): EUR 1,126,400",
        "Electrical installation (distribution, lighting, power, fire alarm, data, BMS): EUR 948,100",
        "Sprinkler installation: NOT INCLUDED - we do not carry out sprinkler works",
        "Builder's work in connection: Included (holes up to 150mm only)",
        "Preliminaries and supervision: EUR 96,000",
        "Total: EUR 2,170,500 excl. VAT",
        "Qualifications: Price based on 6-day working week. Price fixed for 6 months only, then subject to SEAI-index inflation adjustment. Retention capped at 2.5%.",
    ]:
        doc.add_paragraph(line)
    doc.save(d / "Kestrel Building Services - Tender Return.docx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Northpoint Mechanical & Electrical Ltd - Riverside Apartments M&E - Priced Summary", None])
    ws.append(["Date", "2026-05-18"])
    for row in [
        ("Mechanical services", 1210000), ("Electrical services incl. BMS", 975000),
        ("Sprinkler installation (Section 5 Rev 01)", 236000), ("Builder's work in connection", 64000),
        ("Testing & commissioning", 27000), ("Provisional sum - ESB connection", 30000),
        ("Total excl. VAT", 2542000),
        ("Exclusions", "Out-of-hours working; temporary supplies"),
        ("Assumptions", "Programme 56 weeks; 5 day week; no phasing between blocks"),
    ]:
        ws.append(list(row))
    wb.properties.created = wb.properties.modified = FIXED
    wb.save(d / "Northpoint M&E - Priced Summary.xlsx")


# --- subcontractor compliance -------------------------------------------

SUBCONTRACTORS = [
    # name, package, contact, RCT rate, EL expiry, PL expiry, safe pass (ok, total), RAMS
    ("Keelvane Civils Ltd", "Groundworks & drainage", "mick@keelvane.example", "0%", "2027-03-31", "2027-03-31", (7, 7), "Approved"),
    ("Torcmore Steel Fabrications Ltd", "Structural steel", "g.lynch@torcmore.example", "20%", "2027-01-31", "2026-10-31", (6, 6), "Approved"),
    ("Brightwater M&E Ltd", "M&E services", "owen@brightwater-me.example", "35%", "2027-06-30", "2027-06-30", (8, 8), "Approved"),
    ("Laneway Drylining Ltd", "Drylining & ceilings", "jurgis@laneway.example", "20%", "2027-02-28", "2027-02-28", (4, 6), "Not submitted"),
    ("Slatefield Roofing Ltd", "Roofing", "sean@slatefield.example", "20%", "2026-11-20", "2027-04-30", (5, 5), "Approved"),
]


def write_compliance() -> None:
    import openpyxl

    d = OUT / "compliance"
    d.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Subcontractors"
    ws.append(["Subcontractor", "Package", "Contact", "RCT deduction rate", "EL insurance expiry", "PL insurance expiry",
               "Operatives with valid Safe Pass", "Operatives on site", "RAMS status"])
    for name, pkg, contact, rct, el, pl, (sp_ok, sp_n), rams in SUBCONTRACTORS:
        ws.append([name, pkg, contact, rct, el, pl, sp_ok, sp_n, rams])
    wb.properties.created = wb.properties.modified = FIXED
    wb.save(d / "Subcontractor Compliance Register.xlsx")
    for name, _pkg, _c, _rct, el, pl, _sp, _rams in SUBCONTRACTORS:
        if name.startswith("Laneway"):
            continue  # certificate not yet received
        write_pdf(d / f"Insurance Certificate - {name}.pdf", f"Insurance - {name}",
                  f"""CERTIFICATE OF INSURANCE
Insured: {name}
Employer's Liability: limit EUR 13,000,000 any one occurrence. Period of insurance to {el}.
Public Liability: limit EUR 6,500,000 any one occurrence. Period of insurance to {pl}.
Indemnity to principal: Lee Valley Housing Partnership CLG and Brennock Construction Limited.
Issued by: Example Mutual Insurance DAC (fictitious).""")


# --- contract + eval dataset ---------------------------------------------

def write_contract() -> None:
    d = OUT / "contract"
    d.mkdir(parents=True, exist_ok=True)
    write_pdf(d / "Riverside Apartments - Conditions of Contract.pdf", CONTRACT_TITLE, CONTRACT_TEXT)


def write_eval_dataset() -> None:
    EVAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for msg in MESSAGES:
        name, email = P[msg["frm"]]
        rows.append({
            "key": msg["key"], "channel": msg["channel"], "timestamp": _dt(msg["dt"]).isoformat(),
            "author": f"{name} <{email}>" if msg["channel"] == "email" else name,
            "subject": msg["subject"], "text": msg["body"],
            "label": msg["label"], "clauses": msg["clauses"], "alt": msg["alt"],
            "trigger": msg["trigger"], "note": msg["note"],
        })
    for i, (date_s, who, body, lab) in enumerate(DIARY, 1):
        rows.append({
            "key": f"D{i:02d}", "channel": "diary", "timestamp": f"{date_s}T17:00:00+01:00",
            "author": P[who][0], "subject": f"Site diary {date_s}", "text": body.strip(),
            "label": lab["label"], "clauses": lab.get("clauses", []), "alt": lab.get("alt", []),
            "trigger": lab.get("trigger"), "note": lab.get("note"),
        })
    EVAL_OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")


def main() -> None:
    write_contract()
    write_emails()
    write_whatsapp()
    write_diaries()
    write_drawings()
    write_quotes()
    write_compliance()
    write_eval_dataset()
    files = sorted(p for p in OUT.rglob("*") if p.is_file())
    print(f"Wrote {len(files)} files to {OUT}")
    print(f"Wrote eval dataset to {EVAL_OUT}")


if __name__ == "__main__":
    main()
