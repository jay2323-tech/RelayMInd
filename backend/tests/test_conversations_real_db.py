import os
import subprocess
import sys
import uuid
import pytest
from dotenv import load_dotenv

from relaymind.graph.connection import create_client
from relaymind.graph.access import AccessDenied
from relaymind.contracts.models import TrustedContext
from relaymind.memory.conversations import (
    create_session,
    save_message,
    load_messages,
    ConflictingMessageError,
    ConflictingSessionError,
)

load_dotenv()

# Live FalkorDB tests are explicitly opt-in.
# To run: set RUN_LIVE_FALKORDB_TESTS=1 in environment.
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_FALKORDB_TESTS") not in ("1", "true", "TRUE"),
    reason="Live FalkorDB tests are explicitly opt-in. Set RUN_LIVE_FALKORDB_TESTS=1 to run.",
)


@pytest.fixture
def test_session():
    """
    Provides a uniquely identified test session and cleans up ONLY this test session
    and its linked messages upon completion. Does NOT delete shared demo graphs or data.
    """
    client = create_client()
    context = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    project_id = "launch-01"
    session_id = f"test-sess-{uuid.uuid4()}"

    session = create_session(client, context, project_id, session_id)

    yield client, context, project_id, session_id, session

    # Narrowly-scoped cleanup: delete only this test session and its messages
    from relaymind.graph.access import authorized_graph
    try:
        graph = authorized_graph(client, context, project_id)
        graph.query(
            "MATCH (s:Session {id: $session_id}) "
            "OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m:Message) "
            "DETACH DELETE s, m",
            params={"session_id": session_id},
        )
    except Exception:
        pass


def test_real_falkordb_session_retry_and_conflict(test_session):
    client, context, project_id, session_id, original_session = test_session

    # Idempotent retry preserves created_at and owner_id
    retried_session = create_session(client, context, project_id, session_id)
    assert retried_session.id == original_session.id
    assert retried_session.created_at == original_session.created_at
    assert retried_session.owner_id == original_session.owner_id

    # Conflicting reuse with different project
    with pytest.raises(AccessDenied):
        create_session(client, context, "launch-unauthorized", session_id)


def test_real_falkordb_two_messages_persistence_and_order(test_session):
    client, context, project_id, session_id, _ = test_session

    msg1_id = f"msg-{uuid.uuid4()}"
    msg2_id = f"msg-{uuid.uuid4()}"

    # Backend assigns sequence numbers monotonically
    saved_msg1 = save_message(
        client=client,
        context=context,
        project_id=project_id,
        session_id=session_id,
        message_id=msg1_id,
        role="user",
        content="Let's review the launch plan.",
    )
    saved_msg2 = save_message(
        client=client,
        context=context,
        project_id=project_id,
        session_id=session_id,
        message_id=msg2_id,
        role="assistant",
        content="I have reviewed the plan. Free tier is scheduled for Friday.",
    )

    assert saved_msg1.seq == 1
    assert saved_msg2.seq == 2

    # Load messages and verify ordering
    loaded = load_messages(client, context, project_id, session_id)
    assert len(loaded) == 2
    assert loaded[0].id == msg1_id
    assert loaded[0].seq == 1
    assert loaded[0].content == "Let's review the launch plan."
    assert loaded[1].id == msg2_id
    assert loaded[1].seq == 2
    assert loaded[1].content == "I have reviewed the plan. Free tier is scheduled for Friday."

    # Test after_seq pagination: after_seq=1 returns only msg2
    page = load_messages(client, context, project_id, session_id, after_seq=1, limit=10)
    assert len(page) == 1
    assert page[0].id == msg2_id
    assert page[0].seq == 2

    # Test idempotent retry: retrying msg1 produces no duplicate and preserves seq/created_at
    retry_msg1 = save_message(
        client=client,
        context=context,
        project_id=project_id,
        session_id=session_id,
        message_id=msg1_id,
        role="user",
        content="Let's review the launch plan.",
    )
    assert retry_msg1.id == msg1_id
    assert retry_msg1.seq == 1
    assert retry_msg1.created_at == saved_msg1.created_at

    # Total count remains 2
    all_msgs = load_messages(client, context, project_id, session_id)
    assert len(all_msgs) == 2

    # Conflicting reuse of msg1_id with different content fails
    with pytest.raises(ConflictingMessageError):
        save_message(
            client=client,
            context=context,
            project_id=project_id,
            session_id=session_id,
            message_id=msg1_id,
            role="user",
            content="Conflicting new text",
        )

    # Unauthorized access: tenant-b context is rejected
    context_b = TrustedContext(tenant_id="demo-b", user_id="developer-b")
    with pytest.raises(AccessDenied):
        load_messages(client, context_b, project_id, session_id)

    # Verification in a FRESH, separate Python process
    # Demonstrates persistent retrieval across process boundary
    verify_script = f"""
import sys
from relaymind.graph.connection import create_client
from relaymind.contracts.models import TrustedContext
from relaymind.memory.conversations import load_messages

c = create_client()
ctx = TrustedContext(tenant_id='demo-a', user_id='developer-a')
msgs = load_messages(c, ctx, '{project_id}', '{session_id}')
assert len(msgs) == 2, f'Expected 2 messages, got {{len(msgs)}}'
assert msgs[0].id == '{msg1_id}'
assert msgs[1].id == '{msg2_id}'
assert msgs[0].seq == 1
assert msgs[1].seq == 2
print('SUCCESS_FRESH_PROCESS')
"""
    result = subprocess.run(
        [sys.executable, "-c", verify_script],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "SUCCESS_FRESH_PROCESS" in result.stdout
