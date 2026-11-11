"""End-to-end flow through the API on a real Postgres test database (offline LLM provider)."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from notice.db import session_scope
from notice.deadlines import DeadlineRule, WorkingCalendar, compute_deadline

from .conftest import register

DEMO = Path(__file__).resolve().parents[2] / "demo_data" / "riverside"
CONTRACT = DEMO / "contract" / "Riverside Apartments - Conditions of Contract.pdf"

CHANGE_EMAIL = b"""From: Rory Nagle <r.nagle@kilcrea.example>
To: Declan Murphy <d.murphy@brennock.example>
Subject: Block B foundations - RA-STR-110 rev C
Date: Tue, 18 Aug 2026 10:14:00 +0100

Declan,

Please find attached revision C. Pad foundations P7 to P14 now 2.4m x 2.4m x 900 deep (previously 1.8m x 1.8m).
No cost implications expected. Please work to rev C from today.

Rory
"""


@pytest.fixture(scope="module")
def setup(migrated):
    from fastapi.testclient import TestClient

    from notice.llm import set_provider
    from notice.main import app

    set_provider(None)
    c = TestClient(app)
    h = register(c, "qs@flow.example")
    p = c.post("/api/projects", json={"name": "Flow Test", "contract_form": "PWC", "holiday_region": "IE"}, headers=h).json()
    c.post(f"/api/projects/{p['id']}/parties", headers=h,
           json={"name": "Rory Nagle", "organisation": "Kilcrea", "role": "engineer", "email": "r.nagle@kilcrea.example"})
    c.post(f"/api/projects/{p['id']}/parties", headers=h,
           json={"name": "Fionnuala Hegarty", "organisation": "HKP", "role": "employers_representative", "email": "hegarty@hkp.example"})
    c.post(f"/api/projects/{p['id']}/shutdowns", headers=h, json={"name": "Christmas", "start": "2026-12-21", "end": "2027-01-03"})
    r = c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": (CONTRACT.name, CONTRACT.read_bytes())},
               data={"kind": "contract"})
    assert r.status_code == 200, r.text
    return c, h, p


def test_contract_rules_extracted_and_pending(setup):
    c, h, p = setup
    contracts = c.get(f"/api/projects/{p['id']}/contract", headers=h).json()
    assert len(contracts) == 1 and contracts[0]["status"] == "pending_review"
    rules = contracts[0]["rules"]
    refs = {r["clause_ref"] for r in rules}
    assert {"3.3", "3.4", "4.6", "8.3", "8.5", "9.2", "10.1"} <= refs
    assert all(r["status"] == "proposed" for r in rules)
    r92 = next(r for r in rules if r["clause_ref"] == "9.2")
    assert r92["period_value"] == 10 and r92["period_unit"] == "working_days" and r92["condition_precedent"]
    doc = c.get(f"/api/documents/{contracts[0]['document_id']}", headers=h).json()
    assert doc["text"][r92["source_char_start"]:r92["source_char_end"]] == r92["source_quote"]


def test_message_before_rule_approval_is_low_confidence(setup):
    c, h, p = setup
    eml = CHANGE_EMAIL.replace(b"Subject: Block B", b"Subject: Early Block B")
    c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": ("early.eml", eml)})
    items = c.get(f"/api/projects/{p['id']}/review", headers=h).json()
    assert len(items) == 1 and items[0]["low_confidence"]
    assert "No approved contract rule" in items[0]["summary"]
    c.post(f"/api/review/{items[0]['id']}/dismiss", headers=h, json={"comment": "test"})


def test_rule_approval_with_edit_is_logged(setup):
    c, h, p = setup
    rules = c.get(f"/api/projects/{p['id']}/contract", headers=h).json()[0]["rules"]
    for r in rules:
        if r["rule_type"] in ("notice", "time_bar"):
            edits = {"recipient": "Fionnuala Hegarty (ER)"} if r["clause_ref"] == "9.2" else None
            res = c.post(f"/api/rules/{r['id']}/review", headers=h, json={"decision": "approve", "edits": edits})
            assert res.status_code == 200 and res.json()["status"] == "approved"
    bad = c.post(f"/api/rules/{rules[0]['id']}/review", headers=h, json={"decision": "approve", "edits": {"source_quote": "x"}})
    assert bad.status_code == 422
    audit = c.get(f"/api/projects/{p['id']}/audit", headers=h).json()
    edited = [a for a in audit if a["action"] == "contract_rule.approve" and a["details"].get("edited")]
    assert len(edited) == 1 and edited[0]["details"]["after"]["recipient"] == "Fionnuala Hegarty (ER)"


def test_notice_agent_end_to_end(setup):
    c, h, p = setup
    r = c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": ("rev_c.eml", CHANGE_EMAIL)})
    assert r.status_code == 200 and r.json()["created"]
    dup = c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": ("again.eml", CHANGE_EMAIL)})
    assert dup.json()["created"] is False  # content-hash dedupe

    items = c.get(f"/api/projects/{p['id']}/review", headers=h).json()
    assert len(items) == 1
    ri = c.get(f"/api/review/{items[0]['id']}", headers=h).json()
    assert ri["category"] in ("change", "instruction")
    assert ri["draft"]["subject"].startswith("CONTRACT NOTICE")
    assert ri["payload"]["rules"], "a contract clause must be linked"

    # every citation must point at the exact passage it quotes
    assert ri["citations"]
    for cit in ri["citations"]:
        doc = c.get(f"/api/documents/{cit['document_id']}", headers=h).json()
        assert doc["text"][cit["char_start"]:cit["char_end"]] == cit["quote"]

    # deadline computed by the engine, not the model
    cal = WorkingCalendar(region="IE", shutdowns=())
    rule = ri["payload"]["rules"][0]
    dl = next(d for d in ri["deadlines"] if d["rule_id"] == rule["id"])
    period = int(dl["trace"]["period"])
    assert dl["due_date"] == compute_deadline(date(2026, 8, 18), DeadlineRule(period, "working_days"), cal).due_date.isoformat()


def test_review_edit_recomputes_deadline_and_export_requires_approval(setup):
    c, h, p = setup
    ri = c.get(f"/api/projects/{p['id']}/review", headers=h).json()[0]
    draft_id = ri["draft_id"]
    assert c.get(f"/api/drafts/{draft_id}/export?format=docx", headers=h).status_code == 409

    res = c.post(f"/api/review/{ri['id']}/edit", headers=h,
                 json={"trigger_date": "2026-12-18", "body": "Edited body", "comment": "awareness date corrected"}).json()
    assert res["draft"]["body"] == "Edited body" and res["draft"]["version"] == 2
    dl = res["deadlines"][0]
    # 18 Dec 2026 + N WD with Christmas shutdown 21 Dec - 3 Jan: counting resumes 4 Jan 2027
    assert dl["due_date"] >= "2027-01-04" and dl["trace"]["trigger_date"] == "2026-12-18"

    assert c.post(f"/api/review/{ri['id']}/approve", headers=h, json={}).json()["status"] == "approved"
    assert c.post(f"/api/review/{ri['id']}/approve", headers=h, json={}).status_code == 409
    docx = c.get(f"/api/drafts/{draft_id}/export?format=docx", headers=h)
    pdf = c.get(f"/api/drafts/{draft_id}/export?format=pdf", headers=h)
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    issued = c.post(f"/api/review/{ri['id']}/mark-issued", headers=h, json={"issued_on": "2026-12-18"}).json()
    assert issued["event"]["status"] == "notified"
    assert any(d["status"] == "met" for d in issued["deadlines"])
    actions = [a["action"] for a in issued["actions"]]
    assert actions == ["edit", "approve", "mark_issued"]


def test_dismiss_cancels_deadlines(setup):
    c, h, p = setup
    eml = (b"From: Rory Nagle <r.nagle@kilcrea.example>\nTo: Declan <d@x.example>\nSubject: Sprinkler tank room\n"
           b"Date: Thu, 10 Sep 2026 10:00:00 +0100\n\nThe sprinkler tank room has to go up from 4.5m x 6m to 6m x 7m. "
           b"Revised layout attached.\n")
    c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": ("tank.eml", eml)})
    pending = c.get(f"/api/projects/{p['id']}/review", headers=h).json()
    target = pending[0]
    out = c.post(f"/api/review/{target['id']}/dismiss", headers=h, json={"comment": "not a change"}).json()
    assert out["status"] == "dismissed" and all(d["status"] == "cancelled" for d in out["deadlines"])
    reopened = c.post(f"/api/review/{target['id']}/reopen", headers=h, json={}).json()
    assert reopened["status"] == "pending" and all(d["status"] == "running" for d in reopened["deadlines"])


def test_documents_and_logs_are_immutable(setup):
    with pytest.raises(DBAPIError), session_scope() as db:
        db.execute(text("UPDATE documents SET text = 'tampered'"))
    with pytest.raises(DBAPIError), session_scope() as db:
        db.execute(text("DELETE FROM items"))
    with pytest.raises(DBAPIError), session_scope() as db:
        db.execute(text("UPDATE audit_log SET action = 'x'"))
    with pytest.raises(DBAPIError), session_scope() as db:
        db.execute(text("DELETE FROM review_actions"))


def test_audit_chain_verifies(setup):
    c, h, _ = setup
    assert c.get("/api/audit/verify", headers=h).json() == {"ok": True, "first_bad_id": None}


def test_tenancy_isolation(setup):
    c, h, p = setup
    other = register(c, "other@rival.example", org="Rival Builders")
    assert c.get(f"/api/projects/{p['id']}", headers=other).status_code == 404
    assert c.get(f"/api/projects/{p['id']}/review", headers=other).status_code == 404
    ri = c.get(f"/api/projects/{p['id']}/review?status=all", headers=h).json()[0]
    assert c.get(f"/api/review/{ri['id']}", headers=other).status_code == 404
    assert c.post(f"/api/review/{ri['id']}/dismiss", headers=other, json={}).status_code == 404
    assert c.get("/api/projects", headers=other).json() == []


def test_auth_required(setup):
    c, _, p = setup
    assert c.get(f"/api/projects/{p['id']}").status_code == 401
    assert c.post("/api/auth/login", json={"email": "qs@flow.example", "password": "wrong-pass"}).status_code == 401


def test_deadline_calculator_endpoint(setup):
    c, h, p = setup
    r = c.post(f"/api/projects/{p['id']}/deadline-calculator", headers=h,
               json={"trigger_date": "2026-10-23", "period": 1, "unit": "working_days"}).json()
    assert r["due_date"] == "2026-10-27"
