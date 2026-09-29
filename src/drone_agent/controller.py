"""Webots main-thread entry point."""
import json
import os
import time
from pathlib import Path
from .protocol import Config
from .artifacts import Artifacts,write_json
from .runtime import Runtime
from .agent import AgentLoop
from .webots_backend import WebotsBackend
from .provider import CloudPolicy


class ScriptedPolicy:
    """Explicit user-supplied decision script for controller integration checks."""
    def __init__(self,path):
        self.items=iter(json.loads(Path(path).read_text()));self.attempts=0;self.calls=0
    def complete(self,messages):
        item=next(self.items)
        current=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
        self.calls+=1
        arguments=dict(item.get('arguments',{}),based_on_frame_id=current,note='scripted engineering check')
        return {'role':'assistant','content':None,'tool_calls':[{'id':f'script_{self.calls:06}',
            'type':'function','function':{'name':item['tool'],'arguments':json.dumps(arguments)}}]}


def main():
    from controller import Robot
    directory=Path(os.environ['DRONE_AGENT_RUN'])
    config=Config.model_validate_json(Path(os.environ['DRONE_AGENT_CONFIG']).read_text())
    artifacts=Artifacts(directory,config)
    from .preview import PreviewWriter
    preview=PreviewWriter(directory)
    try:
        backend=WebotsBackend(Robot(),config)
        runtime=Runtime(backend,config,artifacts,preview=preview)
        script=os.getenv('DRONE_AGENT_SCRIPT')
        policy=ScriptedPolicy(script) if script else CloudPolicy(config,artifacts)
        from .reference import ReferenceGenerator
        generator=ReferenceGenerator(config,artifacts) if config.max_references and not script else None
        AgentLoop(runtime,policy,artifacts,config,reference_generator=generator).run()
    except Exception as error:
        artifacts.event('controller_error',{'type':type(error).__name__})
        if not (directory/'summary.json').exists():
            artifacts.finish({'status':'aborted','reason':'controller_initialization_error',
                              'selected':None,'selected_id':None,'landing':None,'landed':False})
    finally:
        preview.close()
