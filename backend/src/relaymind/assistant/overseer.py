"""Overseer (Phase 1): a deterministic gate that checks an answer's claims against the graph.

No model is involved. Input is the answer text plus its STRUCTURED claims (contracts.assistant.Claims);
output is an OverseerVerdict. Checks, per docs/agent-build-instructions.md section 7 + amendments:

  grounding   every cited ID resolves through the SAME scoped lookup the agent engine uses
              (sources, owned conversation messages, sourced episodes, platform records)
  currency    IDs presented as current decisions really are current (no incoming SUPERSEDES);
              this includes the hold version an order answer is based on, so a superseded hold
              cannot pass just because the exposed set happens to be unchanged
  conflicts   a conflicted topic is named as a conflict and never presented as decided
  tasks       a claimed affected-task list equals find_affected_tasks exactly
  orders      a claimed exposed-order list equals affected_orders exactly, per hold
  unknowns    unknown-traceability orders are named and never called safe/unaffected
  records     every claimed (record, state) pair matches the graph
  state_words each state word in the text (approved/applied/shipped/...) is backed by a verified
              (record, state) pair of a matching kind, or is explicitly negated ("not approved",
              "no changes were applied"). No word whitelist: "applied" needs an applied action record.

The badge this verdict backs reads "Checked against project records" — it never means the prose is
perfect, only that every verifiable claim in it matched the graph at check time.
"""
from __future__ import annotations

import re
from typing import Any

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.assistant import Claims, OverseerFailure, OverseerVerdict, RecordState

# word -> (kind, state) pairs that can back it
WORD_BACKING: dict[str, set[tuple[str, str]]] = {
    "approved": {("decision", "current"), ("decision", "superseded"), ("plan_review", "approved"),
                 ("action", "approved"), ("action", "applied")},
    "rejected": {("plan_review", "rejected"), ("action", "rejected")},
    "applied": {("action", "applied")},
    "shipped": {("order", "shipped")},
    "scheduled": {("reminder", "scheduled")},
    "delivered": {("reminder", "delivered")},
    "confirmed": {("work_item", "confirmed")},
    "cancelled": {("work_item", "cancelled"), ("task", "cancelled")},
    "completed": {("work_item", "completed"), ("run", "completed"), ("task", "done")},
    "superseded": {("decision", "superseded")},
    "executed": set(), "undone": set(), "reverted": set(),     # never backed: only allowed when negated
}
_STATE_RE = re.compile(r"\b(" + "|".join(WORD_BACKING) + r")\b", re.I)
_NEGATORS = re.compile(r"\b(not|no|never|nothing|none|without|neither|nor)\b|n't\b", re.I)


def _negated(text: str, start: int) -> bool:
    """True if a negator appears within the 6 words before this position, in the same sentence."""
    sentence_start = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    window = text[sentence_start:start].split()[-6:]
    return bool(_NEGATORS.search(" ".join(window)))


class GraphFacts:
    """Graph truth the Overseer compares claims against, always inside the caller's scope."""

    def __init__(self, client: Any, scope: AgentJobScope):
        self.client, self.scope = client, scope
        self.ctx, self.project_id = scope.trusted_context(), scope.project_id
        self._engine = None

    def _engine_for_scope(self):
        if self._engine is None:
            from relaymind.agents.engine import CoordinationEngine
            from relaymind.platform.bridge import GraphPlatformBridge

            class _NoModel:
                def reply(self, *a, **k):
                    raise RuntimeError("The Overseer never calls a model")
            self._engine = CoordinationEngine.for_job(self.client, self.scope, _NoModel(),
                                                      GraphPlatformBridge(self.client))
        return self._engine

    def resolves(self, evidence_id: str) -> bool:
        """Same lookup as the agent engine (incl. conversation/episode memory), so they never disagree."""
        from relaymind.agents.loop import AgentBlocked
        from relaymind.graph.access import AccessDenied
        try:
            self._engine_for_scope().evidence(evidence_id)
            return True
        except (AccessDenied, LookupError, AgentBlocked):
            return False

    def current_state(self):
        from relaymind.memory.decisions import get_current_decisions
        return get_current_decisions(self.client, self.ctx, self.project_id)

    def affected_task_ids(self) -> set[str]:
        from relaymind.memory.tasks import find_affected_tasks
        return {a.task.task_id for a in find_affected_tasks(self.client, self.ctx, self.project_id)}

    def exposed(self, hold_id: str) -> tuple[set[str], set[str]]:
        from relaymind.memory import manufacturing as mf
        report = mf.affected_orders(self.client, self.ctx, self.project_id, hold_id)
        return ({a.order.order_id for a in report.affected},
                {o.order_id for o in report.unknown_traceability})

    def record_state(self, kind: str, record_id: str) -> set[str]:
        """Every state this record is in right now (empty = missing / not visible in scope)."""
        from relaymind.graph.access import AccessDenied
        try:
            if kind == "decision":
                from relaymind.memory.decisions import get_decision
                return {"current" if get_decision(self.client, self.ctx, self.project_id, record_id).is_current
                        else "superseded"}
            if kind == "order":
                from relaymind.memory.manufacturing import get_order
                return {get_order(self.client, self.ctx, self.project_id, record_id).status}
            if kind == "task":
                from relaymind.memory.tasks import get_task
                return {get_task(self.client, self.ctx, self.project_id, record_id).status}
            if kind == "work_item":
                from relaymind.workflow.work_setup import get_item
                return {get_item(self.client, self.scope, record_id).status}
            if kind == "reminder":
                from relaymind.workflow.reminders import get_reminder
                return {get_reminder(self.client, self.scope, record_id)["status"]}
            if kind == "plan_review":
                from relaymind.workflow.plan_reviews import review_by_id
                review = review_by_id(self.client, self.scope, record_id)
                return {review.decision} if review else set()
            if kind == "action":
                from relaymind.services.actions import get_action
                action = get_action(self.client, self.ctx, self.project_id, record_id)
                return {action.status} | ({"applied"} if action.status == "approved" and action.applied_version_id
                                          else set())
            if kind == "run":
                return {self._engine_for_scope().store.get("run", record_id)["status"]}
        except (AccessDenied, LookupError):
            return set()
        return set()


def oversee(text: str, claims: Claims, facts) -> OverseerVerdict:
    failures: list[OverseerFailure] = []
    checks = 0

    def fail(check: str, detail: str):
        failures.append(OverseerFailure(check=check, detail=detail[:500]))

    # grounding -------------------------------------------------------------
    for cited in dict.fromkeys(claims.cited_ids):
        checks += 1
        if not facts.resolves(cited):
            fail("grounding", f"cited ID does not resolve in this project scope: {cited}")

    # currency + conflicts (incl. the hold versions order answers are based on) ---------
    presented_current = list(dict.fromkeys(claims.current_decision_ids + list(claims.hold_versions.values())))
    if presented_current or claims.covers_decisions:
        state = facts.current_state()
        current = {d.id for d in state.current}
        conflicted = {i for c in state.conflicts for i in c.decision_ids}
        for decision_id in presented_current:
            checks += 1
            if decision_id in conflicted:
                fail("conflicts", f"{decision_id} is in a conflict but was presented as the current decision")
            elif decision_id not in current:
                fail("currency", f"{decision_id} was presented as current but is superseded or unknown")
        if claims.covers_decisions and state.conflicts:
            checks += 1
            if "conflict" not in text.lower():
                fail("conflicts", "the project has conflicting decisions but the answer does not say so")

    # exact affected-task set -----------------------------------------------
    if claims.affected_task_ids is not None:
        checks += 1
        actual = facts.affected_task_ids()
        if set(claims.affected_task_ids) != actual:
            fail("tasks", f"affected tasks differ from the graph: answer {sorted(set(claims.affected_task_ids))} "
                          f"vs graph {sorted(actual)}")

    # exact exposed-order sets + unknowns ------------------------------------
    if claims.exposed_orders is not None:
        expected_unknown: set[str] = set()
        for hold_id, order_ids in claims.exposed_orders.items():
            checks += 1
            if hold_id not in claims.hold_versions:
                fail("currency", f"{hold_id}: the answer does not state which hold version it is based on")
            exposed, unknown = facts.exposed(hold_id)
            expected_unknown |= unknown
            if set(order_ids) != exposed:
                fail("orders", f"{hold_id}: exposed orders differ from the graph: answer {sorted(set(order_ids))} "
                               f"vs graph {sorted(exposed)}")
        checks += 1
        if set(claims.unknown_order_ids) != expected_unknown:
            fail("unknowns", f"unknown-traceability orders differ: answer {sorted(set(claims.unknown_order_ids))} "
                             f"vs graph {sorted(expected_unknown)}")
    for unknown_id in claims.unknown_order_ids:
        checks += 1
        if unknown_id not in text:
            fail("unknowns", f"{unknown_id} has unknown traceability but is not named in the answer")
            continue
        for line in text.splitlines():
            if unknown_id in line and re.search(r"\b(safe|unaffected|not affected)\b", line, re.I) \
                    and "not proven safe" not in line.lower():
                fail("unknowns", f"{unknown_id} has unknown traceability but the answer calls it safe")

    # (record, state) pairs ----------------------------------------------------
    verified: set[tuple[str, str]] = set()
    for rs in claims.record_states:
        checks += 1
        actual = facts.record_state(rs.kind, rs.id)
        if rs.status in actual:
            verified.add((rs.kind, rs.status))
        else:
            fail("records", f"{rs.kind} {rs.id} is not '{rs.status}' (graph: {sorted(actual) or 'not found'})")
    verified |= {("decision", "current")} if presented_current and not any(
        f.check in ("currency", "conflicts") for f in failures) else set()

    # state words need a verified record of a matching kind -------------------
    if claims.lint_state_words:
        checks += 1
        unbacked = set()
        for m in _STATE_RE.finditer(text):
            word = m.group(1).lower()
            if _negated(text, m.start()):
                continue
            if not (WORD_BACKING[word] & verified):
                unbacked.add(word)
        if unbacked:
            fail("state_words", "state words without a verified backing record: " + ", ".join(sorted(unbacked)))

    return OverseerVerdict(ok=not failures, checks_run=checks, failures=failures)


def gate(client: Any, scope: AgentJobScope, text: str, claims: Claims, fallback: str) -> tuple[str, OverseerVerdict]:
    """Oversee a deterministic reply; on failure return `fallback` (which must claim nothing)."""
    verdict = oversee(text, claims, GraphFacts(client, scope))
    return (text, verdict) if verdict.ok else (fallback, verdict)


# ------------------------------------------------------------- narrated run summaries

def narration_claims(run: dict, plan: dict | None) -> Claims:
    """Verifiable claims of a narrated run summary: its citations. The prose itself was already
    judged semantically by the independent Reviewer, so the state-word lint is off (amendment 1)."""
    cited: list[str] = []
    if plan:
        cited = list(dict.fromkeys(plan.get("decision_ids", [])
                                   + [i for step in plan.get("steps", []) for i in step.get("evidence_ids", [])]))
    return Claims(cited_ids=cited, lint_state_words=False)


def safe_summary(run: dict, plan: dict | None) -> str:
    """Deterministic fallback when the narrated summary fails its checks (e.g. a citation no longer
    resolves). States only what the persisted records say; invents nothing."""
    review = ((run.get("result") or {}).get("review") or {}).get("status")
    lines = [f"The run finished with status: {run['status'].replace('_', ' ')}."]
    if review:
        lines.append(f"Independent review: {review.replace('_', ' ')}.")
    if plan:
        lines.append("A plan was saved, but I could not re-verify every record it cites just now, "
                     "so I am not repeating its contents here. Open the plan card to read it.")
    lines.append("No business changes were applied by this run.")
    return " ".join(lines)


def narrated_summary(client: Any, scope: AgentJobScope, run: dict, plan: dict | None) -> tuple[str, OverseerVerdict]:
    """Narrator (agents.presentation) output gated by the Overseer; falls back to a safe template."""
    from relaymind.agents.presentation import conversation_reply
    text = conversation_reply(run, plan)
    verdict = oversee(text, narration_claims(run, plan), GraphFacts(client, scope))
    if not verdict.ok:
        return safe_summary(run, plan), verdict
    return text, verdict
