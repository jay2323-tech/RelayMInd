"""Real manufacturing graph + scripted model: no live Gemini calls."""
import os
from uuid import uuid4
import pytest
from relaymind.agents.engine import CoordinationEngine
from relaymind.contracts.coordination import HandoffRecord
from relaymind.platform.aw_incident import load_incident
from relaymind.platform.bridge import GraphPlatformBridge
from relaymind.memory.conversations import create_session
from test_manufacturing_real_db import world, AW
from test_agent_loop import ScriptedModel

pytestmark=pytest.mark.skipif(os.getenv('RUN_LIVE_FALKORDB_TESTS')!='1',reason='Opt-in live database')

PLAN={'final':{'summary':'Investigate current hold with QA',
    'decision_ids':['aw-dec-hold-v1'],
    'steps':[{'task':'Keep batch quarantine pending human disposition',
              'evidence_ids':['aw-src-hold-v1']}],'uncertainties':['Named assignee unknown']}}


def engine(world,model):
    client,graph,pid=world
    load_incident(client,AW,pid,'before-change')
    sid='mfg-agent-'+uuid4().hex
    create_session(client,AW,pid,sid)
    return CoordinationEngine(client,AW,pid,sid,model,GraphPlatformBridge(client))


def change_order(graph,pid):
    graph.query("MATCH (o:Order {id:'AW-O101',project_id:$p})-[:HAS_VERSION]->(v:OrderVersion) "
        "WHERE NOT (v)<-[:PREVIOUS]-(:OrderVersion) "
        "CREATE (o)-[:HAS_VERSION]->(n:OrderVersion {id:'AW-O101:v2',order_id:'AW-O101',"
        "project_id:$p,version:2,version_key:'AW-O101:2',status:'on_hold',model:'AW-M1',"
        "units:12,traceability:'known',source_id:'aw-src-trace'}) CREATE (n)-[:PREVIOUS]->(v)",params={'p':pid})


def test_typed_tools_scope_and_manifest_catches_uncited_order_version(world):
    model=ScriptedModel([PLAN])
    e=engine(world,model)
    run=e.plan_run('Investigate QH-17',procedure_id='quality-hold-review')
    assert run.status=='awaiting_review',run.error
    handoff=HandoffRecord.model_validate(e.store.get('handoff',run.handoff_ids[0]))
    assert handoff.manufacturing_versions[0].version_id=='aw-dec-hold-v1'
    tools=e._tools(e.decisions(),None,None)
    assert tools['get_order'].execute(order_id='AW-O101')['version_id']=='AW-O101:v1'
    report=tools['affected_orders'].execute(hold_id='QH-17')
    assert sorted(a['order']['order_id'] for a in report['affected'])==['AW-O101','AW-O102']
    assert report['unknown_traceability'][0]['order_id']=='AW-O105'
    change_order(world[1],world[2])
    # This order was NOT cited in the plan; impact manifest must still detect it.
    review=e.review_handoff(handoff.id)
    assert review.review.status=='needs_revision'
    assert review.review.issues[0].evidence_ids==['aw-dec-hold-v1']
    assert len(model.inputs)==1


def test_traceability_change_invalidates_without_source_or_decision_change(world):
    e=engine(world,ScriptedModel([PLAN]))
    run=e.plan_run('Investigate QH-17',procedure_id='quality-hold-review')
    world[1].query("MATCH (a:Assembly {id:'AW-A104',project_id:$p}), (o:Order {id:'AW-O105',project_id:$p}) "
                   "CREATE (a)-[:ALLOCATED_TO {source_id:'aw-src-trace'}]->(o)",params={'p':world[2]})
    assert e.review_handoff(run.handoff_ids[0]).review.status=='needs_revision'


def test_order_change_during_review_overrides_model_acceptance(world):
    class Model(ScriptedModel):
        def reply(self,*args,**kwargs):
            if len(self.inputs)==1:
                change_order(world[1],world[2])
            return super().reply(*args,**kwargs)
    model=Model([PLAN,{'final':{'status':'accepted','issues':[]}}])
    e=engine(world,model)
    run=e.plan_run('Investigate QH-17',procedure_id='quality-hold-review')
    review=e.review_handoff(run.handoff_ids[0])
    assert review.review.status=='needs_revision' and len(model.inputs)==2


def test_impact_change_during_planning_cannot_save_fresh_looking_handoff(world):
    class Model(ScriptedModel):
        def reply(self,*args,**kwargs):
            change_order(world[1],world[2])
            return super().reply(*args,**kwargs)
    e=engine(world,Model([PLAN]))
    run=e.plan_run('Investigate QH-17',procedure_id='quality-hold-review')
    assert run.status=='blocked' and run.handoff_ids==[]
