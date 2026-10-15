import pytest
from pydantic import ValidationError

from relaymind.contracts.models import TrustedContext
from relaymind.contracts.conversations import SessionRecord, MessageRecord
from relaymind.graph.access import AccessDenied
from relaymind.memory.conversations import (
    create_session,
    save_message,
    load_messages,
    ConflictingMessageError,
    ConflictingSessionError,
    DatabaseOperationError,
)


class FakeQueryResult:
    def __init__(self, result_set):
        self.result_set = result_set


class FakeFalkorDBGraph:
    """
    Test double simulating FalkorDB query execution in-memory.
    Clearly labeled as a test double — NOT persistent storage.
    """
    def __init__(self):
        # sessions maps session_id -> dict(owner_id, project_id, created_at, messages)
        self.sessions = {}
        self.messages_by_id = {}
        self.should_fail = False

    def ro_query(self, query: str, params=None):
        return self.query(query, params)

    def query(self, query: str, params=None):
        if self.should_fail:
            raise RuntimeError("Simulated database failure")

        params = params or {}

        # 1. Check existing session for create_session
        if "MATCH (s:Session {id: $session_id})" in query and "OPTIONAL MATCH (s)-[:ABOUT]->(p:Project)" in query:
            s_id = params.get("session_id")
            if s_id in self.sessions:
                s = self.sessions[s_id]
                return FakeQueryResult([[s_id, s["owner_id"], s["created_at"], s["project_id"]]])
            return FakeQueryResult([])

        # 2. Create session
        if "CREATE (s:Session" in query and "MERGE (p:Project" in query:
            s_id = params.get("session_id")
            s_owner = params.get("owner_id")
            s_proj = params.get("project_id")
            s_now = params.get("now_ms")
            self.sessions[s_id] = {
                "owner_id": s_owner,
                "project_id": s_proj,
                "created_at": s_now,
                "messages": [],
            }
            return FakeQueryResult([[s_id, s_owner, s_now]])

        # 3. require_session check: MATCH (s:Session {id: $session_id, owner_id: $owner_id})-[:ABOUT]->(p:Project {id: $project_id})
        if "MATCH (s:Session" in query and "owner_id: $owner_id" in query:
            s_id = params.get("session_id")
            owner_id = params.get("owner_id")
            proj_id = params.get("project_id")
            if s_id in self.sessions:
                s = self.sessions[s_id]
                if s["owner_id"] == owner_id and s["project_id"] == proj_id:
                    return FakeQueryResult([[s_id]])
            return FakeQueryResult([])

        # 4. Check existing message
        if "MATCH (m:Message {id: $message_id})" in query:
            m_id = params.get("message_id")
            if m_id in self.messages_by_id:
                m = self.messages_by_id[m_id]
                return FakeQueryResult([[m["id"], m["session_id"], m["role"], m["content"], m["created_at"], m["seq"]]])
            return FakeQueryResult([])

        # 5. Allocate sequence: MATCH (s:Session)-[:HAS_MESSAGE]->(m:Message) RETURN coalesce(max(m.seq), 0)
        if "coalesce(max(m.seq), 0)" in query:
            s_id = params.get("session_id")
            s = self.sessions.get(s_id, {"messages": []})
            max_seq = max([m["seq"] for m in s["messages"]], default=0)
            return FakeQueryResult([[max_seq]])

        # 6. Insert message
        if "CREATE (m:Message" in query:
            s_id = params.get("session_id")
            msg_data = {
                "id": params.get("message_id"),
                "session_id": s_id,
                "role": params.get("role"),
                "content": params.get("content"),
                "created_at": params.get("created_at"),
                "seq": params.get("seq"),
            }
            self.messages_by_id[msg_data["id"]] = msg_data
            if s_id in self.sessions:
                self.sessions[s_id]["messages"].append(msg_data)
            return FakeQueryResult([[
                msg_data["id"],
                msg_data["session_id"],
                msg_data["role"],
                msg_data["content"],
                msg_data["created_at"],
                msg_data["seq"],
            ]])

        # 7. Load messages with after_seq
        if "WHERE m.seq > $after_seq" in query:
            s_id = params.get("session_id")
            after_seq = params.get("after_seq", 0)
            limit = params.get("limit", 100)
            s = self.sessions.get(s_id, {"messages": []})
            filtered = [m for m in s["messages"] if m["seq"] > after_seq]
            sorted_msgs = sorted(filtered, key=lambda m: (m["seq"], m["id"]))[:limit]
            rows = [
                [m["id"], m["session_id"], m["role"], m["content"], m["created_at"], m["seq"]]
                for m in sorted_msgs
            ]
            return FakeQueryResult(rows)

        return FakeQueryResult([])


class FakeFalkorDBClient:
    """Test double for FalkorDB client routing to a FakeFalkorDBGraph."""
    def __init__(self):
        self.graphs = {}

    def select_graph(self, name: str):
        if name not in self.graphs:
            self.graphs[name] = FakeFalkorDBGraph()
        return self.graphs[name]


@pytest.fixture
def fake_client():
    return FakeFalkorDBClient()


@pytest.fixture
def auth_context():
    return TrustedContext(tenant_id="demo-a", user_id="developer-a")


def test_session_creation_and_idempotent_retry(fake_client, auth_context):
    session1 = create_session(fake_client, auth_context, "launch-01", "sess-test-1")
    assert session1.id == "sess-test-1"
    assert session1.owner_id == "developer-a"
    assert session1.project_id == "launch-01"

    # Retrying the same session_id with same owner/project preserves created_at
    session2 = create_session(fake_client, auth_context, "launch-01", "sess-test-1")
    assert session2.id == session1.id
    assert session2.created_at == session1.created_at
    assert session2.owner_id == session1.owner_id


def test_session_creation_rejects_conflicting_reuse(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-conflict-1")

    # Conflicting reuse with different project
    with pytest.raises(AccessDenied):  # context is only authorized for launch-01
        create_session(fake_client, auth_context, "launch-other", "sess-conflict-1")


def test_message_validation_rejects_empty_content_and_invalid_role(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-val-1")

    # Reject whitespace-only content
    with pytest.raises(ValidationError):
        save_message(fake_client, auth_context, "launch-01", "sess-val-1", "msg-1", "user", "   ")

    # Reject invalid role
    with pytest.raises(ValidationError):
        save_message(fake_client, auth_context, "launch-01", "sess-val-1", "msg-1", "moderator", "Valid content")


def test_backend_assigns_sequence_numbers_monotonically(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-seq-1")

    m1 = save_message(fake_client, auth_context, "launch-01", "sess-seq-1", "msg-1", "user", "First")
    m2 = save_message(fake_client, auth_context, "launch-01", "sess-seq-1", "msg-2", "assistant", "Second")
    m3 = save_message(fake_client, auth_context, "launch-01", "sess-seq-1", "msg-3", "user", "Third")

    assert m1.seq == 1
    assert m2.seq == 2
    assert m3.seq == 3


def test_after_seq_pagination(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-page-1")

    for i in range(1, 6):
        save_message(fake_client, auth_context, "launch-01", "sess-page-1", f"msg-{i}", "user", f"Content {i}")

    # Page 1: first 2 messages
    page1 = load_messages(fake_client, auth_context, "launch-01", "sess-page-1", after_seq=0, limit=2)
    assert len(page1) == 2
    assert [m.seq for m in page1] == [1, 2]

    # Page 2: next 2 messages
    page2 = load_messages(fake_client, auth_context, "launch-01", "sess-page-1", after_seq=2, limit=2)
    assert len(page2) == 2
    assert [m.seq for m in page2] == [3, 4]

    # Page 3: last 1 message
    page3 = load_messages(fake_client, auth_context, "launch-01", "sess-page-1", after_seq=4, limit=2)
    assert len(page3) == 1
    assert [m.seq for m in page3] == [5]

    # Page 4: beyond end -> empty list
    page4 = load_messages(fake_client, auth_context, "launch-01", "sess-page-1", after_seq=5, limit=2)
    assert page4 == []


def test_load_messages_validates_arguments(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-args-1")

    with pytest.raises(ValueError, match="after_seq must be non-negative"):
        load_messages(fake_client, auth_context, "launch-01", "sess-args-1", after_seq=-1)

    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        load_messages(fake_client, auth_context, "launch-01", "sess-args-1", limit=0)

    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        load_messages(fake_client, auth_context, "launch-01", "sess-args-1", limit=101)


def test_idempotent_save_message_retry_preserves_seq_and_time(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-idem-1")

    orig = save_message(fake_client, auth_context, "launch-01", "sess-idem-1", "msg-fixed", "user", "Hello")
    retried = save_message(fake_client, auth_context, "launch-01", "sess-idem-1", "msg-fixed", "user", "Hello")

    assert orig.id == retried.id
    assert orig.seq == retried.seq
    assert orig.created_at == retried.created_at

    msgs = load_messages(fake_client, auth_context, "launch-01", "sess-idem-1")
    assert len(msgs) == 1


def test_conflicting_message_id_reuse_is_rejected(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-conf-1")

    save_message(fake_client, auth_context, "launch-01", "sess-conf-1", "msg-same-id", "user", "Hello")

    with pytest.raises(ConflictingMessageError):
        save_message(fake_client, auth_context, "launch-01", "sess-conf-1", "msg-same-id", "assistant", "Different")


def test_unauthorized_session_access_denied(fake_client, auth_context):
    # Session does not exist in graph -> AccessDenied
    with pytest.raises(AccessDenied):
        save_message(fake_client, auth_context, "launch-01", "uncreated-session", "msg-1", "user", "Hello")

    with pytest.raises(AccessDenied):
        load_messages(fake_client, auth_context, "launch-01", "uncreated-session")


def test_database_failure_does_not_report_success(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-fail-1")
    graph = fake_client.select_graph("relaymind_demo_a")
    graph.should_fail = True

    with pytest.raises(DatabaseOperationError):
        save_message(fake_client, auth_context, "launch-01", "sess-fail-1", "msg-1", "user", "Hello")

    with pytest.raises(DatabaseOperationError):
        load_messages(fake_client, auth_context, "launch-01", "sess-fail-1")
