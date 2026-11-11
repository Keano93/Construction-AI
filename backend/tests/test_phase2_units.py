"""Unit tests for the Revision agent diff and the Claims agent core (no database)."""

from datetime import date, datetime

from notice.agents.claims_agent.core import Evidence, notice_compliance, verify_timeline
from notice.agents.claims_agent.schemas import TimelineEntry, TimelineOut
from notice.agents.identifiers import identifiers
from notice.agents.revision_agent.diff import diff_documents, diff_registers, diff_text, revision_key, split_units
from notice.agents.revision_agent.offline import assess_one

REG_A = "## Sheet: Register\nDrawing No\tTitle\tRevision\tDate\nRA-STR-110\tFoundations\tB\t2026-06-20\nRA-ARC-201\tGA\tP2\t2026-06-12\nRA-OLD-999\tWithdrawn\tA\t2026-06-01\n"
REG_B = "## Sheet: Register\nDrawing No\tTitle\tRevision\tDate\nRA-STR-110\tFoundations\tC\t2026-08-18\nRA-ARC-201\tGA\tP2\t2026-06-12\nSK-S-031\tLift pit\t-\t2026-10-09\n"


def test_revision_key_strips_revision_markers():
    assert revision_key("Drawing Register Rev A.xlsx") == revision_key("Drawing Register Rev B.xlsx") == "drawing register"
    assert revision_key("M&E Spec Section 5 Rev 01.pdf") == revision_key("M&E Spec Section 5 Rev 02.pdf")
    assert revision_key("RA-ARC-204 Rev P2.pdf") == revision_key("RA-ARC-204_P3.pdf") == "ra-arc-204"
    assert revision_key("RA-ARC-204 Rev P2.pdf") != revision_key("RA-ARC-205 Rev P2.pdf")


def test_register_diff_kinds_fields_and_spans():
    method, changes = diff_documents(REG_A, REG_B)
    assert method == "register"
    by_key = {c.key: c for c in changes}
    assert set(by_key) == {"RA-STR-110", "SK-S-031", "RA-OLD-999"}  # unchanged RA-ARC-201 not reported
    rev = by_key["RA-STR-110"]
    assert rev.kind == "revised" and rev.fields["Revision"] == ["B", "C"] and rev.issue_date == "2026-08-18"
    assert by_key["SK-S-031"].kind == "added" and by_key["RA-OLD-999"].kind == "removed"
    for c in changes:
        if c.new_span:
            assert REG_B[c.new_span[0]:c.new_span[1]] == c.new_text
        if c.old_span:
            assert REG_A[c.old_span[0]:c.old_span[1]] == c.old_text


SPEC_1 = """SPEC Section 5 - Revision 01
5.1 Scope: Category 2 system serving
Blocks A and B.
5.2 Water supply: tank 72 m3 net capacity, GRP.
5.3 Pumps: Single electric duty pump.
"""
SPEC_2 = """SPEC Section 5 - Revision 02
5.1 Scope: Category 2 system serving
Blocks A and B.
5.2 Water supply: tank 110 m3 net capacity, steel.
5.3 Pumps: Duty and standby diesel pumpsets.
5.6 Commissioning: witnessed by the fire engineer.
"""


def test_split_units_rejoins_wrapped_lines():
    units = split_units(SPEC_1)
    assert [u.key for u in units][1:] == ["5.1", "5.2", "5.3"]
    assert units[1].text == "5.1 Scope: Category 2 system serving\nBlocks A and B."


def test_text_diff_aligns_by_clause_number():
    changes = diff_text(SPEC_1, SPEC_2)
    kinds = {c.key: c.kind for c in changes}
    assert "5.1" not in kinds  # unchanged despite the wrap
    assert kinds["5.2"] == "modified" and kinds["5.3"] == "modified" and kinds["5.6"] == "added"
    c52 = next(c for c in changes if c.key == "5.2")
    assert {"old": "72", "new": "110"} in c52.word_diff
    assert SPEC_2[c52.new_span[0]:c52.new_span[1]] == c52.new_text


def test_offline_assessor_flags_upgrades_not_admin():
    changes = {c.key: c.to_dict() for c in diff_text(SPEC_1, SPEC_2)}
    assert assess_one(changes["5.3"]).potential_variation
    assert assess_one(changes["5.2"]).cost_impact in ("low", "medium")
    header = next(c.to_dict() for c in diff_text(SPEC_1, SPEC_2) if c.key.startswith("label:") or c.label.startswith("SPEC"))
    assert not assess_one(header).potential_variation


def test_identifiers_ignore_revision_codes():
    ids = identifiers("RA-STR-110 rev C at grid B4-B6, P3 plans, RFI 014")
    assert {"RA-STR-110", "B4-B6", "RFI014"} <= ids and "P3" not in ids


def _ev(i, text, ts):
    return Evidence(id=f"E{i}", item_id=f"item{i}", document_id="doc", filename="f", channel="email", author="a",
                    timestamp=ts, text=text, doc_offset=100 * i, linked=True)


def test_timeline_verification_orders_by_record_date_and_drops_fabrications():
    ev = [_ev(1, "Soft ground found at B4.", datetime(2026, 8, 20, 11)), _ev(2, "Plant standing all day.", datetime(2026, 8, 21, 17))]
    out = TimelineOut(entries=[
        TimelineEntry(evidence_id="E2", description="standing", significance="effect", quote="Plant standing all day"),
        TimelineEntry(evidence_id="E1", description="found", significance="cause", quote="Soft ground found at B4"),
        TimelineEntry(evidence_id="E1", description="made up", significance="cause", quote="the engineer admitted liability"),
        TimelineEntry(evidence_id="E9", description="unknown", significance="record", quote="anything"),
    ], gaps=[])
    rows, issues = verify_timeline(out, ev)
    assert [r["evidence_id"] for r in rows] == ["E1", "E2"]  # sorted by the record's own timestamp
    assert rows[0]["char_start"] == 100 and len(issues) == 2


def test_notice_compliance_states():
    base = {"event_ref": "PE-1", "clause_ref": "9.2", "title": "Change", "trigger_date": date(2026, 8, 18), "status": "running"}
    rows = notice_compliance([
        {**base, "condition_precedent": True, "due_date": date(2026, 9, 1), "met_on": None},
        {**base, "condition_precedent": True, "due_date": date(2026, 9, 1), "met_on": date(2026, 8, 30)},
        {**base, "condition_precedent": True, "due_date": date(2026, 9, 1), "met_on": date(2026, 9, 4)},
        {**base, "condition_precedent": False, "due_date": date(2026, 12, 1), "met_on": None},
        {**base, "condition_precedent": True, "due_date": date(2026, 9, 1), "met_on": None, "status": "cancelled"},
    ], today=date(2026, 11, 11))
    assert [r["state"] for r in rows] == ["not_given_overdue", "given_in_time", "given_late", "not_given_open", "cancelled"]
    assert [r["time_bar_risk"] for r in rows] == [True, False, True, False, False]


def test_register_detection_falls_back_to_text():
    assert diff_documents("just some text\nmore", "just some text\nchanged")[0] == "text"
    assert diff_registers(REG_A, REG_A) == []
