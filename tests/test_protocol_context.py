import base64
import hashlib
import json
import cv2
import numpy as np
import pytest
from pydantic import ValidationError
from drone_agent.protocol import Decision, Observation, Config
from drone_agent.artifacts import Artifacts
from drone_agent.context import ContextBuilder
from native_helpers import reply, review_arguments


def obs(seq=1):
    pixels=np.full((12,16,3),[0,0,255],np.uint8)
    pixels[1:]=[seq%256,(seq//256)%256,255]
    ok, image = cv2.imencode('.png',pixels)
    assert ok
    return Observation(frame_id=f'frame_{seq:06}', captured_at=float(seq), received_at=float(seq),
                       image_png=image.tobytes(), battery_pct=90, connected=True, airborne=False, landed=True)


@pytest.mark.parametrize('tool,args', [('act', {'kind':'forward','value':0.1}),
 ('act',{'kind':'forward','value':True}), ('act',{'kind':'takeoff','value':1}),
 ('act',{'kind':'cw','value':361}), ('view_images',{'image_ids':['../../truth.json']}),
 ('view_images',{'image_ids':['frame_000001']*4}), ('finish',{}), ('capture',{'x':1})])
def test_invalid_tool_arguments_never_reach_dispatch(tool,args):
    with pytest.raises(ValidationError):
        Decision.model_validate({'tool':tool,'arguments':args,'based_on_frame_id':'frame_000001','note':''})


def test_observation_public_contract_has_no_internal_pose():
    assert obs().public(now=3) == {'frame_id':'frame_000001','captured_at':1.0,'image_age_s':2.0,
                      'battery_pct':90.0,'connected':True,'airborne':False,'landed':True}


def test_capture_preserves_real_pixels_and_source(tmp_path):
    a=Artifacts(tmp_path/'run', Config())
    o=obs()
    a.observe(o)
    shot=a.capture(o)
    decoded=cv2.imread(str(a.directory/shot['path']))
    assert decoded[0,0].tolist()==[0,0,255]
    assert shot['source_frame_id']==o.frame_id
    with pytest.raises(KeyError): a.image('../../evaluation/truth.jsonl')
    assert a.image(shot['id']).read_bytes()==o.image_png


def images(payload):
    return [part for msg in payload for part in (msg['content'] if isinstance(msg['content'],list) else [])
            if part['type']=='image_url']


def test_model_images_are_jpeg_without_resizing_or_changing_saved_evidence(tmp_path):
    pixels=np.empty((96,128,3),np.uint8)
    pixels[:,:64]=[10,30,220]
    pixels[:,64:]=[220,60,10]
    ok,png=cv2.imencode('.png',pixels)
    assert ok
    observation=obs().model_copy(update={'image_png':png.tobytes()})
    a=Artifacts(tmp_path/'run',Config(framing_policy='flexible'))
    a.configure_photo_frame({'mode':'set','aspect_ratio':'1:1','degradation_reason':'Accept reduced detail for channel verification.','rectangle':{'left':32,'top':16,'width':64,'height':64}},observation)
    shot=a.capture(observation)
    crop=a.images[shot['framed_photo_id']]
    preview=a.frame_preview(observation)
    originals={identity:a.image(identity).read_bytes() for identity in a.images}
    c=ContextBuilder(a,'test')
    c.request_images([shot['id'],crop['id']],observation.frame_id)
    messages=c.build(observation,{})
    labels=[json.loads(p['text']) for p in messages[-1]['content']
            if p['type']=='text' and 'image_id' in json.loads(p['text'])]
    assert [p['image_id'] for p in labels]==[observation.frame_id,shot['id'],crop['id']]
    assert labels[0]['viewfinder']['source_frame_id']==observation.frame_id
    assert all('aliases' not in p for p in labels)
    for label,part in zip(labels,images(messages),strict=True):
        url=part['image_url']['url']
        assert url.startswith('data:image/jpeg;base64,')
        sent=base64.b64decode(url.split(',',1)[1],validate=True)
        assert sent.startswith(b'\xff\xd8')
        identity=label['image_id']
        original=a.image(label['viewfinder']['id']).read_bytes() if 'viewfinder' in label else originals[identity]
        expected=cv2.imdecode(np.frombuffer(original,np.uint8),cv2.IMREAD_COLOR)
        actual=cv2.imdecode(np.frombuffer(sent,np.uint8),cv2.IMREAD_COLOR)
        assert actual.shape==expected.shape
        for x in (8,expected.shape[1]-8):
            np.testing.assert_allclose(actual[8,x],expected[8,x],atol=3,rtol=0)
        assert a.image(identity).read_bytes()==originals[identity]
        assert c.visible_images[identity]==hashlib.sha256(originals[identity]).hexdigest()
        assert hashlib.sha256(sent).hexdigest()!=c.visible_images[identity]
        for alias in label.get('aliases',[]):
            assert c.visible_images[alias['image_id']]==hashlib.sha256(originals[alias['image_id']]).hexdigest()
            assert a.image(alias['image_id']).read_bytes()==originals[alias['image_id']]
    review=a.review_photo(review_arguments(crop['id']),c.visible_images,
                          tool_call_id='review_jpeg',based_on_frame_id=observation.frame_id)
    assert review['image_sha256']==crop['sha256']
    assert a.valid_review(crop['id'])==review


def test_model_encoding_rejects_changed_source_evidence(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    c=ContextBuilder(a,'test')
    c.record_round_end(1,obs(1))
    a.image('frame_000001').write_bytes(obs(1).image_png+b'changed')
    with pytest.raises(ValueError,match='image_evidence_changed'):
        c.build(obs(2),{})


def test_context_history_and_ablation_remove_all_old_navigation_images(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    for n in range(1,5): a.observe(obs(n))
    photo=a.capture(obs(2))
    c=ContextBuilder(a, '找到人物，拍全身照', navigation_history=True)
    c.record_round_end(1,obs(2))
    c.record_round_end(2,obs(3))
    c.record(reply('act',{'kind':'left','value':100}), {'status':'completed'})
    full=c.build(obs(4),{'remaining_s':100})
    assert len(images(full))==3
    assert 'left' in json.dumps(full)
    c.navigation_history=False
    current=c.build(obs(4),{'remaining_s':100})
    assert len(images(current))==1
    with pytest.raises(ValueError): c.request_images(['frame_000001'], 'frame_000004')
    c.request_images([photo['id']], 'frame_000004')
    compared=c.build(obs(4),{'remaining_s':100})
    assert len(images(compared))==2
    assert photo['id'] in json.dumps(compared)


def test_frame_identity_cannot_be_rewritten(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    a.observe(obs(1))
    changed=obs(1).model_copy(update={'image_png':obs(1).image_png+b'x'})
    with pytest.raises(ValueError): a.observe(changed)


def test_no_history_review_of_former_current_does_not_leak_on_next_request(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    c=ContextBuilder(a,'test',navigation_history=False)
    c.build(obs(1),{})
    c.request_images(['frame_000001'],'frame_000001')
    messages=c.build(obs(2),{})
    import json
    shown=[json.loads(x['text'])['image_id'] for x in messages[-1]['content']
           if x['type']=='text' and 'image_id' in json.loads(x['text'])]
    assert shown==['frame_000002']


def test_history_uses_only_previous_round_ends_and_catalog_omits_other_frames(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    c=ContextBuilder(a,'test')
    assert len(images(c.build(obs(1),{})))==1
    for number,frame in [(1,10),(2,20),(3,30)]:
        end=c.record_round_end(number,obs(frame),tool_call_id=f'call_{number}')
        c.record(reply('photo_frame',{'mode':'clear'},call_id=f'call_{number}'),{'status':'completed','round_end':end})
        a.observe(obs(frame+1))
        a.observe(obs(frame+2))
    messages=c.build(obs(40),{})
    labels=[json.loads(p['text']) for p in messages[-1]['content']
            if p['type']=='text' and 'image_id' in json.loads(p['text'])]
    assert [p['image_id'] for p in labels]==['frame_000040','frame_000030','frame_000020']
    assert labels[1]['round_ends']==[{'round':3,'tool_call_id':'call_3'}]
    state=json.loads(messages[-1]['content'][0]['text'])
    assert {p['id'] for p in state['image_catalog']}=={'frame_000040','frame_000030','frame_000020'}
    assert 'frame_000010' in messages[3]['content']
    c.request_images(['frame_000010'],'frame_000040')
    assert 'frame_000010' in json.dumps(c.build(obs(41),{})[-1])


@pytest.mark.parametrize('history',[True,False])
def test_identical_pixels_keep_distinct_evidence_and_do_not_bypass_ablation(tmp_path,history):
    a=Artifacts(tmp_path/'run',Config())
    a.configure_photo_frame({'mode':'clear'},obs())
    original=obs(1)
    current=obs(2).model_copy(update={'image_png':original.image_png})
    shot=a.capture(original)
    c=ContextBuilder(a,'test',navigation_history=history)
    c.record_round_end(1,original)
    c.request_images([shot['id']],'frame_000002')
    messages=c.build(current,{})
    assert len(images(messages))==1
    label=json.loads(messages[-1]['content'][1]['text'])
    assert label['image_id']=='frame_000002' and label['current']
    assert label['aliases'][0]['image_id']==shot['id']
    assert label['aliases'][0]['captured_at']==1. and not label['aliases'][0]['current']
    assert c.visible_frames=={'frame_000002'}
    review=a.review_photo(review_arguments(),c.visible_images,tool_call_id='review',based_on_frame_id='frame_000002')
    assert review['image_sha256']==shot['sha256']
    automatic=c.build(current,{})
    assert len(images(automatic))==1
    assert c.visible_frames==({'frame_000002','frame_000001'} if history else {'frame_000002'})


def test_public_results_keep_required_evidence_without_repeating_review_payload(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    c=ContextBuilder(a,'test')
    photo=a.capture(obs(1))
    c.request_images([photo['id']],'frame_000001')
    c.build(obs(2),{})
    arguments=review_arguments()
    review=a.review_photo(arguments,c.visible_images,tool_call_id='review',based_on_frame_id='frame_000002')
    message=reply('review_photo',arguments,call_id='review')
    message['tool_calls'][0]['extra_content']={'google':{'thought_signature':'opaque-token'}}
    c.record(message,{'status':'completed','review':review,'photo':photo})
    assert c.history[-2]==message
    result=json.loads(c.history[-1]['content'])
    assert result['review']=={'id':'review_000001','image_id':'shot_000001','fulfillment':'satisfied','next_step':'finish'}
    assert result['photo']['source_frame_id']=='frame_000001'
    assert 'path' not in result['photo'] and 'sha256' not in result['photo']
    assert a.reviews[0]['checks']==arguments['checks']
