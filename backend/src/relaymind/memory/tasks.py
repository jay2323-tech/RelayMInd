"""Task memory: stable Task identity plus immutable TaskVersion chain.

Design: docs/memory-design.md section 2.2.
- (:Task)-[:HAS_VERSION]->(:TaskVersion); new versions point (:TaskVersion)-[:PREVIOUS]->(old).
- Current version = no incoming PREVIOUS. Zero or several current versions is an
  integrity error and is reported, never repaired by picking the highest number.
- BLOCKED_BY and IMPLEMENTS are seeded structure on the Task identity.
New versions are created only by approved actions (relaymind.services.actions).
"""
from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from relaymind.contracts.models import TrustedContext
from relaymind.contracts.tasks import AffectedTask, DecisionLink, TaskDependencies, TaskView
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory.locking import serialized_write


class TaskMemoryError(Exception):
    """Base exception for task memory operations."""


class TaskIntegrityError(TaskMemoryError):
    """A task does not have exactly one current version."""


class ConflictingTaskError(TaskMemoryError):
    """A task or person ID is already used with different content, or a reference is missing."""


def _now() -> int:
    return int(time.time() * 1000)


@serialized_write
def record_person(client: Any, context: TrustedContext, project_id: str, person_id: str, name: str) -> None:
    """Seed/setup only. Idempotent for identical name."""
    graph = authorized_graph(client, context, project_id)
    rows = graph.query(
        "MATCH (p:Project {id: $project}) OPTIONAL MATCH (x:Person {id: $id}) "
        "WITH p, x WHERE x IS NULL "
        "CREATE (:Person {id: $id, name: $name, project_id: $project})-[:MEMBER_OF]->(p) RETURN 1",
        params={"project": project_id, "id": person_id, "name": name}).result_set
    if rows:
        return
    existing = graph.ro_query("MATCH (x:Person {id: $id}) RETURN x.name", params={"id": person_id}).result_set
    if not existing:
        raise AccessDenied("Project unavailable")
    if existing[0][0] != name:
        raise ConflictingTaskError("Person ID already used with a different name")


@serialized_write
def record_task(
    client: Any, context: TrustedContext, project_id: str, task_id: str, title: str,
    status: str = "todo", assigned_to: Optional[str] = None,
    implements: Iterable[str] = (), blocked_by: Iterable[str] = (),
    created_at: Optional[int] = None,
) -> TaskView:
    """Seed/setup only: create a Task identity with its first version in one query.

    Idempotent: an existing task with identical structure and v1 content is returned.
    """
    implements, blocked_by = sorted(set(implements)), sorted(set(blocked_by))
    created_at = created_at or _now()
    graph = authorized_graph(client, context, project_id)
    rows = graph.query(
        "MATCH (p:Project {id: $project}) "
        "OPTIONAL MATCH (x:Task {id: $id}) WITH p, x WHERE x IS NULL "
        "OPTIONAL MATCH (d:Decision)-[:ABOUT]->(p) WHERE d.id IN $implements "
        "WITH p, collect(DISTINCT d) AS decisions WHERE size(decisions) = size($implements) "
        "OPTIONAL MATCH (b:Task)-[:ABOUT]->(p) WHERE b.id IN $blocked_by "
        "WITH p, decisions, collect(DISTINCT b) AS blockers WHERE size(blockers) = size($blocked_by) "
        "OPTIONAL MATCH (owner:Person {id: $owner}) "
        "WITH p, decisions, blockers, owner WHERE $owner IS NULL OR owner IS NOT NULL "
        "CREATE (t:Task {id: $id, project_id: $project, created_at: $created_at})-[:ABOUT]->(p) "
        "CREATE (v:TaskVersion {id: $vid, task_id: $id, project_id: $project, version: 1, "
        "  version_key: $vkey, title: $title, status: $status, created_at: $created_at, "
        "  created_by: $by}) "
        "CREATE (t)-[:HAS_VERSION]->(v) "
        "FOREACH (o IN CASE WHEN owner IS NULL THEN [] ELSE [owner] END | CREATE (v)-[:ASSIGNED_TO]->(o)) "
        "FOREACH (d IN decisions | CREATE (t)-[:IMPLEMENTS]->(d)) "
        "FOREACH (b IN blockers | CREATE (t)-[:BLOCKED_BY]->(b)) "
        "RETURN t.id",
        params={"project": project_id, "id": task_id, "vid": f"{task_id}:v1", "vkey": f"{task_id}:1",
                "title": title, "status": status, "owner": assigned_to, "implements": implements,
                "blocked_by": blocked_by, "created_at": created_at, "by": context.user_id}).result_set
    if not rows:
        try:
            existing = get_task(client, context, project_id, task_id)
        except AccessDenied:
            raise ConflictingTaskError("Task references a missing decision, blocker or person") from None
        if (existing.version != 1 or existing.title != title or existing.implements != implements
                or existing.blocked_by != blocked_by):
            raise ConflictingTaskError("Task ID already used with different content")
        return existing
    return get_task(client, context, project_id, task_id)


_TASK_VIEW = (
    "MATCH (:Project {id: $project})<-[:ABOUT]-(t:Task) {where} "
    "MATCH (t)-[:HAS_VERSION]->(v:TaskVersion) WHERE NOT (v)<-[:PREVIOUS]-(:TaskVersion) "
    "OPTIONAL MATCH (v)-[:ASSIGNED_TO]->(owner:Person) "
    "OPTIONAL MATCH (t)-[:IMPLEMENTS]->(d:Decision) "
    "WITH t, v, owner, collect(DISTINCT d.id) AS implements "
    "OPTIONAL MATCH (t)-[:BLOCKED_BY]->(b:Task) "
    "WITH t, v, owner, implements, collect(DISTINCT b.id) AS blocked_by "
    "OPTIONAL MATCH (t)<-[:BLOCKED_BY]-(down:Task) "
    "RETURN t.id, t.project_id, v.id, v.version, v.title, v.status, owner.id, v.created_at, "
    "v.created_by, implements, blocked_by, collect(DISTINCT down.id) "
    "ORDER BY t.id, v.version"
)


def _views(graph, project_id: str, where: str = "", params: Optional[dict] = None) -> list[TaskView]:
    rows = graph.ro_query(_TASK_VIEW.replace("{where}", where),
                          params={"project": project_id, **(params or {})}).result_set
    keys = ("task_id", "project_id", "version_id", "version", "title", "status", "assigned_to",
            "created_at", "created_by", "implements", "blocked_by", "blocks")
    views = [TaskView(**dict(zip(keys, row))) for row in rows]
    seen = [v.task_id for v in views]
    duplicated = sorted({t for t in seen if seen.count(t) > 1})
    if duplicated:
        raise TaskIntegrityError("Several current versions for task(s): " + ", ".join(duplicated))
    for v in views:
        v.implements.sort(); v.blocked_by.sort(); v.blocks.sort()
    return views


def get_task(client: Any, context: TrustedContext, project_id: str, task_id: str) -> TaskView:
    graph = authorized_graph(client, context, project_id)
    found = _views(graph, project_id, "WHERE t.id = $id", {"id": task_id})
    if not found:
        exists = graph.ro_query("MATCH (:Project {id: $project})<-[:ABOUT]-(t:Task {id: $id}) RETURN t.id",
                                params={"project": project_id, "id": task_id}).result_set
        if exists:
            raise TaskIntegrityError(f"Task {task_id} has no current version")
        raise AccessDenied("Task unavailable or access denied")
    return found[0]


def list_tasks(client: Any, context: TrustedContext, project_id: str) -> list[TaskView]:
    return _views(authorized_graph(client, context, project_id), project_id)


def get_task_history(client: Any, context: TrustedContext, project_id: str, task_id: str) -> list[dict]:
    """Every version of a task, oldest first, following PREVIOUS edges."""
    graph = authorized_graph(client, context, project_id)
    rows = graph.ro_query(
        "MATCH (:Project {id: $project})<-[:ABOUT]-(t:Task {id: $id})-[:HAS_VERSION]->(v:TaskVersion) "
        "OPTIONAL MATCH (v)-[:PREVIOUS]->(prev:TaskVersion) "
        "OPTIONAL MATCH (v)-[:ASSIGNED_TO]->(o:Person) "
        "OPTIONAL MATCH (v)-[:CAUSED_BY]->(a:ProposedAction) "
        "RETURN v.id, v.version, v.title, v.status, o.id, v.created_at, v.created_by, prev.id, a.id "
        "ORDER BY v.version",
        params={"project": project_id, "id": task_id}).result_set
    if not rows:
        raise AccessDenied("Task unavailable or access denied")
    keys = ("version_id", "version", "title", "status", "assigned_to", "created_at",
            "created_by", "previous_version_id", "caused_by_action")
    return [dict(zip(keys, r)) for r in rows]


def trace_dependencies(client: Any, context: TrustedContext, project_id: str, task_id: str) -> TaskDependencies:
    """The task, what blocks it, what it blocks, and whether its decisions are still current."""
    graph = authorized_graph(client, context, project_id)
    task = get_task(client, context, project_id, task_id)
    related = {v.task_id: v for v in _views(graph, project_id, "WHERE t.id IN $ids",
                                            {"ids": task.blocked_by + task.blocks})}
    links = graph.ro_query(
        "MATCH (:Project {id: $project})<-[:ABOUT]-(t:Task {id: $id})-[:IMPLEMENTS]->(d:Decision) "
        "OPTIONAL MATCH (d)<-[:SUPERSEDES]-(n:Decision) "
        "RETURN d.id, collect(DISTINCT n.id) ORDER BY d.id",
        params={"project": project_id, "id": task_id}).result_set
    return TaskDependencies(
        task=task,
        blocked_by=[related[i] for i in task.blocked_by if i in related],
        blocks=[related[i] for i in task.blocks if i in related],
        implements=[DecisionLink(decision_id=d, is_current=not n, superseded_by=sorted(n)) for d, n in links])


def find_affected_tasks(client: Any, context: TrustedContext, project_id: str) -> list[AffectedTask]:
    """Tasks implementing a decision that has since been superseded (graph traversal)."""
    graph = authorized_graph(client, context, project_id)
    rows = graph.ro_query(
        "MATCH (:Project {id: $project})<-[:ABOUT]-(t:Task)-[:IMPLEMENTS]->(old:Decision)"
        "<-[:SUPERSEDES]-(new:Decision) "
        "RETURN t.id, old.id, collect(DISTINCT new.id) ORDER BY t.id, old.id",
        params={"project": project_id}).result_set
    views = {v.task_id: v for v in _views(graph, project_id, "WHERE t.id IN $ids", {"ids": [r[0] for r in rows]})}
    return [AffectedTask(task=views[t], superseded_decision_id=old, replaced_by=sorted(new))
            for t, old, new in rows if t in views]
