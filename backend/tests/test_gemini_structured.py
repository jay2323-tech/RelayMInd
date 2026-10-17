import json
from unittest.mock import patch
import pytest
from relaymind.agents.providers import JsonProvider, ProviderError, gemini_reply_schema
from relaymind.contracts.models import Review, Plan
from relaymind.contracts.coordination import EvidenceArguments
from test_provider_adapters import Response


def instruction(model):
    return 'Required final schema: '+json.dumps(model.model_json_schema())


@pytest.mark.parametrize('model',[Review,Plan])
def test_gemini_wire_constrains_envelope_final_and_tool_arguments(model):
    tools={'fetch_evidence':{'description':'Read evidence','arguments':EvidenceArguments.model_json_schema()}}
    request=JsonProvider('gemini','model','secret')._request(instruction(model),[],tools)
    schema=json.loads(request.data)['generationConfig']['responseJsonSchema']
    final,calls=schema['anyOf']
    assert final['required']==['final'] and final['additionalProperties'] is False
    assert set(final['properties']['final']['properties'])==set(model.model_fields)
    assert '$ref' not in json.dumps(schema)
    assert calls['properties']['calls']['minItems']==1
    variant=calls['properties']['calls']['items']['anyOf'][0]
    assert variant['properties']['name']['enum']==['fetch_evidence']
    assert variant['properties']['arguments']['required']==['evidence_id']


def test_no_tools_means_only_final_branch():
    assert len(gemini_reply_schema(instruction(Review),{})['anyOf'])==1


def test_invalid_review_envelope_still_fails_and_logs_only_stage(caplog):
    wire={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(
        {'status':'accepted','issues':[],'secret_marker':'SECRET_VALUE'})}]}}]}
    with patch('relaymind.agents.providers.urlopen',return_value=Response(wire)) as request:
        with pytest.raises(ProviderError):
            JsonProvider('gemini','model','SECRET_KEY').reply(instruction(Review),[],{})
    assert request.call_count==2
    assert 'envelope_schema' in caplog.text
    assert 'SECRET_VALUE' not in caplog.text and 'SECRET_KEY' not in caplog.text
