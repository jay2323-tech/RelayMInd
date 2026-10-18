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


_CLAUSE_BREAK = re.compile(r"[.;:,!?\n]|\b(?:and|but|while|whereas|so)\b", re.I)
_RECORD_ID = re.compile(r"(?<![A-Za-z0-9-])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+(?![A-Za-z0-9-])")


def _negated(text: str, start: int) -> bool:
    """True only if a negator governs THIS status word: same clause, at most 4 words before it.

    "No problems remain; action a-1 was applied" -> the "No" is in another clause -> not negated.
    "No business changes were applied" / "You have not approved or rejected" -> negated.
    """
    breaks = [m.end() for m in _CLAUSE_BREAK.finditer(text, 0, start)]
    clause = text[(breaks[-1] if breaks else 0):start]
    return bool(_NEGATORS.search(" ".join(clause.split()[-4:])))


_SPAN_BREAK = re.compile(r"[;:!?\n]|\.(?=\s|$)")


def _claim_span(text: str, start: int) -> str:
    """The clause a status word belongs to, INCLUDING lists joined by commas/and ("a-1 and a-2 were
    applied"), so every record asserted alongside the word is checked. Bounded by . ; : ! ? newline."""
    lefts = [m.end() for m in _SPAN_BREAK.finditer(text, 0, start)]
    right = _SPAN_BREAK.search(text, start)
    return text[(lefts[-1] if lefts else 0):(right.start() if right else len(text))]


def _id_tokens(span: str) -> set[str]:
    """Exact record-ID tokens (letters, hyphen-joined, containing a digit). Compared whole, never as
    substrings, so a-1 can never vouch for a-10."""
    return {t for t in _RECORD_ID.findall(span)
            if any(ch.isdigit() for ch in t) and any(ch.isalpha() for ch in t)}   # not dates like 2026-10-18


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

    def message_text(self, message_id: str) -> str | None:
        """Stored content of one of the CALLER's own messages in this project (owner-checked), or None."""
        from relaymind.graph.access import authorized_graph
        graph = authorized_graph(self.client, self.ctx, self.project_id)
        rows = graph.ro_query(
            "MATCH (s:Session {owner_id: $owner})-[:ABOUT]->(:Project {id: $p}) "
            "MATCH (s)-[:HAS_MESSAGE]->(m:Message {id: $id}) RETURN m.content",
            params={"owner": self.ctx.user_id, "p": self.project_id, "id": message_id}).result_set
        return rows[0][0] if len(rows) == 1 else None

    def exists(self, token: str) -> bool:
        """Any record in this project scope with this exact id (evidence records or people)."""
        if self.resolves(token):
            return True
        from relaymind.graph.access import authorized_graph
        graph = authorized_graph(self.client, self.ctx, self.project_id)
        return bool(graph.ro_query("MATCH (p:Person {id: $id})-[:MEMBER_OF]->(:Project {id: $p}) RETURN p.id",
                                   params={"id": token, "p": self.project_id}).result_set)

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
                review = review_by_id(self.client, self.scope, record_id, any_session=True)   # caller's own
                return {review.decision} if review else set()
            if kind == "action":
                from relaymind.services.actions import get_action
                action = get_action(self.client, self.ctx, self.project_id, record_id)
                # A human-approved action is stored as "applied" once its new version exists.
                return {action.status} | ({"approved"} if action.status == "applied" and action.applied_version_id
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

    # quotes from earlier chats must be literally present in the message they cite ------
    for ref in claims.source_quotes:
        checks += 1
        source = facts.message_text(ref.message_id)
        excerpt = " ".join(ref.snippet.strip("…").split())
        if source is None:
            fail("quotes", f"quoted message is not one of your messages in this project: {ref.message_id}")
        elif not excerpt or excerpt not in " ".join(source.split()):
            fail("quotes", f"the quote attributed to {ref.message_id} is not what that message says")

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
    # verified: (kind, state) -> the names (id + aliases) of the records that back it
    verified: dict[tuple[str, str], set[str]] = {}
    for rs in claims.record_states:
        checks += 1
        actual = facts.record_state(rs.kind, rs.id)
        if rs.status in actual:
            verified.setdefault((rs.kind, rs.status), set()).update([rs.id, *rs.aliases])
        else:
            fail("records", f"{rs.kind} {rs.id} is not '{rs.status}' (graph: {sorted(actual) or 'not found'})")
    if presented_current and not any(f.check in ("currency", "conflicts") for f in failures):
        verified.setdefault(("decision", "current"), set()).update(presented_current)
    alias_of: dict[str, list[tuple[str, str]]] = {}      # a name can belong to several records
    for rs in claims.record_states:                       # (e.g. two decisions on one plan revision)
        for name in [rs.id, *rs.aliases]:
            if (rs.kind, rs.id) not in alias_of.setdefault(name, []):
                alias_of[name].append((rs.kind, rs.id))
    known_names = set(alias_of) | set(claims.cited_ids) | set(presented_current)

    # state words need a verified record of a matching kind -------------------
    if claims.lint_state_words:
        # Verbatim record text is masked ONLY at the exact line + column where the producer placed it.
        # The same words elsewhere (e.g. a sentence the assistant added) are still checked.
        text = mask_quotes(text, claims.quoted_spans)
        checks += 1
        unbacked = set()
        for m in _STATE_RE.finditer(text):
            word = m.group(1).lower()
            if _negated(text, m.start()):
                continue
            pairs = WORD_BACKING[word]
            kinds = {k for k, _ in pairs}
            relevant, problems = 0, []
            # Every record named in this clause is checked against the graph on its own.
            for token in sorted(_id_tokens(_claim_span(text, m.start()))):
                lookups = alias_of[token] if token in alias_of else [(k, token) for k in sorted(kinds)]
                found = [(k, st) for k, rid in lookups if k in kinds for st in facts.record_state(k, rid)]
                if found:
                    relevant += 1
                    if not any(pair in pairs for pair in found):
                        problems.append(f"{token} is {'/'.join(sorted({st for _, st in found}))}")
                elif token not in known_names and not facts.exists(token):
                    problems.append(f"{token} does not exist")
                # else: a different kind of record (a person, batch, source...) - not what the word describes
            if problems:
                unbacked.add(f"{word} ({'; '.join(problems)})")
            elif relevant == 0 and not any(verified.get(pair) for pair in pairs):
                unbacked.add(word)
        if unbacked:
            fail("state_words", "state words without a verified backing record: " + ", ".join(sorted(unbacked)))

    return OverseerVerdict(ok=not failures, checks_run=checks, failures=failures)


def mask_quotes(text: str, spans) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        for span in sorted((s for s in spans if s.line == line), key=lambda s: s.start, reverse=True):
            if span.start + span.length <= len(line):
                line = line[:span.start] + "\u00abquoted\u00bb" + line[span.start + span.length:]
        lines[i] = line
    return "\n".join(lines)


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
