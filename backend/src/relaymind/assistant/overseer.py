"""Overseer (Phase 1): a deterministic gate that checks an answer's claims against the graph.

No model is involved. Input is the answer text plus its STRUCTURED claims (contracts.assistant.Claims);
output is an OverseerVerdict. Checks, per docs/agent-build-instructions.md section 7 + amendments:

  grounding   every cited ID resolves through the caller's own scoped evidence lookup
  currency    IDs presented as current decisions really are current (no incoming SUPERSEDES)
  conflicts   a conflicted topic is named as a conflict and never presented as decided
  tasks       a claimed affected-task list equals find_affected_tasks exactly
  orders      a claimed exposed-order list equals affected_orders exactly, per hold
  unknowns    unknown-traceability orders are named and never called safe/unaffected
  state_words state words in the text (approved/applied/shipped/...) must be record-backed
              (producers allow exactly the words their records contain; model prose that the
              independent Reviewer already judged sets lint_state_words=False)

The badge this verdict backs reads "Checked against project records" — it never means the prose is
perfect, only that every verifiable claim in it matched the graph at check time.
"""
from __future__ import annotations

import re
from typing import Any

from relaymind.contracts.agent_jobs import AgentJobScope
from relaymind.contracts.assistant import Claims, OverseerFailure, OverseerVerdict

STATE_WORDS = ("approved", "rejected", "applied", "shipped", "delivered", "scheduled", "executed",
               "confirmed", "cancelled", "completed", "undone", "reverted")
_STATE_RE = re.compile(r"\b(" + "|".join(STATE_WORDS) + r")\b", re.I)


class GraphFacts:
    """Graph truth the Overseer compares claims against, always inside the caller's scope."""

    def __init__(self, client: Any, scope: AgentJobScope):
        self.client, self.scope = client, scope
        self.ctx, self.project_id = scope.trusted_context(), scope.project_id

    def resolves(self, evidence_id: str) -> bool:
        from relaymind.graph.access import AccessDenied
        from relaymind.platform.bridge import GraphPlatformBridge
        try:
            GraphPlatformBridge(self.client).evidence(self.ctx, self.project_id, evidence_id)
            return True
        except (AccessDenied, LookupError):
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

    # currency + conflicts ---------------------------------------------------
    if claims.current_decision_ids or claims.covers_decisions:
        state = facts.current_state()
        current = {d.id for d in state.current}
        conflicted = {i for c in state.conflicts for i in c.decision_ids}
        for decision_id in claims.current_decision_ids:
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

    # record-backed state words ----------------------------------------------
    if claims.lint_state_words:
        checks += 1
        allowed = {w.lower() for w in claims.allowed_state_words}
        loose = sorted({m.group(1).lower() for m in _STATE_RE.finditer(text)} - allowed)
        if loose:
            fail("state_words", "state words without a backing record: " + ", ".join(loose))

    return OverseerVerdict(ok=not failures, checks_run=checks, failures=failures)


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
