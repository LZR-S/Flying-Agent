"""Immutable image evidence and append-only event records."""
import hashlib
import json
import math
import threading
import time
from pathlib import Path
import cv2
import numpy as np
from .protocol import Config, CropPhoto, Observation, PhotoFrame, ReviewPhoto, TRANSLATIONS, ROTATIONS
from .viewfinder import render_viewfinder


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


class Artifacts:
    def __init__(self, directory: Path, config: Config):
        self.directory=Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.trace=self.directory/'trace.jsonl'
        self.trace.touch(exist_ok=False)
        self.lock=threading.Lock()
        self.images={}
        self.navigation=[]
        self.shots=[]
        self.crops=[]
        self.references=[]
        self.composition_reference=None
        self.photo_frame={'version':0,'rectangle':None}
        self.default_aspect_ratio=config.default_aspect_ratio
        self.default_guides=config.default_guides
        self.framing_policy=config.framing_policy
        self.frame_contract=None
        self.motion_sequence=0
        self.last_motion=None
        self.composition_feedback=None
        self.previews={}
        self.viewfinders={}
        self.reviews=[]
        write_json(self.directory/'configuration.json', config.model_dump())

    def event(self, event, data):
        row={'event':event,'wall_time':time.time(),'monotonic':time.monotonic(),'data':data}
        with self.lock, self.trace.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')

    def observe(self, observation: Observation):
        identity=observation.frame_id
        digest=hashlib.sha256(observation.image_png).hexdigest()
        if identity in self.images:
            if self.images[identity]['sha256'] != digest:
                raise ValueError('frame identity reused with different pixels')
            return self.images[identity]
        record={'id':identity,'kind':'navigation','path':f'frames/{identity}.png',
                'captured_at':observation.captured_at,'sha256':digest,'motion_sequence':self.motion_sequence}
        self._image(record, observation.image_png)
        self.navigation.append(identity)
        self.event('observation', observation.public(time.monotonic()) | {'image':record})
        return record

    def _image(self, record, data):
        path=self.directory/record['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f: f.write(data)
        self.images[record['id']]=record
        write_json(self.directory/'images.json',self.images)

    def capture(self, observation: Observation):
        exposure=self.observe(observation)
        pixels=cv2.imdecode(np.frombuffer(observation.image_png,np.uint8),cv2.IMREAD_UNCHANGED)
        if pixels is None: raise ValueError('invalid_image')
        height,width=pixels.shape[:2]
        identity=f'shot_{len(self.shots)+1:06}'
        record={'id':identity,'kind':'capture','path':f'shots/{identity}.png',
                'source_frame_id':observation.frame_id,'captured_at':observation.captured_at,
                'motion_sequence':exposure['motion_sequence'],
                'width_px':width,'height_px':height,'aspect_ratio':f'{width//math.gcd(width,height)}:{height//math.gcd(width,height)}',
                'sha256':hashlib.sha256(observation.image_png).hexdigest()}
        self._image(record, observation.image_png)
        self.shots.append(record)
        self.event('capture',record)
        if self.photo_frame['rectangle'] is not None:
            framed=self._crop(record,self.photo_frame['rectangle'],'photo_frame',self.photo_frame['version'],
                              self.photo_frame['resolution']['degradation_reason'])
            record['framed_photo_id']=framed['id']
            write_json(self.directory/'images.json',self.images)
        return record

    @property
    def manual_crop_count(self):
        return sum(p['derivation']=='crop_photo' for p in self.crops)

    def initialize_photo_frame(self, observation):
        if self.photo_frame=={'version':0,'rectangle':None}:
            self.configure_photo_frame({'mode':'set','aspect_ratio':(self.frame_contract or {}).get('aspect_ratio',self.default_aspect_ratio)},observation,lock=False)

    def configure_photo_frame(self, arguments, observation, *, lock=True):
        setting=PhotoFrame.model_validate(arguments)
        if setting.mode=='clear' and self.frame_contract is not None:
            raise ValueError('frame_contract_locked')
        frame={'version':self.photo_frame['version']+int(lock),'rectangle':None}
        if setting.mode=='guides':
            if self.photo_frame['rectangle'] is None:raise ValueError('photo_frame_required')
            frame=dict(self.photo_frame,version=frame['version'],guides=setting.guides)
        if setting.mode=='set':
            pixels=cv2.imdecode(np.frombuffer(observation.image_png,np.uint8),cv2.IMREAD_UNCHANGED)
            if pixels is None:raise ValueError('invalid_source_image')
            height,width=pixels.shape[:2]
            maximum=self._maximum_frame(width,height,setting.aspect_ratio)
            rectangle=setting.rectangle.model_dump() if setting.rectangle else maximum
            if self._dimensions(rectangle)['aspect_ratio']!=setting.aspect_ratio:
                raise ValueError('frame_aspect_ratio_mismatch')
            resolution=self._resolution(width,height,rectangle,setting.degradation_reason)
            self._check_frame_contract(self._dimensions(rectangle))
            frame.update(rectangle=rectangle,aspect_ratio=setting.aspect_ratio,resolution=resolution,
                         guides=setting.guides or self.photo_frame.get('guides',self.default_guides))
            if lock:self._bind_frame_contract(self._dimensions(rectangle))
        self.photo_frame=frame
        write_json(self.directory/'photo-frame.json',self.photo_frame)
        self.event('photo_frame',self.photo_frame)
        return dict(self.photo_frame)

    def viewfinder(self, observation):
        if self.photo_frame['rectangle'] is None:return None
        source=self.observe(observation)
        key=(observation.frame_id,self.photo_frame['version'])
        if key in self.viewfinders:return self.viewfinders[key]
        pixels=cv2.imdecode(np.frombuffer(observation.image_png,np.uint8),cv2.IMREAD_COLOR)
        if pixels is None:raise ValueError('invalid_source_image')
        rendered=render_viewfinder(pixels,self.photo_frame)
        ok,png=cv2.imencode('.png',rendered)
        if not ok:raise OSError('viewfinder_encode_failed')
        identity=f'viewfinder_{len(self.viewfinders)+1:06}'
        record={'id':identity,'kind':'viewfinder','path':f'previews/{identity}.png',
                'source_frame_id':observation.frame_id,'source_sha256':source['sha256'],
                'captured_at':observation.captured_at,'frame_version':self.photo_frame['version'],
                'crop_box_px':dict(self.photo_frame['rectangle']),'guides':self.photo_frame['guides'],
                'width_px':pixels.shape[1],'height_px':pixels.shape[0],
                'sha256':hashlib.sha256(png.tobytes()).hexdigest()}
        self._image(record,png.tobytes())
        self.viewfinders[key]=record
        self.event('viewfinder',record)
        return record

    @staticmethod
    def _crop_pixels(data, rectangle):
        pixels=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_UNCHANGED)
        if pixels is None: raise ValueError('invalid_source_image')
        height,width=pixels.shape[:2]
        left,top,w,h=(rectangle[k] for k in ('left','top','width','height'))
        if left+w>width or top+h>height: raise ValueError('crop_out_of_bounds')
        ok,png=cv2.imencode('.png',pixels[top:top+h,left:left+w])
        if not ok: raise OSError('crop_encode_failed')
        return png.tobytes()

    @staticmethod
    def _dimensions(rectangle):
        width,height=rectangle['width'],rectangle['height']
        divisor=math.gcd(width,height)
        return {'width_px':width,'height_px':height,'aspect_ratio':f'{width//divisor}:{height//divisor}'}

    @staticmethod
    def _maximum_frame(width, height, aspect_ratio):
        w,h=map(int,aspect_ratio.split(':'))
        scale=min(width//w,height//h)
        if scale==0:raise ValueError('aspect_ratio_does_not_fit_source')
        w,h=w*scale,h*scale
        return {'left':(width-w)//2,'top':(height-h)//2,'width':w,'height':h}

    def _resolution(self, width, height, rectangle, degradation_reason):
        if rectangle['left']+rectangle['width']>width or rectangle['top']+rectangle['height']>height:
            raise ValueError('crop_out_of_bounds')
        maximum=self._maximum_frame(width,height,self._dimensions(rectangle)['aspect_ratio'])
        count=rectangle['width']*rectangle['height']
        maximum_count=maximum['width']*maximum['height']
        degraded=count<maximum_count
        if degraded and self.framing_policy=='max_native':raise ValueError('maximum_native_frame_required')
        if degraded and degradation_reason is None:raise ValueError('resolution_downgrade_requires_reason')
        return {'source_width_px':width,'source_height_px':height,'pixel_count':count,
                'retained_source_fraction':count/(width*height),
                'maximum_width_px':maximum['width'],'maximum_height_px':maximum['height'],
                'maximum_pixel_count':maximum_count,'retained_max_frame_fraction':count/maximum_count,
                'degraded':degraded,'degradation_reason':degradation_reason}

    def _check_frame_contract(self, dimensions):
        if self.frame_contract and any(dimensions[k]!=v for k,v in self.frame_contract.items()):
            raise ValueError('frame_contract_locked')

    def _bind_frame_contract(self, dimensions):
        if self.framing_policy=='max_native' and self.frame_contract is None:
            self.frame_contract=dict(dimensions)
            self.event('frame_contract',self.frame_contract)

    def validate_delivery(self, identity):
        photo=self.images[identity]
        if self.frame_contract and any(photo[k]!=v for k,v in self.frame_contract.items()):
            raise ValueError('delivery_frame_mismatch')
        if self.framing_policy=='max_native' and photo.get('resolution',{}).get('degraded'):
            raise ValueError('maximum_native_frame_required')

    def record_motion(self, action_id, action, based_on_frame_id, note):
        if action.kind not in (*TRANSLATIONS,*ROTATIONS,'takeoff'):return
        self.motion_sequence+=1
        self.last_motion={'action_id':action_id,'kind':action.kind,'requested_value':action.value,
                          'based_on_frame_id':based_on_frame_id,'note':note,'sequence':self.motion_sequence}
        self.event('composition_motion',self.last_motion)

    def _needs_fresh_capture(self, photo):
        if self.framing_policy!='max_native' or photo['motion_sequence']>=self.motion_sequence:return False
        for review in reversed(self.reviews):
            if review['image_id']==photo['id']:return review['fulfillment']!='satisfied'
        return any(r['source_frame_id']==photo['source_frame_id'] and r['fulfillment']!='satisfied'
                   for r in self.reviews)

    def motion_context(self):
        captures=[p['id'] for p in self.shots if p['motion_sequence']==self.motion_sequence]
        return {'last_motion':self.last_motion,'captures_after_last_motion':captures,
                'capture_after_last_motion_required':bool(self.composition_feedback and self.last_motion and not captures)}

    def frame_preview(self, observation):
        rectangle=self.photo_frame['rectangle']
        if rectangle is None:return None
        self.observe(observation)
        key=(observation.frame_id,self.photo_frame['version'])
        if key in self.previews:return self.previews[key]
        data=self._crop_pixels(observation.image_png,rectangle)
        identity=f'preview_{len(self.previews)+1:06}'
        record={'id':identity,'kind':'preview','path':f'previews/{identity}.png',
                'source_frame_id':observation.frame_id,'captured_at':observation.captured_at,
                'source_sha256':hashlib.sha256(observation.image_png).hexdigest(),
                'frame_version':self.photo_frame['version'],'crop_box_px':dict(rectangle),
                'resolution':dict(self.photo_frame['resolution']),
                **self._dimensions(rectangle),'sha256':hashlib.sha256(data).hexdigest()}
        self._image(record,data)
        self.previews[key]=record
        self.event('frame_preview',record)
        return record

    def crop_photo(self, arguments):
        crop=CropPhoto.model_validate(arguments)
        source=self.images.get(crop.source_id)
        if source is None or source['kind']!='capture': raise ValueError('unknown_source_photo')
        return self._crop(source,crop.model_dump(include={'left','top','width','height'}),'crop_photo',
                          degradation_reason=crop.degradation_reason)

    def _crop(self, source, rectangle, derivation, frame_version=None, degradation_reason=None):
        original=self.image(source['id']).read_bytes()
        if hashlib.sha256(original).hexdigest()!=source['sha256']:raise ValueError('image_evidence_changed')
        resolution=self._resolution(source['width_px'],source['height_px'],rectangle,degradation_reason)
        self._check_frame_contract(self._dimensions(rectangle))
        if derivation=='crop_photo' and self._needs_fresh_capture(source):raise ValueError('fresh_capture_required')
        data=self._crop_pixels(original,rectangle)
        identity=f'crop_{len(self.crops)+1:06}'
        record={'id':identity,'kind':'crop','path':f'crops/{identity}.png',
                'source_shot_id':source['id'],'source_frame_id':source['source_frame_id'],
                'source_sha256':source['sha256'],'captured_at':source['captured_at'],'created_at':time.time(),
                'motion_sequence':source['motion_sequence'],
                'crop_box_px':dict(rectangle),'derivation':derivation,**self._dimensions(rectangle),
                'resolution':resolution,
                'sha256':hashlib.sha256(data).hexdigest()}
        if frame_version is not None:record['frame_version']=frame_version
        self._image(record,data)
        self.crops.append(record)
        self._bind_frame_contract(self._dimensions(rectangle))
        self.event('crop',record)
        return record

    def _evidence_intact(self, photo):
        try:
            if hashlib.sha256(self.image(photo['id']).read_bytes()).hexdigest()!=photo['sha256']:return False
            if photo['kind'] in ('crop','reference'):
                source=self.images[photo['source_shot_id'] if photo['kind']=='crop' else photo['source_image_id']]
                return (source['sha256']==photo['source_sha256'] and
                        hashlib.sha256(self.image(source['id']).read_bytes()).hexdigest()==source['sha256'])
            return True
        except OSError:
            return False

    def add_reference(self, result, source, *, request_id, tool_call_id):
        from .reference import validate_reference_png
        if not self._evidence_intact(source):raise ValueError('image_evidence_changed')
        width,height=validate_reference_png(result['image'])
        identity=f'ref_{len(self.references)+1:06}'
        record={'id':identity,'kind':'reference','synthetic':True,'path':f'references/{identity}.png',
                'source_image_id':source['id'],'source_sha256':source['sha256'],
                'created_at':time.time(),'sha256':hashlib.sha256(result['image']).hexdigest(),
                **self._dimensions({'width':width,'height':height}),
                'model':result['model'],'parameters':result['parameters'],'usage':result['usage'],
                'request_id':request_id,'tool_call_id':tool_call_id}
        self._image(record,result['image'])
        self.references.append(record)
        self.composition_reference=record
        self.event('reference',record)
        return record

    def review_photo(self, arguments, visible_images, *, tool_call_id, based_on_frame_id):
        review=ReviewPhoto.model_validate(arguments)
        photo=self.images.get(review.image_id)
        if photo is None or photo['kind'] not in ('capture','crop'):raise ValueError('unknown_shot_id')
        if review.image_id not in visible_images:raise ValueError('review_image_not_visible')
        if visible_images[review.image_id]!=photo['sha256'] or not self._evidence_intact(photo):
            raise ValueError('image_evidence_changed')
        comparison=review.reference_comparison
        active=self.composition_reference
        if active and (comparison is None or comparison.reference_id!=active['id']):
            raise ValueError('reference_comparison_required')
        reference=None
        if comparison:
            reference=self.images.get(comparison.reference_id)
            if reference is None or reference['kind']!='reference':raise ValueError('unknown_reference_id')
            if reference['id'] not in visible_images:raise ValueError('reference_not_visible')
            if visible_images[reference['id']]!=reference['sha256'] or not self._evidence_intact(reference):
                raise ValueError('image_evidence_changed')
        statuses={check.status for check in review.checks}
        fulfillment='unsatisfied' if 'unsatisfied' in statuses else 'unknown' if 'unknown' in statuses else 'satisfied'
        if fulfillment=='satisfied' and self._needs_fresh_capture(photo):raise ValueError('fresh_capture_required')
        record={'id':f'review_{len(self.reviews)+1:06}',**review.model_dump(exclude_none=True),
                'fulfillment':fulfillment,'image_sha256':photo['sha256'],
                'source_sha256':photo.get('source_sha256',photo['sha256']),
                'source_frame_id':photo['source_frame_id'],'created_at':time.time(),
                'tool_call_id':tool_call_id,'based_on_frame_id':based_on_frame_id,
                'visible_image_ids':list(visible_images)}
        if reference:
            record['reference_sha256']=reference['sha256']
            record['reference_source_sha256']=reference['source_sha256']
            if comparison.use_reference:self.composition_reference=reference
            elif active:self.composition_reference=None
        self.reviews.append(record)
        if fulfillment!='satisfied' or review.next_step=='continue':
            self.composition_feedback={k:record[k] for k in ('image_id','source_frame_id','checks',
                                        'quality_issues','rationale','fulfillment','next_step')}
        else:
            self.composition_feedback=None
        write_json(self.directory/'agent-photo-reviews.json',self.reviews)
        self.event('photo_review',record)
        return record

    def valid_review(self, identity):
        photo=self.images.get(identity)
        if photo is None or not self._evidence_intact(photo):return None
        for review in reversed(self.reviews):
            if (review['image_id']!=identity or review['image_sha256']!=photo['sha256']
                    or review['source_sha256']!=photo.get('source_sha256',photo['sha256'])):continue
            reference_id=review.get('reference_comparison',{}).get('reference_id')
            if self.composition_reference and reference_id!=self.composition_reference['id']:return None
            if reference_id:
                reference=self.images[reference_id]
                if (not self._evidence_intact(reference) or review['reference_sha256']!=reference['sha256']
                        or review['reference_source_sha256']!=reference['source_sha256']):return None
            return review
        return None

    def image(self, identity):
        return self.directory/self.images[identity]['path']

    def finish(self, summary):
        summary=dict(summary, shots=self.shots, crops=self.crops, photo_frame=self.photo_frame,
                     framing_policy=self.framing_policy,frame_contract=self.frame_contract,
                     composition_feedback=self.composition_feedback,motion_context=self.motion_context(),
                     references=self.references,composition_reference=self.composition_reference,
                     photo_reviews=self.reviews, selected_review=self.valid_review(summary.get('selected_id')),
                     selected_photo=self.images.get(summary.get('selected_id')))
        self.event('finish',summary)
        write_json(self.directory/'summary.json',summary)
        return summary
