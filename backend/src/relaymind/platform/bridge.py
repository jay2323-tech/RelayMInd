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
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory import decisions as dm
from relaymind.memory import manufacturing as mf
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
        record = self._manufacturing_evidence(context, project_id, evidence_id)
        if record is not None:
            return record
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
        if d.topic.startswith(mf.HOLD_TOPIC_PREFIX):
            lines += self._hold_lines(context, project_id, d)
        return "\n".join(lines)

    # ---------------------------------------------------- manufacturing
    def _hold_lines(self, context, project_id, d) -> list[str]:
        graph = authorized_graph(self.client, context, project_id)
        batches = sorted(r[0] for r in graph.ro_query(
            "MATCH (d:Decision {id: $d, project_id: $p})-[:HOLDS]->(b:Batch) RETURN b.id",
            params={"d": d.id, "p": project_id}).result_set)
        lines = [f"Batches held by this hold version: {', '.join(batches) or 'none recorded'}"]
        if not d.is_current:
            return lines + ["This hold version is superseded; recompute impact from the current hold version."]
        try:
            report = mf.affected_orders(self.client, context, project_id, d.topic[len(mf.HOLD_TOPIC_PREFIX):].upper())
        except mf.ManufacturingError as exc:
            return lines + [f"Impact unavailable: {exc}"]
        lines.append("Orders exposed under the CURRENT hold (graph query " + report.query + "): " + "; ".join(
            f"{a.order.order_id} ({a.order.status}, {a.exposure}, via {a.assembly_id}/{a.batch_id})"
            for a in report.affected))
        if report.unknown_traceability:
            lines.append("Unknown traceability (not proven safe): "
                         + ", ".join(o.order_id for o in report.unknown_traceability))
        return lines

    def _manufacturing_evidence(self, context, project_id, evidence_id):
        """Order, Batch and Assembly records of the authorized project, with sourced trace edges."""
        graph = authorized_graph(self.client, context, project_id)
        try:
            order = mf.get_order(self.client, context, project_id, evidence_id)
        except AccessDenied:
            order = None
        if order is not None:
            via = graph.ro_query(
                "MATCH (o:Order {id: $id, project_id: $p})<-[al:ALLOCATED_TO]-(a:Assembly)-[:USES_BATCH]->(b:Batch) "
                "RETURN a.id, b.id, al.source_id", params={"id": evidence_id, "p": project_id}).result_set
            lines = [f"[Order {order.order_id}] version {order.version}, status {order.status}, "
                     f"model {order.model or 'unknown'}, units {order.units if order.units is not None else 'unknown'}, "
                     f"traceability {order.traceability}"]
            lines += [f"Installed: assembly {a} uses batch {b} (source {src})" for a, b, src in via]
            has_traces = graph.ro_query("MATCH (a:Assembly {project_id: $p}) RETURN a.id LIMIT 1",
                                        params={"p": project_id}).result_set
            if not via and has_traces:   # only meaningful where installation traces exist (manufacturing)
                lines.append("No installation trace recorded: exposure is UNKNOWN, not safe.")
            lines.append(f"Source: {order.source_id}")
            return EvidenceRecord(id=order.order_id, text="\n".join(lines)[:_MAX], source_id=order.source_id)
        if graph.ro_query("MATCH (h:Hold {id: $id, project_id: $p}) RETURN h.id",
                          params={"id": evidence_id, "p": project_id}).result_set:
            try:
                report = mf.affected_orders(self.client, context, project_id, evidence_id)
            except (AccessDenied, mf.ManufacturingError) as exc:
                text = f"[Hold {evidence_id}] current scope unavailable: {exc}"
                return EvidenceRecord(id=evidence_id, text=text[:_MAX], source_id=evidence_id)
            h = report.hold
            lines = [f"[Hold {evidence_id}] current version {h.decision_id} (v{h.decision_version})"
                     + (f", supersedes {', '.join(h.supersedes)}" if h.supersedes else ""),
                     f"Text: {h.decision_text}", f"Held batches: {', '.join(h.held_batches)}",
                     "Exposed orders: " + "; ".join(f"{a.order.order_id} ({a.order.status}, {a.exposure})" for a in report.affected)]
            if report.unknown_traceability:
                lines.append("Unknown traceability (not proven safe): "
                             + ", ".join(o.order_id for o in report.unknown_traceability))
            return EvidenceRecord(id=evidence_id, text="\n".join(lines)[:_MAX], source_id=h.source_ids[0])
        for label in ("Batch", "Assembly"):
            if not graph.ro_query(f"MATCH (x:{label} {{id: $id, project_id: $p}}) RETURN x.id",
                                  params={"id": evidence_id, "p": project_id}).result_set:
                continue
            edges = graph.ro_query(
                f"MATCH (x:{label} {{id: $id, project_id: $p}})-[r:USES_BATCH|ALLOCATED_TO]->(y) "
                "RETURN 'out' AS dir, type(r) AS rel, y.id AS other, r.source_id AS src "
                f"UNION MATCH (x:{label} {{id: $id, project_id: $p}})<-[r:USES_BATCH|ALLOCATED_TO|HOLDS]-(y) "
                "RETURN 'in' AS dir, type(r) AS rel, y.id AS other, r.source_id AS src",
                params={"id": evidence_id, "p": project_id}).result_set
            text = f"[{label} {evidence_id}]\n" + "\n".join(
                (f"{evidence_id} -{t}-> {y}" if d == "out" else f"{y} -{t}-> {evidence_id}") + (f" (source {src})" if src else "")
                for d, t, y, src in edges)
            return EvidenceRecord(id=evidence_id, text=text[:_MAX], source_id=next((e[3] for e in edges if e[3]), evidence_id))
        return None

    def required_tasks(self, context: TrustedContext, project_id: str) -> list[dict]:
        """Active affected tasks that every project-level plan must address.

        Derived from graph relationships, not natural-language evidence parsing.
        Already paused/cancelled/done tasks need no new triage requirement.
        """
        grouped={}
        for affected in tm.find_affected_tasks(self.client,context,project_id):
            task=affected.task
            if task.status not in {'todo','in_progress'}:
                continue
            item=grouped.setdefault(task.task_id,dict(task_id=task.task_id,title=task.title,
                version_id=task.version_id,version=task.version,
                superseded_decision_ids=[],replacement_decision_ids=[]))
            item['superseded_decision_ids']=sorted(set(item['superseded_decision_ids']+[affected.superseded_decision_id]))
            item['replacement_decision_ids']=sorted(set(item['replacement_decision_ids']+affected.replaced_by))
        return [grouped[key] for key in sorted(grouped)]

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
