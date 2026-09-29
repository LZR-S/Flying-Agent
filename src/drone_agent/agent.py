"""A single multimodal decision loop for the complete photography task."""
import queue
import threading
import time
from pydantic import ValidationError
from .context import ContextBuilder
from .protocol import Action, parse_tool_decision, native_tool_definitions, validation_feedback
from .runtime import MissionEnd
from .artifacts import write_json


class AgentLoop:
    def __init__(self, runtime, policy, artifacts, config, *, reference_generator=None):
        self.runtime=runtime; self.policy=policy; self.artifacts=artifacts; self.config=config
        self.context=ContextBuilder(artifacts,config.brief,config.navigation_history,initial_speed_cm_s=config.speed_cm_s)
        self.steps=0
        self.pending_review_id=None
        self.reference_generator=reference_generator
        self.reference_attempts=0

    def _generate_reference(self, arguments, tool_call_id):
        if self.reference_attempts>=self.config.max_references:raise ValueError('reference_budget')
        if self.reference_generator is None or not getattr(self.reference_generator,'available',True):
            raise ValueError('reference_unavailable')
        source=self.artifacts.images.get(arguments['source_id'])
        if source is None or source['id'] not in self.context.visible_images:
            raise ValueError('reference_source_not_visible')
        if (source['kind'] not in ('capture','navigation') or not self.artifacts._evidence_intact(source)
                or self.context.visible_images[source['id']]!=source['sha256']):
            raise ValueError('image_evidence_changed')
        self.runtime.check()
        self.reference_attempts+=1
        identity=f'ref_request_{self.reference_attempts:06}'
        data=self.artifacts.image(source['id']).read_bytes()
        replies=queue.Queue(maxsize=1)
        epoch=self.runtime.epoch
        def call():
            try:
                replies.put((True,self.reference_generator.generate(**arguments,source=data,call_id=identity)))
            except Exception as error:replies.put((False,error))
        started=time.monotonic()
        metric={'request_id':identity,'tool_call_id':tool_call_id,'source_id':source['id'],
                'status':'interrupted','usage':None}
        self.artifacts.event('reference_started',metric)
        threading.Thread(target=call,daemon=True,name='reference-request').start()
        deadline=started+self.config.reference_timeout_s
        try:
            while replies.empty():
                if time.monotonic()>=deadline:raise ValueError('reference_timeout')
                self.runtime.service()
            self.runtime.check()
            if time.monotonic()>=deadline:raise ValueError('reference_timeout')
            if epoch!=self.runtime.epoch:raise MissionEnd('reference_invalidated')
            ok,result=replies.get()
            if not ok:
                allowed={'reference_timeout','reference_http_error','reference_response_too_large',
                         'invalid_reference_response','invalid_reference_image','invalid_reference_dimensions',
                         'reference_base64_required','reference_unavailable'}
                reason=str(result) if isinstance(result,ValueError) and str(result) in allowed else 'reference_failed'
                raise ValueError(reason)
            metric.update(usage=result['usage'],model=result['model'])
            reference=self.artifacts.add_reference(result,source,request_id=identity,tool_call_id=tool_call_id)
            metric.update(status='completed',reference_id=reference['id'])
            requested=[reference['id']]
            if source['kind']=='capture' or self.config.navigation_history:requested.append(source['id'])
            self.context.request_images(requested,self.runtime.backend.observe().frame_id)
            return reference
        except (ValueError,MissionEnd) as error:
            metric.update(status='interrupted' if isinstance(error,MissionEnd) else 'failed',reason=str(error))
            raise
        finally:
            metric['duration_s']=time.monotonic()-started
            self.artifacts.event('reference_attempt',metric)
            write_json(self.artifacts.directory/'reference-metrics'/f'{identity}.json',metric)

    def _require_review(self, photo, tool_call_id):
        self.pending_review_id=photo['id']
        observation=self.runtime.backend.observe()
        self.context.request_photo_comparison(photo,observation.frame_id)
        self.artifacts.event('review_checkpoint',{'status':'required','image_id':photo['id'],
            'image_sha256':photo['sha256'],'tool_call_id':tool_call_id,'airborne':observation.airborne})

    def _decision(self, messages):
        replies=queue.Queue(maxsize=1)
        epoch=self.runtime.epoch
        def call():
            try: replies.put((True,self.policy.complete(messages)))
            except Exception as error: replies.put((False,error))
        thread=threading.Thread(target=call,daemon=True,name='vlm-request')
        thread.start()
        deadline=time.monotonic()+self.config.api_timeout_s
        while replies.empty():
            if time.monotonic()>=deadline: raise MissionEnd('api_timeout')
            self.runtime.service()
        self.runtime.check()
        if time.monotonic()>=deadline: raise MissionEnd('api_timeout')
        if epoch!=self.runtime.epoch: raise MissionEnd('decision_invalidated')
        ok,result=replies.get()
        if not ok: raise result
        return result

    def run(self):
        selected=None; reason='step_budget'; status='incomplete'; failures=0; finished=False
        write_json(self.artifacts.directory/'tool-definitions.json',native_tool_definitions())
        try:
            for self.steps in range(1,self.config.max_steps+1):
                if self.policy.attempts>=self.config.max_api_attempts: raise MissionEnd('api_attempt_budget')
                observation=self.runtime.observe()
                budgets=self.runtime.budgets(self.steps-1,self.policy.attempts,len(self.artifacts.shots))
                budgets['remaining_reference_attempts']=max(0,self.config.max_references-self.reference_attempts)
                budgets['reference_available']=bool(self.reference_generator and
                    getattr(self.reference_generator,'available',True) and self.config.max_references)
                budgets['reference_timeout_s']=self.config.reference_timeout_s
                messages=self.context.build(observation,budgets,pending_review_id=self.pending_review_id)
                self.artifacts.event('inference_started',{'round':self.steps,'based_on_frame_id':observation.frame_id})
                try:
                    raw=self._decision(messages)
                finally:
                    self.artifacts.event('inference_finished',{'round':self.steps})
                try:
                    call_id,d=parse_tool_decision(raw)
                    if call_id in self.context.seen_tool_call_ids:
                        raise ValueError('duplicate_tool_call_id')
                    if d.based_on_frame_id not in self.context.visible_frames:
                        raise ValueError('unseen_frame_reference')
                except (ValidationError,ValueError) as error:
                    failures+=1
                    protocol_reason='invalid_tool_arguments' if isinstance(error,ValidationError) else str(error)
                    result={'status':'rejected','reason':protocol_reason,'pending_review_id':self.pending_review_id}
                    if isinstance(error,ValidationError):
                        result['validation_errors']=validation_feedback(error)
                    result['round_end']=self.context.record_round_end(self.steps,self.runtime.backend.observe())
                    self.artifacts.event('protocol_error',{'round':self.steps,'response':raw,**result})
                    self.context.record(raw,result)
                    if failures>=3: raise MissionEnd('protocol_error_limit')
                    continue
                failures=0
                self.artifacts.event('decision',{'round':self.steps,'tool_call_id':call_id,**d.model_dump()})
                result={'status':'completed'}
                try:
                    if self.pending_review_id is not None:
                        permitted=(d.tool=='view_images' or
                                   d.tool=='act' and d.arguments['kind']=='stop' or
                                   d.tool=='review_photo' and d.arguments['image_id']==self.pending_review_id)
                        if not permitted:raise ValueError('photo_review_pending')
                    if d.tool=='act':
                        action=Action.model_validate(d.arguments)
                        r=self.runtime.execute(action,f'native:{call_id}',d.based_on_frame_id)
                        result=r.model_dump()
                        if r.status=='completed':
                            self.artifacts.record_motion(r.action_id,action,d.based_on_frame_id,d.note)
                        if r.status!='unknown':
                            after=self.runtime.observe()
                            result['observation']=after.public(time.monotonic())
                    elif d.tool=='capture':
                        if len(self.artifacts.shots)>=self.config.max_photos: raise ValueError('photo_budget')
                        photo=self.runtime.capture()
                        result['photo']=photo
                        if 'framed_photo_id' in photo:
                            photo=self.artifacts.images[photo['framed_photo_id']]
                            result['framed_photo']=photo
                        self._require_review(photo,call_id)
                    elif d.tool=='crop_photo':
                        if self.artifacts.manual_crop_count>=self.config.max_crops: raise ValueError('crop_budget')
                        self.runtime.check()
                        photo=self.artifacts.crop_photo(d.arguments)
                        self._require_review(photo,call_id)
                        self.runtime.check()
                        result['photo']=photo
                    elif d.tool=='photo_frame':
                        result['photo_frame']=self.artifacts.configure_photo_frame(d.arguments,self.runtime.backend.observe())
                    elif d.tool=='generate_reference':
                        result['reference']=self._generate_reference(d.arguments,call_id)
                    elif d.tool=='review_photo':
                        result['review']=self.artifacts.review_photo(d.arguments,self.context.visible_images,
                            tool_call_id=call_id,based_on_frame_id=d.based_on_frame_id)
                        if self.pending_review_id==d.arguments['image_id']:
                            self.artifacts.event('review_checkpoint',{'status':'completed',
                                'image_id':self.pending_review_id,'review_id':result['review']['id'],
                                'tool_call_id':call_id,'airborne':self.runtime.backend.observe().airborne})
                            self.pending_review_id=None
                    elif d.tool=='view_images':
                        self.context.request_images(d.arguments['image_ids'],observation.frame_id)
                        result['image_ids']=d.arguments['image_ids']
                    else:
                        if not self.runtime.backend.observe().landed: raise ValueError('landing_required')
                        identity=d.arguments['shot_id']
                        if identity is not None and not any(p['id']==identity for p in self.artifacts.shots+self.artifacts.crops):
                            raise ValueError('unknown_shot_id')
                        if identity is not None:self.artifacts.validate_delivery(identity)
                        review=self.artifacts.valid_review(identity) if identity else None
                        if identity and review is None:raise ValueError('review_required')
                        if review and review['next_step']!='finish':raise ValueError('review_not_final')
                        selected=identity; finished=True
                        reason='agent_finished' if selected else 'agent_abandoned'
                        status=('completed' if review['fulfillment']=='satisfied' else 'partial') if selected else 'incomplete'
                except ValueError as error:
                    result={'status':'rejected','reason':str(error)}
                    if str(error) in ('review_required','review_not_final','review_image_not_visible'):
                        identity=d.arguments.get('shot_id',d.arguments.get('image_id'))
                        self.context.request_images([identity],observation.frame_id)
                    elif str(error)=='fresh_capture_required':
                        identity=d.arguments.get('image_id',d.arguments.get('source_id'))
                        self.context.request_images([identity],observation.frame_id)
                result['pending_review_id']=self.pending_review_id
                if result['status']!='unknown':
                    result['round_end']=self.context.record_round_end(
                        self.steps,self.runtime.backend.observe(),tool_call_id=call_id)
                self.artifacts.event('tool_result',{'round':self.steps,'tool_call_id':call_id,'tool':d.tool,**result})
                self.context.record(raw,result)
                if result['status']=='unknown': raise MissionEnd('unknown_action')
                if finished: break
        except MissionEnd as error:
            reason=str(error); status='aborted'
        except Exception as error:
            reason='api_error' if type(error).__module__.startswith('httpx') else 'runtime_error'
            status='aborted'
            self.artifacts.event('error',{'type':type(error).__name__})
        finally:
            if not finished:
                try: self.runtime.recover()
                except Exception as error:
                    self.artifacts.event('recovery_error',{'type':type(error).__name__})
            landing=self.runtime.landing
            try: landed=self.runtime.backend.observe().landed
            except Exception: landed=False
            self.runtime.epoch+=1
            self.runtime.backend.close()
        return self.artifacts.finish({'status':status,'reason':reason,'selected_id':selected,
            'selected':None if selected is None else self.artifacts.images[selected]['path'],
            'landing':landing,'landed':landed,'agent_finished':finished,'steps':self.steps,
            'pending_review_id':self.pending_review_id,
            'api_attempts':self.policy.attempts,'action_requests':self.runtime.requests,
            'reference_attempts':self.reference_attempts,
            'elapsed_s':time.monotonic()-self.runtime.started,'completed_wall_time':time.time()})
