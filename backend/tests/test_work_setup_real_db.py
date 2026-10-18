"""B3 guided work setup over HTTP against real FalkorDB (chat flow + structured API).

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. No model is used by setup turns (the scripted provider from the
shared fixture would only serve planning requests). Throwaway project per test.
"""
from uuid import uuid4

from relaymind.memory.tasks import record_person
from test_plan_review_real_db import NS, login, pytestmark, wait_done, world  # noqa: F401  (fixture + skip mark)


def say(c, pid, sid, text):
    rid = c.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": text}).json()["run_id"]
    return wait_done(c, pid, sid, rid)["run"]


def test_chat_setup_asks_for_missing_fields_and_never_guesses(world):
    pid, client = world
    record_person(client, NS, pid, "ns-ops-lead", "Operations lead")
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]

    first = say(c, pid, sid, "Set up new work: Supplier recovery follow-up")
    assert (first["request_kind"], first["status"]) == ("work_setup", "completed")
    assert "Still needed" in first["answer"] and "Start date" in first["answer"] and "ns-ops-lead" in first["answer"]
    [item] = c.get(f"/api/projects/{pid}/work-items").json()
    assert (item["status"], item["title"], item["start_date"], item["deadline"]) == (
        "draft", "Supplier recovery follow-up", None, None)

    second = say(c, pid, sid, "start: 2026-10-20\ndeadline: next Friday")
    assert "don't guess" in second["answer"]
    item = c.get(f"/api/projects/{pid}/work-items/{item['id']}").json()
    assert (item["start_date"], item["deadline"]) == ("2026-10-20", None)

    third = say(c, pid, sid, "deadline: 2026-10-10")                      # before start: rejected, not saved
    assert "before start date" in third["answer"]
    assert c.get(f"/api/projects/{pid}/work-items/{item['id']}").json()["deadline"] is None

    assert say(c, pid, sid, "What changed?")["request_kind"] == "factual"  # not swallowed by the open draft

    early = say(c, pid, sid, "confirm")                                    # incomplete -> refused, still draft
    assert "Still missing" in early["answer"]
    say(c, pid, sid, "deadline: 2026-10-31\ntimezone: Asia/Kolkata\noutcome: All exposed orders dispositioned\n"
                     "owner: ns-ops-lead\nreminders: daily at 09:00")
    done = say(c, pid, sid, "confirm")
    assert "Confirmed: Supplier recovery follow-up" in done["answer"]
    item = c.get(f"/api/projects/{pid}/work-items/{item['id']}").json()
    assert (item["status"], item["deadline"], item["timezone"], item["owner_id"], item["missing"]) == (
        "confirmed", "2026-10-31", "Asia/Kolkata", "ns-ops-lead", [])
    assert item["reminder"] == {"kind": "daily_summary", "time_of_day": "09:00", "custom_times": []}


def test_structured_api_validation_versions_and_isolation(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    op = str(uuid4())
    body = {"operation_id": op, "title": "Audit", "start_date": "2026-11-01", "timezone": "UTC"}
    r = c.post(f"/api/projects/{pid}/sessions/{sid}/work-items", json=body)
    assert r.status_code == 201, r.text
    item = r.json()
    assert c.post(f"/api/projects/{pid}/sessions/{sid}/work-items", json=body).json()["id"] == item["id"]   # idempotent
    assert c.post(f"/api/projects/{pid}/sessions/{sid}/work-items",
                  json={**body, "created_by": "x"}).status_code == 422                       # no identity fields
    assert c.post(f"/api/projects/{pid}/sessions/{sid}/work-items",
                  json={"operation_id": str(uuid4()), "timezone": "IST"}).status_code == 422  # ambiguous zone
    url = f"/api/projects/{pid}/work-items/{item['id']}"
    assert c.post(url, json={"expected_version": 1, "deadline": "2026-10-01"}).status_code == 422   # before start
    assert c.post(url, json={"expected_version": 1, "owner_id": "nobody"}).status_code == 422       # not a person
    v2 = c.post(url, json={"expected_version": 1, "deadline": "2026-11-30", "owner_id": "developer-a"}).json()
    assert v2["version"] == 2
    assert c.post(url, json={"expected_version": 1, "outcome": "x"}).status_code == 409             # stale version
    tr = url + "/transition"
    assert c.post(tr, json={"expected_version": 2, "action": "complete"}).status_code == 409        # not confirmed
    assert c.post(tr, json={"expected_version": 2, "action": "confirm"}).status_code == 422         # missing fields
    v3 = c.post(url, json={"expected_version": 2, "outcome": "Audit closed", "reminder": {"kind": "none"}}).json()
    confirmed = c.post(tr, json={"expected_version": v3["version"], "action": "confirm"}).json()
    assert confirmed["status"] == "confirmed" and confirmed["confirmed_at"]
    # Confirmed items are editable (decisions change; history kept as versioned snapshots).
    edited = c.post(url, json={"expected_version": confirmed["version"], "deadline": "2026-12-15"})
    assert edited.status_code == 200 and edited.json()["version"] == confirmed["version"] + 1
    assert edited.json()["status"] == "confirmed" and edited.json()["deadline"] == "2026-12-15"
    confirmed = edited.json()
    for other in ("northstar.peer", "harbor.lead"):
        o = login(other)
        assert o.get(url).status_code == 404 and o.get(f"/api/projects/{pid}/work-items").json() == []
        assert o.post(tr, json={"expected_version": confirmed["version"], "action": "cancel"}).status_code == 404
    finished = c.post(tr, json={"expected_version": confirmed["version"], "action": "complete"}).json()
    assert finished["status"] == "completed"
    assert c.post(tr, json={"expected_version": finished["version"], "action": "cancel"}).status_code == 409
    assert c.post(url, json={"expected_version": finished["version"], "title": "y"}).status_code == 409   # completed: locked


def test_natural_phrasing_starts_setup_in_chat(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    run = say(c, pid, sid, "I'm working on the supplier recovery follow-up, deadline is 25 October 2026")
    assert (run["request_kind"], run["status"]) == ("work_setup", "completed")
    [item] = c.get(f"/api/projects/{pid}/work-items").json()
    assert (item["title"], item["deadline"], item["status"]) == ("supplier recovery follow-up", "2026-10-25", "draft")
    assert "Still needed" in run["answer"]
    nxt = say(c, pid, sid, "I'm working on the launch, what should we do next?")   # question: NOT setup
    assert nxt["request_kind"] != "work_setup"
