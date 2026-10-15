"""Conversation memory module.

Handles session creation, message persistence, and deterministic retrieval with
after_seq pagination backed by FalkorDB.

CONCURRENCY GUARANTEES & CURRENT LIMITATIONS:
---------------------------------------------
Guaranteed:
- Single-worker / serialized write safety: monotonic sequence number allocation (1, 2, 3...) per session.
- Stable operation IDs: retrying create_session or save_message with identical payloads returns the
  original record without creating duplicate graph nodes and preserves original creation timestamp/seq.
- Conflict rejection: reusing an existing session_id or message_id with conflicting attributes (different
  project, owner, role, content, or session) is explicitly rejected.
- Graph and tenant isolation: graph selection is derived strictly from trusted server context;
  session ownership is verified before every read and write.

Limitations (Pending shared platform safeguards):
- Multi-worker concurrency: Sequence allocation queries `coalesce(max(m.seq), 0) + 1`. If two concurrent
  workers write to the same session simultaneously, they could race on sequence allocation. Multi-worker
  safety requires database-level unique constraints on (session_id, seq) and message_id, or distributed
  locking, which must be agreed and implemented with the platform owner before making multi-worker claims.
- MERGE alone is not a concurrency guarantee in FalkorDB without supporting unique constraints.
"""

from __future__ import annotations

import time
from typing import Any, Literal
from pydantic import Field, field_validator

from relaymind.contracts.models import StrictModel, TrustedContext
from relaymind.contracts.conversations import SessionRecord, MessageRecord
from relaymind.graph.connection import create_client
from relaymind.graph.access import authorized_graph, require_session, AccessDenied


class ConversationMemoryError(Exception):
    """Base exception for conversation memory operations."""
    pass


class ConflictingMessageError(ConversationMemoryError):
    """Raised when attempting to reuse a message ID with conflicting content."""
    pass


class ConflictingSessionError(ConversationMemoryError):
    """Raised when attempting to reuse a session ID with conflicting owner or project."""
    pass


class DatabaseOperationError(ConversationMemoryError):
    """Raised when a graph database operation fails."""
    pass


class SaveMessageInput(StrictModel):
    message_id: str = Field(min_length=1, description="Unique UUID for the message / operation")
    project_id: str = Field(min_length=1, description="Associated project identifier")
    session_id: str = Field(min_length=1, description="Session UUID this message belongs to")
    role: Literal["user", "assistant"] = Field(description="Role of the sender")
    content: str = Field(min_length=1, max_length=16000, description="Message body text")

    @field_validator("content")
    @classmethod
    def validate_content_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message content must not be blank or whitespace-only.")
        return v


def create_session(
    client: Any,
    context: TrustedContext,
    project_id: str,
    session_id: str,
) -> SessionRecord:
    """
    Creates a new conversation session associated with an authorized project.

    If the session_id already exists:
    - Retrying with the same owner and project returns the original SessionRecord,
      preserving the original created_at timestamp (idempotent).
    - If the existing session belongs to a different owner or project, raises ConflictingSessionError.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty")
    if not project_id or not project_id.strip():
        raise ValueError("project_id must not be empty")

    graph = authorized_graph(client, context, project_id)

    # Check if session already exists
    check_query = (
        "MATCH (s:Session {id: $session_id}) "
        "OPTIONAL MATCH (s)-[:ABOUT]->(p:Project) "
        "RETURN s.id, s.owner_id, s.created_at, p.id"
    )
    try:
        existing_res = graph.query(check_query, params={"session_id": session_id}).result_set
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to check existing session: {exc}") from exc

    if existing_res:
        row = existing_res[0]
        ex_id, ex_owner, ex_created_at, ex_proj = row[0], row[1], row[2], row[3]
        if ex_owner == context.user_id and ex_proj == project_id:
            # Idempotent retry: preserve original owner and creation time
            return SessionRecord(
                id=ex_id,
                project_id=project_id,
                owner_id=ex_owner,
                created_at=ex_created_at,
            )
        else:
            raise ConflictingSessionError(
                f"Session '{session_id}' already exists with conflicting owner or project: "
                f"(owner={ex_owner}, project={ex_proj}) vs requested (owner={context.user_id}, project={project_id})"
            )

    now_ms = int(time.time() * 1000)
    create_query = (
        "MERGE (p:Project {id: $project_id}) "
        "ON CREATE SET p.name = $project_id "
        "CREATE (s:Session {id: $session_id, owner_id: $owner_id, created_at: $now_ms}) "
        "CREATE (s)-[:ABOUT]->(p) "
        "RETURN s.id, s.owner_id, s.created_at"
    )
    try:
        insert_res = graph.query(
            create_query,
            params={
                "project_id": project_id,
                "session_id": session_id,
                "owner_id": context.user_id,
                "now_ms": now_ms,
            },
        ).result_set
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to create session: {exc}") from exc

    if not insert_res:
        raise DatabaseOperationError("Session creation query returned no records")

    rec = insert_res[0]
    return SessionRecord(
        id=rec[0],
        project_id=project_id,
        owner_id=rec[1],
        created_at=rec[2],
    )


def save_message(
    client: Any,
    context: TrustedContext,
    project_id: str,
    session_id: str,
    message_id: str,
    role: Literal["user", "assistant"],
    content: str,
) -> MessageRecord:
    """
    Saves a message to FalkorDB linked to its parent session.

    Backend code assigns the sequence number (monotonically increasing starting at 1 per session)
    and the UTC epoch millisecond timestamp. Never accepts seq or timestamp from the caller.

    Guarantees:
    - Enforces session access and project authorization via trusted context before writes.
    - Uses parameterized Cypher queries.
    - Idempotent: retrying the exact same write with identical payload returns the existing record
      with its original seq and timestamp.
    - Rejects conflicting reuse of an existing message_id.
    """
    validated = SaveMessageInput(
        message_id=message_id,
        project_id=project_id,
        session_id=session_id,
        role=role,
        content=content,
    )

    db_client = client if client is not None else create_client()
    graph = authorized_graph(db_client, context, project_id)

    # Enforce that caller has access to the session
    try:
        require_session(graph, context, project_id, session_id)
    except AccessDenied:
        raise
    except Exception as exc:
        raise DatabaseOperationError(f"Database error during session access check: {exc}") from exc

    # Check if a message with this message_id already exists
    check_query = (
        "MATCH (m:Message {id: $message_id}) "
        "RETURN m.id, m.session_id, m.role, m.content, m.created_at, m.seq"
    )
    try:
        existing_res = graph.query(check_query, params={"message_id": validated.message_id}).result_set
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to check existing message: {exc}") from exc

    if existing_res:
        existing_row = existing_res[0]
        ex_id, ex_sess_id, ex_role, ex_content, ex_created_at, ex_seq = existing_row

        # Check if identical payload (idempotent retry)
        if (
            ex_sess_id == validated.session_id
            and ex_role == validated.role
            and ex_content == validated.content
        ):
            return MessageRecord(
                id=ex_id,
                session_id=ex_sess_id,
                role=ex_role,
                content=ex_content,
                created_at=ex_created_at,
                seq=ex_seq,
            )
        else:
            raise ConflictingMessageError(
                f"Message ID '{validated.message_id}' already exists with conflicting attributes: "
                f"(session={ex_sess_id}, role={ex_role}) vs requested "
                f"(session={validated.session_id}, role={validated.role})"
            )

    # Server assigns sequence number: max(seq) in this session + 1
    seq_query = (
        "MATCH (s:Session {id: $session_id})-[:HAS_MESSAGE]->(m:Message) "
        "RETURN coalesce(max(m.seq), 0) AS max_seq"
    )
    try:
        seq_res = graph.query(seq_query, params={"session_id": validated.session_id}).result_set
        max_seq = seq_res[0][0] if seq_res else 0
        next_seq = int(max_seq) + 1
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to allocate sequence number: {exc}") from exc

    now_ms = int(time.time() * 1000)

    # Insert new message and link to session
    insert_query = (
        "MATCH (s:Session {id: $session_id}) "
        "CREATE (m:Message {"
        "  id: $message_id, "
        "  session_id: $session_id, "
        "  role: $role, "
        "  content: $content, "
        "  created_at: $created_at, "
        "  seq: $seq"
        "}) "
        "CREATE (s)-[:HAS_MESSAGE]->(m) "
        "RETURN m.id, m.session_id, m.role, m.content, m.created_at, m.seq"
    )
    try:
        insert_res = graph.query(
            insert_query,
            params={
                "session_id": validated.session_id,
                "message_id": validated.message_id,
                "role": validated.role,
                "content": validated.content,
                "created_at": now_ms,
                "seq": next_seq,
            },
        ).result_set
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to insert message: {exc}") from exc

    if not insert_res or len(insert_res) != 1:
        raise DatabaseOperationError("Write query did not return the expected inserted record")

    row = insert_res[0]
    return MessageRecord(
        id=row[0],
        session_id=row[1],
        role=row[2],
        content=row[3],
        created_at=row[4],
        seq=row[5],
    )


def load_messages(
    client: Any,
    context: TrustedContext,
    project_id: str,
    session_id: str,
    after_seq: int = 0,
    limit: int = 100,
) -> list[MessageRecord]:
    """
    Loads messages for an authorized session ordered deterministically by seq ASC, id ASC.
    Supports cursor pagination via after_seq.
    """
    if after_seq < 0:
        raise ValueError("after_seq must be non-negative (>= 0)")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100 inclusive")

    db_client = client if client is not None else create_client()
    graph = authorized_graph(db_client, context, project_id)

    # Enforce that caller has access to the session
    try:
        require_session(graph, context, project_id, session_id)
    except AccessDenied:
        raise
    except Exception as exc:
        raise DatabaseOperationError(f"Database error during session access check: {exc}") from exc

    read_query = (
        "MATCH (s:Session {id: $session_id})-[:HAS_MESSAGE]->(m:Message) "
        "WHERE m.seq > $after_seq "
        "RETURN m.id, m.session_id, m.role, m.content, m.created_at, m.seq "
        "ORDER BY m.seq ASC, m.id ASC "
        "LIMIT $limit"
    )
    try:
        rows = graph.query(
            read_query,
            params={"session_id": session_id, "after_seq": after_seq, "limit": limit},
        ).result_set
    except Exception as exc:
        raise DatabaseOperationError(f"Failed to query messages: {exc}") from exc

    records = []
    for row in rows:
        records.append(
            MessageRecord(
                id=row[0],
                session_id=row[1],
                role=row[2],
                content=row[3],
                created_at=row[4],
                seq=row[5],
            )
        )
    return records
