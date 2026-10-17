"""Graph-derived coverage and reviewer task semantics; scripted model, real DB."""
import copy
import json
import os
import pytest
from relaymind.platform.aw_incident import load_incident
from test_manufacturing_real_db import world, AW
from test_manufacturing_agents_real_db import engine, PLAN
from test_agent_loop import ScriptedModel

pytestmark=pytest.mark.skipif(os.getenv('RUN_LIVE_FALKORDB_TESTS')!='1',reason='Opt-in live database')


@pytest.mark.parametrize('orders,missing',[
    ([],['AW-O101','AW-O102']),
    (['AW-O101'],['AW-O102']),
    (['aw-src-trace'],['AW-O101','AW-O102']),
])
def test_missing_orders_rejected_before_any_reviewer_model(world,orders,missing):
    plan=copy.deepcopy(PLAN)
    plan['final']['steps'][0]['evidence_ids']=['aw-src-hold-v1']+orders
    model=ScriptedModel([plan])  # No Reviewer response supplied.
    e=engine(world,model)
    run=e.plan_run('Investigate hold',procedure_id='quality-hold-review')
    assert run.status=='awaiting_review',run.error
    review=e.review_handoff(run.handoff_ids[0])
    assert review.review.status=='needs_revision'
    assert review.review.issues[0].evidence_ids==missing
    assert len(model.inputs)==1


def revised_plan(orders):
    return {'final':{'summary':'Revise inherited incident work under hold v2',
        'decision_ids':['aw-dec-hold-v2'],
        'steps':[{'task':'Continue QA quarantine of B101 and pause the inherited O103 shipment under hold v2. '
            'Hold open exposed orders and request QA exposure review for shipped units; human approval required.',
            'task_ids':['aw-task-quarantine-b101','aw-task-ship-o103'],
            'evidence_ids':['aw-dec-hold-v2','aw-task-quarantine-b101','aw-task-ship-o103']+orders}],
        'uncertainties':['QA disposition and named assignees remain unapproved']}}


def test_after_change_coverage_is_recomputed_and_tasks_are_reviewed_as_revised_work(world):
    model=ScriptedModel([revised_plan(['AW-O101','AW-O102','AW-O103']),
                         {'final':{'status':'accepted','issues':[]}}])
    e=engine(world,model)
    load_incident(world[0],AW,world[2],'after-change')
    required=e.required_orders(e.decisions())
    assert [r['order_id'] for r in required]==['AW-O101','AW-O102','AW-O103']
    assert next(r for r in required if r['order_id']=='AW-O102')['exposure']=='shipped_exposure_review'
    assert 'AW-O105' not in {r['order_id'] for r in required}  # Unknown, not asserted unaffected.
    run=e.plan_run('Revise incident work',procedure_id='quality-hold-review')
    assert run.status=='awaiting_review',run.error
    review=e.review_handoff(run.handoff_ids[0])
    assert review.review.status=='accepted'
    system,transcript,_=model.inputs[-1]
    assert 'historical linkage alone is not grounds for rejection' in system
    assert 'reject a proposal that continues a contradicted old action' in system
    context=json.loads(transcript[0]['content'])
    assert len(context['required_affected_tasks'])==2
    assert all(t['superseded_decision_ids']==['aw-dec-hold-v1'] for t in context['required_affected_tasks'])
    assert [r['order_id'] for r in context['required_exposed_orders']]==['AW-O101','AW-O102','AW-O103']


def test_after_change_omitted_new_order_cannot_pass_with_all_required_tasks(world):
    model=ScriptedModel([revised_plan(['AW-O101','AW-O102'])])
    e=engine(world,model)
    load_incident(world[0],AW,world[2],'after-change')
    run=e.plan_run('Revise incident work',procedure_id='quality-hold-review')
    review=e.review_handoff(run.handoff_ids[0])
    assert review.review.status=='needs_revision'
    assert review.review.issues[0].evidence_ids==['AW-O103']
    assert len(model.inputs)==1


def test_multiple_exposure_paths_require_one_citation_per_order(world):
    e=engine(world,ScriptedModel([]))
    world[1].query("MATCH (a:Assembly {id:'AW-A102',project_id:$p}), (o:Order {id:'AW-O101',project_id:$p}) "
                   "CREATE (a)-[:ALLOCATED_TO {source_id:'aw-src-trace'}]->(o)",params={'p':world[2]})
    assert [r['order_id'] for r in e.required_orders(e.decisions())]==['AW-O101','AW-O102']


def test_complete_coverage_never_forces_reviewer_acceptance(world):
    plan=revised_plan(['AW-O101','AW-O102','AW-O103'])
    plan['final']['steps'][0]['task']='Ship AW-O103 immediately despite hold v2'
    model=ScriptedModel([plan,{'final':{'status':'needs_revision','issues':[
        {'reason':'Shipping contradicts the current hold; obtain QA disposition first',
         'evidence_ids':['aw-dec-hold-v2','AW-O103']}]}}])
    e=engine(world,model)
    load_incident(world[0],AW,world[2],'after-change')
    run=e.plan_run('Revise incident work',procedure_id='quality-hold-review')
    review=e.review_handoff(run.handoff_ids[0])
    assert review.review.status=='needs_revision'
    assert 'Shipping contradicts' in review.review.issues[0].reason


def test_structured_task_citations_are_recovered_and_persisted(world):
    plan=revised_plan(['AW-O101','AW-O102','AW-O103'])
    tasks=plan['final']['steps'][0]['task_ids']
    plan['final']['steps'][0]['evidence_ids']=[
        i for i in plan['final']['steps'][0]['evidence_ids'] if i not in tasks]
    model=ScriptedModel([plan,{'final':{'status':'accepted','issues':[]}}])
    e=engine(world,model)
    load_incident(world[0],AW,world[2],'after-change')
    run=e.plan_run('Revise incident work',procedure_id='quality-hold-review')
    assert run.status=='awaiting_review',run.error
    handoff=e.store.get('handoff',run.handoff_ids[0])
    citations=handoff['plan']['steps'][0]['evidence_ids']
    assert all(citations.count(t)==1 for t in tasks)
    assert set(tasks).issubset({v['evidence_id'] for v in handoff['evidence_versions']})
    assert e.review_handoff(run.handoff_ids[0]).review.status=='accepted'


def test_normalization_does_not_make_unknown_task_evidence_valid(world):
    plan=copy.deepcopy(PLAN)
    plan['final']['steps'][0]['task_ids']=['other-company-or-invented-task']
    e=engine(world,ScriptedModel([plan]))
    run=e.plan_run('Investigate hold',procedure_id='quality-hold-review')
    assert run.status=='blocked'
    assert run.handoff_ids==[]
