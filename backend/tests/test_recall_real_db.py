"""Multi-chat memory M1: recall across the caller's own chats, against real FalkorDB (no model call).

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. Messages are seeded directly into owned sessions; recall questions run
through the real HTTP API. Covers cross-chat recall, Overseer verification, the current question never
matching itself, honest "nothing found", and isolation from other users and other companies.
"""
from relaymind.memory.conversations import save_message
from relaymind.workflow.recall import is_recall, query_terms
from test_plan_review_real_db import NS, login, pytestmark, wait_done, world  # noqa: F401


def say(c, pid, sid, text):
    rid = c.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": text}).json()["run_id"]
    return wait_done(c, pid, sid, rid)["run"]


def seed_chat(c, client, pid, ctx, lines):
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    for i, (role, text) in enumerate(lines):
        save_message(client, ctx, pid, sid, f"{sid}-m{i}", role, text)
    return sid


def test_detection_and_terms():
    assert is_recall("Do you remember what I said about the Coldline delay?")
    assert is_recall("what did I mention earlier about pricing?")
    assert is_recall("in the other chat I mentioned vendors")
    assert not is_recall("What changed?") and not is_recall("Remember that Coldline prefers calls")
    assert query_terms("do you remember what I said about the Coldline delay?") == ["coldline", "delay"]


def test_recall_finds_what_i_said_in_another_chat(world):
    pid, client = world
    c = login("northstar.lead")
    chat_a = seed_chat(c, client, pid, NS, [("user", "Coldline prefers phone calls before 10am, never email."),
                                            ("assistant", "Noted."),
                                            ("user", "The pricing page needs legal review first.")])
    chat_b = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    run = say(c, pid, chat_b, "Do you remember what I said about Coldline?")
    assert (run["request_kind"], run["status"]) == ("factual", "completed")
    assert "Coldline prefers phone calls before 10am" in run["answer"] and f"{chat_a}-m0" in run["answer"]
    assert 'In "Coldline prefers phone calls' in run["answer"]                      # chat named by its first message
    assert "not an approved decision" in run["answer"]
    assert run["overseer"]["ok"] and run["overseer"]["checks_run"] >= 1             # quote grounded via owned lookup
    assert "pricing page" not in run["answer"]                                      # irrelevant line not quoted
    assert "Noted." not in run["answer"]                                            # only what the USER said


def test_current_question_never_matches_itself_and_nothing_found_is_honest(world):
    pid, client = world
    c = login("northstar.lead")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    run = say(c, pid, sid, "Do you remember what I said about zebra crossings?")
    assert run["status"] == "completed" and "no matching earlier messages for these terms: zebra, crossings" in run["answer"]
    again = say(c, pid, sid, "Do you remember what I said about zebra crossings?")
    assert "no matching earlier messages" in again["answer"]                        # earlier recall question skipped


def test_recall_is_isolated_per_user_and_company(world):
    pid, client = world
    c = login("northstar.lead")
    seed_chat(c, client, pid, NS, [("user", "Coldline prefers phone calls before 10am.")])
    for other in ("northstar.peer", "harbor.lead"):                                 # same company, other company
        o = login(other)
        sid = o.post(f"/api/projects/{pid}/sessions").json()["id"]
        run = say(o, pid, sid, "Do you remember what I said about Coldline?")
        assert "Coldline prefers phone calls" not in run["answer"], other
        assert "no matching earlier messages" in run["answer"]


def test_assistant_replies_are_recalled_separately_and_labelled(world):
    pid, client = world
    c = login("northstar.lead")
    from relaymind.memory.artifacts import ArtifactStore
    chat = seed_chat(c, client, pid, NS, [("user", "How should we handle the Coldline delay?")])
    rid = "22222222-3333-4444-5555-666666666666"                      # a PLANNING run: RelayMind's suggestion
    ArtifactStore(client, NS, pid, chat).put("run", rid, {
        "id": rid, "project_id": pid, "session_id": chat, "owner_id": "developer-a", "tenant_id": "demo-a",
        "company_id": "northstar", "request": "How should we handle the Coldline delay?",
        "request_kind": "planning", "status": "completed"})
    save_message(client, NS, pid, chat, f"{rid}-completed-summary", "assistant",
                 "I suggest calling Coldline before confirming any new date.")
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    mine = say(c, pid, sid, "what did you suggest about Coldline?")
    assert "RelayMind replied" in mine["answer"] and "calling Coldline before confirming" in mine["answer"]
    assert "you said" not in mine["answer"]
    assert [r["role"] for r in mine["memory_refs"]] == ["assistant"]
    theirs = say(c, pid, sid, "what did I say about Coldline?")
    assert "you said" in theirs["answer"] and "RelayMind replied" not in theirs["answer"]
    ref = theirs["memory_refs"][0]                                       # navigation fields for the UI
    assert (ref["role"], ref["session_id"], ref["message_id"]) == ("user", chat, f"{chat}-m0")
    assert ref["chat_title"].startswith("How should we handle") and ref["created_at"] > 0


def test_doctored_quote_is_caught_and_capability_is_advertised(world, monkeypatch):
    from relaymind.workflow import recall
    pid, client = world
    c = login("northstar.lead")
    seed_chat(c, client, pid, NS, [("user", "Coldline prefers phone calls before 10am.")])
    real = recall._snippet
    monkeypatch.setattr(recall, "_snippet", lambda text, terms: real(text, terms).replace("phone calls", "emails"))
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    run = say(c, pid, sid, "Do you remember what I said about Coldline?")
    assert run["status"] == "blocked" and "emails" not in run["answer"]    # misquote never shown
    assert c.get(f"/api/projects/{pid}/workflow/capabilities").json()["memory"] is True


def test_recall_explains_its_search(world):
    pid, client = world
    c = login("northstar.lead")
    seed_chat(c, client, pid, NS, [("user", f"Coldline note number {i}: check the pallets.") for i in range(5)])
    sid = c.post(f"/api/projects/{pid}/sessions").json()["id"]
    run = say(c, pid, sid, "Do you remember what I said about Coldline?")
    info = run["memory_search"]
    assert (info["method"], info["matches"], info["shown"], info["more"], info["role"]) == ("keyword", 5, 3, True, "user")
    assert info["scanned"] >= 5 and "2 more matched" in run["answer"] and run["overseer"]["ok"]
