"""Episodic memory module.

Records and retrieves what happened historically, linked to an authorized project
and a supporting source message in an accessible session.

CONCURRENCY GUARANTEES & PAGINATION BOUNDARIES:
---------------------------------------------
Guaranteed:
- Single-worker / serialized write safety: atomic creation of (Episode)-[:ABOUT]->(Project)
  and (Episode)-[:SUPPORTED_BY]->(Message) in a single parameterized Cypher query.
- Stable operation IDs: retrying save_episode with identical attributes returns the original
  record, preserving original creation timestamp and recorded_by identity.
- Conflict rejection: reusing an existing episode_id with conflicting attributes (project,
  source_message_id, summary, or occurred_at) or attempting to reuse an episode ID across
  different user identities is explicitly rejected.
- Source session access enforcement: both save_episode and load_episodes require that the
  supporting source message belongs to a session owned by context.user_id within the authorized project.
- Tenant isolation: graph selection is derived strictly from trusted server context.

Pagination Boundary & Offset Behavior:
- load_episodes uses bounded offset pagination (1 <= limit <= 50, offset >= 0).
- Ordering is deterministic: ORDER BY e.occurred_at DESC, e.id ASC.
- Note on concurrent writes: Because offset pagination is index-based, inserting new episodes
  between page fetches may shift results. Cursor-based pagination (e.g. by occurred_at/id)
  can be introduced if dynamic write streaming is required.
- MERGE alone is not a concurrency guarantee in FalkorDB without unique constraints.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from relaymind.contracts.models import TrustedContext
from relaymind.contracts.episodes import EpisodeRecord
from relaymind.graph.connection import create_client
from relaymind.graph.access import authorized_graph, AccessDenied


class EpisodeMemoryError(Exception):
    """Base exception for episodic memory operations."""
    pass


class InaccessibleSourceMessageError(EpisodeMemoryError, AccessDenied):
    """Raised when a supporting source message does not exist or is not accessible to the user."""
    pass


class ConflictingEpisodeError(EpisodeMemoryError):
    """Raised when attempting to reuse an episode ID with conflicting attributes or ownership."""
    pass


class DatabaseOperationError(EpisodeMemoryError):
    """Raised when a graph database operation fails."""
    pass


def save_episode(
    client: Any,
    context: TrustedContext,
    project_id: str,
    episode_id: str,
    source_message_id: str,
    summary: str,
    occurred_at: Optional[int] = None,
) -> EpisodeRecord:
    """
    Saves an episodic memory linked to its project and supporting source message.

    Guarantees:
    - Verifies that source_message_id exists in the authorized project and in a session
      owned by context.user_id. Raises InaccessibleSourceMessageError if not.
    - Defaults occurred_at to the source message's stored timestamp if not explicitly supplied.
    - Idempotent: retrying with identical attributes returns the original record.
    - Conflicting reuse: reusing episode_id with differing attributes or by another user
      raises ConflictingEpisodeError.
    - Server sets created_at (UTC epoch ms), recorded_by (context.user_id), and status ('recorded').
    - Atomically creates (Episode)-[:ABOUT]->(Project) and (Episode)-[:SUPPORTED_BY]->(Message).
    """
    if not episode_id or not episode_id.strip():
        raise ValueError("episode_id must not be empty")
    if not project_id or not project_id.strip():
        raise ValueError("project_id must not be empty")
    if not source_message_id or not source_message_id.strip():
        raise ValueError("source_message_id must not be empty")

    stripped_summary = summary.strip()
    if not stripped_summary:
        raise ValueError("Summary must not be blank or whitespace-only.")
    if len(stripped_summary) > 16000:
        raise ValueError("Summary must not exceed 16000 characters.")

    if occurred_at is not None and occurred_at <= 0:
        raise ValueError("occurred_at must be a positive timestamp")

    db_client = client if client is not None else create_client()
    try:
        graph = authorized_graph(db_client, context, project_id)
    except AccessDenied:
        raise
    except Exception as exc:
        raise DatabaseOperationError(f"Database access check failed: {exc}") from exc

    # 1. Verify source message exists in a session owned by this user in this project
    source_check_query = (
        "MATCH (p:Project {id: $project_id}) "
        "MATCH (s:Session {owner_id: $owner_id})-[:ABOUT]->(p) "
        "MATCH (s)-[:HAS_MESSAGE]->(m:Message {id: $source_message_id}) "
        "RETURN m.id, m.created_at"
    )
    try:
        source_res = graph.query(
            source_check_query,
            params={
                "project_id": project_id,
                "owner_id": context.user_id,
                "source_message_id": source_message_id,
            },
        ).result_set
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to verify source message: {exc}") from exc

    if not source_res:
        raise InaccessibleSourceMessageError("Source message unavailable or access denied")

    source_row = source_res[0]
    msg_created_at = source_row[1]

    # Default occurred_at to the supporting message's timestamp if not explicitly supplied
    final_occurred_at = occurred_at if occurred_at is not None else int(msg_created_at)

    # 2. Check if an episode with this episode_id already exists
    check_query = (
        "MATCH (e:Episode {id: $episode_id}) "
        "OPTIONAL MATCH (e)-[:ABOUT]->(p:Project) "
        "OPTIONAL MATCH (e)-[:SUPPORTED_BY]->(m:Message) "
        "RETURN e.id, p.id, m.id, e.summary, e.occurred_at, e.created_at, e.recorded_by, e.status"
    )
    try:
        existing_res = graph.query(check_query, params={"episode_id": episode_id}).result_set
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to check existing episode: {exc}") from exc

    if existing_res:
        row = existing_res[0]
        ex_id, ex_proj, ex_source, ex_summary, ex_occurred, ex_created, ex_recorded_by, ex_status = row

        # Check if identical payload and same recorded_by identity (idempotent retry)
        if (
            ex_recorded_by == context.user_id
            and ex_proj == project_id
            and ex_source == source_message_id
            and ex_summary == stripped_summary
            and int(ex_occurred) == final_occurred_at
        ):
            return EpisodeRecord(
                id=ex_id,
                project_id=ex_proj,
                source_message_id=ex_source,
                summary=ex_summary,
                occurred_at=int(ex_occurred),
                created_at=int(ex_created),
                recorded_by=ex_recorded_by,
                status=ex_status,
            )
        else:
            raise ConflictingEpisodeError(
                f"Episode ID '{episode_id}' already exists with conflicting attributes or ownership."
            )

    now_ms = int(time.time() * 1000)

    # 3. Create Episode node and link to Project and Source Message atomically
    insert_query = (
        "MATCH (p:Project {id: $project_id}) "
        "MATCH (s:Session {owner_id: $owner_id})-[:ABOUT]->(p) "
        "MATCH (s)-[:HAS_MESSAGE]->(m:Message {id: $source_message_id}) "
        "CREATE (e:Episode {"
        "  id: $episode_id, "
        "  project_id: $project_id, "
        "  summary: $summary, "
        "  occurred_at: $occurred_at, "
        "  created_at: $created_at, "
        "  recorded_by: $owner_id, "
        "  status: 'recorded'"
        "}) "
        "CREATE (e)-[:ABOUT]->(p) "
        "CREATE (e)-[:SUPPORTED_BY]->(m) "
        "RETURN e.id, p.id, m.id, e.summary, e.occurred_at, e.created_at, e.recorded_by, e.status"
    )
    try:
        insert_res = graph.query(
            insert_query,
            params={
                "project_id": project_id,
                "owner_id": context.user_id,
                "source_message_id": source_message_id,
                "episode_id": episode_id,
                "summary": stripped_summary,
                "occurred_at": final_occurred_at,
                "created_at": now_ms,
            },
        ).result_set
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to insert episode: {exc}") from exc

    if not insert_res or len(insert_res) != 1:
        raise DatabaseOperationError("Write query did not return the expected inserted episode record")

    rec = insert_res[0]
    return EpisodeRecord(
        id=rec[0],
        project_id=rec[1],
        source_message_id=rec[2],
        summary=rec[3],
        occurred_at=int(rec[4]),
        created_at=int(rec[5]),
        recorded_by=rec[6],
        status=rec[7],
    )


def load_episodes(
    client: Any,
    context: TrustedContext,
    project_id: str,
    limit: int = 10,
    offset: int = 0,
) -> list[EpisodeRecord]:
    """
    Retrieves project episodes ordered deterministically (occurred_at DESC, id ASC).
    Enforces source-session access: only returns episodes whose supporting source
    message belongs to a session accessible to context.user_id.

    Bounded pagination: 1 <= limit <= 50, offset >= 0.
    """
    if limit < 1 or limit > 50:
        raise ValueError("limit must be between 1 and 50 inclusive")
    if offset < 0:
        raise ValueError("offset must be non-negative (>= 0)")

    db_client = client if client is not None else create_client()
    try:
        graph = authorized_graph(db_client, context, project_id)
    except AccessDenied:
        raise
    except Exception as exc:
        raise DatabaseOperationError(f"Database access check failed: {exc}") from exc

    read_query = (
        "MATCH (e:Episode)-[:ABOUT]->(p:Project {id: $project_id}) "
        "MATCH (e)-[:SUPPORTED_BY]->(m:Message)<-[:HAS_MESSAGE]-(s:Session {owner_id: $owner_id})-[:ABOUT]->(p) "
        "RETURN e.id, p.id, m.id, e.summary, e.occurred_at, e.created_at, e.recorded_by, e.status "
        "ORDER BY e.occurred_at DESC, e.id ASC "
        "SKIP $offset "
        "LIMIT $limit"
    )
    try:
        rows = graph.query(
            read_query,
            params={
                "project_id": project_id,
                "owner_id": context.user_id,
                "offset": offset,
                "limit": limit,
            },
        ).result_set
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to query episodes: {exc}") from exc

    records = []
    for r in rows:
        records.append(
            EpisodeRecord(
                id=r[0],
                project_id=r[1],
                source_message_id=r[2],
                summary=r[3],
                occurred_at=int(r[4]),
                created_at=int(r[5]),
                recorded_by=r[6],
                status=r[7],
            )
        )
    return records
