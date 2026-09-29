"""Audited, bounded Chat Completions client; credentials never enter artifacts."""
import base64
import json
import os
import shlex
import time
from pathlib import Path
import httpx
from .artifacts import write_json
from .runtime import MissionEnd
from .protocol import native_tool_definitions
from .responses import ResponsesAdapter


def load_credentials(path=None):
    values=dict(os.environ)
    if path:
        aliases={'BASE_URL':'DRONE_PHOTO_VLM_BASE_URL','API_KEY':'DRONE_PHOTO_VLM_API_KEY'}
        for line in Path(path).read_text().splitlines():
            line=line.strip().removeprefix('export ')
            if not line or line.startswith('#') or '=' not in line:continue
            key,value=line.split('=',1);key=key.strip()
            if key in ('BASE_URL','API_KEY','DRONE_PHOTO_IMAGE_BASE_URL','DRONE_PHOTO_IMAGE_API_KEY',
                       'DRONE_PHOTO_VLM_BASE_URL','DRONE_PHOTO_VLM_API_KEY'):
                values[key]=' '.join(shlex.split(value,comments=True))
                if key in aliases or key.startswith('DRONE_PHOTO_VLM_'):
                    os.environ[aliases.get(key,key)]=values[key]
    from .reference import reference_environment
    image_environment=reference_environment(values)
    for key in ('DRONE_PHOTO_IMAGE_BASE_URL','DRONE_PHOTO_IMAGE_API_KEY'):os.environ.pop(key,None)
    os.environ.update(image_environment)


class CloudPolicy:
    def __init__(self,config,artifacts,*,base_url=None,api_key=None,transport=None):
        self.config=config;self.artifacts=artifacts;self.attempts=0;self.calls=0
        self.base_url=(base_url or os.getenv('DRONE_PHOTO_VLM_BASE_URL') or '').rstrip('/')
        self.api_key=api_key or os.getenv('DRONE_PHOTO_VLM_API_KEY')
        if not self.api_key or not self.base_url:raise ValueError('API endpoint and key required')
        parsed=httpx.URL(self.base_url)
        if parsed.path in ('','/'):self.base_url+='/v1'
        self.transport=transport
        self.responses=ResponsesAdapter() if config.model=='gpt-6-astra' else None

    def complete(self,messages):
        if self.attempts>=self.config.max_api_attempts:raise MissionEnd('api_attempt_budget')
        self.calls+=1;call_id=f'call_{self.calls:06}'
        payload={'model':self.config.model,'messages':messages,'temperature':0,
                 'tools':native_tool_definitions(),'tool_choice':'auto','parallel_tool_calls':False}
        if self.config.model=='qwen3.8-flash':
            payload['enable_thinking']=False
            payload['tool_choice']='required'
        if self.responses:
            payload=self.responses.request(self.config.model,messages,payload['tools'])
        endpoint='/responses' if self.responses else '/chat/completions'
        context_metrics=_request_sizes(payload)
        write_json(self.artifacts.directory/'api'/f'{call_id}.request.json',payload)
        start=time.monotonic();deadline=start+self.config.api_timeout_s
        with httpx.Client(transport=self.transport,trust_env=False) as client:
            for attempt in range(2):
                if self.attempts>=self.config.max_api_attempts:raise MissionEnd('api_attempt_budget')
                remaining=deadline-time.monotonic()
                if remaining<=0:raise MissionEnd('api_timeout')
                self.attempts+=1;began=time.monotonic();response=None;usage=None;ok=False
                try:
                    response=client.post(self.base_url+endpoint,
                        headers={'Authorization':'Bearer '+self.api_key},json=payload,timeout=remaining)
                    response.raise_for_status()
                    body=response.json()
                    usage=self.responses.usage(body) if self.responses else body.get('usage')
                    write_json(self.artifacts.directory/'api'/f'{call_id}.response.json',body)
                    message=self.responses.message(body) if self.responses else body['choices'][0]['message']
                    ok=True
                    return message
                except (httpx.TransportError,httpx.HTTPStatusError) as error:
                    status=response.status_code if response is not None else None
                    retryable=status is None or status==429 or status>=500
                    if attempt or not retryable:raise error
                finally:
                    row={'call_id':call_id,'attempt':attempt+1,'global_attempt':self.attempts,
                         'model':self.config.model,'duration_s':time.monotonic()-began,
                         'ok':ok,'http_status':None if response is None else response.status_code,'usage':usage,
                         'context':context_metrics}
                    with (self.artifacts.directory/'api-metrics.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                    self.artifacts.event('api_attempt',row)


def _request_sizes(payload):
    messages=payload.get('messages',payload.get('input',[]))
    content=messages[-1].get('content') if messages else None
    parts=content if isinstance(content,list) else []
    state={};state_chars=0;label_chars=0;aliases=0;image_bytes=0;image_url_chars=0;image_count=0
    for part in parts:
        if part['type'] in ('text','input_text'):
            try:label=json.loads(part['text'])
            except (ValueError,TypeError):continue
            if not isinstance(label,dict):continue
            if label.get('message_kind')=='runtime_observation':
                state=label;state_chars+=len(part['text'])
            elif 'image_id' in label:
                label_chars+=len(part['text']);aliases+=len(label.get('aliases',[]))
        elif part['type'] in ('image_url','input_image'):
            url=part['image_url']['url'] if part['type']=='image_url' else part['image_url']
            image_count+=1;image_url_chars+=len(url)
            image_bytes+=len(base64.b64decode(url.split(',',1)[1],validate=True))
    def chars(value):return len(json.dumps(value,ensure_ascii=False,separators=(',',':')))
    return {'round':state.get('round'),'image_count':image_count,'deduplicated_image_count':aliases,
            'image_bytes':image_bytes,'image_data_url_chars':image_url_chars,
            'fixed_messages_chars':chars(messages[:2]),'tool_schema_chars':chars(payload['tools']),
            'history_chars':chars(messages[2:-1] if state else messages[2:]),
            'state_chars':state_chars,'image_metadata_chars':label_chars}
