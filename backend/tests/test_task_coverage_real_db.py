"""Coverage gate on Claude's real graph bridge; model is explicitly scripted."""
import os
import pytest
from relaymind.agents.engine import CoordinationEngine
from relaymind.platform.bridge import GraphPlatformBridge
from test_agent_loop import ScriptedModel
from test_platform_bridge_real_db import world,CTX,_plan

pytestmark=pytest.mark.skipif(os.getenv('RUN_LIVE_FALKORDB_TESTS')!='1',reason='Opt-in real DB')


def test_graph_bridge_discovers_both_affected_task_ids(world):
    client,pid,sid,n=world
    required=GraphPlatformBridge(client).required_tasks(CTX,pid)
    assert [task['task_id'] for task in required]==[n('t1'),n('t2')]
    assert all(task['superseded_decision_ids']==[n('d1')] for task in required)


def test_missing_task_is_rejected_without_calling_reviewer_model(world):
    client,pid,sid,n=world
    bridge=GraphPlatformBridge(client)
    response=_plan(n)
    response['final']['steps'][0]['task_ids']=[n('t1')]
    # Merely naming another task in text does not satisfy structured coverage.
    response['final']['steps'][0]['task']='Pause '+n('t1')+' and '+n('t2')
    planner=CoordinationEngine(client,CTX,pid,sid,ScriptedModel([response]),bridge)
    run=planner.plan_run('Review launch',run_id=pid+'-coverage',procedure_id=pid+'-review')
    assert run.status=='awaiting_review',run.error
    model=ScriptedModel([])
    reviewer=CoordinationEngine(client,CTX,pid,sid,model,bridge)
    review=reviewer.review_handoff(run.handoff_ids[0])
    assert review.review.status=='needs_revision'
    assert review.review.issues[0].evidence_ids==[n('t2')]
    assert not model.inputs


def test_structured_task_ids_recover_supporting_evidence(world):
    client,pid,sid,n=world
    response=_plan(n)
    response['final']['steps'][0]['evidence_ids']=[n('d2')]
    run=CoordinationEngine(client,CTX,pid,sid,ScriptedModel([response]),GraphPlatformBridge(client)).plan_run(
        'Review launch',run_id=pid+'-bad-evidence',procedure_id=pid+'-review')
    assert run.status=='awaiting_review',run.error


def test_correction_can_cover_missing_tasks_and_finish(world):
    client,pid,sid,n=world
    incomplete=_plan(n)
    incomplete['final']['steps'][0]['task_ids']=[]
    accepted={'final':{'status':'accepted','issues':[]}}
    corrected=_plan(n)
    corrected['final']['steps'][0]['evidence_ids']=[n('d2')]
    engine=CoordinationEngine(client,CTX,pid,sid,ScriptedModel([incomplete,corrected,accepted]),GraphPlatformBridge(client))
    run=engine.run('Review launch',run_id=pid+'-fixed-coverage',procedure_id=pid+'-review')
    assert run.status=='completed',run.error
    assert len(run.handoff_ids)==2
    assert engine.store.get('review',run.handoff_ids[0])['review']['status']=='needs_revision'
