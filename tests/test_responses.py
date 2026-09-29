import json

import httpx
import pytest

from drone_agent.artifacts import Artifacts, write_json
from drone_agent.audit import audit_requests
from drone_agent.context import ContextBuilder
from drone_agent.protocol import Config
from drone_agent.provider import CloudPolicy
from native_helpers import reply
from test_protocol_context import obs


@pytest.mark.parametrize('history', [True, False])
def test_responses_replays_reasoning_and_tool_results_without_retaining_old_image_blocks(tmp_path, history):
    config=Config(model='gpt-6-astra',navigation_history=history)
    artifacts=Artifacts(tmp_path/'run',config)
    write_json(artifacts.directory/'launch.json',config.model_dump())
    context=ContextBuilder(artifacts,'test',navigation_history=history)
    calls=[]
    output=[{'type':'reasoning','id':'rs_test','summary':[], 'encrypted_content':'opaque-reasoning'},
            {'type':'function_call','id':'fc_test','call_id':'call_test','name':'photo_frame',
             'arguments':reply('photo_frame',{'mode':'clear'})['tool_calls'][0]['function']['arguments']}]
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'output':output,'usage':{
            'input_tokens':42,'output_tokens':8,'total_tokens':50,
            'input_tokens_details':{'cached_tokens':21},'output_tokens_details':{'reasoning_tokens':5}}})
    policy=CloudPolicy(config,artifacts,base_url='https://test.invalid/v1',api_key='test',
                       transport=httpx.MockTransport(handler))
    response=policy.complete(context.build(obs(1),{}))
    context.record(response,{'status':'completed','observation':obs(2).public(2.)})
    context.record_round_end(1,obs(2),tool_call_id='call_test')
    policy.complete(context.build(obs(3),{}))
    second=calls[1]
    assert second['input'][2:4]==output
    result=second['input'][4]
    assert result['type']=='function_call_output' and result['call_id']=='call_test'
    assert json.loads(result['output'])['status']=='completed'
    assert 'previous_response_id' not in second and second['store'] is False
    blocks=[part for item in second['input'] if isinstance(item.get('content'),list)
            for part in item['content'] if part['type']=='input_image']
    assert len(blocks)==(2 if history else 1)
    labels=[json.loads(p['text']) for p in second['input'][-1]['content'] if p['type']=='input_text']
    assert [p['image_id'] for p in labels if 'image_id' in p]==(
        ['frame_000003','frame_000002'] if history else ['frame_000003'])
    audit=audit_requests(artifacts.directory)
    assert audit['status']=='passed' and len(audit['requests'][1]['images'])==len(blocks)
    metrics=[json.loads(line) for line in (artifacts.directory/'api-metrics.jsonl').read_text().splitlines()]
    assert metrics[0]['usage']=={'prompt_tokens':42,'completion_tokens':8,'total_tokens':50,
        'prompt_tokens_details':{'cached_tokens':21},'completion_tokens_details':{'reasoning_tokens':5}}


@pytest.mark.parametrize('item',[
    {'type':'function_call','name':'photo_frame','call_id':'call_x','arguments':'{"height_m":1}'},
    {'type':'function_call_output','call_id':'call_x','output':'{"yaw_deg":90}'},
    {'role':'user','content':[{'type':'input_text','text':'{"position":[1,2,3]}'}]},
])
def test_responses_audit_checks_actual_inputs(tmp_path,item):
    write_json(tmp_path/'api/test.request.json',{'input':[item]})
    assert audit_requests(tmp_path)['status']=='failed'


def test_duplicate_response_call_id_cannot_rewrite_accepted_history():
    from drone_agent.responses import ResponsesAdapter
    from drone_agent.protocol import native_tool_definitions
    adapter=ResponsesAdapter()
    original={'type':'function_call','id':'fc_1','call_id':'call_same','name':'photo_frame','arguments':'{"mode":"clear"}'}
    first=adapter.message({'output':[original]})
    adapter.message({'output':[dict(original,name='act',arguments='{"kind":"forward","value":500}')]})
    request=adapter.request('gpt-6-astra',[first],native_tool_definitions())
    assert request['input']==[original]
