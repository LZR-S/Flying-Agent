"""Single-owner, tick-driven execution. No image interpretation lives here."""
import time
from .backend import Backend
from .protocol import Action, ActionResult


class MissionEnd(RuntimeError):
    pass


class Runtime:
    def __init__(self, backend: Backend, config, artifacts, clock=time.monotonic, preview=None):
        self.backend=backend; self.config=config; self.artifacts=artifacts; self.clock=clock
        self.started=clock(); self.deadline=self.started+config.duration_s
        self.epoch=0; self.results={}; self.identities={}; self.requests=0; self.motion_unknown=False
        self.last_command_at=self.started; self.next_command_at=self.started
        self.recovery_attempted=False; self.landing=None
        self.preview=preview

    def _tick(self):
        self.backend.tick()
        if self.preview is not None:
            self.preview.offer(self.backend.observe(), self.artifacts.photo_frame)

    def check(self):
        if self.clock()>=self.deadline: raise MissionEnd('mission_deadline')
        for name,reason in [('stop.request','operator_stop'),('evaluation/abort.signal','boundary_violation')]:
            if (self.artifacts.directory/name).exists(): raise MissionEnd(reason)
        o=self.backend.observe()
        if not o.connected: raise MissionEnd('link_down')
        boundary=getattr(self.backend,'outside_boundary',None)
        if boundary is not None and boundary(): raise MissionEnd('boundary_violation')
        if self.clock()-o.received_at>self.config.max_image_age_s: raise MissionEnd('stale_image')
        if o.airborne and o.battery_pct<=self.config.min_battery_pct: raise MissionEnd('low_battery')

    def service(self):
        self._tick()
        self.check()
        self._maintain_session()

    def _maintain_session(self):
        o=self.backend.observe()
        if o.airborne:
            idle=self.clock()-self.last_command_at
            if idle>=15.:raise MissionEnd('sdk_idle_timeout')
            if idle>=self.config.keepalive_interval_s:
                if not self.backend.keepalive():raise MissionEnd('sdk_keepalive_failed')
                self.last_command_at=self.clock()
                self.next_command_at=self.last_command_at+self.config.command_gap_s
                # Report what the backend actually sent. Simulation holds position
                # in the controller and sends nothing, so it reports None rather
                # than crediting itself with a hardware keepalive it never issued.
                self.artifacts.event('maintenance',{'command':getattr(self.backend,'keepalive_command',None),
                                                    'source':'runtime','status':'completed'})

    def observe(self):
        self.service()
        o=self.backend.observe()
        self.artifacts.observe(o)
        return o

    def capture(self):
        self.check()
        observation=self.backend.capture()
        self.check()
        return self.artifacts.capture(observation)

    def execute(self, action: Action, identity: str, based_on: str, source='model'):
        if identity in self.identities and self.identities[identity] != action:
            raise ValueError('action_id_conflict')
        if identity in self.results: return self.results[identity]
        self.identities[identity]=action.model_copy()
        if self.motion_unknown and source!='recovery': raise MissionEnd('unknown_action')
        if source!='recovery':
            self.check()
            if self.requests>=self.config.max_actions: raise MissionEnd('action_budget')
            self.requests+=1
        o=self.backend.observe()
        reason=('already_airborne' if action.kind=='takeoff' and o.airborne else
                'already_landed' if action.kind=='land' and o.landed else
                'not_airborne' if action.kind not in ('takeoff','land','hold','speed','stop') and not o.airborne else '')
        event={'action_id':identity,'action':action.model_dump(),'source':source,
               'based_on_frame_id':based_on,'execution_frame_id':o.frame_id,'epoch':self.epoch,'sdk_command':action.sdk_command(),
               'value_unit':'cm' if action.kind in ('forward','back','left','right','up','down') else
                            'degrees' if action.kind in ('cw','ccw') else 'cm/s' if action.kind=='speed' else
                            's' if action.kind=='hold' else None}
        self.artifacts.event('action_requested',event)
        if reason:
            result=ActionResult(action_id=identity,status='rejected',reason=reason)
        else:
            if source!='recovery':
                while self.clock()<self.next_command_at:self.service()
            event['execution_frame_id']=self.backend.observe().frame_id
            self.artifacts.event('action_started',event)
            start=self.clock()
            try:
                self.backend.begin(action,identity)
                while True:
                    self._tick()
                    result=self.backend.poll()
                    if result is not None: break
                    if source=='recovery':
                        if self.clock()-start>=self.config.recovery_s:
                            self.backend.stop_motion()
                            result=ActionResult(action_id=identity,status='unknown',reason='recovery_timeout')
                            break
                    else:
                        self.check()
                        if action.kind=='hold':self._maintain_session()
            except BaseException:
                self.backend.stop_motion()
                result=ActionResult(action_id=identity,status='unknown',reason='execution_interrupted')
                self.results[identity]=result
                self.motion_unknown=True; self.epoch+=1
                self.artifacts.event('action_result',event|result.model_dump())
                raise
        if result.status!='rejected':
            self.last_command_at=self.clock()
            self.next_command_at=self.last_command_at+self.config.command_gap_s
        self.results[identity]=result
        self.artifacts.event('action_result',event|result.model_dump())
        if result.status=='unknown': self.motion_unknown=True; self.epoch+=1
        if action.kind=='land' and result.status!='rejected':
            self.landing={'source':source,'status':result.status,'confirmed':self.backend.observe().landed}
            self.artifacts.event('landing',self.landing)
        return result

    def recover(self):
        if self.recovery_attempted: return
        self.recovery_attempted=True; self.epoch+=1
        self.backend.stop_motion()
        o=self.backend.observe()
        if not o.landed:
            self.execute(Action(kind='land'),'recovery_land',o.frame_id,source='recovery')

    def budgets(self, steps, attempts, shots):
        return {'remaining_s':max(0.,self.deadline-self.clock()),'remaining_steps':max(0,self.config.max_steps-steps),
                'remaining_actions':max(0,self.config.max_actions-self.requests),
                'remaining_api_attempts':max(0,self.config.max_api_attempts-attempts),
                'remaining_photos':max(0,self.config.max_photos-shots),
                'remaining_crops':max(0,self.config.max_crops-self.artifacts.manual_crop_count)}
