import pytest
from relaymind.agents.loop import AgentLoop, ReadTool, AgentBlocked
from relaymind.contracts.coordination import ModelReply, NoArguments, EvidenceArguments
from relaymind.contracts.models import Plan


class ScriptedModel:
    """A labeled model double, never used as the application provider."""
    def __init__(self,replies):
        self.replies=iter(replies)
        self.inputs=[]
    def reply(self,system,transcript,tools,timeout=30):
        self.inputs.append((system,list(transcript),tools))
        return ModelReply.model_validate(next(self.replies))


def final_plan():
    return {'final':{'summary':'Launch free tier','steps':[{'task':'Review scope','evidence_ids':['decision-02']}],
                     'decision_ids':['decision-02']}}


def test_real_tool_result_is_returned_to_model():
    model=ScriptedModel([{'calls':[{'id':'1','name':'read','arguments':{}}]},final_plan()])
    actual=[]
    tool=ReadTool('Read persisted data',NoArguments,lambda:actual.append(True) or {'scope':'free'})
    plan=AgentLoop(model).run('Plan','request',{'read':tool},Plan)
    assert actual==[True]
    assert model.inputs[1][1][-1]['result']=={'scope':'free'}
    assert plan.decision_ids==['decision-02']


def test_unknown_tool_does_not_execute():
    model=ScriptedModel([{'calls':[{'id':'1','name':'write_cypher','arguments':{}}]}])
    with pytest.raises(AgentBlocked,match='Unknown tool'):
        AgentLoop(model).run('Plan','request',{},Plan)


def test_extra_tenant_argument_rejected_before_tool():
    from pydantic import ValidationError
    model=ScriptedModel([{'calls':[{'id':'1','name':'read','arguments':{'tenant_id':'other'}}]}])
    called=[]
    with pytest.raises(ValidationError):
        AgentLoop(model).run('Plan','request',{'read':ReadTool('',NoArguments,lambda:called.append(1))},Plan)
    assert not called


def test_tool_budget_stops_loop():
    model=ScriptedModel([{'calls':[{'id':'1','name':'read','arguments':{}}]},
                        {'calls':[{'id':'2','name':'read','arguments':{}}]}])
    with pytest.raises(AgentBlocked,match='Tool-call limit'):
        AgentLoop(model,max_calls=1).run('Plan','request',{'read':ReadTool('',NoArguments,lambda:{})},Plan)


def test_repeated_tool_id_is_rejected():
    response={'calls':[{'id':'same','name':'read','arguments':{}}]}
    with pytest.raises(AgentBlocked,match='repeated'):
        AgentLoop(ScriptedModel([response,response])).run('Plan','request',{'read':ReadTool('',NoArguments,lambda:{})},Plan)


def test_context_budget_rejects_oversized_request():
    with pytest.raises(AgentBlocked,match='Context limit'):
        AgentLoop(ScriptedModel([]),context_chars=20).run('Plan','large request'*100,{},Plan)


def test_provider_fallback_only_on_retryable_errors():
    from relaymind.agents.providers import FallbackProvider, ProviderError
    class Broken:
        def __init__(self,retry): self.retry=retry
        def reply(self,*args,**kwargs): raise ProviderError('Unavailable',self.retry)
    fallback=ScriptedModel([final_plan()])
    assert FallbackProvider(Broken(True),fallback).reply('s',[],{}).final is not None
    with pytest.raises(ProviderError):
        FallbackProvider(Broken(False),fallback).reply('s',[],{})
