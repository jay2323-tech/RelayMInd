"""Review-only reproductions for PR27 7253212; expected failures until fixed.
Run against that checkout with its backend/src and backend/tests on PYTHONPATH,
RUN_LIVE_FALKORDB_TESTS=1 and local FalkorDB credentials loaded. Uses throwaway
projects and scripted providers; never modifies demo decisions.
"""
from test_watcher_real_db import world, login, start, alerts, supersede, NS
from relaymind.assistant import watcher
from relaymind.memory.tasks import record_task


def test_further_action_basis_change_creates_new_alert(world):
    pid, client = world
    record_task(client, NS, pid, f'{pid}-task', 'Prepare pricing', 'todo', None, [f'{pid}-dec'], [])
    c = login('northstar.lead')
    c.post(f'/api/projects/{pid}/actions', json={'task_id':f'{pid}-task','new_status':'paused','reason':'Review','based_on':[f'{pid}-dec']})
    supersede(client,pid,f'{pid}-dec2',f'{pid}-dec','Second scope')
    [first] = alerts(c,pid)
    c.post(f"/api/projects/{pid}/alerts/{first['id']}/ack")
    supersede(client,pid,f'{pid}-dec3',f'{pid}-dec2','Third scope')
    rows = alerts(c,pid)
    assert len(rows) == 2, rows
    assert {a['status'] for a in rows} == {'open','resolved'}


def test_lookup_failure_does_not_resolve_known_staleness(world,monkeypatch):
    pid, client = world
    c=login('northstar.lead')
    sid=c.post(f'/api/projects/{pid}/sessions').json()['id']
    start(c,pid,sid,mode='plan_then_pause')
    supersede(client,pid,f'{pid}-dec2',f'{pid}-dec','Second scope')
    [first]=alerts(c,pid)
    def unavailable(*args,**kwargs):
        raise ConnectionError('temporary lookup failure')
    monkeypatch.setattr(watcher,'_engine',unavailable)
    rows=alerts(c,pid)
    assert rows[0]['status']=='open', rows


def test_watcher_capability_is_advertised(world):
    pid, client = world
    c = login('northstar.lead')
    response = c.get(f'/api/projects/{pid}/workflow/capabilities')
    assert response.status_code == 200
    assert response.json().get('watcher') is True, response.json()
