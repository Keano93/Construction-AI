"""Commercial pack over a date range: sections, ranges, estimates, issued notices, exports, tenancy."""

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
    h = register(c, "qs@pack.example")
    p = c.post("/api/projects", json={"name": "Pack Test", "contract_form": "PWC", "holiday_region": "IE"}, headers=h).json()
    c.post(f"/api/projects/{p['id']}/parties", headers=h,
           json={"name": "Rory Nagle", "organisation": "Kilcrea", "role": "engineer", "email": "r.nagle@kilcrea.example"})
    c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": (CONTRACT.name, CONTRACT.read_bytes())}, data={"kind": "contract"})
    for r in c.get(f"/api/projects/{p['id']}/contract", headers=h).json()[0]["rules"]:
        if r["rule_type"] in ("notice", "time_bar"):
            c.post(f"/api/rules/{r['id']}/review", headers=h, json={"decision": "approve"})
    c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": ("old.eml", _email(
        "RA-STR-110 rev C", "Tue, 18 Aug 2026 10:00:00 +0100", "Revision C attached: pad foundations now 2.4m x 2.4m (previously 1.8m)."))})
    c.post(f"/api/projects/{p['id']}/documents", headers=h, files={"file": ("new.eml", _email(
        "Sprinkler tank room", "Mon, 09 Nov 2026 09:00:00 +0000", "The sprinkler tank room has to go up from 4.5m x 6m to 6m x 7m. Revised layout attached."))})
    return c, h, p


def _get(c, h, p, frm, to):
    r = c.get(f"/api/projects/{p['id']}/pack?from={frm}&to={to}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_range_controls_new_items_and_weeks(env):
    c, h, p = env
    week = _get(c, h, p, "2026-11-07", "2026-11-13")
    assert (week["from"], week["to"]) == ("2026-11-07", "2026-11-13")
    assert [e["title"] for e in week["new_events"]] == ["Sprinkler tank room"]
    assert sum(w["count"] for w in week["weekly"]) == 1 and week["weekly"][0]["week_start"] == "2026-11-02"
    month = _get(c, h, p, "2026-08-01", "2026-11-13")
    assert {e["title"] for e in month["new_events"]} >= {"RA-STR-110 rev C", "Sprinkler tank room"}
    # the register is the position at the end of the period: events after it are excluded
    before = _get(c, h, p, "2026-08-01", "2026-08-31")
    assert all("Sprinkler" not in r["title"] for r in before["register"])
    assert c.get(f"/api/projects/{p['id']}/pack?from=2026-11-13&to=2026-11-01", headers=h).status_code == 422
    assert c.get(f"/api/projects/{p['id']}/pack?from=2024-01-01&to=2026-11-13", headers=h).status_code == 422
    default = c.get(f"/api/projects/{p['id']}/pack", headers=h).json()
    from datetime import date, timedelta
    assert default["to"] == date.today().isoformat() and default["from"] == (date.today() - timedelta(days=6)).isoformat()


def test_notice_buckets_relative_to_period_end(env):
    c, h, p = env
    pack = _get(c, h, p, "2026-11-07", "2026-11-13")
    by_title = {n["event_title"]: n for n in pack["notices"]}
    assert by_title["RA-STR-110 rev C"]["bucket"] == "overdue"
    # 9 Nov + 10 working days = 23 Nov, which is 6 working days after 13 Nov
    assert by_title["Sprinkler tank room"]["bucket"] == "next_10"
    assert by_title["Sprinkler tank room"]["working_days_remaining"] == 6


def test_estimates_totals_and_audit(env):
    c, h, p = env
    pack = _get(c, h, p, "2026-08-01", "2026-11-13")
    old = next(r for r in pack["register"] if r["title"] == "RA-STR-110 rev C")
    new = next(r for r in pack["register"] if r["title"] == "Sprinkler tank room")
    assert c.patch(f"/api/events/{old['event_id']}/estimate", headers=h, json={"estimated_value": 18500, "value_note": "bigger pads"}).status_code == 200
    assert c.patch(f"/api/events/{new['event_id']}/estimate", headers=h, json={"estimated_value": 48000}).status_code == 200
    assert c.patch(f"/api/events/{new['event_id']}/estimate", headers=h, json={"estimated_value": -5}).status_code == 422
    # changing only the value keeps the note
    c.patch(f"/api/events/{old['event_id']}/estimate", headers=h, json={"estimated_value": 19000})
    pack = _get(c, h, p, "2026-08-01", "2026-11-13")
    t = pack["totals"]
    assert t["all"] == 67000 and t["not_notified"] == 67000 and t["time_bar_risk"] == 19000
    assert next(r for r in pack["register"] if r["title"] == "RA-STR-110 rev C")["value_note"] == "bigger pads"
    assert pack["summary"]["estimated_total"] == 67000
    est = [a for a in c.get(f"/api/projects/{p['id']}/audit", headers=h).json() if a["action"] == "event.estimate"]
    assert len(est) == 3


def test_issued_notice_appears_in_period(env):
    c, h, p = env
    pack = _get(c, h, p, "2026-11-07", "2026-11-13")
    tank = next(n for n in pack["notices"] if n["event_title"] == "Sprinkler tank room")
    rid = tank["review_item_id"]
    assert c.post(f"/api/review/{rid}/approve", headers=h, json={}).status_code == 200
    assert c.post(f"/api/review/{rid}/mark-issued", headers=h, json={"issued_on": "2026-11-12"}).status_code == 200
    pack = _get(c, h, p, "2026-11-07", "2026-11-13")
    assert [(i["event_title"], i["in_time"]) for i in pack["issued"]] == [("Sprinkler tank room", True)]
    assert next(r for r in pack["register"] if r["title"] == "Sprinkler tank room")["notice_state"] == "issued"
    assert pack["notice_position"]["issued"] >= 1
    earlier = _get(c, h, p, "2026-11-01", "2026-11-11")
    assert earlier["issued"] == []  # issued after that period ended
    assert next(r for r in earlier["register"] if r["title"] == "Sprinkler tank room")["notice_state"] == "open"


def test_exports(env):
    c, h, p = env
    pdf = c.get(f"/api/projects/{p['id']}/pack/export?format=pdf&from=2026-08-01&to=2026-11-13", headers=h)
    docx = c.get(f"/api/projects/{p['id']}/pack/export?format=docx&from=2026-08-01&to=2026-11-13", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and "2026-08-01 to 2026-11-13" in pdf.headers["content-disposition"]
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    assert c.get(f"/api/projects/{p['id']}/pack/export?format=xls", headers=h).status_code == 422


def test_pack_tenancy(env):
    c, h, p = env
    other = register(c, "rival@pack.example", org="Rival")
    assert c.get(f"/api/projects/{p['id']}/pack", headers=other).status_code == 404
    assert c.get(f"/api/projects/{p['id']}/pack/export", headers=other).status_code == 404
    ev = c.get(f"/api/projects/{p['id']}/events", headers=h).json()[0]
    assert c.patch(f"/api/events/{ev['id']}/estimate", headers=other, json={"estimated_value": 1}).status_code == 404
