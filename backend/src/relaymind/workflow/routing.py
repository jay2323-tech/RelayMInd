"""B2: route a chat message to factual Q&A, planning or (later) guided work setup.

Routing is deterministic and conservative:
- Only clear, whole-question patterns are answered as FACTS (no model call, graph reads only).
- Anything asking for judgement or next steps ("what should", "plan", "recommend", ...) goes to
  the Planner -> Reviewer workflow, exactly as before.
- When unsure, plan. A misrouted planning request costs one model run; a misrouted factual answer
  would skip review, so ambiguity always falls through to planning.

Factual answers cite record IDs, state unknowns explicitly (unknown traceability, conflicts, empty
results) and never come from seeded decisions when the user asks what THEY approved: that reads
the human audit (PlanReview + decided ProposedAction) only. Read failures are reported, not hidden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.assistant import Claims, RecordState

Intent = Literal["approvals", "current_decisions", "changes", "exposed_orders", "affected_tasks", "run_status"]

_PLANNING = re.compile(
    r"\b(what should|should (we|i)|next steps?|^plan|(make|create|build|write) (a |the |an )?plan|plan (the|a|an|for|out|our)|"
    r"planning|propose|proposal|recommend|suggest|how (do|should|can) we|draft|prepare|may we|can we|could we|help me|"
    r"decide|figure out|fix|resolve|continue|replan\w*|must|need(s)? to|ought|investigate|evaluate|why)\b")

_INTENTS: list[tuple[Intent, re.Pattern]] = [
    ("approvals", re.compile(
        r"\b(what|which)\b.*\b(did i|have i|i've|i have)\b.*\b(approv\w*|reject\w*|review\w*|sign(ed)? off)\b"
        r"|\bmy (approvals|reviews|decisions)\b|\bapproval history\b")),
    ("exposed_orders", re.compile(
        r"\borders?\b.*\b(affected|exposed|impacted|at risk|held|on hold|blocked)\b"
        r"|\b(affected|exposed|impacted|held)\b.*\borders?\b")),
    ("affected_tasks", re.compile(
        r"\btasks?\b.*\b(affected|stale|impacted|outdated|out of date|superseded)\b"
        r"|\b(affected|stale|impacted|outdated)\b.*\btasks?\b")),
    ("run_status", re.compile(
        r"\bstatus of (my |the )?(plan|run|request)s?\b|\b(is|are) (my |the )?(plan|run)s? (done|ready|finished|complete)\b")),
    ("changes", re.compile(r"\bwhat(\s+has|'s|\s+have)?\s+changed\b|\bwhat was (changed|superseded)\b|\bdecision history\b")),
    ("current_decisions", re.compile(
        r"\b(what|which) (is|are) (the )?current\b|\bcurrent (approved )?(decisions?|route|scope|hold)\b"
        r"|\bwhat (is|are) (the )?approved (decisions?|route|scope)\b")),
]


@dataclass(frozen=True)
class Route:
    kind: Literal["factual", "planning"]
    intent: Intent | None = None


def classify(text: str) -> Route:
    t = " ".join(re.sub(r"[^a-z0-9'\s-]", " ", text.lower()).split())
    if not t or len(t) > 300 or _PLANNING.search(t):
        return Route("planning")
    for intent, pattern in _INTENTS:
        if pattern.search(t):
            return Route("factual", intent)
    return Route("planning")


# --------------------------------------------------------------------------- answers

def _decisions(client, ctx, project_id) -> tuple[str, Claims]:
    from relaymind.memory.decisions import get_current_decisions
    state = get_current_decisions(client, ctx, project_id)
    claims = Claims(covers_decisions=True,
                    quoted_spans=[d.text for d in state.current],
                    current_decision_ids=[d.id for d in state.current],
                    cited_ids=[i for d in state.current for i in [d.id, *d.source_ids]]
                    + [i for c in state.conflicts for i in c.decision_ids])
    if not state.current and not state.conflicts:
        return "No current approved decision is recorded for this project.", claims
    lines = ["**Current approved decisions**"]
    lines += [f"- {d.topic}: {d.text} ({d.id}, version {d.version}; sources {', '.join(d.source_ids)})"
              for d in sorted(state.current, key=lambda d: d.topic)]
    for c in state.conflicts:
        lines.append(f"- **In conflict, needs human resolution:** {c.topic} has more than one current decision "
                     f"({', '.join(c.decision_ids)}). I won't pick one.")
    return "\n".join(lines), claims


def _changes(client, ctx, project_id) -> tuple[str, Claims]:
    from relaymind.memory.decisions import get_current_decisions, get_decision
    state = get_current_decisions(client, ctx, project_id)
    lines, cited, current, quotes = [], [], [], []
    for d in sorted(state.current + state.conflicting, key=lambda d: d.topic):
        for old_id in d.supersedes:
            old = get_decision(client, ctx, project_id, old_id)
            lines.append(f"- {d.topic}: **was** {old.text} ({old.id}) → **now** {d.text} ({d.id}; sources "
                         f"{', '.join(d.source_ids)})")
            cited += [old.id, d.id, *d.source_ids]
            quotes += [old.text, d.text]
            if d.is_current:
                current.append(d.id)
    claims = Claims(covers_decisions=True, cited_ids=cited, current_decision_ids=current, quoted_spans=quotes)
    if not lines:
        return "Nothing in this project's decision history has been replaced yet, so nothing has changed.", claims
    task_rows, task_claims = _affected_task_lines(client, ctx, project_id)
    claims = claims.model_copy(update={
        "affected_task_ids": task_claims.affected_task_ids,
        "cited_ids": claims.cited_ids + task_claims.cited_ids,
        "quoted_spans": claims.quoted_spans + task_claims.quoted_spans,
        "record_states": claims.record_states + task_claims.record_states})
    out = ["**What changed (approved decisions)**", *lines]
    if task_rows:
        out += ["", "**Work still based on the old decisions**", *task_rows]
    return "\n".join(out), claims


def _affected_task_lines(client, ctx, project_id) -> tuple[list[str], Claims]:
    from relaymind.memory.tasks import find_affected_tasks
    rows, affected = [], sorted(find_affected_tasks(client, ctx, project_id), key=lambda a: a.task.task_id)
    for a in affected:
        owner = f", owner {a.task.assigned_to}" if a.task.assigned_to else ", no owner recorded"
        rows.append(f"- {a.task.task_id} \"{a.task.title}\" ({a.task.status}{owner}) still implements superseded "
                    f"{a.superseded_decision_id}; replaced by {', '.join(a.replaced_by) or 'nothing recorded'}")
    claims = Claims(affected_task_ids=sorted({a.task.task_id for a in affected}),
                    cited_ids=[i for a in affected for i in [a.task.task_id, a.superseded_decision_id, *a.replaced_by]],
                    quoted_spans=[a.task.title for a in affected],
                    record_states=[RecordState(kind="decision", id=i, status="superseded")
                                   for i in sorted({a.superseded_decision_id for a in affected})]
                    + [RecordState(kind="task", id=a.task.task_id, status=a.task.status) for a in affected])
    return rows, claims


def _affected_tasks(client, ctx, project_id) -> tuple[str, Claims]:
    rows, claims = _affected_task_lines(client, ctx, project_id)
    if not rows:
        return "No task in this project still implements a superseded decision.", claims
    return "\n".join(["**Tasks affected by changed decisions**", *rows]), claims


def _orders(client, ctx, project_id) -> tuple[str, Claims]:
    from relaymind.memory import manufacturing as mf
    from relaymind.memory.decisions import get_current_decisions
    state = get_current_decisions(client, ctx, project_id)
    holds = sorted({d.topic[len(mf.HOLD_TOPIC_PREFIX):].upper() for d in state.current + state.conflicting
                    if d.topic.startswith(mf.HOLD_TOPIC_PREFIX)})
    if not holds:
        return ("No current hold is recorded for this project, so no order is exposed by a hold. "
                "(This is not a statement about other risks.)"), Claims(exposed_orders={})
    out, exposed_map, unknown_ids, cited, states, versions = [], {}, [], [], [], {}
    for hold_id in holds:
        r = mf.affected_orders(client, ctx, project_id, hold_id)
        exposed_map[hold_id] = [a.order.order_id for a in r.affected]
        versions[hold_id] = r.hold.decision_id          # checked for currency even if the set is unchanged
        unknown_ids += [o.order_id for o in r.unknown_traceability]
        cited += [hold_id, r.hold.decision_id] + exposed_map[hold_id] + [o.order_id for o in r.unknown_traceability] \
            + list(r.hold.held_batches) + [x for a in r.affected for x in (a.assembly_id, a.batch_id)]
        states += [RecordState(kind="order", id=a.order.order_id, status=a.order.status) for a in r.affected]
        out.append(f"**Orders exposed by {hold_id}** (current version {r.hold.decision_id}, held batches "
                   f"{', '.join(r.hold.held_batches) or 'none'})")
        out += [f"- {a.order.order_id}: {a.order.status}, "
                f"{'open order to hold' if a.exposure == 'open_order_hold' else 'already shipped - needs exposure review'}"
                f" (via assembly {a.assembly_id} / batch {a.batch_id})" for a in r.affected] or ["- none"]
        if r.unknown_traceability:
            out.append("**Unknown, not proven safe** (no installation trace): "
                       + ", ".join(o.order_id for o in r.unknown_traceability))
    claims = Claims(exposed_orders=exposed_map, hold_versions=versions, unknown_order_ids=sorted(set(unknown_ids)),
                    cited_ids=cited, record_states=states)
    return "\n".join(out), claims


def _approvals(client, scope: AgentJobScope) -> tuple[str, Claims]:
    from relaymind.services.actions import list_actions
    from relaymind.workflow.plan_reviews import list_reviews
    ctx = scope.trusted_context()
    reviews = list_reviews(client, ctx, tenant_id=scope.tenant_id, company_id=scope.company_id,
                           user_id=scope.user_id, project_id=scope.project_id, limit=20)
    actions = sorted((a for a in list_actions(client, ctx, scope.project_id)
                      if a.status != "proposed" and a.decided_by == scope.user_id),
                     key=lambda a: a.decided_at or 0, reverse=True)[:20]
    claims = Claims(quoted_spans=[r.plan_summary for r in reviews if r.plan_summary]
                    + [r.feedback for r in reviews if r.feedback],
                    record_states=[RecordState(kind="plan_review", id=r.id, status=r.decision,
                                               aliases=[r.handoff_id, r.run_id]) for r in reviews]
                    + [RecordState(kind="action", id=a.id, status=a.status) for a in actions])
    if not reviews and not actions:
        return ("You have not approved or rejected any plan or action in this project yet. "
                "Decisions recorded when the project was set up are not your approvals."), claims
    words = {"approved": "Approved", "rejected": "Rejected", "needs_changes": "Requested changes to"}
    out = []
    if reviews:
        out.append("**Plans you reviewed**")
        out += [f"- {words[r.decision]} plan {r.handoff_id}: {r.plan_summary or 'no summary'}"
                + (f" (feedback: {r.feedback})" if r.feedback else "") for r in reviews]
    if actions:
        out.append("**Actions you decided**")
        out += [f"- {a.status.capitalize()}: {a.kind.replace('_', ' ')} on {a.task_id}"
                + (f" → {a.new_status}" if a.new_status else "") + f" ({a.id})" for a in actions]
    return "\n".join(out), claims


def _run_status(client, scope: AgentJobScope) -> tuple[str, Claims]:
    import json
    from relaymind.graph.access import authorized_graph
    from relaymind.workflow.plan_reviews import review_for_handoff
    graph = authorized_graph(client, scope.trusted_context(), scope.project_id)
    rows = graph.ro_query(
        "MATCH (a:AgentArtifact {kind: 'run', session_id: $s, owner_id: $o, project_id: $p}) RETURN a.payload_json",
        params={"s": scope.session_id, "o": scope.user_id, "p": scope.project_id}).result_set
    runs = [json.loads(r[0]) for r in rows]
    runs = [r for r in runs if r.get("company_id") == scope.company_id and r.get("request_kind", "planning") == "planning"]
    if not runs:
        return "There are no plans in this conversation yet.", Claims()
    out, states = ["**Plans in this conversation**"], []
    for r in runs[-5:]:
        review = review_for_handoff(client, scope, r["handoff_ids"][-1]) if r.get("handoff_ids") else None
        human = f"; you {review.decision.replace('_', ' ')} it" if review else ""
        out.append(f"- {r['request'][:80]}: {r['status'].replace('_', ' ')}{human} ({r['id']})")
        states.append(RecordState(kind="run", id=r["id"], status=r["status"]))
        if review:
            states.append(RecordState(kind="plan_review", id=review.id, status=review.decision,
                                      aliases=[review.handoff_id, review.run_id]))
    return "\n".join(out), Claims(record_states=states, quoted_spans=[r["request"][:80] for r in runs[-5:]])


_ANSWERS: dict[Intent, Callable[[Any, AgentJobScope], tuple[str, Claims]]] = {
    "current_decisions": lambda c, s: _decisions(c, s.trusted_context(), s.project_id),
    "changes": lambda c, s: _changes(c, s.trusted_context(), s.project_id),
    "affected_tasks": lambda c, s: _affected_tasks(c, s.trusted_context(), s.project_id),
    "exposed_orders": lambda c, s: _orders(c, s.trusted_context(), s.project_id),
    "approvals": _approvals,
    "run_status": _run_status,
}


def factual_answer(client: Any, scope: AgentJobScope, intent: Intent) -> tuple[str, str | None, Claims | None]:
    """(answer, error_code, claims). Errors are explicit and never replaced by a guess; the claims
    are what the Overseer verifies against the graph before the answer is shown."""
    try:
        text, claims = _ANSWERS[intent](client, scope)
    except Exception as exc:   # access-safe: no record content, only the error class
        return ("I couldn't read the records needed to answer this, so I haven't answered it. "
                f"(Error: {type(exc).__name__})"), type(exc).__name__, None
    return text + ("\n\n_Answered directly from the project's records; no plan was made and nothing was changed._"
                   ), None, claims
