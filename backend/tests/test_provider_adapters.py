import json
import pytest
from unittest.mock import patch
from relaymind.agents.providers import JsonProvider, ProviderError

class Response:
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return json.dumps(self.payload).encode()

@pytest.mark.parametrize('provider',['gemini','groq'])
def test_provider_wire_format_and_secret_location(provider):
    final=json.dumps({'final':{'summary':'Done'}})
    payload=({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':final}]}}]}
             if provider=='gemini' else {'choices':[{'finish_reason':'stop','message':{'content':final}}]})
    with patch('relaymind.agents.providers.urlopen',return_value=Response(payload)) as request:
        result=JsonProvider(provider,'explicit-model','test-secret').reply('System',[],{})
        sent=request.call_args.args[0]
        assert 'test-secret' not in sent.full_url
        assert 'test-secret' not in sent.data.decode()
        body=json.loads(sent.data)
        assert ('generationConfig' in body) if provider=='gemini' else body['response_format']=={'type':'json_object'}
        assert result.final=={'summary':'Done'}

@pytest.mark.parametrize('provider',['gemini','groq'])
def test_invalid_provider_payload_never_becomes_success(provider):
    with patch('relaymind.agents.providers.urlopen',return_value=Response({})):
        with pytest.raises(ProviderError):
            JsonProvider(provider,'explicit-model','test-secret').reply('System',[],{})
