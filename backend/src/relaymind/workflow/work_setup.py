"""B3: guided new-work setup (draft -> confirmed -> completed / cancelled).

Fields: title, intended outcome, start date, deadline, explicit IANA timezone, responsible owner
and reminder preference. Nothing is invented: missing fields stay empty and are asked for in chat.
Validation: deadline >= start date, timezone is a real IANA zone, owner is the current user or a
Person recorded in this project, reminder preference is complete.

Storage: one WorkItem node per item with an optimistic `version`; every write is one guarded query
that also stores an immutable WorkItemSnapshot. Scope: tenant + company + creator + project; the
session the item was set up in is recorded for chat replies. Missing and forbidden look the same.

Chat (no model): a setup request ("set up new work ...") creates a draft; while a draft is open in the
session, messages with explicit "field: value" lines update it, "confirm" confirms it, "cancel setup"
cancels it. Free-text dates such as "next Friday" are not guessed; the reply asks for YYYY-MM-DD.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from typing import Any, Callable

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.workflow import (REQUIRED_WORK_FIELDS, ReminderPreference, WorkFields, WorkItem,
                                          valid_timezone)
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory.locking import serialized_write


class WorkSetupConflict(ValueError):
    """Stale version, wrong status or reused operation (HTTP 409)."""


class WorkSetupInvalid(ValueError):
    """Field values that fail validation (HTTP 422)."""


# Hooks run after a successful transition (B4 reminders registers here). Signature: (client, scope, item).
TRANSITION_HOOKS: list[Callable[[Any, AgentJobScope, WorkItem], None]] = []

_PROPS = ("id", "session_id", "status", "version", "created_by", "created_at", "updated_at", "confirmed_at",
          "title", "outcome", "start_date", "deadline", "timezone", "owner_id", "reminder_json")
_RETURN = "RETURN " + ", ".join(f"w.{p}" for p in _PROPS)
_SCOPE = "w.tenant_id = $tenant AND w.company_id = $company AND w.created_by = $user AND w.project_id = $project"
LABELS = {"title": "Title", "outcome": "Intended outcome", "start_date": "Start date (YYYY-MM-DD)",
          "deadline": "Deadline (YYYY-MM-DD)", "timezone": "Timezone (IANA name, e.g. Asia/Kolkata)",
          "owner_id": "Responsible owner (me, or a person ID)", "reminder": "Reminder preference"}


def _now() -> int:
    return int(time.time() * 1000)


def _params(scope: AgentJobScope) -> dict:
    return {"tenant": scope.tenant_id, "company": scope.company_id, "user": scope.user_id,
            "project": scope.project_id, "session": scope.session_id}


def _graph(client, scope):
    return authorized_graph(client, scope.trusted_context(), scope.project_id)


def missing_fields(item: WorkFields) -> list[str]:
    return [f for f in REQUIRED_WORK_FIELDS if getattr(item, f) is None]


def _item(row) -> WorkItem:
    d = dict(zip(_PROPS, row))
    reminder = d.pop("reminder_json")
    d["reminder"] = ReminderPreference.model_validate_json(reminder) if reminder else None
    for k in ("start_date", "deadline"):
        d[k] = date.fromisoformat(d[k]) if d[k] else None
    item = WorkItem(**d)
    item.missing = missing_fields(item)
    return item


def get_item(client: Any, scope: AgentJobScope, item_id: str) -> WorkItem:
    rows = _graph(client, scope).ro_query(f"MATCH (w:WorkItem {{id: $id}}) WHERE {_SCOPE} {_RETURN}",
                                          params={**_params(scope), "id": item_id}).result_set
    if len(rows) != 1:
        raise AccessDenied("Work item unavailable or access denied")
    return _item(rows[0])


def list_items(client: Any, scope: AgentJobScope, status: str | None = None) -> list[WorkItem]:
    rows = _graph(client, scope).ro_query(
        f"MATCH (w:WorkItem) WHERE {_SCOPE} AND ($status IS NULL OR w.status = $status) {_RETURN} "
        "ORDER BY w.created_at DESC LIMIT 100", params={**_params(scope), "status": status}).result_set
    return [_item(r) for r in rows]


def open_draft(client: Any, scope: AgentJobScope) -> WorkItem | None:
    rows = _graph(client, scope).ro_query(
        f"MATCH (w:WorkItem {{status: 'draft', session_id: $session}}) WHERE {_SCOPE} {_RETURN} "
        "ORDER BY w.created_at DESC LIMIT 1", params=_params(scope)).result_set
    return _item(rows[0]) if rows else None


def people(client: Any, scope: AgentJobScope) -> list[str]:
    rows = _graph(client, scope).ro_query(
        "MATCH (p:Person)-[:MEMBER_OF]->(:Project {id: $project}) RETURN p.id ORDER BY p.id",
        params={"project": scope.project_id}).result_set
    return [r[0] for r in rows]


def validate(client: Any, scope: AgentJobScope, merged: WorkFields) -> list[str]:
    errors = []
    if merged.start_date and merged.deadline and merged.deadline < merged.start_date:
        errors.append(f"Deadline {merged.deadline} is before start date {merged.start_date}")
    if merged.owner_id and merged.owner_id != scope.user_id and merged.owner_id not in people(client, scope):
        errors.append(f"Owner {merged.owner_id} is not a person in this project")
    r = merged.reminder
    if r and r.kind == "custom" and merged.start_date and merged.deadline:
        outside = [t for t in r.custom_times if not (str(merged.start_date) <= t[:10] <= str(merged.deadline))]
        if outside:
            errors.append("Custom reminder times must fall between the start date and the deadline: " + ", ".join(outside))
    return errors


def _merge(item: WorkFields | None, changes: WorkFields) -> WorkFields:
    base = item.model_dump(include=set(REQUIRED_WORK_FIELDS)) if item else {}
    base.update({k: v for k, v in changes.model_dump(include=set(REQUIRED_WORK_FIELDS)).items() if v is not None})
    return WorkFields.model_validate(base)


def _field_params(f: WorkFields) -> dict:
    return {"title": f.title, "outcome": f.outcome, "start": f.start_date.isoformat() if f.start_date else None,
            "deadline": f.deadline.isoformat() if f.deadline else None, "tz": f.timezone, "owner": f.owner_id,
            "reminder": f.reminder.model_dump_json() if f.reminder else None}


_SNAPSHOT = ("CREATE (snap:WorkItemSnapshot {work_item_id: w.id, version: w.version, status: w.status, at: $now, "
             "fields_json: $snapshot}) CREATE (w)-[:HAS_SNAPSHOT]->(snap) ")


@serialized_write
def create_draft(client: Any, scope: AgentJobScope, fields: WorkFields, operation_id: str) -> WorkItem:
    graph = _graph(client, scope)
    prior = graph.ro_query("MATCH (w:WorkItem {operation_id: $op}) RETURN w.id, w.tenant_id, w.company_id, "
                           "w.created_by, w.project_id", params={"op": operation_id}).result_set
    if prior:
        if tuple(prior[0][1:]) != (scope.tenant_id, scope.company_id, scope.user_id, scope.project_id):
            raise WorkSetupConflict("operation_id was already used")
        return get_item(client, scope, prior[0][0])
    merged = _merge(None, fields)
    errors = validate(client, scope, merged)
    if errors:
        raise WorkSetupInvalid("; ".join(errors))
    now, item_id = _now(), "wi-" + operation_id.replace("-", "")[:16]
    rows = graph.query(
        "MATCH (s:Session {id: $session, owner_id: $user})-[:ABOUT]->(p:Project {id: $project}) "
        "OPTIONAL MATCH (x:WorkItem {operation_id: $op}) WITH s, p, x WHERE x IS NULL "
        "CREATE (w:WorkItem {id: $id, operation_id: $op, tenant_id: $tenant, company_id: $company, created_by: $user, "
        "project_id: $project, session_id: $session, status: 'draft', version: 1, created_at: $now, updated_at: $now, "
        "confirmed_at: null, title: $title, outcome: $outcome, start_date: $start, deadline: $deadline, timezone: $tz, "
        "owner_id: $owner, reminder_json: $reminder})-[:FOR_PROJECT]->(p) CREATE (w)-[:SET_UP_IN]->(s) "
        + _SNAPSHOT + "RETURN w.id",
        params={**_params(scope), **_field_params(merged), "id": item_id, "op": operation_id, "now": now,
                "snapshot": merged.model_dump_json()}).result_set
    if len(rows) != 1:
        raise WorkSetupConflict("Work item could not be created")
    return get_item(client, scope, item_id)


@serialized_write
def update_draft(client: Any, scope: AgentJobScope, item_id: str, changes: WorkFields,
                 expected_version: int) -> WorkItem:
    item = get_item(client, scope, item_id)
    if item.status != "draft":
        raise WorkSetupConflict(f"Work item is {item.status}; only drafts can be edited")
    merged = _merge(item, changes)
    errors = validate(client, scope, merged)
    if errors:
        raise WorkSetupInvalid("; ".join(errors))
    rows = _graph(client, scope).query(
        f"MATCH (w:WorkItem {{id: $id}}) WHERE {_SCOPE} AND w.version = $expected AND w.status = 'draft' "
        "SET w.title = $title, w.outcome = $outcome, w.start_date = $start, w.deadline = $deadline, w.timezone = $tz, "
        "w.owner_id = $owner, w.reminder_json = $reminder, w.version = w.version + 1, w.updated_at = $now "
        + _SNAPSHOT + "RETURN w.id",
        params={**_params(scope), **_field_params(merged), "id": item_id, "expected": expected_version,
                "now": _now(), "snapshot": merged.model_dump_json()}).result_set
    if len(rows) != 1:
        raise WorkSetupConflict("Work item changed since you loaded it (stale version); reload and retry")
    return get_item(client, scope, item_id)


_TRANSITIONS = {"confirm": ("draft", "confirmed"), "complete": ("confirmed", "completed"),
                "cancel": (("draft", "confirmed"), "cancelled")}


@serialized_write
def transition(client: Any, scope: AgentJobScope, item_id: str, action: str, expected_version: int) -> WorkItem:
    item = get_item(client, scope, item_id)
    allowed, target = _TRANSITIONS[action]
    allowed = (allowed,) if isinstance(allowed, str) else allowed
    if item.status not in allowed:
        raise WorkSetupConflict(f"Cannot {action} a work item that is {item.status}")
    if action == "confirm":
        if item.missing:
            raise WorkSetupInvalid("Still missing: " + ", ".join(LABELS[f] for f in item.missing))
        errors = validate(client, scope, item)
        if errors:
            raise WorkSetupInvalid("; ".join(errors))
    now = _now()
    rows = _graph(client, scope).query(
        f"MATCH (w:WorkItem {{id: $id}}) WHERE {_SCOPE} AND w.version = $expected AND w.status IN $allowed "
        "SET w.status = $target, w.version = w.version + 1, w.updated_at = $now, "
        "w.confirmed_at = CASE WHEN $target = 'confirmed' THEN $now ELSE w.confirmed_at END "
        + _SNAPSHOT + "RETURN w.id",
        params={**_params(scope), "id": item_id, "expected": expected_version, "allowed": list(allowed),
                "target": target, "now": now, "snapshot": item.model_dump_json(include=set(REQUIRED_WORK_FIELDS))}
    ).result_set
    if len(rows) != 1:
        raise WorkSetupConflict("Work item changed since you loaded it (stale version); reload and retry")
    done = get_item(client, scope, item_id)
    for hook in TRANSITION_HOOKS:
        hook(client, scope, done)
    return done


# ------------------------------------------------------------------- chat parsing

_START = re.compile(r"^\s*(please\s+)?(set\s?up|create|start|add|new)\s+(a\s+|an\s+|some\s+)?(new\s+)?"
                    r"(work(\s+item)?|workstream|initiative|piece of work|project work)\b(.*)$", re.I | re.S)
_KEYS = {
    "title": r"title|name|called",
    "outcome": r"outcome|intended outcome|goal|objective",
    "start_date": r"start(?:\s+date)?|starts|begin(?:s)?",
    "deadline": r"deadline|due(?:\s+date)?|end(?:\s+date)?|finish(?:\s+by)?",
    "timezone": r"time\s?zone|tz",
    "owner_id": r"owner|responsible(?:\s+owner)?|assigned\s+to",
    "reminder": r"reminders?|remind\s+me",
}
_LINE = re.compile(r"(?m)^\s*(?P<key>" + "|".join(f"(?:{v})" for v in _KEYS.values()) + r")\s*[:=-]\s*(?P<value>.+?)\s*$", re.I)


def _key_of(raw: str) -> str:
    for field, pattern in _KEYS.items():
        if re.fullmatch(pattern, raw.strip(), re.I):
            return field
    raise KeyError(raw)


def _reminder(value: str) -> ReminderPreference:
    v = value.strip().lower()
    if v in ("none", "off", "no", "no reminders"):
        return ReminderPreference(kind="none")
    m = re.fullmatch(r"(daily(?:\s+summary)?|milestones?)\s+at\s+(\d{1,2}:\d{2})", v)
    if m:
        hhmm = m.group(2).zfill(5)
        return ReminderPreference(kind="milestones" if m.group(1).startswith("milestone") else "daily_summary",
                                  time_of_day=hhmm)
    m = re.fullmatch(r"custom\s+(.+)", v)
    if m:
        return ReminderPreference(kind="custom", custom_times=[t.strip().upper().replace(" ", "T")
                                                               for t in re.split(r"[,;]", m.group(1)) if t.strip()])
    raise ValueError("Reminders: use 'daily at 09:00', 'milestones at 09:00', 'custom 2026-10-25T10:00' or 'none'")


def parse_fields(text: str, me: str) -> tuple[WorkFields, list[str]]:
    """Explicit 'field: value' lines only. Returns (fields, errors); unparseable values are reported."""
    values, errors = {}, []
    for line in re.split(r"[\n;]+", text):
        m = _LINE.match(line)
        if not m:
            continue
        field, value = _key_of(m.group("key")), m.group("value").strip().rstrip(".")
        try:
            if field in ("start_date", "deadline"):
                values[field] = date.fromisoformat(value)
            elif field == "timezone":
                values[field] = valid_timezone(value)
            elif field == "owner_id":
                values[field] = me if value.lower() in ("me", "myself", "i") else value
            elif field == "reminder":
                values[field] = _reminder(value)
            else:
                values[field] = value[:2000]
        except ValueError as exc:
            msg = str(exc).splitlines()[0]
            if field in ("start_date", "deadline"):
                msg = f"{LABELS[field]}: '{value}' is not a YYYY-MM-DD date (I don't guess relative dates)"
            errors.append(msg)
    return WorkFields.model_validate(values), errors


def _describe(item: WorkItem) -> list[str]:
    r = item.reminder
    reminder = None if r is None else {
        "none": "none", "daily_summary": f"daily summary at {r.time_of_day}",
        "milestones": f"milestones at {r.time_of_day}", "custom": "custom: " + ", ".join(r.custom_times)}[r.kind]
    shown = {"title": item.title, "outcome": item.outcome, "start_date": item.start_date, "deadline": item.deadline,
             "timezone": item.timezone, "owner_id": item.owner_id, "reminder": reminder}
    return [f"- {LABELS[k].split(' (')[0]}: {v}" for k, v in shown.items() if v is not None]


def _guide(client, scope, item: WorkItem, errors: list[str]) -> str:
    out = [f"**Work setup: {item.title or 'untitled'}** ({item.id}, {item.status}, version {item.version})"]
    captured = _describe(item)
    if captured:
        out += ["Captured:", *captured]
    if errors:
        out += ["", "**Not saved, please fix:**", *[f"- {e}" for e in errors]]
    if item.missing:
        team = ", ".join(people(client, scope)) or "none recorded"
        out += ["", "**Still needed:**", *[f"- {LABELS[f]}" for f in item.missing], "",
                "Reply with lines like:", "```", "title: Supplier recovery follow-up",
                "outcome: All exposed orders dispositioned", "start: 2026-10-20", "deadline: 2026-10-31",
                "timezone: Asia/Kolkata", "owner: me", "reminders: daily at 09:00", "```",
                f"People in this project: {team}. Reminder options: daily at HH:MM, milestones at HH:MM, "
                "custom YYYY-MM-DDTHH:MM, or none."]
    elif item.status == "draft":
        out += ["", "Everything is filled in. Reply **confirm** to confirm this work, or change any field."]
    return "\n".join(out)


_CONFIRM = ("confirm", "yes confirm", "confirm it", "yes, confirm", "confirm.")
_CANCEL = ("cancel setup", "cancel", "cancel it", "stop setup")


def chat_turn(client: Any, scope: AgentJobScope, text: str, operation_id: str) -> str | None:
    """Handle a setup message, or return None if this message is not about work setup."""
    from relaymind.workflow.reminders import confirmation_note
    start = _START.match(text)
    lowered = " ".join(text.lower().split())
    if start is None and lowered not in _CONFIRM + _CANCEL and not _LINE.search(text.replace(";", "\n")):
        return None                       # cheap exit: not setup-shaped, no database read
    draft = open_draft(client, scope)
    if draft is not None and lowered in _CONFIRM:
        try:
            item = transition(client, scope, draft.id, "confirm", draft.version)
        except (WorkSetupInvalid, WorkSetupConflict) as exc:
            return _guide(client, scope, draft, [str(exc)])
        return "\n".join([f"**Confirmed: {item.title}** ({item.id})", *_describe(item), "", confirmation_note(client, scope, item)])
    if draft is not None and lowered in _CANCEL:
        item = transition(client, scope, draft.id, "cancel", draft.version)
        return f"Cancelled the draft {item.title or item.id}. Nothing was scheduled."
    fields, errors = parse_fields(text, scope.user_id)
    has_fields = any(v is not None for v in fields.model_dump().values())
    if start is None and not (draft is not None and (has_fields or errors)):
        return None
    if start is not None and fields.title is None:
        rest = re.sub(r"^[\s:,-]*(called|named|titled)?\s*", "", start.group(7).split("\n")[0]).strip(" .:")
        if rest and not _LINE.match(rest):
            fields = fields.model_copy(update={"title": rest[:200]})
    try:
        if start is not None or draft is None:
            item = create_draft(client, scope, fields, operation_id)
        else:
            item = update_draft(client, scope, draft.id, fields, draft.version)
    except WorkSetupInvalid as exc:
        target = draft or create_draft(client, scope, WorkFields(title=fields.title), operation_id)
        return _guide(client, scope, target, errors + str(exc).split("; "))
    return _guide(client, scope, item, errors)
