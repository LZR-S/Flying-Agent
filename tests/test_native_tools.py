import copy
import json

import httpx
import pytest

from drone_agent import protocol
from drone_agent.artifacts import Artifacts
from drone_agent.context import ContextBuilder
from drone_agent.provider import CloudPolicy
from native_helpers import reply, review_arguments
from test_protocol_context import obs, images


def test_native_schema_keeps_action_ranges_and_requires_frame_provenance():
    tools=protocol.native_tool_definitions()
    assert {t['function']['name'] for t in tools}=={'act','capture','crop_photo','photo_frame','generate_reference','review_photo','view_images','finish'}
    for tool in tools:
        schema=tool['function']['parameters']
        assert {'based_on_frame_id','note'}<=set(schema['required'])
        assert schema['additionalProperties'] is False
    act=next(t['function']['parameters'] for t in tools if t['function']['name']=='act')
    assert len(act['oneOf'])==13


def test_provider_sends_native_tools_and_preserves_provider_signature(tmp_path):
    message=reply('photo_frame',{'mode':'clear'})
    message['tool_calls'][0]['extra_content']={'google':{'thought_signature':'opaque-token'}}
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':message,'finish_reason':'tool_calls'}]})
    p=CloudPolicy(protocol.Config(),Artifacts(tmp_path/'run',protocol.Config()),
        base_url='https://test.invalid',api_key='secret',transport=httpx.MockTransport(handler))
    assert p.complete([])==message
    assert calls[0]['tool_choice']=='auto'
    assert calls[0]['parallel_tool_calls'] is False
    assert 'response_format' not in calls[0]
    assert len(calls[0]['tools'])==8


def test_frame_schema_uses_explicit_mode_and_omittable_non_nullable_settings():
    schemas={t['function']['name']:t['function']['parameters'] for t in protocol.native_tool_definitions()}
    frame=schemas['photo_frame']
    assert frame['properties']['mode']['enum']==['set','clear','guides']
    assert set(frame['required'])=={'mode','based_on_frame_id','note'}
    assert not {'oneOf','anyOf','allOf'} & frame.keys()
    rectangle=frame['properties']['rectangle']
    assert rectangle['type']=='object' and 'anyOf' not in rectangle
    assert 'default' not in rectangle
    assert set(rectangle['required'])=={'left','top','width','height'}
    for field in ('aspect_ratio','degradation_reason'):
        assert frame['properties'][field]['type']=='string'
        assert not {'anyOf','default'} & frame['properties'][field].keys()
    assert schemas['crop_photo']['properties']['degradation_reason']['type']=='string'


@pytest.mark.parametrize('name,arguments',[
    ('observe',{}),('set_photo_frame',{'rectangle':{'left':0,'top':0,'width':6,'height':9}}),
    ('clear_photo_frame',{}),
])
def test_retired_tools_are_rejected(name,arguments):
    with pytest.raises(ValueError):protocol.parse_tool_decision(reply(name,arguments))


def test_rectangle_type_error_is_actionable_without_echoing_input(tmp_path):
    from drone_agent.agent import AgentLoop
    from test_loop_runtime import setup,Policy
    from test_frame_review import BOX
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    seen=[]
    def corrected(messages):
        seen.extend(json.loads(m['content']) for m in messages if m['role']=='tool')
        assert a.photo_frame['version']==0 and a.photo_frame['aspect_ratio']=='16:9'
        assert a.frame_contract is None
        current=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
        return reply('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX},frame=current,call_id='corrected')
    policy=Policy([('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':'{"private_marker":"DO_NOT_ECHO"}'}),corrected,
                   ('photo_frame',{'mode':'clear'}),('finish',{'shot_id':None,'abandon':True})])
    result=AgentLoop(r,policy,a,config).run()
    error=seen[0]['validation_errors'][0]
    assert error['location']==['rectangle'] and error['type']=='model_type'
    assert error['expected_type']=='object' and error['received_type']=='string'
    assert set(error['example'])=={'left','top','width','height'}
    assert 'DO_NOT_ECHO' not in json.dumps(seen)
    assert result['reason']=='agent_abandoned' and b.sent==[]
    assert a.photo_frame=={'version':2,'rectangle':None}


def test_context_links_text_tool_results_and_attaches_only_current_user_images(tmp_path):
    a=Artifacts(tmp_path/'run',protocol.Config())
    c=ContextBuilder(a,'task')
    c.build(obs(1),{})
    message=reply('photo_frame',{'mode':'clear'})
    message['tool_calls'][0]['extra_content']={'google':{'thought_signature':'opaque-token'}}
    c.record(message,{'status':'completed','observation':obs(2).public(2.)})
    c.record_round_end(1,obs(2),tool_call_id='call_test')
    messages=c.build(obs(3),{})
    assert [m['role'] for m in messages]==['system','user','assistant','tool','user']
    assert messages[2]==message
    assert messages[3]['tool_call_id']=='call_test'
    assert isinstance(messages[3]['content'],str)
    assert len(images(messages))==2
    assert all(not isinstance(m.get('content'),list) for m in messages[:-1])
    metadata=json.loads(messages[-1]['content'][0]['text'])
    assert metadata['after_tool_call_id']=='call_test'
    labels=[json.loads(p['text']) for p in messages[-1]['content'] if p['type']=='text']
    assert next(x for x in labels if x.get('image_id')=='frame_000002')['source_tool_call_id']=='call_test'
    assert 'Tools: ' not in messages[0]['content']


def test_native_history_does_not_reintroduce_old_images_under_ablation(tmp_path):
    a=Artifacts(tmp_path/'run',protocol.Config())
    c=ContextBuilder(a,'task',navigation_history=False)
    c.build(obs(1),{})
    photo=a.capture(obs(1))
    c.record(reply('capture'),{'status':'completed','photo':photo})
    c.request_images([photo['id']],'frame_000001')
    first=c.build(obs(2),{})
    assert len(images(first))==2
    c.record(reply('photo_frame',{'mode':'clear'},call_id='call_next'),{'status':'completed','observation':obs(2).public(2.)})
    assert len(images(c.build(obs(3),{})))==1


def test_multiple_native_calls_receive_errors_without_dispatch(tmp_path):
    from test_loop_runtime import setup,Policy
    from drone_agent.agent import AgentLoop
    config,a,b,r=setup(tmp_path)
    multi=reply('act',{'kind':'takeoff'},call_id='call_a')
    multi['tool_calls']+=reply('act',{'kind':'land'},call_id='call_b')['tool_calls']
    seen=[]
    def finish(messages):
        seen.extend(messages)
        current=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
        return reply('finish',{'shot_id':None,'abandon':True},frame=current,call_id='call_end')
    result=AgentLoop(r,Policy([lambda _:multi,finish]),a,config).run()
    assert result['reason']=='agent_abandoned'
    assert b.sent==[]
    results=[m for m in seen if m['role']=='tool']
    assert [m['tool_call_id'] for m in results]==['call_a','call_b']
    assert all(json.loads(m['content'])['status']=='rejected' for m in results)


def test_reused_call_id_never_executes_new_action(tmp_path):
    from test_loop_runtime import setup,Policy
    from drone_agent.agent import AgentLoop
    config,a,b,r=setup(tmp_path)
    def call(name,args,identity):
        def model(messages):
            current=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
            return reply(name,args,frame=current,call_id=identity)
        return model
    policy=Policy([call('photo_frame',{'mode':'clear'},'same'),call('act',{'kind':'takeoff'},'same'),
                   call('finish',{'shot_id':None,'abandon':True},'end')])
    result=AgentLoop(r,policy,a,config).run()
    assert result['reason']=='agent_abandoned'
    assert b.sent==[]
    assert 'duplicate_tool_call_id' in a.trace.read_text()


def test_tool_arguments_use_local_validation_even_when_api_accepts_them():
    message=reply('act',{'kind':'forward','value':1})
    with pytest.raises(ValueError):protocol.parse_tool_decision(message)


def test_native_request_audit_handles_null_assistant_content_and_function_arguments(tmp_path):
    from drone_agent.audit import audit_requests
    from drone_agent.artifacts import write_json
    root=tmp_path/'run';(root/'api').mkdir(parents=True)
    message=reply('photo_frame',{'mode':'clear'})
    write_json(root/'api/call.request.json',{'tools':protocol.native_tool_definitions(),'messages':[
        message,{'role':'tool','tool_call_id':'call_test','content':'{"status":"completed"}'}]})
    assert audit_requests(root)['status']=='passed'
    message['tool_calls'][0]['function']['arguments']='{"height_m":1}'
    write_json(root/'api/call.request.json',{'messages':[message]})
    assert audit_requests(root)['status']=='failed'


def test_native_scripted_policy_still_uses_same_loop(tmp_path):
    from drone_agent.controller import ScriptedPolicy
    from drone_agent.agent import AgentLoop
    from test_loop_runtime import setup
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    script=tmp_path/'script.json'
    script.write_text(json.dumps([{'tool':'capture'},{'tool':'review_photo','arguments':review_arguments()},{'tool':'finish','arguments':{'shot_id':'shot_000001'}}]))
    result=AgentLoop(r,ScriptedPolicy(script),a,config).run()
    assert result['status']=='completed'
    assert result['api_attempts']==0


def test_corrected_protocol_error_does_not_replace_step_budget_reason(tmp_path):
    from drone_agent.agent import AgentLoop
    from test_loop_runtime import setup,Policy
    config,a,b,r=setup(tmp_path,max_steps=2)
    result=AgentLoop(r,Policy([lambda _: {},('photo_frame',{'mode':'clear'})]),a,config).run()
    assert result['reason']=='step_budget'
    assert b.sent==[]


@pytest.mark.parametrize('corruption', ['bad_json','duplicate_ids','unknown_tool','extra_argument',
                                       'invalid_name','long_name','non_ascii_name'])
def test_invalid_native_call_can_be_corrected_without_action_dispatch(tmp_path,corruption):
    from drone_agent.agent import AgentLoop
    from test_loop_runtime import setup,Policy
    config,a,b,r=setup(tmp_path)
    malformed=reply('act',{'kind':'takeoff'})
    function=malformed['tool_calls'][0]['function']
    if corruption=='bad_json':
        function['arguments']='{'
    elif corruption=='duplicate_ids':
        malformed['tool_calls'].append(copy.deepcopy(malformed['tool_calls'][0]))
    elif corruption=='unknown_tool':
        function['name']='execute_code'
    elif corruption in ('invalid_name','long_name','non_ascii_name'):
        function['name']={'invalid_name':'bad tool','long_name':'x'*65,'non_ascii_name':'拍照'}[corruption]
    else:
        arguments=json.loads(function['arguments'])
        arguments['path']='/private/forbidden'
        function['arguments']=json.dumps(arguments)
    seen=[]
    def finish(messages):
        seen.extend(messages)
        current=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
        return reply('finish',{'shot_id':None,'abandon':True},frame=current,call_id='end')
    result=AgentLoop(r,Policy([lambda _:malformed,finish]),a,config).run()
    assert result['reason']=='agent_abandoned'
    assert b.sent==[]
    calls=[call for message in seen for call in message.get('tool_calls',[])]
    responses=[message for message in seen if message['role']=='tool']
    assert [call['id'] for call in calls]==[message['tool_call_id'] for message in responses]
    if corruption in ('bad_json','duplicate_ids','invalid_name','long_name','non_ascii_name'):
        assert not calls
        assert any('protocol_error' in str(message['content']) for message in seen)
    else:
        assert len(responses)==1
        assert json.loads(responses[0]['content'])['status']=='rejected'


def test_native_nested_schema_is_expanded_for_provider_and_retains_validation():
    schemas={t['function']['name']:t['function']['parameters'] for t in protocol.native_tool_definitions()}
    review=schemas['review_photo']
    assert '$ref' not in json.dumps(review) and '$defs' not in review
    check=review['properties']['checks']['items']
    assert set(check['required'])=={'requirement','status','evidence'}
    assert check['additionalProperties'] is False
    assert set(check['properties']['status']['enum'])=={'satisfied','unsatisfied','unknown'}
    rectangle=schemas['photo_frame']['properties']['rectangle']
    assert rectangle['properties']['width']['exclusiveMinimum']==0


def test_nested_protocol_error_exposes_fields_without_raw_inputs(tmp_path):
    from drone_agent.agent import AgentLoop
    from test_loop_runtime import setup,Policy
    config,a,b,r=setup(tmp_path)
    arguments=review_arguments()
    arguments['checks'][0]['check']=arguments['checks'][0].pop('requirement')
    seen=[]
    def corrected(messages):
        seen.extend(json.loads(m['content']) for m in messages if m['role']=='tool')
        current=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
        return reply('finish',{'shot_id':None,'abandon':True},frame=current,call_id='end')
    AgentLoop(r,Policy([('review_photo',arguments),corrected]),a,config).run()
    assert seen[0]['reason']=='invalid_tool_arguments'
    assert {'location':['checks',0,'requirement'],'type':'missing'} in seen[0]['validation_errors']
    assert all(set(e)=={'location','type'} for e in seen[0]['validation_errors'])
