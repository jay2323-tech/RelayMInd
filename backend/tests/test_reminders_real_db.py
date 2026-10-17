"""B4 reminder scheduling + worker delivery against real FalkorDB (throwaway graph).

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. Time is injected (`now=`) so due times are deterministic; the worker
is the real `run_once` used by scripts/reminder_worker.py. Covers idempotent scheduling, delivery,
dedupe on rerun / fresh client / concurrent workers, crash-after-message retry, retry exhaustion,
snooze, reschedule, stop on complete, and the worker liveness flag.
"""
import os
import threading
from datetime import date
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.models import TrustedContext
from relaymind.contracts.workflow import ReminderPreference, WorkFields
from relaymind.graph import access
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client
from relaymind.memory.conversations import create_session, load_messages
from relaymind.workflow import reminders as rem
from relaymind.workflow import work_setup as ws

load_dotenv()
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1", reason="Opt-in live FalkorDB tests")


@pytest.fixture
def env(monkeypatch):
    tag = uuid4().hex[:10]
    pid, gname = f"remtest-{tag}", f"relaymind_hbtest_{tag}"
    monkeypatch.setitem(access._DEMO_ACCESS, ("demo-b", "developer-b"), (gname, frozenset({pid})))
    client = create_client()
    ctx = TrustedContext(tenant_id="demo-b", user_id="developer-b")
    graph = authorized_graph(client, ctx, pid)
    graph.query("CREATE (:Project {id: $p})", params={"p": pid})
    create_session(client, ctx, pid, "s1")
    scope = AgentJobScope(tenant_id="demo-b", user_id="developer-b", company_id="harbor", project_id=pid, session_id="s1")
    yield client, graph, scope, ctx
    assert graph.name.startswith("relaymind_hbtest_")
    graph.delete()


def confirmed(client, scope, kind="daily_summary", start=date(2030, 1, 1), end=date(2030, 1, 3), **extra):
    pref = ReminderPreference(kind=kind, time_of_day=extra.pop("time_of_day", "09:00") if kind != "custom" else None,
                              custom_times=extra.pop("custom", []))
    item = ws.create_draft(client, scope, WorkFields(title="Follow-up", outcome="Done", start_date=start, deadline=end,
                                                      timezone="Asia/Kolkata", owner_id=scope.user_id, reminder=pref),
                           str(uuid4()))
    return ws.transition(client, scope, item.id, "confirm", item.version)


def run(client, graph, now, **kw):
    return rem.run_once(client, [graph.name], now=now, **kw)


def reminder_messages(client, ctx, scope):
    return [m for m in load_messages(client, ctx, scope.project_id, "s1", 0, 100) if m.id.startswith("reminder-")]


def test_schedule_deliver_dedupe_and_stop(env):
    client, graph, scope, ctx = env
    item = confirmed(client, scope)
    due = [r["due_at"] for r in rem.list_reminders(client, scope, item_id=item.id)]
    assert len(due) == 3 and rem.schedule(client, scope, item) == 0                      # idempotent scheduling
    assert run(client, graph, due[0] - 1) == {"delivered": 0, "stopped": 0, "retry": 0, "failed": 0}
    assert run(client, graph, due[0])["delivered"] == 1
    assert run(client, graph, due[0])["delivered"] == 0                                  # rerun: no duplicate
    assert rem.run_once(create_client(), [graph.name], now=due[0])["delivered"] == 0     # "restarted" worker
    msgs = reminder_messages(client, ctx, scope)
    assert len(msgs) == 1 and "Daily reminder: Follow-up" in msgs[0].content and "2 days left" in msgs[0].content
    deliveries = graph.ro_query("MATCH (d:ReminderDelivery) RETURN count(d)").result_set[0][0]
    assert deliveries == 1
    done = ws.transition(client, scope, item.id, "complete", item.version)
    statuses = sorted(r["status"] for r in rem.list_reminders(client, scope, item_id=item.id))
    assert statuses == ["delivered", "stopped", "stopped"]
    assert run(client, graph, due[-1] + 1)["delivered"] == 0 and done.status == "completed"


def test_concurrent_workers_deliver_once(env):
    client, graph, scope, ctx = env
    item = confirmed(client, scope, start=date(2030, 1, 1), end=date(2030, 1, 1))
    [r] = rem.list_reminders(client, scope, item_id=item.id)
    go, results = threading.Barrier(4), []

    def worker():
        go.wait()
        results.append(rem.run_once(create_client(), [graph.name], now=r["due_at"])["delivered"])
    threads = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert sum(results) == 1 and len(reminder_messages(client, ctx, scope)) == 1


def test_crash_after_message_retries_without_duplicate_and_exhausts(env):
    client, graph, scope, ctx = env
    item = confirmed(client, scope, start=date(2030, 1, 1), end=date(2030, 1, 2))
    first, second = sorted(r["due_at"] for r in rem.list_reminders(client, scope, item_id=item.id))

    def crash_after_write(c, cx, r, it):
        rem.in_app_delivery(c, cx, r, it)
        raise ConnectionError("simulated crash after the message was written")
    assert run(client, graph, first, deliver=crash_after_write)["retry"] == 1
    [r1] = [r for r in rem.list_reminders(client, scope, item_id=item.id) if r["due_at"] == first]
    assert (r1["status"], r1["attempts"], r1["last_error"]) == ("scheduled", 1, "ConnectionError")
    assert run(client, graph, first + 1)["delivered"] == 0                     # backoff respected
    assert run(client, graph, r1["snoozed_until"])["delivered"] == 1
    assert len(reminder_messages(client, ctx, scope)) == 1                     # identical message, not duplicated

    def always_fail(*_):
        raise TimeoutError()
    now = second
    for _ in range(rem.MAX_ATTEMPTS):
        run(client, graph, now, deliver=always_fail)
        now += 10 ** 9
    [r2] = [r for r in rem.list_reminders(client, scope, item_id=item.id) if r["due_at"] == second]
    assert (r2["status"], r2["attempts"], r2["last_error"]) == ("failed", rem.MAX_ATTEMPTS, "TimeoutError")


def test_snooze_reschedule_and_worker_status_check(env):
    client, graph, scope, ctx = env
    item = confirmed(client, scope, kind="milestones", start=date(2030, 1, 1), end=date(2030, 1, 9))
    rs = rem.list_reminders(client, scope, item_id=item.id)
    assert [r["label"] for r in rs] == ["start", "midpoint", "day before deadline", "deadline"]
    snoozed = rem.snooze(client, scope, rs[0]["id"], 60, now=rs[0]["due_at"] - 1000)
    assert snoozed["snoozed_until"] == rs[0]["due_at"] - 1000 + 3_600_000
    assert run(client, graph, rs[0]["due_at"])["delivered"] == 0               # not at the original time
    assert run(client, graph, snoozed["snoozed_until"])["delivered"] == 1
    follow = rem.snooze(client, scope, rs[0]["id"], 30, now=snoozed["snoozed_until"])   # delivered -> follow-up
    assert follow["status"] == "scheduled" and follow["id"] != rs[0]["id"]

    moved = ws.update_reminder(client, scope, item.id, ReminderPreference(kind="custom", custom_times=["2030-01-05T18:00"]),
                               item.version)
    after = rem.list_reminders(client, scope, item_id=item.id, status="scheduled")
    assert [r["label"] for r in after] == ["custom"] and moved.reminder.kind == "custom"

    # Worker re-checks the item at delivery time even if a reminder is still scheduled.
    graph.query("MATCH (w:WorkItem {id: $id}) SET w.status = 'cancelled'", params={"id": item.id})
    assert run(client, graph, after[0]["due_at"])["stopped"] == 1


def test_capability_reflects_a_running_worker(env):
    client, graph, scope, ctx = env
    client.connection.delete(rem.HEARTBEAT_KEY)
    assert rem.worker_alive(client) is False
    stop = threading.Event()
    t = threading.Thread(target=rem.worker_loop, args=(client, 0.2, stop), daemon=True)
    t.start()
    try:
        for _ in range(50):
            if rem.worker_alive(client):
                break
            stop.wait(0.05)
        assert rem.worker_alive(client) is True
    finally:
        stop.set(); t.join(5)
