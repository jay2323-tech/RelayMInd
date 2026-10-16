"""Concrete PlatformBridge for the agent engine (docs/agent-platform-integration.md).

Adapts platform storage to the engine contracts without renaming storage fields:
- current_decisions: every current decision, INCLUDING all sides of a conflict, so the
  engine's duplicate-topic check blocks planning instead of silently skipping a topic.
- DecisionReference has one source_id; we pass the first (sorted) source. Every
  source stays listed in the decision's evidence text and is fetchable by its own ID.
- evidence: Source, Decision and Task records in the authorized project. Decision
  evidence includes relationship-derived state (current / superseded / in conflict),
  what it supersedes, and which tasks implement it or the decisions it replaced, so
  the Planner can explain what changed and discover affected task IDs.
- dependencies: graph dependencies of one task, as a flat list of relation records.

Every method authorizes via authorized_graph(context, project_id) inside the memory
functions. Nothing here accepts graph names, tenant IDs or Cypher from the model.
"""
from __future__ import annotations

from typing import Any

from relaymind.contracts.coordination import DecisionReference, EvidenceRecord
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import AccessDenied
from relaymind.memory import decisions as dm
from relaymind.memory import tasks as tm

_MAX = 16000


def _task_line(t) -> str:
    owner = f", owner {t.assigned_to}" if t.assigned_to else ""
    return f"{t.task_id} \"{t.title}\" ({t.status}, v{t.version}{owner})"


class GraphPlatformBridge:
    def __init__(self, client: Any):
        self.client = client

    # ---------------------------------------------------------- decisions
    def current_decisions(self, context: TrustedContext, project_id: str) -> list[DecisionReference]:
        state = dm.get_current_decisions(self.client, context, project_id)
        return [DecisionReference(id=d.id, version=d.version, topic=d.topic, text=d.text,
                                  source_id=d.source_ids[0])
                for d in state.current + state.conflicting]

    # ----------------------------------------------------------- evidence
    def evidence(self, context: TrustedContext, project_id: str, evidence_id: str) -> EvidenceRecord:
        source = dm.get_source(self.client, context, project_id, evidence_id, _missing_ok=True)
        if source is not None:
            return EvidenceRecord(id=source.id, text=f"[Source: {source.kind}] {source.title}\n{source.text}"[:_MAX],
                                  source_id=source.id)
        try:
            decision = dm.get_decision(self.client, context, project_id, evidence_id)
        except AccessDenied:
            decision = None
        if decision is not None:
            return EvidenceRecord(id=decision.id, text=self._decision_text(context, project_id, decision)[:_MAX],
                                  source_id=decision.source_ids[0])
        try:
            task = tm.get_task(self.client, context, project_id, evidence_id)
        except AccessDenied:
            raise AccessDenied("Evidence unavailable or access denied") from None
        lines = [f"[Task] {_task_line(task)}"]
        if task.implements:
            lines.append("Implements decisions: " + ", ".join(task.implements))
        if task.blocked_by:
            lines.append("Blocked by: " + ", ".join(task.blocked_by))
        if task.blocks:
            lines.append("Blocks: " + ", ".join(task.blocks))
        return EvidenceRecord(id=task.task_id, text="\n".join(lines)[:_MAX], source_id=task.version_id)

    def _decision_text(self, context, project_id, d) -> str:
        state = dm.get_current_decisions(self.client, context, project_id)
        rivals = next((c.decision_ids for c in state.conflicts if d.id in c.decision_ids), None)
        if rivals:
            status = "IN CONFLICT with " + ", ".join(i for i in rivals if i != d.id) + " (requires human resolution)"
        elif d.is_current:
            status = "CURRENT"
        else:
            status = "SUPERSEDED by " + ", ".join(d.superseded_by) + " (historical, not current)"
        lines = [f"[Decision {d.id}] topic {d.topic}, version {d.version}, {status}",
                 f"Text: {d.text}", f"Approved by {d.approved_by}",
                 "Sources (fetch each by ID): " + ", ".join(d.source_ids)]
        tasks = tm.list_tasks(self.client, context, project_id)
        own = [t for t in tasks if d.id in t.implements]
        if own:
            lines.append("Tasks implementing this decision: " + "; ".join(_task_line(t) for t in own))
        for old_id in d.supersedes:
            old = dm.get_decision(self.client, context, project_id, old_id)
            lines.append(f"Supersedes {old.id} (version {old.version}): {old.text}")
            affected = [t for t in tasks if old.id in t.implements]
            if affected:
                lines.append(f"Tasks still implementing superseded {old.id}: "
                             + "; ".join(_task_line(t) for t in affected))
        return "\n".join(lines)

    # ------------------------------------------------------- dependencies
    def dependencies(self, context: TrustedContext, project_id: str, task_id: str) -> list[dict]:
        deps = tm.trace_dependencies(self.client, context, project_id, task_id)
        records = [{"relation": "task", **deps.task.model_dump()}]
        records += [{"relation": "blocked_by", **t.model_dump()} for t in deps.blocked_by]
        records += [{"relation": "blocks", **t.model_dump()} for t in deps.blocks]
        records += [{"relation": "implements", **link.model_dump()} for link in deps.implements]
        return records


def factory(client: Any, context: TrustedContext, project_id: str) -> GraphPlatformBridge:
    """Entry point for `python -m relaymind.agents.cli --platform relaymind.platform.bridge:factory`."""
    return GraphPlatformBridge(client)
