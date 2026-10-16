from concurrent.futures import ThreadPoolExecutor
import pytest
from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.memory.conversations import create_session,save_message
from relaymind.memory.episodes import save_episode,load_episodes,InaccessibleSourceMessageError
from test_episodes import FakeFalkorDBClient


def test_authorized_peer_cannot_read_or_cite_private_source(monkeypatch):
    # Both users pass project access; this exercises source-session authorization.
    monkeypatch.setitem(access._DEMO_ACCESS,('demo-a','peer'),('relaymind_demo_a',frozenset({'launch-01'})))
    client=FakeFalkorDBClient()
    a=TrustedContext(tenant_id='demo-a',user_id='developer-a')
    b=TrustedContext(tenant_id='demo-a',user_id='peer')
    create_session(client,a,'launch-01','private-session')
    save_message(client,a,'launch-01','private-session','private-message','user','Private')
    save_episode(client,a,'launch-01','private-episode','private-message','History')
    with pytest.raises(InaccessibleSourceMessageError):
        save_episode(client,b,'launch-01','stolen-episode','private-message','History')
    assert load_episodes(client,b,'launch-01')==[]


def test_parallel_identical_episode_retry_is_serialized():
    client=FakeFalkorDBClient()
    ctx=TrustedContext(tenant_id='demo-a',user_id='developer-a')
    create_session(client,ctx,'launch-01','s')
    save_message(client,ctx,'launch-01','s','m','user','Event')
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda _:save_episode(client,ctx,'launch-01','one-episode','m','History'),range(20)))
    assert len({(e.id,e.created_at) for e in results})==1
    assert len(load_episodes(client,ctx,'launch-01'))==1
