"""Reproducible pause/change/resume scenarios using real FalkorDB.

Default model and decision policy are explicitly scenario fixtures. Production
PlatformBridge lives with Claude. Fixture labels are distinct from production data.
"""
import argparse
import json
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.contracts.coordination import DecisionReference,EvidenceRecord,ModelReply
from relaymind.graph.access import authorized_graph,require_session,AccessDenied
from relaymind.graph.connection import create_client
from relaymind.memory.conversations import create_session,save_message
from relaymind.memory.episodes import save_episode
from relaymind.memory.procedures import approve_procedure
from relaymind.agents.engine import CoordinationEngine
from relaymind.agents.providers import provider_from_env


def configuration(name):
    path=Path(__file__).resolve().parents[4]/'fixtures/pause-resume-scenarios.json'
    return json.loads(path.read_text())['scenarios'][name]


class ScenarioBridge:
    """Synthetic decision/source/dependency fixture, persisted in the real graph."""
    def __init__(self,client,context,project_id,instance):
        self.context,self.project_id,self.instance=context,project_id,instance
        self.graph=authorized_graph(client,context,project_id)
        require_session(self.graph,context,project_id,instance+'-session')

    def _access(self,context,project_id):
        if context!=self.context or project_id!=self.project_id:
            raise AccessDenied('Scenario access denied')
        require_session(self.graph,context,project_id,self.instance+'-session')

    def current_decisions(self,context,project_id):
        self._access(context,project_id)
        rows=self.graph.ro_query(
            "MATCH (d:ScenarioDecision {scenario_id:$scenario,current:true}) "
            "-[:SUPPORTED_BY]->(s:ScenarioSource) RETURN d.id,d.version,d.topic,d.text,s.id",
            params={'scenario':self.instance}).result_set
        return [DecisionReference(id=row[0],version=row[1],topic=row[2],text=row[3],source_id=row[4]) for row in rows]

    def evidence(self,context,project_id,evidence_id):
        self._access(context,project_id)
        rows=self.graph.ro_query(
            "MATCH (d:ScenarioDecision {scenario_id:$scenario,id:$id})-[:SUPPORTED_BY]->(s:ScenarioSource) "
            "RETURN d.id,d.text,s.id",params={'scenario':self.instance,'id':evidence_id}).result_set
        if len(rows)!=1:
            raise AccessDenied('Scenario evidence unavailable')
        return EvidenceRecord(id=rows[0][0],text=rows[0][1],source_id=rows[0][2])

    def dependencies(self,context,project_id,task_id):
        self._access(context,project_id)
        rows=self.graph.ro_query(
            "MATCH path=(root:ScenarioTask {scenario_id:$scenario,id:$task})"
            "-[:BLOCKED_BY*0..4]->(t:ScenarioTask) "
            "RETURN t.id,t.name,length(path) ORDER BY length(path),t.id",
            params={'scenario':self.instance,'task':task_id}).result_set
        return [{'task_id':row[0],'name':row[1],'hops':row[2]} for row in rows]


class ScriptedScenarioModel:
    """Deterministic scenario driver, NOT a live model or intelligence benchmark."""
    def __init__(self,name,instance):
        self.config=configuration(name)
        self.instance=instance

    def reply(self,system,transcript,tools,timeout=30):
        prompt=json.loads(transcript[0]['content'])
        if 'independent Reviewer' in system:
            return ModelReply(final={'status':'accepted','issues':[]})
        # Exercise an actual graph traversal before returning the scripted plan.
        if len(transcript)==1:
            return ModelReply(calls=[{'id':'dependency-read','name':'trace_dependencies',
                                      'arguments':{'task_id':self.instance+'-task-0'}}])
        decision=prompt['current_decisions'][0]
        is_new=decision['version']==2
        task=self.config['after_step'] if is_new else self.config['before_step']
        return ModelReply(final={'summary':decision['text'],
                    'steps':[{'task':task,'evidence_ids':[decision['id']]}],
                    'uncertainties':[],'decision_ids':[decision['id']]})


def seed(client,context,instance,name):
    config=configuration(name)
    create_session(client,context,'launch-01',instance+'-session')
    message=save_message(client,context,'launch-01',instance+'-session',instance+'-message',
                         'user',config['before'])
    save_episode(client,context,'launch-01',instance+'-episode',message.id,
                 'Historical requirement: '+config['before'])
    approve_procedure(client,context,'launch-01',instance+'-procedure',1,'Scenario review',
        ['Check current requirement against plan','Verify evidence','Do not claim actions were executed'],
        'Explicit synthetic scenario setup',human_approved=True)
    graph=authorized_graph(client,context,'launch-01')
    graph.query(
        "CREATE (s:ScenarioSource {scenario_id:$scenario,id:$source,text:$text}) "
        "CREATE (d:ScenarioDecision {scenario_id:$scenario,id:$decision,version:1,topic:$topic,text:$text,current:true}) "
        "CREATE (d)-[:SUPPORTED_BY]->(s)",
        params={'scenario':instance,'source':instance+'-source-1','decision':instance+'-decision-1',
                'text':config['before'],'topic':config['topic']})
    for index,name in enumerate(config['tasks']):
        graph.query('CREATE (t:ScenarioTask {scenario_id:$scenario,id:$id,name:$name})',
                    params={'scenario':instance,'id':instance+'-task-'+str(index),'name':name})
    graph.query(
        "MATCH (a:ScenarioTask {id:$a}),(b:ScenarioTask {id:$b}),(c:ScenarioTask {id:$c}),"
        "(d:ScenarioDecision {id:$decision}) "
        "CREATE (a)-[:BLOCKED_BY]->(b) CREATE (b)-[:BLOCKED_BY]->(c) CREATE (b)-[:IMPLEMENTS]->(d)",
        params={'a':instance+'-task-0','b':instance+'-task-1','c':instance+'-task-2',
                'decision':instance+'-decision-1'})


def change_requirement(client,context,instance,name):
    # Fixture-only mutation: production decision approval/supersession remains Claude's.
    bridge=ScenarioBridge(client,context,'launch-01',instance)
    config=configuration(name)
    rows=bridge.graph.query(
        "MATCH (old:ScenarioDecision {scenario_id:$scenario,current:true,version:1}) "
        "CREATE (s:ScenarioSource {scenario_id:$scenario,id:$source,text:$text}) "
        "CREATE (d:ScenarioDecision {scenario_id:$scenario,id:$decision,version:2,topic:$topic,text:$text,current:true}) "
        "CREATE (d)-[:SUPPORTED_BY]->(s) CREATE (d)-[:REPLACES]->(old) "
        "SET old.current=false RETURN d.id",
        params={'scenario':instance,'source':instance+'-source-2','decision':instance+'-decision-2',
                'text':config['after'],'topic':config['topic']}).result_set
    if not rows:
        raise ValueError('Scenario requirement was already changed or is unavailable')


def engine_for(client,context,instance,name,live_model=False):
    provider=provider_from_env() if live_model else ScriptedScenarioModel(name,instance)
    bridge=ScenarioBridge(client,context,'launch-01',instance)
    return CoordinationEngine(client,context,'launch-01',instance+'-session',provider,bridge)


def cleanup(client,context,instance):
    # Instance UUID and session ownership must match; this is never a graph reset.
    bridge=ScenarioBridge(client,context,'launch-01',instance)
    g=bridge.graph
    g.query("MATCH (a:AgentArtifact {session_id:$session}) OPTIONAL MATCH (a)-[:HAS_SNAPSHOT]->(v:AgentRunSnapshot) DETACH DELETE a,v",params={'session':instance+'-session'})
    g.query("MATCH (p:Procedure {id:$id}) DETACH DELETE p",params={'id':instance+'-procedure'})
    for label in ['ScenarioTask','ScenarioDecision','ScenarioSource']:
        # Label is fixed program code, not caller/model input.
        g.query('MATCH (n:'+label+' {scenario_id:$scenario}) DETACH DELETE n',params={'scenario':instance})
    g.query("MATCH (s:Session {id:$session}) OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m:Message) OPTIONAL MATCH (e:Episode)-[:SUPPORTED_BY]->(m) DETACH DELETE e,m,s",params={'session':instance+'-session'})


def main():
    parser=argparse.ArgumentParser(description='Explicit synthetic pause/change/resume demonstration')
    parser.add_argument('--scenario',required=True,choices=['launch','coding'])
    parser.add_argument('--phase',required=True,choices=['start','change','resume','report','cleanup'])
    parser.add_argument('--instance')
    parser.add_argument('--live-model',action='store_true',help='Use configured Gemini/Groq; decision data remains synthetic')
    args=parser.parse_args()
    instance=args.instance or ('pause-demo-'+str(uuid4()) if args.phase=='start' else None)
    if not instance or not instance.startswith('pause-demo-') or len(instance)>100:
        parser.error('Use the pause-demo-* instance ID printed by start')
    load_dotenv()
    if args.live_model:provider_from_env() # Validate configuration before fixture writes.
    client=create_client()
    ctx=TrustedContext(tenant_id='demo-a',user_id='developer-a')
    result={'scenario':args.scenario,'instance':instance,'phase':args.phase,
            'model_mode':'live' if args.live_model else 'scripted-fixture',
            'platform_mode':'synthetic-graph-fixture'}
    if args.phase=='start':
        seed(client,ctx,instance,args.scenario)
        engine=engine_for(client,ctx,instance,args.scenario,args.live_model)
        run=engine.plan_run(configuration(args.scenario)['request'],run_id=instance+'-run',procedure_id=instance+'-procedure')
        if run.status=='awaiting_review':run=engine.pause_run(run.id)
        result['run']=run.model_dump()
    elif args.phase=='change':
        change_requirement(client,ctx,instance,args.scenario)
        result['changed']=True
    elif args.phase=='cleanup':
        cleanup(client,ctx,instance);result['cleaned']=True
    else:
        engine=engine_for(client,ctx,instance,args.scenario,args.live_model)
        if args.phase=='resume':result['run']=engine.resume_run(instance+'-run').model_dump()
        result['comparison']=engine.explain_changes(instance+'-run',[instance+'-task-0'])
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
