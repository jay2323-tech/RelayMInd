import os
import subprocess
import sys
import uuid
import pytest
from dotenv import load_dotenv

from relaymind.graph.connection import create_client
from relaymind.graph.access import AccessDenied
from relaymind.contracts.models import TrustedContext
from relaymind.memory.conversations import create_session, save_message
from relaymind.memory.episodes import (
    save_episode,
    load_episodes,
    InaccessibleSourceMessageError,
    ConflictingEpisodeError,
)

load_dotenv()

# Live FalkorDB tests are explicitly opt-in.
# To run: set RUN_LIVE_FALKORDB_TESTS=1 in environment.
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_FALKORDB_TESTS") not in ("1", "true", "TRUE"),
    reason="Live FalkorDB tests are explicitly opt-in. Set RUN_LIVE_FALKORDB_TESTS=1 to run.",
)


@pytest.fixture
def real_db_fixture():
    """
    Creates an isolated test session and supporting message in FalkorDB.
    Teardown deletes ONLY this specific session, its messages, and linked test episodes.
    Never deletes shared demo graphs.
    """
    client = create_client()
    context = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    project_id = "launch-01"
    session_id = f"test-sess-{uuid.uuid4()}"
    msg_id = f"test-msg-{uuid.uuid4()}"
    created_episode_ids = []

    create_session(client, context, project_id, session_id)
    msg = save_message(client, context, project_id, session_id, msg_id, "user", "Discussed launch with payment tests.")

    yield client, context, project_id, session_id, msg, created_episode_ids

    # Narrow cleanup: only clean nodes created for this test session
    from relaymind.graph.access import authorized_graph
    try:
        graph = authorized_graph(client, context, project_id)
        # Delete specific test episodes
        for ep_id in created_episode_ids:
            graph.query("MATCH (e:Episode {id: $id}) DETACH DELETE e", params={"id": ep_id})
        # Delete test session and its messages
        graph.query(
            "MATCH (s:Session {id: $session_id}) "
            "OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m:Message) "
            "DETACH DELETE s, m",
            params={"session_id": session_id},
        )
    except Exception:
        pass


def test_real_falkordb_save_and_retrieve_episode(real_db_fixture):
    client, context, project_id, session_id, msg, created_episodes = real_db_fixture

    ep_id = f"ep-{uuid.uuid4()}"
    created_episodes.append(ep_id)

    # 1. Save episode linked to message without explicit occurred_at
    ep = save_episode(
        client=client,
        context=context,
        project_id=project_id,
        episode_id=ep_id,
        source_message_id=msg.id,
        summary="The team agreed on payment testing for Friday launch.",
    )

    assert ep.id == ep_id
    assert ep.project_id == project_id
    assert ep.source_message_id == msg.id
    assert ep.summary == "The team agreed on payment testing for Friday launch."
    # Default occurred_at should match the message's timestamp
    assert ep.occurred_at == msg.created_at
    assert ep.recorded_by == context.user_id
    assert ep.status == "recorded"

    # 2. Retrieve episode and verify fields
    loaded = load_episodes(client, context, project_id, limit=10, offset=0)
    matching = [e for e in loaded if e.id == ep_id]
    assert len(matching) == 1
    found = matching[0]
    assert found.id == ep_id
    assert found.source_message_id == msg.id
    assert found.occurred_at == msg.created_at
    assert found.summary == "The team agreed on payment testing for Friday launch."

    # 3. Idempotent retry preserves original attributes
    retried = save_episode(
        client=client,
        context=context,
        project_id=project_id,
        episode_id=ep_id,
        source_message_id=msg.id,
        summary="The team agreed on payment testing for Friday launch.",
    )
    assert retried.id == ep.id
    assert retried.created_at == ep.created_at
    assert retried.occurred_at == ep.occurred_at

    # 4. Conflicting reuse with different summary fails
    with pytest.raises(ConflictingEpisodeError):
        save_episode(
            client=client,
            context=context,
            project_id=project_id,
            episode_id=ep_id,
            source_message_id=msg.id,
            summary="Different conflicting summary",
        )

    # 5. Non-existent source message is rejected
    with pytest.raises(InaccessibleSourceMessageError):
        save_episode(
            client=client,
            context=context,
            project_id=project_id,
            episode_id=f"ep-fake-{uuid.uuid4()}",
            source_message_id="non-existent-msg-id-123",
            summary="Fake source summary",
        )

    # 6. Cross-tenant access denied: tenant B cannot cite tenant A's message
    context_b = TrustedContext(tenant_id="demo-b", user_id="developer-b")
    with pytest.raises(InaccessibleSourceMessageError):
        save_episode(
            client=client,
            context=context_b,
            project_id=project_id,
            episode_id=f"ep-b-{uuid.uuid4()}",
            source_message_id=msg.id,
            summary="Tenant B attempting to cite tenant A message",
        )

    # 7. Verification in a FRESH, separate Python process
    # Proves persistence across Python backend process restarts
    verify_script = f"""
import sys
from relaymind.graph.connection import create_client
from relaymind.contracts.models import TrustedContext
from relaymind.memory.episodes import load_episodes

c = create_client()
ctx = TrustedContext(tenant_id='demo-a', user_id='developer-a')
eps = load_episodes(c, ctx, '{project_id}', limit=50)
matching = [e for e in eps if e.id == '{ep_id}']
assert len(matching) == 1, f'Expected 1 matching episode, got {{len(matching)}}'
assert matching[0].source_message_id == '{msg.id}'
assert matching[0].summary == 'The team agreed on payment testing for Friday launch.'
assert matching[0].occurred_at == {msg.created_at}
assert matching[0].recorded_by == '{context.user_id}'
assert matching[0].status == 'recorded'
print('SUCCESS_EPISODE_FRESH_PROCESS')
"""
    result = subprocess.run(
        [sys.executable, "-c", verify_script],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "SUCCESS_EPISODE_FRESH_PROCESS" in result.stdout
