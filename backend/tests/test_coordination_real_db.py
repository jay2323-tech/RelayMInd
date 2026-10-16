"""Real FalkorDB, scripted model/decision bridge. NOT live LLM verification."""
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.contracts.coordination import DecisionReference,EvidenceRecord
from relaymind.memory.conversations import create_session,save_message
from relaymind.memory.episodes import save_episode
from relaymind.memory.procedures import approve_procedure,get_procedure
from relaymind.memory.artifacts import ArtifactStore,ArtifactConflict
from relaymind.graph.connection import create_client
from relaymind.graph.access import authorized_graph,AccessDenied
from relaymind.agents.engine import CoordinationEngine
from test_agent_loop import ScriptedModel,final_plan

load_dotenv()
pytestmark=pytest.mark.skipif(os.getenv('RUN_LIVE_FALKORDB_TESTS')!='1',reason='Opt-in live FalkorDB tests')


class FixturePlatform:
    """Explicit fixture until Claude's real decision tools are connected."""
    def __init__(self):
        self.current=[DecisionReference(id='decision-02',version=1,topic='launch-scope',
                         text='Launch free tier only; postpone payments',source_id='fixture-source')]
    def current_decisions(self,context,project_id): return self.current
    def evidence(self,context,project_id,evidence_id):
        match=next((d for d in self.current if d.id==evidence_id),None)
        if match is None: raise AccessDenied('Evidence unavailable')
        return EvidenceRecord(id=match.id,text=match.text,source_id=match.source_id)
    def dependencies(self,context,project_id,task_id): return []


@pytest.fixture
def scope():
    client=create_client()
    ctx=TrustedContext(tenant_id='demo-a',user_id='developer-a')
    tag='agent-test-'+str(uuid4())
    sid=tag+'-session'
    create_session(client,ctx,'launch-01',sid)
    procedure=approve_procedure(client,ctx,'launch-01',tag,1,'Launch review',
        ['Check approved scope','Reject unsupported steps'],'Synthetic test setup',human_approved=True)
    yield client,ctx,tag,sid,procedure
    graph=authorized_graph(client,ctx,'launch-01')
    # Delete only UUID-scoped artifacts created by this fixture, no graph resets.
    graph.query("MATCH (a:AgentArtifact {session_id:$sid}) OPTIONAL MATCH (a)-[:HAS_SNAPSHOT]->(v:AgentRunSnapshot) DETACH DELETE a,v",params={'sid':sid})
    graph.query("MATCH (p:Procedure {id:$id}) DETACH DELETE p",params={'id':tag})
    graph.query("MATCH (s:Session {id:$sid}) OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m:Message) OPTIONAL MATCH (e:Episode)-[:SUPPORTED_BY]->(m) DETACH DELETE e,m,s",params={'sid':sid})


def make_engine(scope,replies,bridge=None):
    client,ctx,tag,sid,_=scope
    return CoordinationEngine(client,ctx,'launch-01',sid,ScriptedModel(replies),bridge or FixturePlatform())


def test_real_store_handoff_recovery_and_review(scope):
    client,ctx,tag,sid,proc=scope
    e=make_engine(scope,[final_plan()])
    run=e.plan_run('Continue launch',run_id=tag,procedure_id=tag)
    assert run.status=='awaiting_review',run.error
    # New engine instance receives no Planner chat state.
    reviewer=make_engine(scope,[{'final':{'status':'accepted','issues':[]}}])
    reviewed=reviewer.continue_run(tag)
    assert reviewed.status=='completed',reviewed.error
    assert reviewed.result.procedure_version==1
    assert reviewer.review_handoff(tag+'-r1')==reviewed.result
    # Independent Python process verifies actual persisted handoff/review records.
    code=f"""
from relaymind.graph.connection import create_client
from relaymind.contracts.models import TrustedContext
from relaymind.memory.artifacts import ArtifactStore
s=ArtifactStore(create_client(),TrustedContext(tenant_id='demo-a',user_id='developer-a'),'launch-01',{sid!r})
assert s.get('handoff',{(tag+'-r1')!r})['plan']['decision_ids']==['decision-02']
assert s.get('review',{(tag+'-r1')!r})['review']['status']=='accepted'
print('RECOVERED')
"""
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=20,check=True)
    assert 'RECOVERED' in result.stdout


def test_one_correction_round_then_stop(scope):
    _,_,tag,_,_=scope
    reject={'final':{'status':'needs_revision','issues':[{'reason':'Clarify plan','evidence_ids':['decision-02']}]}}
    engine=make_engine(scope,[final_plan(),reject,final_plan(),reject])
    run=engine.run('Continue launch',run_id=tag,procedure_id=tag)
    assert run.status=='needs_revision',run.error
    assert len(run.handoff_ids)==2


def test_changed_decision_rejects_stale_plan_without_model(scope):
    _,_,tag,_,_=scope
    bridge=FixturePlatform()
    engine=make_engine(scope,[final_plan()],bridge)
    run=engine.plan_run('Continue launch',run_id=tag,procedure_id=tag)
    bridge.current=[DecisionReference(id='decision-03',version=2,topic='launch-scope',text='Postpone launch',source_id='new-source')]
    # No model replies available: stale decision rejection must be deterministic.
    fresh=make_engine(scope,[],bridge)
    review=fresh.review_handoff(run.handoff_ids[0])
    assert review.review.status=='needs_revision'


def test_procedure_version_is_immutable(scope):
    client,ctx,tag,sid,proc=scope
    updated=approve_procedure(client,ctx,'launch-01',tag,2,'Launch review',
        ['Check updated scope'],'Setup v2',human_approved=True)
    assert get_procedure(client,ctx,'launch-01',tag).version==2
    assert get_procedure(client,ctx,'launch-01',tag,1).steps==proc.steps
    with pytest.raises(ValueError):
        approve_procedure(client,ctx,'launch-01',tag,1,'Changed',['Different'],'Setup',human_approved=True)


def test_parallel_handoff_claim_has_one_winner(scope):
    client,ctx,tag,sid,_=scope
    engine=make_engine(scope,[final_plan()])
    run=engine.plan_run('Continue launch',run_id=tag,procedure_id=tag)
    store=engine.store
    def claim(_):
        try:return store.claim(run.handoff_ids[0])
        except ArtifactConflict:return None
    with ThreadPoolExecutor(max_workers=5) as pool:
        winners=[token for token in pool.map(claim,range(5)) if token]
    assert len(winners)==1
    store.release(run.handoff_ids[0],winners[0])


def test_unknown_evidence_blocks_plan(scope):
    _,_,tag,_,_=scope
    response=final_plan()
    response['final']['steps'][0]['evidence_ids']=['invented']
    run=make_engine(scope,[response]).plan_run('Continue launch',run_id=tag,procedure_id=tag)
    assert run.status=='blocked'


def test_sourced_episode_parallel_retry_against_real_db(scope):
    client,ctx,tag,sid,_=scope
    msg=save_message(client,ctx,'launch-01',sid,tag+'-msg','user','Launch discussion')
    with ThreadPoolExecutor(max_workers=5) as pool:
        episodes=list(pool.map(lambda _:save_episode(client,ctx,'launch-01',tag+'-episode',msg.id,'Historical discussion'),range(10)))
    assert len({(e.id,e.created_at) for e in episodes})==1
    graph=authorized_graph(client,ctx,'launch-01')
    assert graph.ro_query('MATCH (e:Episode {id:$id}) RETURN count(e)',params={'id':tag+'-episode'}).result_set==[[1]]


def test_independent_process_claims_have_one_winner(scope):
    client,ctx,tag,sid,_=scope
    engine=make_engine(scope,[final_plan()])
    run=engine.plan_run('Continue launch',run_id=tag,procedure_id=tag)
    code=f"""
from relaymind.graph.connection import create_client
from relaymind.contracts.models import TrustedContext
from relaymind.memory.artifacts import ArtifactStore,ArtifactConflict
store=ArtifactStore(create_client(),TrustedContext(tenant_id='demo-a',user_id='developer-a'),'launch-01',{sid!r})
try:
 print('WIN:'+store.claim({run.handoff_ids[0]!r}))
except ArtifactConflict:
 print('NO_CLAIM')
"""
    def invoke(_):
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True,timeout=20)
        return result.stdout.strip()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(invoke,range(3)))
    assert sum(x.startswith('WIN:') for x in results)==1


def test_foreign_session_cannot_read_artifacts(scope):
    client,ctx,tag,sid,_=scope
    run=make_engine(scope,[final_plan()]).plan_run('Continue launch',run_id=tag,procedure_id=tag)
    other=TrustedContext(tenant_id='demo-b',user_id='developer-b')
    with pytest.raises(AccessDenied):
        ArtifactStore(client,other,'launch-01',sid)
