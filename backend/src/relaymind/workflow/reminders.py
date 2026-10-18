"""B4: durable reminder scheduling and in-app delivery.

Schedule: when a work item is confirmed, one Reminder node is created per future occurrence, computed
in the item's IANA timezone:
- daily_summary at HH:MM: every day from start date to deadline;
- milestones at HH:MM: start, midpoint, day before deadline, deadline (deduplicated);
- custom: each listed local date-time.
Past occurrences are not scheduled. `delivery_key` (item + due time) is unique, so scheduling twice
cannot duplicate reminders.

Delivery (in-app only; no external channel is connected): a worker process claims due reminders with a
lease (one conditional query), checks the work item is still confirmed, writes the reminder message into
the item's chat session (deterministic id + content, so a retry after a crash cannot duplicate it),
records a ReminderDelivery and marks the reminder delivered. Failures are counted with exponential
backoff; after MAX_ATTEMPTS the reminder is marked failed with the error class. Completing or cancelling
the item stops all scheduled reminders, and the worker re-checks status at delivery time.

Snooze: an upcoming reminder moves to now + N minutes; a delivered one gets a single follow-up reminder.
Reschedule: confirmed items can change their reminder preference; future scheduled reminders are stopped
and recomputed. Nothing here claims delivery that did not happen.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.models import TrustedContext
from relaymind.contracts.workflow import ReminderPreference, WorkItem
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory.locking import serialized_write

MAX_ATTEMPTS = 5
LEASE_MS = 60_000
MAX_OCCURRENCES = 400


class ReminderConflict(ValueError):
    """Wrong state for this reminder operation (HTTP 409)."""


def _now() -> int:
    return int(time.time() * 1000)


def _epoch_ms(local: datetime, tz: str) -> int:
    return int(local.replace(tzinfo=ZoneInfo(tz)).timestamp() * 1000)


def occurrences(item: WorkItem) -> list[tuple[int, str]]:
    """(due epoch ms, label) for every occurrence of the item's reminder preference."""
    r: ReminderPreference | None = item.reminder
    if r is None or r.kind == "none":
        return []
    tz, start, end = item.timezone, item.start_date, item.deadline

    def at(day: date) -> datetime:
        hh, mm = map(int, r.time_of_day.split(":"))
        return datetime(day.year, day.month, day.day, hh, mm)
    if r.kind == "daily_summary":
        days = (end - start).days + 1
        if days > MAX_OCCURRENCES:
            raise ValueError(f"Daily reminders over more than {MAX_OCCURRENCES} days are not supported")
        out = [(_epoch_ms(at(start + timedelta(d)), tz), "daily summary") for d in range(days)]
    elif r.kind == "milestones":
        marks = {start: "start", start + (end - start) // 2: "midpoint", end - timedelta(1): "day before deadline",
                 end: "deadline"}
        out = [(_epoch_ms(at(d), tz), label) for d, label in sorted(marks.items()) if start <= d <= end]
    else:
        out = [(_epoch_ms(datetime.strptime(t, "%Y-%m-%dT%H:%M"), tz), "custom") for t in r.custom_times]
    return sorted(set(out))


def _graph(client, scope: AgentJobScope):
    return authorized_graph(client, scope.trusted_context(), scope.project_id)


_FIELDS = ("id", "work_item_id", "label", "due_at", "snoozed_until", "status", "attempts", "last_error",
           "delivered_at", "session_id")
_RETURN = "RETURN " + ", ".join(f"r.{f}" for f in _FIELDS)
_SCOPE = "r.tenant_id = $tenant AND r.company_id = $company AND r.created_by = $user AND r.project_id = $project"


def _params(scope):
    return {"tenant": scope.tenant_id, "company": scope.company_id, "user": scope.user_id, "project": scope.project_id}


def _row(row) -> dict:
    return dict(zip(_FIELDS, row))


@serialized_write
def schedule(client: Any, scope: AgentJobScope, item: WorkItem, *, now: int | None = None) -> int:
    """Create reminders for future occurrences. Idempotent by delivery_key. Returns how many are new."""
    now = _now() if now is None else now
    created = 0
    for due, label in occurrences(item):
        if due <= now:
            continue
        rows = _graph(client, scope).query(
            "MATCH (w:WorkItem {id: $item, status: 'confirmed'}) WHERE w.tenant_id = $tenant AND w.company_id = $company "
            "AND w.created_by = $user AND w.project_id = $project "
            "OPTIONAL MATCH (x:Reminder {delivery_key: $key}) WITH w, x WHERE x IS NULL "
            "CREATE (r:Reminder {id: $id, delivery_key: $key, work_item_id: w.id, label: $label, due_at: $due, "
            "snoozed_until: null, status: 'scheduled', attempts: 0, last_error: null, delivered_at: null, "
            "claim_token: null, lease_until: 0, tenant_id: $tenant, company_id: $company, created_by: $user, "
            "project_id: $project, session_id: w.session_id, created_at: $now})-[:FOR_WORK]->(w) RETURN r.id",
            params={**_params(scope), "item": item.id, "key": f"{item.id}:{due}", "id": f"rem-{uuid4().hex[:16]}",
                    "label": label, "due": due, "now": now}).result_set
        created += len(rows)
    return created


@serialized_write
def stop_all(client: Any, scope: AgentJobScope, item_id: str, reason: str) -> int:
    rows = _graph(client, scope).query(
        f"MATCH (r:Reminder {{work_item_id: $item}}) WHERE {_SCOPE} AND r.status = 'scheduled' "
        "SET r.status = 'stopped', r.last_error = $reason RETURN r.id",
        params={**_params(scope), "item": item_id, "reason": reason}).result_set
    return len(rows)


def on_transition(client: Any, scope: AgentJobScope, item: WorkItem) -> None:
    """Work-setup hook: schedule on confirm; stop on complete/cancel."""
    if item.status == "confirmed":
        schedule(client, scope, item)
    elif item.status in ("completed", "cancelled"):
        stop_all(client, scope, item.id, f"work item {item.status}")


def list_reminders(client: Any, scope: AgentJobScope, *, item_id: str | None = None,
                   status: str | None = None) -> list[dict]:
    rows = _graph(client, scope).ro_query(
        f"MATCH (r:Reminder) WHERE {_SCOPE} AND ($item IS NULL OR r.work_item_id = $item) "
        f"AND ($status IS NULL OR r.status = $status) {_RETURN} ORDER BY coalesce(r.snoozed_until, r.due_at) LIMIT 500",
        params={**_params(scope), "item": item_id, "status": status}).result_set
    return [_row(r) for r in rows]


def get_reminder(client, scope, reminder_id) -> dict:
    rows = _graph(client, scope).ro_query(f"MATCH (r:Reminder {{id: $id}}) WHERE {_SCOPE} {_RETURN}",
                                          params={**_params(scope), "id": reminder_id}).result_set
    if len(rows) != 1:
        raise AccessDenied("Reminder unavailable or access denied")
    return _row(rows[0])


@serialized_write
def snooze(client: Any, scope: AgentJobScope, reminder_id: str, minutes: int, *, now: int | None = None) -> dict:
    now = _now() if now is None else now
    r = get_reminder(client, scope, reminder_id)
    until = now + minutes * 60_000
    graph = _graph(client, scope)
    if r["status"] == "scheduled":
        graph.query(f"MATCH (r:Reminder {{id: $id}}) WHERE {_SCOPE} AND r.status = 'scheduled' "
                    "SET r.snoozed_until = $until RETURN r.id", params={**_params(scope), "id": reminder_id, "until": until})
        return get_reminder(client, scope, reminder_id)
    if r["status"] == "delivered":
        rows = graph.query(
            f"MATCH (r:Reminder {{id: $id}})-[:FOR_WORK]->(w:WorkItem {{status: 'confirmed'}}) WHERE {_SCOPE} "
            "CREATE (n:Reminder {id: $new, delivery_key: r.delivery_key + ':snooze:' + toString($until), "
            "work_item_id: r.work_item_id, label: r.label + ' (snoozed)', due_at: $until, snoozed_until: null, "
            "status: 'scheduled', attempts: 0, last_error: null, delivered_at: null, claim_token: null, lease_until: 0, "
            "tenant_id: r.tenant_id, company_id: r.company_id, created_by: r.created_by, project_id: r.project_id, "
            "session_id: r.session_id, created_at: $now})-[:FOR_WORK]->(w) CREATE (n)-[:SNOOZE_OF]->(r) RETURN n.id",
            params={**_params(scope), "id": reminder_id, "new": f"rem-{uuid4().hex[:16]}", "until": until,
                    "now": now}).result_set
        if len(rows) != 1:
            raise ReminderConflict("The work item is no longer active")
        return get_reminder(client, scope, rows[0][0])
    raise ReminderConflict(f"Cannot snooze a {r['status']} reminder")


def reschedule(client: Any, scope: AgentJobScope, item: WorkItem) -> int:
    """Stop future scheduled reminders and schedule the item's current preference."""
    stop_all(client, scope, item.id, "rescheduled")
    return schedule(client, scope, item)


# ----------------------------------------------------------------------------- delivery

def message_text(r: dict, item: WorkItem) -> str:
    """Deterministic (no 'now'), so a retried delivery writes an identical, idempotent message."""
    tz = ZoneInfo(item.timezone)
    when = datetime.fromtimestamp(r["due_at"] / 1000, tz).strftime("%Y-%m-%d %H:%M")
    days_left = (item.deadline - datetime.fromtimestamp(r["due_at"] / 1000, tz).date()).days
    lead = {"daily summary": "Daily reminder", "start": "Starts today", "midpoint": "Halfway point",
            "day before deadline": "Due tomorrow", "deadline": "Due today"}.get(r["label"], "Reminder")
    return (f"**{lead}: {item.title}** ({when} {item.timezone})\n"
            f"- Outcome: {item.outcome}\n- Owner: {item.owner_id}\n- Deadline: {item.deadline} "
            f"({days_left} day{'s' if days_left != 1 else ''} left)\n"
            f"_In-app reminder for {item.id}. Snooze it, or mark the work as done to stop reminders._")


def _deliver_one(client, graph, ctx: TrustedContext, r: dict, token: str, now: int, deliver) -> str:
    from relaymind.workflow.work_setup import get_item
    scope = AgentJobScope(tenant_id=ctx.tenant_id, user_id=ctx.user_id, company_id=r["company_id"],
                          project_id=r["project_id"], session_id=r["session_id"])
    item = get_item(client, scope, r["work_item_id"])
    if item.status != "confirmed":
        graph.query("MATCH (r:Reminder {id: $id, claim_token: $t}) SET r.status = 'stopped', "
                    "r.last_error = 'work item ' + $s RETURN r.id", params={"id": r["id"], "t": token, "s": item.status})
        return "stopped"
    deliver(client, ctx, r, item)
    rows = graph.query(
        "MATCH (r:Reminder {id: $id, claim_token: $t, status: 'delivering'}) "
        "MERGE (d:ReminderDelivery {id: r.delivery_key}) ON CREATE SET d.channel = 'in_app', d.delivered_at = $now, "
        "d.reminder_id = r.id, d.project_id = r.project_id, d.attempt = r.attempts + 1 "
        "MERGE (r)-[:DELIVERED_AS]->(d) "
        "SET r.status = 'delivered', r.delivered_at = $now, r.attempts = r.attempts + 1, r.claim_token = null RETURN r.id",
        params={"id": r["id"], "t": token, "now": now}).result_set
    if len(rows) != 1:
        raise RuntimeError("Lease lost before the delivery was recorded")
    return "delivered"


def in_app_delivery(client, ctx: TrustedContext, r: dict, item: WorkItem) -> None:
    from relaymind.memory.conversations import save_message
    save_message(client, ctx, r["project_id"], r["session_id"], f"reminder-{r['id']}", "assistant", message_text(r, item))


def run_once(client: Any, graph_names: list[str] | None = None, *, now: int | None = None,
             deliver=in_app_delivery) -> dict:
    """Deliver every due reminder in the mapped graphs once. Safe to run from several workers."""
    from relaymind.graph.access import _DEMO_ACCESS
    now = _now() if now is None else now
    stats = {"delivered": 0, "stopped": 0, "retry": 0, "failed": 0}
    targets = {}
    for (tenant, user), (graph_name, projects) in sorted(_DEMO_ACCESS.items()):
        if graph_names is None or graph_name in graph_names:
            targets.setdefault(graph_name, (tenant, user, sorted(projects)[0]))
    for graph_name, (tenant, user, project) in targets.items():
        graph = authorized_graph(client, TrustedContext(tenant_id=tenant, user_id=user), project)
        due = graph.ro_query(
            "MATCH (r:Reminder) WHERE (r.status = 'scheduled' AND coalesce(r.snoozed_until, r.due_at) <= $now) "
            "OR (r.status = 'delivering' AND r.lease_until < $now) "
            "RETURN r.id, r.tenant_id, r.created_by, r.company_id, r.project_id, r.session_id, r.work_item_id, "
            "r.due_at, r.label ORDER BY r.due_at LIMIT 200", params={"now": now}).result_set
        for rid, r_tenant, r_user, company, project_id, session_id, item_id, due_at, label in due:
            token = uuid4().hex
            claimed = graph.query(
                "MATCH (r:Reminder {id: $id}) WHERE (r.status = 'scheduled' AND coalesce(r.snoozed_until, r.due_at) <= $now) "
                "OR (r.status = 'delivering' AND r.lease_until < $now) "
                "SET r.status = 'delivering', r.claim_token = $t, r.lease_until = $lease RETURN r.id",
                params={"id": rid, "now": now, "t": token, "lease": now + LEASE_MS}).result_set
            if len(claimed) != 1:
                continue                                   # another worker took it
            r = {"id": rid, "company_id": company, "project_id": project_id, "session_id": session_id,
                 "work_item_id": item_id, "due_at": due_at, "label": label}
            ctx = TrustedContext(tenant_id=r_tenant, user_id=r_user)
            try:
                stats[_deliver_one(client, graph, ctx, r, token, now, deliver)] += 1
            except Exception as exc:                       # error class only; never record content
                rows = graph.query(
                    "MATCH (r:Reminder {id: $id, claim_token: $t}) SET r.attempts = r.attempts + 1, "
                    "r.last_error = $err, r.claim_token = null, "
                    "r.status = CASE WHEN r.attempts + 1 >= $max THEN 'failed' ELSE 'scheduled' END, "
                    "r.snoozed_until = CASE WHEN r.attempts + 1 >= $max THEN r.snoozed_until "
                    "ELSE $now + 30000 * toInteger(2 ^ r.attempts) END RETURN r.status",
                    params={"id": rid, "t": token, "err": type(exc).__name__, "max": MAX_ATTEMPTS, "now": now}).result_set
                stats["failed" if rows and rows[0][0] == "failed" else "retry"] += 1
    return stats


def confirmation_note(client, scope, item: WorkItem) -> str:
    if item.reminder is None or item.reminder.kind == "none":
        return "No reminders were requested."
    upcoming = list_reminders(client, scope, item_id=item.id, status="scheduled")
    if not upcoming:
        return "No future reminder times fall inside this work's dates, so none were scheduled."
    first = datetime.fromtimestamp(upcoming[0]["due_at"] / 1000, ZoneInfo(item.timezone)).strftime("%Y-%m-%d %H:%M")
    note = (f"Scheduled {len(upcoming)} in-app reminder{'s' if len(upcoming) != 1 else ''} in this conversation; "
            f"the first is at {first} {item.timezone}. Reminders stop when you finish or cancel the work. "
            "No email or other external channel is connected.")
    if not worker_alive(client):
        note += (" Saved; delivery is waiting for the reminder worker, which is currently OFFLINE - "
                 "no reminder will arrive until it is running (scripts/reminder_worker.py).")
    return note


# ----------------------------------------------------------------------------- worker liveness

HEARTBEAT_KEY = "relaymind:reminder_worker:heartbeat"


def heartbeat(client: Any, now: int | None = None) -> None:
    # No expiry: the timestamp stays readable so the UI can show "last seen" after the worker dies.
    client.connection.set(HEARTBEAT_KEY, str(_now() if now is None else now))


def last_heartbeat(client: Any) -> int | None:
    """Epoch ms of the last worker heartbeat ever recorded, or None."""
    try:
        value = client.connection.get(HEARTBEAT_KEY)
        return int(value) if value else None
    except Exception:
        return None


def worker_alive(client: Any) -> bool:
    """True only if a worker reported within the last 2 minutes."""
    beat = last_heartbeat(client)
    return beat is not None and _now() - beat < 120_000


def worker_loop(client: Any, interval: float = 15.0, stop=None) -> None:
    import logging
    log = logging.getLogger(__name__)
    while stop is None or not stop.is_set():
        try:
            heartbeat(client)
            stats = run_once(client)
            if any(stats.values()):
                log.info("reminder_worker %s", stats)
        except Exception as exc:   # keep running; class name only
            log.error("reminder_worker_error %s", type(exc).__name__)
        if stop is not None:
            stop.wait(interval)
        else:
            time.sleep(interval)
