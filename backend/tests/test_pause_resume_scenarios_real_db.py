"""Both scenarios use real FalkorDB and an explicitly scripted model fixture."""
import json
import os
import subprocess
import sys
from uuid import uuid4
import pytest
from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.connection import create_client
from relaymind.memory.artifacts import ArtifactConflict
from relaymind.demo.scenarios import seed,cleanup,configuration,engine_for,change_requirement

load_dotenv()
pytestmark=pytest.mark.skipif(os.getenv('RUN_LIVE_FALKORDB_TESTS')!='1',reason='Opt-in real database scenarios')


@pytest.fixture(params=['launch','coding'])
def scenario(request):
    client=create_client()
    context=TrustedContext(tenant_id='demo-a',user_id='developer-a')
    instance='pause-demo-'+str(uuid4())
    name=request.param
    seed(client,context,instance,name)
    yield client,context,instance,name
    cleanup(client,context,instance)


def paused_run(scenario):
    client,ctx,instance,name=scenario
    engine=engine_for(client,ctx,instance,name)
    run=engine.plan_run(configuration(name)['request'],run_id=instance+'-run',procedure_id=instance+'-procedure')
    assert run.status=='awaiting_review',run.error
    paused=engine.pause_run(run.id)
    assert paused.status=='paused'
    return engine,paused


def test_pause_blocks_review_and_survives_reload(scenario):
    client,ctx,instance,name=scenario
    engine,paused=paused_run(scenario)
    assert engine.continue_run(paused.id).status=='paused'
    assert engine.pause_run(paused.id).status=='paused'
    with pytest.raises(ArtifactConflict):engine.review_handoff(paused.handoff_ids[0])
    fresh=engine_for(client,ctx,instance,name)
    assert fresh.explain_changes(paused.id)['status']=='paused'
    assert not fresh.explain_changes(paused.id)['decisions_changed']
    completed=fresh.resume_run(paused.id)
    assert completed.status=='completed',completed.error
    assert len(completed.handoff_ids)==1
    assert fresh.resume_run(paused.id)==completed
    with pytest.raises(ArtifactConflict):fresh.pause_run(paused.id)


def test_changed_requirement_resume_in_independent_process(scenario):
    client,ctx,instance,name=scenario
    engine,paused=paused_run(scenario)
    old_handoff=engine.store.get('handoff',paused.handoff_ids[0])
    change_requirement(client,ctx,instance,name)
    # A truly independent backend Python process loads persisted run/handoff state.
    result=subprocess.run([sys.executable,'-m','relaymind.demo.scenarios',
        '--scenario',name,'--phase','resume','--instance',instance],
        capture_output=True,text=True,check=True,timeout=30)
    report=json.loads(result.stdout)
    assert report['model_mode']=='scripted-fixture'
    assert report['platform_mode']=='synthetic-graph-fixture'
    assert report['run']['status']=='completed',report['run']['error']
    assert len(report['run']['handoff_ids'])==2
    changes=report['comparison']
    assert changes['decisions_changed']
    assert changes['changes'][0]['before'][0]['text']==configuration(name)['before']
    assert changes['changes'][0]['current'][0]['text']==configuration(name)['after']
    assert changes['original_plan']['steps'][0]['task']==configuration(name)['before_step']
    assert changes['latest_plan']['steps'][0]['task']==configuration(name)['after_step']
    paths=changes['dependency_paths'][instance+'-task-0']
    assert [row['hops'] for row in paths]==[0,1,2]
    assert changes['action_applied'] is False
    # Original evidence and plan remain unchanged after the revised run.
    assert engine.store.get('handoff',paused.handoff_ids[0])==old_handoff
    assert engine.store.get('review',paused.handoff_ids[0])['review']['status']=='needs_revision'


def test_active_review_cannot_be_paused(scenario):
    client,ctx,instance,name=scenario
    engine=engine_for(client,ctx,instance,name)
    run=engine.plan_run(configuration(name)['request'],run_id=instance+'-run',procedure_id=instance+'-procedure')
    token=engine.store.claim(run.handoff_ids[0])
    with pytest.raises(ArtifactConflict):engine.pause_run(run.id)
    assert engine.store.get('run',run.id)['status']=='awaiting_review'
    engine.store.release(run.handoff_ids[0],token)
