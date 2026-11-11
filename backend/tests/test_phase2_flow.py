"""Revision agent and Claims agent end to end through the API (offline provider, Postgres)."""

from pathlib import Path

import pytest

from .conftest import register

DEMO = Path(__file__).resolve().parents[2] / "demo_data" / "riverside"
CONTRACT = DEMO / "contract" / "Riverside Apartments - Conditions of Contract.pdf"
DRAWINGS = DEMO / "drawings"

GROUND_MSG = b"""From: Declan Murphy <d.murphy@brennock.example>
To: Ciaran Walsh <c.walsh@brennock.example>
Subject: Soft ground at B4-B6
Date: Thu, 20 Aug 2026 14:30:00 +0100

We have hit very soft ground at B4-B6, an old river channel not shown on the site investigation.
Keelvane have two excavators standing at B4-B6 since lunchtime.
"""
STANDING_MSG = b"""From: Declan Murphy <d.murphy@brennock.example>
To: Ciaran Walsh <c.walsh@brennock.example>
Subject: B4-B6 still standing
Date: Fri, 21 Aug 2026 16:00:00 +0100

Plant still standing at B4-B6 all day waiting on the engineer. Two 21t excavators and a dumper idle.
"""
FOUNDATION_MSG = b"""From: Rory Nagle <r.nagle@kilcrea.example>
To: Declan Murphy <d.murphy@brennock.example>
Subject: RA-STR-110 rev C
Date: Tue, 18 Aug 2026 10:14:00 +0100

Revision C of RA-STR-110 attached. Pad foundations now 2.4m x 2.4m (previously 1.8m). Please work to rev C.
"""


@pytest.fixture(scope="module")
def env(migrated):
    from fastapi.testclient import TestClient

    from notice.llm import set_provider
    from notice.main import app

    set_provider(None)
    c = TestClient(app)
    h = register(c, "qs@phase2.example")
    p = c.post("/api/projects", json={"name": "Phase 2", "contract_form": "PWC", "holiday_region": "IE"}, headers=h).json()
    c.post(f"/api/projects/{p['id']}/parties", headers=h,
           json={"name": "Rory Nagle", "organisation": "Kilcrea", "role": "engineer", "email": "r.nagle@kilcrea.example"})
    c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": (CONTRACT.name, CONTRACT.read_bytes())}, data={"kind": "contract"})
    for r in c.get(f"/api/projects/{p['id']}/contract", headers=h).json()[0]["rules"]:
        if r["rule_type"] in ("notice", "time_bar"):
            c.post(f"/api/rules/{r['id']}/review", headers=h, json={"decision": "approve"})
    for name, body in (("found.eml", FOUNDATION_MSG), ("ground.eml", GROUND_MSG), ("standing.eml", STANDING_MSG)):
        c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": (name, body)})
    return c, h, p


def _upload(c, h, p, name):
    r = c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": (name, (DRAWINGS / name).read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["document"]


def test_new_revision_is_compared_automatically(env):
    c, h, p = env
    _upload(c, h, p, "M&E Spec Section 5 Rev 01.pdf")
    assert c.get(f"/api/projects/{p['id']}/revisions", headers=h).json() == []
    rev2 = _upload(c, h, p, "M&E Spec Section 5 Rev 02.pdf")
    comps = c.get(f"/api/projects/{p['id']}/revisions", headers=h).json()
    assert len(comps) == 1 and comps[0]["revised"]["id"] == rev2["id"]
    comp = c.get(f"/api/revisions/{comps[0]['id']}", headers=h).json()
    keys = {ch["key"]: ch for ch in comp["changes"]}
    assert {"5.1", "5.2", "5.3", "5.4", "5.5"} <= set(keys)
    assert keys["5.3"]["assessment"]["potential_variation"]
    assert not next(ch for ch in comp["changes"] if ch["key"].startswith("label:section"))["assessment"]["potential_variation"]
    # every change's spans point at its text in both documents
    rev_doc = c.get(f"/api/documents/{rev2['id']}", headers=h).json()
    for ch in comp["changes"]:
        s, e = ch["new_span"]
        assert rev_doc["text"][s:e] == ch["new_text"]
    ri = c.get(f"/api/review/{comps[0]['review_item_id']}", headers=h).json()
    assert ri["kind"] == "revision_comparison" and ri["comparison"]["id"] == comp["id"]
    for cit in ri["citations"]:
        d = c.get(f"/api/documents/{cit['document_id']}", headers=h).json()
        assert d["text"][cit["char_start"]:cit["char_end"]] == cit["quote"]


def test_raise_variation_hands_off_to_notice_agent(env):
    c, h, p = env
    comp = c.get(f"/api/projects/{p['id']}/revisions", headers=h).json()[0]
    res = c.post(f"/api/revisions/{comp['id']}/changes/{_change_id(c, h, comp, '5.3')}/raise", headers=h, json={"trigger_date": "2026-09-24"})
    assert res.status_code == 200, res.text
    raised = res.json()
    assert raised["mode"] == "new_event"
    ri = c.get(f"/api/review/{raised['review_item']}", headers=h).json()
    assert ri["kind"] == "notice_flag" and ri["agent"] == "notice_agent" and ri["category"] == "change"
    assert ri["payload"]["origin"]["agent"] == "revision_agent"
    assert ri["payload"]["rules"][0]["clause_ref"] == "9.2"
    assert ri["deadlines"][0]["due_date"] == "2026-10-08"  # 24 Sep 2026 + 10 working days
    assert ri["draft"]["subject"].startswith("CONTRACT NOTICE")
    again = c.post(f"/api/revisions/{comp['id']}/changes/{_change_id(c, h, comp, '5.3')}/raise", headers=h, json={})
    assert again.status_code == 409


def _change_id(c, h, comp, key):
    full = c.get(f"/api/revisions/{comp['id']}", headers=h).json()
    return next(ch["id"] for ch in full["changes"] if ch["key"] == key)


def test_register_change_already_on_register_is_attached_not_duplicated(env):
    c, h, p = env
    _upload(c, h, p, "Drawing Register Rev A.xlsx")
    _upload(c, h, p, "Drawing Register Rev B.xlsx")
    comp = next(x for x in c.get(f"/api/projects/{p['id']}/revisions", headers=h).json() if "Register" in x["revised"]["filename"])
    full = c.get(f"/api/revisions/{comp['id']}", headers=h).json()
    stru = next(ch for ch in full["changes"] if ch["key"] == "RA-STR-110")
    assert stru["kind"] == "revised" and stru["cross_refs"]["events"], "the rev C email event should be cross-referenced"
    events_before = len(c.get(f"/api/projects/{p['id']}/events", headers=h).json())
    out = c.post(f"/api/revisions/{comp['id']}/changes/{stru['id']}/raise", headers=h, json={}).json()
    assert out["mode"] == "attached"
    assert len(c.get(f"/api/projects/{p['id']}/events", headers=h).json()) == events_before
    forced = c.post(f"/api/revisions/{comp['id']}/changes/{_change_id(c, h, comp, 'SK-S-031')}/raise", headers=h,
                    json={"force_new": True}).json()
    assert forced["mode"] == "new_event"
    ri = c.get(f"/api/review/{forced['review_item']}", headers=h).json()
    assert ri["event"]["trigger_date"] == "2026-10-09"  # drawing issue date from the register


def test_claims_agent_builds_verified_timeline_and_compliance(env):
    c, h, p = env
    events = c.get(f"/api/projects/{p['id']}/events", headers=h).json()
    ground = [e for e in events if "B4-B6" in e["title"] or "soft" in e["description"].lower()]
    assert ground
    res = c.post(f"/api/projects/{p['id']}/claims", headers=h, json={"event_ids": [ground[0]["id"]], "title": "Ground conditions B4-B6"})
    assert res.status_code == 200, res.text
    claim = res.json()
    assert claim["status"] == "ready" and claim["ref"] == "CL-001"
    assert len(claim["timeline"]) >= 2
    dates = [t["date"] for t in claim["timeline"]]
    assert dates == sorted(dates)
    for t in claim["timeline"]:
        d = c.get(f"/api/documents/{t['document_id']}", headers=h).json()
        assert d["text"][t["char_start"]:t["char_end"]] == t["quote"]
    states = {r["state"] for r in claim["notice_compliance"]}
    assert states and states <= {"not_given_overdue", "not_given_open", "given_in_time", "given_late", "cancelled"}
    assert claim["time_bar_risk"] is True  # August events, notices never given, condition precedent clauses

    claims = c.get(f"/api/projects/{p['id']}/claims", headers=h).json()
    ri = c.get(f"/api/review/{claims[0]['review_item_id']}", headers=h).json()
    assert ri["kind"] == "claim_draft" and ri["claim"]["id"] == claim["id"]
    assert "EUR [to be quantified]" in ri["draft"]["body"] and "6. Chronology" in ri["draft"]["body"]
    assert c.post(f"/api/review/{ri['id']}/approve", headers=h, json={}).status_code == 200
    assert c.get(f"/api/drafts/{ri['draft_id']}/export?format=pdf", headers=h).content[:4] == b"%PDF"


def test_claims_validation_and_tenancy(env):
    c, h, p = env
    assert c.post(f"/api/projects/{p['id']}/claims", headers=h, json={"event_ids": []}).status_code == 422
    other = register(c, "rival@phase2.example", org="Rival")
    comp = c.get(f"/api/projects/{p['id']}/revisions", headers=h).json()[0]
    assert c.get(f"/api/revisions/{comp['id']}", headers=other).status_code == 404
    assert c.post(f"/api/revisions/{comp['id']}/changes/C1/raise", headers=other, json={}).status_code == 404
    claim = c.get(f"/api/projects/{p['id']}/claims", headers=h).json()[0]
    assert c.get(f"/api/claims/{claim['id']}", headers=other).status_code == 404
    ev = c.get(f"/api/projects/{p['id']}/events", headers=h).json()[0]
    p2 = c.post("/api/projects", json={"name": "Theirs"}, headers=other).json()
    assert c.post(f"/api/projects/{p2['id']}/claims", headers=other, json={"event_ids": [ev["id"]]}).status_code == 422
