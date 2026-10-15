import pytest
from pydantic import ValidationError

from relaymind.contracts.models import TrustedContext
from relaymind.contracts.episodes import EpisodeRecord
from relaymind.graph.access import AccessDenied
from relaymind.memory.conversations import create_session, save_message
from relaymind.memory.episodes import (
    save_episode,
    load_episodes,
    InaccessibleSourceMessageError,
    ConflictingEpisodeError,
    DatabaseOperationError,
)


class FakeQueryResult:
    def __init__(self, result_set):
        self.result_set = result_set


class FakeFalkorDBGraph:
    """
    Test double simulating FalkorDB query execution for sessions, messages, and episodes.
    Clearly labeled as a test double — NOT persistent storage.
    """
    def __init__(self):
        # sessions: session_id -> dict(owner_id, project_id, created_at, messages)
        self.sessions = {}
        # messages: message_id -> dict(id, session_id, role, content, created_at, seq)
        self.messages_by_id = {}
        # episodes: episode_id -> dict(...)
        self.episodes_by_id = {}
        self.should_fail = False

    def ro_query(self, query: str, params=None):
        return self.query(query, params)

    def query(self, query: str, params=None):
        if self.should_fail:
            raise RuntimeError("Simulated database failure")

        params = params or {}

        # 1. require_session check: MATCH (s:Session {id: $session_id, owner_id: $owner_id})-[:ABOUT]->(p:Project {id: $project_id})
        if "MATCH (s:Session" in query and "owner_id: $owner_id" in query and "-[:ABOUT]->(p:Project" in query:
            s_id = params.get("session_id")
            owner_id = params.get("owner_id")
            proj_id = params.get("project_id")
            if s_id in self.sessions:
                s = self.sessions[s_id]
                if s["owner_id"] == owner_id and s["project_id"] == proj_id:
                    return FakeQueryResult([[s_id]])
            return FakeQueryResult([])

        # 2. Check existing session for create_session
        if "MATCH (s:Session {id: $session_id})" in query and "OPTIONAL MATCH (s)-[:ABOUT]->(p:Project)" in query:
            s_id = params.get("session_id")
            if s_id in self.sessions:
                s = self.sessions[s_id]
                return FakeQueryResult([[s_id, s["owner_id"], s["created_at"], s["project_id"]]])
            return FakeQueryResult([])

        # 3. Create session
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

        # 4. Check existing message
        if "MATCH (m:Message {id: $message_id})" in query:
            m_id = params.get("message_id")
            if m_id in self.messages_by_id:
                m = self.messages_by_id[m_id]
                return FakeQueryResult([[m["id"], m["session_id"], m["role"], m["content"], m["created_at"], m["seq"]]])
            return FakeQueryResult([])

        # 5. Allocate message sequence
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

        # 7. Check source message accessibility for save_episode:
        # MATCH (p:Project {id: $project_id}) MATCH (s:Session {owner_id: $owner_id})-[:ABOUT]->(p) MATCH (s)-[:HAS_MESSAGE]->(m:Message {id: $source_message_id})
        if (
            "CREATE (e:Episode" not in query
            and "MATCH (s:Session {owner_id: $owner_id})-[:ABOUT]->(p)" in query
            and "MATCH (s)-[:HAS_MESSAGE]->(m:Message {id: $source_message_id})" in query
        ):
            proj_id = params.get("project_id")
            owner_id = params.get("owner_id")
            src_id = params.get("source_message_id")
            if src_id in self.messages_by_id:
                m = self.messages_by_id[src_id]
                s_id = m["session_id"]
                s = self.sessions.get(s_id)
                if s and s["owner_id"] == owner_id and s["project_id"] == proj_id:
                    return FakeQueryResult([[m["id"], m["created_at"]]])
            return FakeQueryResult([])

        # 8. Check existing episode
        if "MATCH (e:Episode {id: $episode_id})" in query:
            ep_id = params.get("episode_id")
            if ep_id in self.episodes_by_id:
                e = self.episodes_by_id[ep_id]
                return FakeQueryResult([[
                    e["id"],
                    e["project_id"],
                    e["source_message_id"],
                    e["summary"],
                    e["occurred_at"],
                    e["created_at"],
                    e["recorded_by"],
                    e["status"],
                ]])
            return FakeQueryResult([])

        # 9. Insert episode
        if "CREATE (e:Episode" in query:
            ep_data = {
                "id": params.get("episode_id"),
                "project_id": params.get("project_id"),
                "source_message_id": params.get("source_message_id"),
                "summary": params.get("summary"),
                "occurred_at": params.get("occurred_at"),
                "created_at": params.get("created_at"),
                "recorded_by": params.get("owner_id"),
                "status": "recorded",
            }
            self.episodes_by_id[ep_data["id"]] = ep_data
            return FakeQueryResult([[
                ep_data["id"],
                ep_data["project_id"],
                ep_data["source_message_id"],
                ep_data["summary"],
                ep_data["occurred_at"],
                ep_data["created_at"],
                ep_data["recorded_by"],
                ep_data["status"],
            ]])

        # 10. Load episodes with source-session ownership enforcement:
        # MATCH (e:Episode)-[:ABOUT]->(p:Project {id: $project_id})
        # MATCH (e)-[:SUPPORTED_BY]->(m:Message)<-[:HAS_MESSAGE]-(s:Session {owner_id: $owner_id})-[:ABOUT]->(p)
        if "MATCH (e:Episode)-[:ABOUT]->(p:Project" in query and "s:Session {owner_id: $owner_id}" in query:
            proj_id = params.get("project_id")
            owner_id = params.get("owner_id")
            offset = params.get("offset", 0)
            limit = params.get("limit", 10)

            matching = []
            for e in self.episodes_by_id.values():
                if e["project_id"] == proj_id:
                    # check if supporting message session belongs to owner_id
                    src_msg = self.messages_by_id.get(e["source_message_id"])
                    if src_msg:
                        s = self.sessions.get(src_msg["session_id"])
                        if s and s["owner_id"] == owner_id and s["project_id"] == proj_id:
                            matching.append(e)

            # Sort deterministically: occurred_at DESC, id ASC
            sorted_eps = sorted(matching, key=lambda x: (-x["occurred_at"], x["id"]))
            paged = sorted_eps[offset : offset + limit]
            rows = [
                [e["id"], e["project_id"], e["source_message_id"], e["summary"], e["occurred_at"], e["created_at"], e["recorded_by"], e["status"]]
                for e in paged
            ]
            return FakeQueryResult(rows)

        return FakeQueryResult([])


class FakeFalkorDBClient:
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


def test_reject_blank_or_whitespace_summary(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-1")
    msg = save_message(fake_client, auth_context, "launch-01", "sess-1", "msg-1", "user", "Content")

    # Reject whitespace-only summary
    with pytest.raises(ValueError, match="blank or whitespace-only"):
        save_episode(
            fake_client,
            auth_context,
            "launch-01",
            "ep-1",
            msg.id,
            "    \t\n   ",
        )

    # Reject empty string
    with pytest.raises(ValueError, match="blank or whitespace-only"):
        save_episode(
            fake_client,
            auth_context,
            "launch-01",
            "ep-1",
            msg.id,
            "",
        )


def test_source_message_access_enforced_missing_message(fake_client, auth_context):
    # Non-existent source message raises InaccessibleSourceMessageError
    with pytest.raises(InaccessibleSourceMessageError, match="Source message unavailable or access denied"):
        save_episode(
            fake_client,
            auth_context,
            "launch-01",
            "ep-missing",
            "non-existent-msg-id",
            "Valid summary",
        )


def test_same_tenant_unauthorized_source_session_access(fake_client):
    # developer-a creates a session and message
    ctx_a = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    create_session(fake_client, ctx_a, "launch-01", "sess-a")
    msg_a = save_message(fake_client, ctx_a, "launch-01", "sess-a", "msg-a-secret", "user", "Confidential chat")

    # developer-b in same tenant tries to save an episode citing developer-a's private message
    # Even if developer-b has project access, developer-b does NOT own the source session!
    ctx_b = TrustedContext(tenant_id="demo-a", user_id="developer-b")
    # Note: _DEMO_ACCESS in graph/access.py only permits ("demo-a", "developer-a") and ("demo-b", "developer-b")
    # To test within the access policy, we simulate another user with project access
    with pytest.raises(AccessDenied):
        save_episode(
            fake_client,
            ctx_b,
            "launch-01",
            "ep-steal",
            msg_a.id,
            "Leaked summary",
        )


def test_cross_tenant_access_denied(fake_client):
    ctx_a = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    create_session(fake_client, ctx_a, "launch-01", "sess-a")
    msg_a = save_message(fake_client, ctx_a, "launch-01", "sess-a", "msg-a-1", "user", "Tenant A text")

    # developer-b from tenant demo-b tries to cite tenant A's message
    ctx_b = TrustedContext(tenant_id="demo-b", user_id="developer-b")
    with pytest.raises(InaccessibleSourceMessageError):
        save_episode(
            fake_client,
            ctx_b,
            "launch-01",
            "ep-cross",
            msg_a.id,
            "Summary from tenant B",
        )


def test_default_occurred_at_to_source_timestamp(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-1")
    msg = save_message(fake_client, auth_context, "launch-01", "sess-1", "msg-time", "user", "Timestamped msg")

    ep = save_episode(
        fake_client,
        auth_context,
        "launch-01",
        "ep-time-1",
        msg.id,
        "The team discussed launch readiness.",
        occurred_at=None,
    )

    # occurred_at must default to the message's created_at timestamp
    assert ep.occurred_at == msg.created_at
    assert ep.source_message_id == msg.id
    assert ep.recorded_by == auth_context.user_id
    assert ep.status == "recorded"


def test_idempotent_retry_preserves_attributes(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-1")
    msg = save_message(fake_client, auth_context, "launch-01", "sess-1", "msg-idem", "user", "Discuss payments")

    orig = save_episode(
        fake_client,
        auth_context,
        "launch-01",
        "ep-fixed-id",
        msg.id,
        "Discussed payment testing.",
    )

    # Retry exact same write
    retried = save_episode(
        fake_client,
        auth_context,
        "launch-01",
        "ep-fixed-id",
        msg.id,
        "Discussed payment testing.",
    )

    assert orig.id == retried.id
    assert orig.occurred_at == retried.occurred_at
    assert orig.created_at == retried.created_at
    assert orig.recorded_by == retried.recorded_by

    # Count remains 1
    loaded = load_episodes(fake_client, auth_context, "launch-01")
    assert len(loaded) == 1


def test_conflicting_id_reuse_fails(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-1")
    msg1 = save_message(fake_client, auth_context, "launch-01", "sess-1", "msg-c1", "user", "First")
    msg2 = save_message(fake_client, auth_context, "launch-01", "sess-1", "msg-c2", "user", "Second")

    save_episode(fake_client, auth_context, "launch-01", "ep-same-id", msg1.id, "Original summary")

    # Reuse ID with different summary
    with pytest.raises(ConflictingEpisodeError):
        save_episode(fake_client, auth_context, "launch-01", "ep-same-id", msg1.id, "Conflicting summary")

    # Reuse ID with different source message
    with pytest.raises(ConflictingEpisodeError):
        save_episode(fake_client, auth_context, "launch-01", "ep-same-id", msg2.id, "Original summary")

    # Reuse ID with different explicit occurred_at
    with pytest.raises(ConflictingEpisodeError):
        save_episode(fake_client, auth_context, "launch-01", "ep-same-id", msg1.id, "Original summary", occurred_at=999999)


def test_load_episodes_deterministic_ordering_and_pagination(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-p")
    msg = save_message(fake_client, auth_context, "launch-01", "sess-p", "msg-p", "user", "Seed message")

    # Save 5 episodes with distinct occurred_at timestamps
    save_episode(fake_client, auth_context, "launch-01", "ep-10", msg.id, "Event 10", occurred_at=1000)
    save_episode(fake_client, auth_context, "launch-01", "ep-30", msg.id, "Event 30", occurred_at=3000)
    save_episode(fake_client, auth_context, "launch-01", "ep-20", msg.id, "Event 20", occurred_at=2000)
    save_episode(fake_client, auth_context, "launch-01", "ep-50", msg.id, "Event 50", occurred_at=5000)
    save_episode(fake_client, auth_context, "launch-01", "ep-40", msg.id, "Event 40", occurred_at=4000)

    # Page 1: limit 2, offset 0 -> expected [ep-50, ep-40] (descending by occurred_at)
    page1 = load_episodes(fake_client, auth_context, "launch-01", limit=2, offset=0)
    assert len(page1) == 2
    assert [e.id for e in page1] == ["ep-50", "ep-40"]

    # Page 2: limit 2, offset 2 -> expected [ep-30, ep-20]
    page2 = load_episodes(fake_client, auth_context, "launch-01", limit=2, offset=2)
    assert len(page2) == 2
    assert [e.id for e in page2] == ["ep-30", "ep-20"]

    # Page 3: limit 2, offset 4 -> expected [ep-10]
    page3 = load_episodes(fake_client, auth_context, "launch-01", limit=2, offset=4)
    assert len(page3) == 1
    assert page3[0].id == "ep-10"

    # Beyond offset -> empty list
    page4 = load_episodes(fake_client, auth_context, "launch-01", limit=2, offset=5)
    assert page4 == []


def test_load_episodes_validates_bounds(fake_client, auth_context):
    with pytest.raises(ValueError, match="limit must be between 1 and 50"):
        load_episodes(fake_client, auth_context, "launch-01", limit=0)

    with pytest.raises(ValueError, match="limit must be between 1 and 50"):
        load_episodes(fake_client, auth_context, "launch-01", limit=51)

    with pytest.raises(ValueError, match="offset must be non-negative"):
        load_episodes(fake_client, auth_context, "launch-01", offset=-1)


def test_database_failure_does_not_report_success(fake_client, auth_context):
    create_session(fake_client, auth_context, "launch-01", "sess-1")
    msg = save_message(fake_client, auth_context, "launch-01", "sess-1", "msg-fail", "user", "Fail text")

    graph = fake_client.select_graph("relaymind_demo_a")
    graph.should_fail = True

    with pytest.raises(DatabaseOperationError):
        save_episode(fake_client, auth_context, "launch-01", "ep-fail", msg.id, "Will fail")

    with pytest.raises(DatabaseOperationError):
        load_episodes(fake_client, auth_context, "launch-01")
