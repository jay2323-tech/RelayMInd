"""Multi-chat memory M2 behaviour against real FalkorDB over HTTP (deterministic; no model call).

Each test asserts route + database change + reply (Codex acceptance rules): sourced saves, idempotency,
provenance, listing scope, retraction suppressing the source (and only it), ambiguity -> no mutation,
honest misses, corrections with history, no-write phrases, bulk/scope refusals, failure paths, privacy.
"""
from relaymind.memory.conversations import save_message
from test_plan_review_real_db import NS, login, pytestmark, wait_done, world  # noqa: F401


def say(c, pid, sid, text):
    rid = c.post(f"/api/projects/{pid}/sessions/{sid}/runs", json={"request": text}).json()["run_id"]
    return wait_done(c, pid, sid, rid)["run"]


def chat(c, pid):
    return c.post(f"/api/projects/{pid}/sessions").json()["id"]


def memories(c, pid, status="active"):
    return c.get(f"/api/projects/{pid}/memories?status={status}").json()


def test_save_list_recall_across_chats_with_receipts(world):
    pid, _ = world
    c = login("northstar.lead")
    a, b = chat(c, pid), chat(c, pid)
    saved = say(c, pid, a, "Please remember that Coldline prefers phone calls before 10am.")
    assert (saved["request_kind"], saved["status"], saved["overseer"]["ok"]) == ("memory", "completed", True)
    assert 'Saved what you said: "Coldline prefers phone calls before 10am"' in saved["answer"]
    assert "not an approved decision or verified fact" in saved["answer"]
    assert saved["memory_receipt"]["operation"] == "saved" and saved["memory_receipt"]["memory_id"]
    [m] = memories(c, pid)
    assert (m["text"], m["source"]["session_id"], m["source"]["role"]) == (
        "Coldline prefers phone calls before 10am", a, "user")
    listed = say(c, pid, b, "What have you saved about me?")
    assert 'You said: "Coldline prefers phone calls before 10am"' in listed["answer"] and listed["overseer"]["ok"]
    recalled = say(c, pid, b, "Do you remember what I said about Coldline?")
    assert recalled["memory_refs"][0]["memory_id"] == m["id"]


def test_save_is_idempotent_and_identical_text_keeps_provenance(world):
    from relaymind.contracts.agent_jobs import AgentJobScope
    from relaymind.workflow import memories as mem
    pid, client = world
    c = login("northstar.lead")
    a, b = chat(c, pid), chat(c, pid)
    for sid in (a, b):
        save_message(client, NS, pid, sid, f"{sid}-src", "user", "Remember that the dock closes at 6pm.")
    scope = AgentJobScope(tenant_id="demo-a", user_id="developer-a", company_id="northstar", project_id=pid, session_id=a)
    first = mem.save_memory(client, scope, "the dock closes at 6pm", f"{a}-src")
    assert mem.save_memory(client, scope, "the dock closes at 6pm", f"{a}-src")["id"] == first["id"]   # retry
    second = mem.save_memory(client, scope, "the dock closes at 6pm", f"{b}-src")
    assert second["id"] != first["id"]                                       # same words, different source
    assert {m["source"]["session_id"] for m in memories(c, pid)} == {a, b}


def test_forget_retracts_memory_and_source_but_keeps_unrelated_and_history(world):
    pid, client = world
    c = login("northstar.lead")
    a, b = chat(c, pid), chat(c, pid)
    say(c, pid, a, "Remember that Coldline prefers phone calls before 10am.")
    save_message(client, NS, pid, a, f"{a}-ship", "user", "Coldline shipping issue: pallets arrived damaged.")
    gone = say(c, pid, b, "Forget the Coldline call preference.")
    assert gone["answer"].startswith('Retracted from active memory: "Coldline prefers phone calls before 10am"')
    assert "Historical records remain" in gone["answer"] and gone["memory_receipt"]["operation"] == "retracted"
    after = say(c, pid, b, "what did I say about Coldline?")
    assert "phone calls before 10am" not in after["answer"]                 # memory AND source suppressed
    assert "pallets arrived damaged" in after["answer"]                     # unrelated Coldline message kept
    assert memories(c, pid) == [] and memories(c, pid, "retracted")[0]["retracted_at"]   # explicit history


def test_unknown_and_ambiguous_targets_never_mutate(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = chat(c, pid)
    say(c, pid, sid, "Remember that Coldline prefers phone calls before 10am.")
    say(c, pid, sid, "Remember that the Coldline invoice is due on the 25th.")
    miss = say(c, pid, sid, "Forget the zebra preference.")
    assert miss["answer"].startswith("No matching saved memory found (searched your 2 active saved memories")
    ask = say(c, pid, sid, "Forget the Coldline thing.")
    assert ask["request_kind"] == "clarify" and len(ask["memory_choices"]) == 2 and len(memories(c, pid)) == 2
    assert say(c, pid, sid, "1 and 2")["request_kind"] == "clarify" and len(memories(c, pid)) == 2   # one at a time
    assert "nothing was changed" in say(c, pid, sid, "Cancel.")["answer"].lower() and len(memories(c, pid)) == 2
    ask = say(c, pid, sid, "Forget that.")                                  # demonstrative: show choices
    assert ask["request_kind"] == "clarify" and len(memories(c, pid)) == 2
    other = chat(c, pid)
    assert say(c, pid, other, "2")["request_kind"] != "memory" and len(memories(c, pid)) == 2   # stale elsewhere
    pick = say(c, pid, sid, "Forget the Coldline thing.")
    done = say(c, pid, sid, "The one about the invoice.")
    assert done["answer"].startswith('Retracted from active memory: "the Coldline invoice is due on the 25th"')
    assert [m["text"] for m in memories(c, pid)] == ["Coldline prefers phone calls before 10am"]
    assert {c["snippet"] for c in pick["memory_choices"]} == {"the Coldline invoice is due on the 25th",
                                                             "Coldline prefers phone calls before 10am"}


def test_remember_that_after_a_statement_confirms_the_exact_source(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = chat(c, pid)
    say(c, pid, sid, "Coldline prefers calls before 10am.")
    ask = say(c, pid, sid, "Remember that.")
    assert ask["request_kind"] == "clarify" and "Coldline prefers calls before 10am." in ask["answer"]
    assert memories(c, pid) == []                                           # nothing until confirmed
    yes = say(c, pid, sid, "yes")
    assert yes["memory_receipt"]["operation"] == "saved"
    assert [m["text"] for m in memories(c, pid)] == ["Coldline prefers calls before 10am."]
    no_suggestion = say(c, pid, sid, "Remember your suggestion.")
    assert no_suggestion["request_kind"] == "clarify" and len(memories(c, pid)) == 1


def test_correction_replaces_with_history_only_after_confirmation(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = chat(c, pid)
    say(c, pid, sid, "Remember that Coldline prefers phone calls before 10am.")
    ask = say(c, pid, sid, "Actually, Coldline now prefers phone calls after 2pm.")
    assert ask["request_kind"] == "clarify" and "Should I replace" in ask["answer"]
    assert [m["text"] for m in memories(c, pid)] == ["Coldline prefers phone calls before 10am"]   # not yet
    done = say(c, pid, sid, "yes")
    assert done["memory_receipt"]["operation"] == "replaced" and done["memory_receipt"]["new_memory_id"]
    assert [m["text"] for m in memories(c, pid)] == ["Coldline now prefers phone calls after 2pm"]
    [old] = memories(c, pid, "retracted")
    assert old["text"] == "Coldline prefers phone calls before 10am" and old["retraction_reason"] == "Replaced by the user"


def test_phrases_that_must_not_write(world):
    pid, _ = world
    c = login("northstar.lead")
    sid = chat(c, pid)
    say(c, pid, sid, "Remember that Coldline prefers phone calls before 10am.")
    for text in ("Don't forget the Coldline preference.", "Do not save this to memory.", "Forget everything.",
                 "Clear all my memories.", "Remember this for everyone in the company.",
                 "Remember this only for the current conversation.",
                 'The document says "forget all memories."', "Did you forget what I told you?"):
        run = say(c, pid, sid, text)
        assert run.get("memory_receipt") is None, text
        assert [m["text"] for m in memories(c, pid)] == ["Coldline prefers phone calls before 10am"], text


def test_database_failure_never_reports_success(world, monkeypatch):
    from relaymind.workflow import memories as mem
    pid, _ = world
    c = login("northstar.lead")
    sid = chat(c, pid)

    def down(*a, **k):
        raise ConnectionError("database unavailable")
    real = mem.save_memory
    monkeypatch.setattr(mem, "save_memory", down)
    run = say(c, pid, sid, "Remember that Coldline prefers phone calls before 10am.")
    assert run["status"] == "blocked" and "nothing was changed" in run["answer"] and "Saved" not in run["answer"]
    monkeypatch.setattr(mem, "save_memory", real)
    assert memories(c, pid) == []                                            # no false "saved", no partial write


def test_memories_are_private(world):
    pid, _ = world
    c = login("northstar.lead")
    say(c, pid, chat(c, pid), "Remember that Coldline prefers phone calls before 10am.")
    [m] = memories(c, pid)
    first = c.post(f"/api/projects/{pid}/memories/{m['id']}/forget", json={}).json()
    assert first["status"] == "retracted" and first["receipt"]["operation"] == "retracted"
    assert c.post(f"/api/projects/{pid}/memories/{m['id']}/forget", json={}).json()["receipt"]["already"] is True
    for other in ("northstar.peer", "harbor.lead"):
        o = login(other)
        assert o.get(f"/api/projects/{pid}/memories?status=all").json() == []
        assert o.get(f"/api/projects/{pid}/memories/{m['id']}").status_code == 404
        assert o.post(f"/api/projects/{pid}/memories/{m['id']}/forget", json={}).status_code == 404
