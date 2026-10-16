import io
import json
from urllib.error import HTTPError
from unittest.mock import patch
import pytest
from relaymind.agents.providers import JsonProvider,ProviderError,FallbackProvider,USER_AGENT
from relaymind.agents.engine import failure_summary
from relaymind.agents.loop import AgentLoop,AgentBlocked,ReadTool
from relaymind.contracts.models import Review
from relaymind.contracts.coordination import NoArguments
from test_agent_loop import ScriptedModel
from test_provider_adapters import Response


def wire(provider='gemini',content=None):
    text=json.dumps(content or {'final':{'status':'accepted','issues':[]}})
    if provider=='gemini':
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':text}]}}]}
    return {'choices':[{'finish_reason':'stop','message':{'content':text}}]}


def http_error(status):
    return HTTPError('https://provider.invalid/secret-url',status,'SECRET_BODY',{},io.BytesIO(b'SECRET_BODY'))


@pytest.mark.parametrize('provider',['gemini','groq'])
def test_user_agent_is_sent_to_both_providers(provider):
    with patch('relaymind.agents.providers.urlopen',return_value=Response(wire(provider))) as request:
        JsonProvider(provider,'model','SECRET_KEY').reply('private prompt',[],{})
        assert request.call_args.args[0].get_header('User-agent')==USER_AGENT


@pytest.mark.parametrize('status',[429,503])
def test_transient_failures_retry_twice_and_recover(status):
    with patch('relaymind.agents.providers.urlopen',side_effect=[http_error(status),http_error(status),Response(wire())]) as request, \
         patch('relaymind.agents.providers.time.sleep') as sleep:
        result=JsonProvider('gemini','model','key').reply('system',[],{})
        assert result.final['status']=='accepted'
        assert request.call_count==3
        assert [c.args[0] for c in sleep.call_args_list]==[0.25,0.5]


def test_retry_limit_then_fallback_has_time_budget():
    primary=JsonProvider('gemini','model','key')
    fallback=JsonProvider('groq','model','key')
    with patch('relaymind.agents.providers.urlopen',side_effect=[http_error(503),http_error(503),http_error(503),Response(wire('groq'))]) as request, \
         patch('relaymind.agents.providers.time.sleep'):
        reply=FallbackProvider(primary,fallback).reply('s',[],{},timeout=10)
        assert reply.final['status']=='accepted'
        assert request.call_count==4
        assert request.call_args_list[0].kwargs['timeout']<=6.5
        assert 'groq.com' in request.call_args_list[-1].args[0].full_url


def test_authentication_error_not_retried():
    with patch('relaymind.agents.providers.urlopen',side_effect=http_error(403)) as request, \
         patch('relaymind.agents.providers.time.sleep') as sleep:
        with pytest.raises(ProviderError) as caught:
            JsonProvider('groq','model','SECRET_KEY').reply('secret prompt',[],{})
        assert request.call_count==1
        assert caught.value.http_status==403
        assert not caught.value.retryable
        sleep.assert_not_called()


def test_retry_does_not_sleep_past_budget():
    with patch('relaymind.agents.providers.urlopen',side_effect=http_error(503)) as request, \
         patch('relaymind.agents.providers.time.sleep') as sleep:
        with pytest.raises(ProviderError):
            JsonProvider('gemini','model','key').reply('s',[],{},timeout=.1)
        assert request.call_count==1
        sleep.assert_not_called()


def test_retry_after_honored_when_budget_allows():
    error=http_error(429)
    error.headers['Retry-After']='2'
    with patch('relaymind.agents.providers.urlopen',side_effect=[error,Response(wire())]), \
         patch('relaymind.agents.providers.time.sleep') as sleep:
        JsonProvider('gemini','model','key').reply('s',[],{},timeout=10)
        sleep.assert_called_once_with(2.0)


def test_invalid_json_envelope_is_corrected_once():
    # Wrong outer shape must be repaired before any tool is executed.
    with patch('relaymind.agents.providers.urlopen',side_effect=[Response(wire(content={'status':'accepted'})),Response(wire())]) as request:
        reply=JsonProvider('gemini','model','key').reply('s',[],{})
        assert reply.final['status']=='accepted'
        assert request.call_count==2
        repaired=json.loads(request.call_args.args[0].data)
        assert 'previous response' in repaired['systemInstruction']['parts'][0]['text']


def test_repeated_invalid_envelope_stops_after_one_repair():
    with patch('relaymind.agents.providers.urlopen',return_value=Response(wire(content={'wrong':'shape'}))) as request:
        with pytest.raises(ProviderError) as caught:
            JsonProvider('gemini','model','key').reply('s',[],{})
        assert request.call_count==2
        assert caught.value.code=='invalid_response'


def test_invalid_final_review_schema_is_corrected_once():
    model=ScriptedModel([{'final':{'verdict':'yes'}},{'final':{'status':'accepted','issues':[]}}])
    events=[]
    result=AgentLoop(model,max_turns=1).run('Review','request',{},Review,events.append)
    assert result.status=='accepted'
    assert len(model.inputs)==2
    assert 'Correcting invalid final output format' in events


def test_repeated_invalid_final_schema_stops():
    model=ScriptedModel([{'final':{'verdict':'yes'}},{'final':{'verdict':'still invalid'}}])
    with pytest.raises(AgentBlocked,match='after one correction'):
        AgentLoop(model).run('Review','request',{},Review)


def test_schema_repair_does_not_repeat_tools():
    model=ScriptedModel([{'calls':[{'id':'read1','name':'read','arguments':{}}]},
                         {'final':{'verdict':'yes'}},{'final':{'status':'accepted','issues':[]}}])
    observed=[]
    AgentLoop(model).run('Review','request',{'read':ReadTool('read',NoArguments,lambda:observed.append(1) or {})},Review)
    assert observed==[1]


def test_safe_failure_logs_metadata_without_credentials_or_prompts(caplog):
    with patch('relaymind.agents.providers.urlopen',side_effect=http_error(403)):
        with pytest.raises(ProviderError) as caught:
            JsonProvider('groq','model','SECRET_KEY').reply('SECRET_PROMPT',[],{})
    summary=failure_summary(caught.value,'review','run-safe')
    assert 'groq' in summary and '403' in summary
    assert 'provider=groq' in caplog.text
    assert 'http_status=403' in caplog.text
    for secret in ['SECRET_KEY','SECRET_PROMPT','SECRET_BODY','secret-url']:
        assert secret not in caplog.text
        assert secret not in summary
