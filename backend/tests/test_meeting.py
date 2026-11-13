"""Weekly commercial meeting: pack contents, estimates, decisions/actions carry-forward, exports, tenancy."""

from pathlib import Path

import pytest

from .conftest import register

CONTRACT = Path(__file__).resolve().parents[2] / "demo_data" / "riverside" / "contract" / "Riverside Apartments - Conditions of Contract.pdf"


def _email(subject: str, date: str, body: str) -> bytes:
    return (f"From: Rory Nagle <r.nagle@kilcrea.example>\nTo: Declan <d@x.example>\nSubject: {subject}\nDate: {date}\n\n{body}\n").encode()


@pytest.fixture(scope="module")
def env(migrated):
    from fastapi.testclient import TestClient

    from notice.llm import set_provider
    from notice.main import app

    set_provider(None)
    c = TestClient(app)
    h = register(c, "qs@meeting.example")
    p = c.post("/api/projects", json={"name": "Meeting Test", "contract_form": "PWC", "holiday_region": "IE"}, headers=h).json()
    c.post(f"/api/projects/{p['id']}/parties", headers=h,
           json={"name": "Rory Nagle", "organisation": "Kilcrea", "role": "engineer", "email": "r.nagle@kilcrea.example"})
    c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": (CONTRACT.name, CONTRACT.read_bytes())}, data={"kind": "contract"})
    for r in c.get(f"/api/projects/{p['id']}/contract", headers=h).json()[0]["rules"]:
        if r["rule_type"] in ("notice", "time_bar"):
            c.post(f"/api/rules/{r['id']}/review", headers=h, json={"decision": "approve"})
    # an old change (overdue by the meeting) and a recent one (due after the meeting)
    c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": ("old.eml", _email(
        "RA-STR-110 rev C", "Tue, 18 Aug 2026 10:00:00 +0100", "Revision C attached: pad foundations now 2.4m x 2.4m (previously 1.8m)."))})
    c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": ("new.eml", _email(
        "Sprinkler tank room", "Mon, 09 Nov 2026 09:00:00 +0000", "The sprinkler tank room has to go up from 4.5m x 6m to 6m x 7m. Revised layout attached."))})
    return c, h, p


def test_pack_sections(env):
    c, h, p = env
    pack = c.get(f"/api/projects/{p['id']}/meeting?date=2026-11-13", headers=h).json()
    assert pack["meeting_date"] == "2026-11-13" and pack["previous_meeting"] is None and pack["since"] == "2026-11-06"
    buckets = {n["event_title"]: n["bucket"] for n in pack["notices"]}
    assert buckets[next(k for k in buckets if "RA-STR-110" in k)] == "overdue"
    # 9 Nov + 10 working days = 23 Nov: after the end of next week, so not listed yet...
    assert not any("Sprinkler" in k for k in buckets)
    later = c.get(f"/api/projects/{p['id']}/meeting?date=2026-11-20", headers=h).json()
    # ...but listed as due next week at the 20 Nov meeting
    assert next(n for n in later["notices"] if "Sprinkler" in n["event_title"])["bucket"] == "next_week"
    new_titles = [e["title"] for e in pack["new_events"]]
    assert any("Sprinkler" in t for t in new_titles) and not any("RA-STR-110" in t for t in new_titles)
    assert pack["summary"]["notices_overdue"] >= 1
    assert all(r["notice_state"] in ("open", "overdue", "issued", "none") for r in pack["register"])


def test_estimates_totals_and_audit(env):
    c, h, p = env
    pack = c.get(f"/api/projects/{p['id']}/meeting?date=2026-11-13", headers=h).json()
    old = next(r for r in pack["register"] if "RA-STR-110" in r["title"])
    new = next(r for r in pack["register"] if "Sprinkler" in r["title"])
    assert c.patch(f"/api/events/{old['event_id']}/estimate", headers=h, json={"estimated_value": 18500, "value_note": "bigger pads"}).status_code == 200
    assert c.patch(f"/api/events/{new['event_id']}/estimate", headers=h, json={"estimated_value": 48000}).status_code == 200
    assert c.patch(f"/api/events/{new['event_id']}/estimate", headers=h, json={"estimated_value": -5}).status_code == 422
    t = c.get(f"/api/projects/{p['id']}/meeting?date=2026-11-13", headers=h).json()["totals"]
    assert t["all"] == 66500 and t["not_notified"] == 66500 and t["time_bar_risk"] == 18500  # 9.2 is a condition precedent
    audit = c.get(f"/api/projects/{p['id']}/audit", headers=h).json()
    est = [a for a in audit if a["action"] == "event.estimate"]
    assert len(est) == 2 and est[-1]["details"]["after"]["value_note"] == "bigger pads"


def test_actions_carry_forward_and_close(env):
    c, h, p = env
    base = f"/api/projects/{p['id']}"
    a = c.post(f"{base}/meeting-items", headers=h, json={"kind": "action", "text": "Issue 9.2 notice for the tank room", "owner": "Aoife",
                                                          "due_date": "2026-11-10", "meeting_date": "2026-11-06"}).json()
    c.post(f"{base}/meeting-items", headers=h, json={"kind": "decision", "text": "Price the tank room before notifying", "meeting_date": "2026-11-06"})
    pack = c.get(f"{base}/meeting?date=2026-11-13", headers=h).json()
    assert pack["previous_meeting"] == "2026-11-06" and pack["since"] == "2026-11-06"
    assert [x["id"] for x in pack["actions_open"]] == [a["id"]] and pack["actions_open"][0]["overdue"]
    assert [d["text"] for d in pack["previous_decisions"]] == ["Price the tank room before notifying"]
    c.patch(f"/api/meeting-items/{a['id']}", headers=h, json={"status": "done", "closed_on": "2026-11-12"})
    pack = c.get(f"{base}/meeting?date=2026-11-13", headers=h).json()
    assert pack["actions_open"] == [] and [x["id"] for x in pack["actions_closed"]] == [a["id"]]
    # the next meeting no longer lists it as closed "since the last meeting"
    c.post(f"{base}/meeting-items", headers=h, json={"kind": "decision", "text": "Notify now", "meeting_date": "2026-11-13"})
    nxt = c.get(f"{base}/meeting?date=2026-11-20", headers=h).json()
    assert nxt["previous_meeting"] == "2026-11-13" and nxt["actions_closed"] == []
    dec = c.get(f"{base}/meeting?date=2026-11-13", headers=h).json()["decisions"]
    assert c.patch(f"/api/meeting-items/{dec[0]['id']}", headers=h, json={"status": "done"}).status_code == 422


def test_exports(env):
    c, h, p = env
    pdf = c.get(f"/api/projects/{p['id']}/meeting/export?format=pdf&date=2026-11-13", headers=h)
    docx = c.get(f"/api/projects/{p['id']}/meeting/export?format=docx&date=2026-11-13", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    assert c.get(f"/api/projects/{p['id']}/meeting/export?format=xls", headers=h).status_code == 422


def test_meeting_tenancy(env):
    c, h, p = env
    other = register(c, "rival@meeting.example", org="Rival")
    assert c.get(f"/api/projects/{p['id']}/meeting", headers=other).status_code == 404
    ev = c.get(f"/api/projects/{p['id']}/events", headers=h).json()[0]
    assert c.patch(f"/api/events/{ev['id']}/estimate", headers=other, json={"estimated_value": 1}).status_code == 404
    item = c.get(f"/api/projects/{p['id']}/meeting?date=2026-11-13", headers=h).json()["decisions"][0]
    assert c.patch(f"/api/meeting-items/{item['id']}", headers=other, json={"text": "hijack"}).status_code == 404
    assert c.post(f"/api/projects/{p['id']}/meeting-items", headers=other, json={"kind": "action", "text": "x y"}).status_code == 404
