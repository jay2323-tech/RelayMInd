"""Decision memory: approved decisions, explicit supersession, current/conflict reads.

Design: docs/memory-design.md sections 2.1 and 3.

- Decision nodes are write-once. A new version is a new node created together
  with SUPERSEDES edges to the decisions it replaces.
- Current = no incoming SUPERSEDES. Conflict = 2+ current decisions on one topic.
  Conflicts are reported; nothing here chooses a winner by time, version or ID.
- Sources are project-level evidence, readable by any identity with project access.

WRITE SAFETY:
- Each write is one guarded query (existence, sources, topic and "replaced
  decision is still current" are checked inside the same query that creates).
- serialized_write additionally serializes writes within one Python process.
- Multi-process behaviour is covered by the opt-in two-process tests
  (tests/test_decisions_atomicity_real_db.py); see docs/verification.md for results.
  Unique constraints on Decision.id / Source.id are created by scripts/setup_graph.py.
"""
from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from relaymind.contracts.decisions import (
    CurrentDecisions, DecisionConflict, DecisionRecord, DecisionView, SourceRecord,
)
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import AccessDenied, authorized_graph
from relaymind.memory.locking import serialized_write


class DecisionMemoryError(Exception):
    """Base exception for decision memory operations."""


class ConflictingDecisionError(DecisionMemoryError):
    """A decision or source ID is already used with different content."""


class InvalidSupersessionError(DecisionMemoryError):
    """A replaced decision is missing, in another topic/project, or no longer current."""


class UnknownSourceError(DecisionMemoryError, AccessDenied):
    """A cited source does not exist in this project."""


class DatabaseOperationError(DecisionMemoryError):
    """The graph write did not produce exactly one record."""


def _now() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------- sources

@serialized_write
def record_source(
    client: Any, context: TrustedContext, project_id: str, source_id: str,
    kind: str, title: str, text: str, created_at: Optional[int] = None,
) -> SourceRecord:
    """Store a project-level source document. Idempotent for identical content."""
    record = SourceRecord(id=source_id, project_id=project_id, kind=kind, title=title,
                          text=text, created_at=created_at or _now())
    graph = authorized_graph(client, context, project_id)
    rows = graph.query(
        "MATCH (p:Project {id: $project}) "
        "OPTIONAL MATCH (existing:Source {id: $id}) "
        "WITH p, existing WHERE existing IS NULL "
        "CREATE (s:Source {id: $id, project_id: $project, kind: $kind, title: $title, "
        "text: $text, created_at: $created_at})-[:ABOUT]->(p) RETURN s.id",
        params=record.model_dump() | {"project": project_id},
    ).result_set
    if len(rows) == 1:
        return record
    existing = get_source(client, context, project_id, source_id, _graph=graph, _missing_ok=True)
    if existing is None:
        raise AccessDenied("Project unavailable")
    if existing.model_dump(exclude={"created_at"}) != record.model_dump(exclude={"created_at"}):
        raise ConflictingDecisionError("Source ID already used with different content")
    return existing


def get_source(client, context, project_id, source_id, *, _graph=None, _missing_ok=False):
    graph = _graph or authorized_graph(client, context, project_id)
    rows = graph.ro_query(
        "MATCH (s:Source {id: $id})-[:ABOUT]->(:Project {id: $project}) "
        "RETURN s.id, s.project_id, s.kind, s.title, s.text, s.created_at",
        params={"id": source_id, "project": project_id},
    ).result_set
    if len(rows) != 1:
        if _missing_ok:
            return None
        raise AccessDenied("Source unavailable or access denied")
    keys = ("id", "project_id", "kind", "title", "text", "created_at")
    return SourceRecord(**dict(zip(keys, rows[0])))


# -------------------------------------------------------------- decisions

_RECORD_QUERY = (
    "MATCH (p:Project {id: $project}) "
    "OPTIONAL MATCH (existing:Decision {id: $id}) "
    "WITH p, existing WHERE existing IS NULL "
    "OPTIONAL MATCH (s:Source)-[:ABOUT]->(p) WHERE s.id IN $source_ids "
    "WITH p, collect(DISTINCT s) AS sources "
    "WHERE size(sources) = size($source_ids) "
    "OPTIONAL MATCH (old:Decision {topic: $topic})-[:ABOUT]->(p) WHERE old.id IN $supersedes "
    "OPTIONAL MATCH (old)<-[:SUPERSEDES]-(newer:Decision) "
    "WITH p, sources, old, count(newer) AS successors "
    "WITH p, sources, "
    "     collect(CASE WHEN old IS NOT NULL AND successors = 0 THEN old END) AS replaced "
    "WHERE size(replaced) = size($supersedes) "
    "WITH p, sources, replaced, "
    "     reduce(v = 0, o IN replaced | CASE WHEN o.version > v THEN o.version ELSE v END) + 1 AS version "
    "CREATE (d:Decision {id: $id, project_id: $project, topic: $topic, version: version, "
    "  text: $text, approved_by: $approved_by, approved_at: $approved_at, created_at: $created_at}) "
    "CREATE (d)-[:ABOUT]->(p) "
    "FOREACH (s IN sources | CREATE (d)-[:SUPPORTED_BY]->(s)) "
    "FOREACH (o IN replaced | CREATE (d)-[:SUPERSEDES {reason: $reason, at: $created_at}]->(o)) "
    "RETURN d.version"
)


@serialized_write
def record_decision(
    client: Any, context: TrustedContext, project_id: str, decision_id: str,
    topic: str, text: str, source_ids: Iterable[str], supersedes: Iterable[str] = (),
    *, reason: str = "", approved_by: Optional[str] = None,
    approved_at: Optional[int] = None, human_approved: bool = False,
) -> DecisionRecord:
    """Record a human-approved decision, optionally superseding current decisions.

    Setup/service operation only; never a model tool. `human_approved` is an explicit
    acknowledgement, not an identity mechanism. `approved_by` defaults to the trusted
    caller; seed scripts may attribute synthetic approvers.
    Idempotent: the same ID with identical content returns the stored record.
    """
    if not human_approved:
        raise PermissionError("Explicit human approval required to record a decision")
    now = _now()
    draft = DecisionRecord(
        id=decision_id, project_id=project_id, topic=topic, version=1, text=text,
        source_ids=list(source_ids), supersedes=list(supersedes),
        approved_by=approved_by or context.user_id, approved_at=approved_at or now, created_at=now,
    )
    if draft.id in draft.supersedes:
        raise InvalidSupersessionError("A decision cannot supersede itself")
    graph = authorized_graph(client, context, project_id)
    rows = graph.query(_RECORD_QUERY, params={
        "project": project_id, "id": draft.id, "topic": draft.topic, "text": draft.text,
        "source_ids": draft.source_ids, "supersedes": draft.supersedes, "reason": reason,
        "approved_by": draft.approved_by, "approved_at": draft.approved_at, "created_at": now,
    }).result_set
    if len(rows) == 1:
        return draft.model_copy(update={"version": rows[0][0]})
    if len(rows) > 1:
        raise DatabaseOperationError("Decision write produced more than one record")
    return _explain_rejected_write(graph, draft)


def _explain_rejected_write(graph, draft: DecisionRecord) -> DecisionRecord:
    """The guarded write returned no row: re-read and report the precise reason."""
    existing = _load(graph, draft.project_id, "WHERE d.id = $id", {"id": draft.id})
    if existing:
        stored = existing[0]
        same = ("topic", "text", "source_ids", "supersedes", "approved_by")
        if all(getattr(stored, f) == getattr(draft, f) for f in same):
            return DecisionRecord(**stored.model_dump(exclude={"superseded_by", "is_current"}))
        raise ConflictingDecisionError("Decision ID already used with different content")
    if graph.ro_query("MATCH (d:Decision {id: $id}) RETURN d.id",
                      params={"id": draft.id}).result_set:
        raise ConflictingDecisionError("Decision ID already used in another project")
    found = {r[0] for r in graph.ro_query(
        "MATCH (s:Source)-[:ABOUT]->(:Project {id: $project}) WHERE s.id IN $ids RETURN s.id",
        params={"project": draft.project_id, "ids": draft.source_ids}).result_set}
    if found != set(draft.source_ids):
        raise UnknownSourceError("Cited source unavailable: " + ", ".join(sorted(set(draft.source_ids) - found)))
    replaced = {d.id: d for d in _load(graph, draft.project_id, "WHERE d.id IN $ids", {"ids": draft.supersedes})}
    for old_id in draft.supersedes:
        old = replaced.get(old_id)
        if old is None:
            raise InvalidSupersessionError(f"Replaced decision {old_id} not found in this project")
        if old.topic != draft.topic:
            raise InvalidSupersessionError(f"Replaced decision {old_id} belongs to topic {old.topic}")
        if not old.is_current:
            raise InvalidSupersessionError(
                f"Replaced decision {old_id} is no longer current (superseded by {', '.join(old.superseded_by)})")
    raise AccessDenied("Project unavailable")


_VIEW_QUERY = (
    "MATCH (d:Decision)-[:ABOUT]->(:Project {id: $project}) {where} "
    "OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(s:Source) "
    "WITH d, collect(DISTINCT s.id) AS sources "
    "OPTIONAL MATCH (d)-[:SUPERSEDES]->(old:Decision) "
    "WITH d, sources, collect(DISTINCT old.id) AS replaces "
    "OPTIONAL MATCH (newer:Decision)-[:SUPERSEDES]->(d) "
    "RETURN d.id, d.project_id, d.topic, d.version, d.text, sources, replaces, "
    "d.approved_by, d.approved_at, d.created_at, collect(DISTINCT newer.id) AS successors "
    "ORDER BY d.topic, d.id"
)


def _load(graph, project_id: str, where: str = "", params: Optional[dict] = None) -> list[DecisionView]:
    rows = graph.ro_query(_VIEW_QUERY.replace("{where}", where),
                          params={"project": project_id, **(params or {})}).result_set
    views = []
    for (id_, project, topic, version, text, sources, replaces,
         approved_by, approved_at, created_at, successors) in rows:
        views.append(DecisionView(
            id=id_, project_id=project, topic=topic, version=version, text=text,
            source_ids=sources, supersedes=replaces, approved_by=approved_by,
            approved_at=approved_at, created_at=created_at,
            superseded_by=sorted(successors), is_current=not successors))
    return views


def get_current_decisions(client: Any, context: TrustedContext, project_id: str) -> CurrentDecisions:
    """Current decisions grouped by topic; topics with 2+ are reported as conflicts.

    One read gives one consistent snapshot for both lists.
    """
    graph = authorized_graph(client, context, project_id)
    current = _load(graph, project_id, "WHERE NOT (d)<-[:SUPERSEDES]-(:Decision)")
    by_topic: dict[str, list[DecisionView]] = {}
    for view in current:
        by_topic.setdefault(view.topic, []).append(view)
    result = CurrentDecisions(current=[], conflicts=[], conflicting=[])
    for topic, views in sorted(by_topic.items()):
        if len(views) == 1:
            result.current.append(views[0])
        else:
            result.conflicting.extend(views)
            result.conflicts.append(DecisionConflict(
                topic=topic, decision_ids=sorted(v.id for v in views),
                source_ids=sorted({s for v in views for s in v.source_ids})))
    return result


def get_decision(client: Any, context: TrustedContext, project_id: str, decision_id: str) -> DecisionView:
    graph = authorized_graph(client, context, project_id)
    found = _load(graph, project_id, "WHERE d.id = $id", {"id": decision_id})
    if len(found) != 1:
        raise AccessDenied("Decision unavailable or access denied")
    return found[0]


def get_decision_history(client: Any, context: TrustedContext, project_id: str, topic: str) -> list[DecisionView]:
    """Every decision ever recorded on a topic, oldest version first."""
    graph = authorized_graph(client, context, project_id)
    views = _load(graph, project_id, "WHERE d.topic = $topic", {"topic": topic})
    return sorted(views, key=lambda v: (v.version, v.approved_at, v.id))
