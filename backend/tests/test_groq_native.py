import io
import json
from urllib.error import HTTPError
from unittest.mock import patch
import pytest
from relaymind.agents.providers import JsonProvider,ProviderError
from relaymind.contracts.models import Review
from test_provider_adapters import Response


def native(name,args,call_id='native-1'):
    return {'choices':[{'finish_reason':'tool_calls','message':{'content':None,'tool_calls':[
        {'id':call_id,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}]}


def test_native_tool_request_and_result_round_trip():
    model=JsonProvider('groq','openai/gpt-oss-120b','secret')
    tools={'fetch_evidence':{'description':'Read source','arguments':{'type':'object','properties':{'evidence_id':{'type':'string'}},'required':['evidence_id']}}}
    with patch('relaymind.agents.providers.urlopen',return_value=Response(native('fetch_evidence',{'evidence_id':'source-02'}))) as send:
        reply=model.reply('Review. Required final schema: '+json.dumps(Review.model_json_schema()),
                          [{'role':'user','content':'Inspect source'}],tools)
        assert reply.calls[0].name=='fetch_evidence'
        body=json.loads(send.call_args.args[0].data)
        assert body['tools'][-1]['function']['parameters']==Review.model_json_schema()
        assert 'Return JSON: {"calls"' not in body['messages'][0]['content']
    transcript=[{'role':'user','content':'Inspect source'},
                {'role':'assistant','calls':[reply.calls[0].model_dump()]},
                {'role':'tool','call_id':'native-1','name':'fetch_evidence','result':{'text':'Free tier'}}]
    with patch('relaymind.agents.providers.urlopen',return_value=Response(native('submit_result',{'status':'accepted','issues':[]}))) as send:
        result=model.reply('Review',transcript,tools)
        assert result.final=={'status':'accepted','issues':[]}
        body=json.loads(send.call_args.args[0].data)
        assert body['messages'][-2]['tool_calls'][0]['id']=='native-1'
        assert body['messages'][-1]['tool_call_id']=='native-1'


@pytest.mark.parametrize('code',['tool_use_failed','json_validate_failed'])
def test_known_groq_400_repairs_once_without_logging_generation(code,caplog):
    body={'error':{'code':code,'message':'PRIVATE_SOURCE','failed_generation':'SECRET_GENERATION'}}
    error=HTTPError('https://api.groq.com/path',400,'bad',{},io.BytesIO(json.dumps(body).encode()))
    with patch('relaymind.agents.providers.urlopen',side_effect=[error,Response(native('submit_result',{'status':'accepted','issues':[]}))]) as send:
        result=JsonProvider('groq','model','SECRET_KEY').reply('PRIVATE_PROMPT',[],{})
        assert result.final['status']=='accepted'
        assert send.call_count==2
        assert code in caplog.text
        for secret in ['PRIVATE_SOURCE','SECRET_GENERATION','SECRET_KEY','PRIVATE_PROMPT']:
            assert secret not in caplog.text


def test_unknown_groq_400_is_not_retried():
    error=HTTPError('https://api.groq.com/path',400,'bad',{},io.BytesIO(b'{"error":{"code":"invalid_request"}}'))
    with patch('relaymind.agents.providers.urlopen',side_effect=error) as send:
        with pytest.raises(ProviderError):JsonProvider('groq','model','key').reply('s',[],{})
        assert send.call_count==1


def test_mixed_native_final_and_read_calls_are_rejected():
    payload=native('submit_result',{'status':'accepted','issues':[]})
    payload['choices'][0]['message']['tool_calls'].append(
        {'id':'other','type':'function','function':{'name':'fetch_evidence','arguments':'{}'}})
    with patch('relaymind.agents.providers.urlopen',return_value=Response(payload)) as send:
        with pytest.raises(ProviderError):JsonProvider('groq','model','key').reply('s',[],{})
        assert send.call_count==2
