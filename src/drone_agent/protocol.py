"""Public contracts contain no flight telemetry or simulator truth."""
import math
import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


ImageID = Annotated[str, Field(pattern=r'^(frame|shot|crop|ref)_[0-9]{6}$')]
PhotoID = Annotated[str, Field(pattern=r'^(shot|crop)_[0-9]{6}$')]
ReviewText = Annotated[str, Field(min_length=1, max_length=1200, pattern=r'\S')]
AspectRatio = Annotated[str, Field(pattern=r'^[1-9][0-9]{0,3}:[1-9][0-9]{0,3}$')]


class Empty(StrictModel):
    pass


TRANSLATIONS = ('forward', 'back', 'left', 'right', 'up', 'down')
ROTATIONS = ('cw', 'ccw')
ACTION_LIMITS = {**{k: (20, 500) for k in TRANSLATIONS}, **{k: (1, 360) for k in ROTATIONS},
                 'speed': (10, 100), 'hold': (0, 30), 'takeoff': (0, 0), 'land': (0, 0), 'stop': (0, 0)}


def action_schema(schema):
    schema['oneOf'] = [
        {'properties': {'kind': {'const': kind}, 'value': {'type': 'integer', 'minimum': low, 'maximum': high}},
         'required': ['kind'] + ([] if low == high == 0 else ['value'])}
        for kind, (low, high) in ACTION_LIMITS.items()
    ]


class Action(StrictModel):
    model_config = ConfigDict(json_schema_extra=action_schema)
    kind: Literal['takeoff','land','forward','back','left','right','up','down','cw','ccw','speed','stop','hold']
    value: int = 0

    @model_validator(mode='before')
    @classmethod
    def required_value(cls, data):
        if isinstance(data, dict) and data.get('kind') not in ('takeoff', 'land', 'stop') and 'value' not in data:
            raise ValueError('this command requires an explicit value')
        return data

    @model_validator(mode='after')
    def bounds(self):
        low, high = ACTION_LIMITS[self.kind]
        if not low <= self.value <= high:
            raise ValueError('action value outside Tello SDK limits')
        return self

    def sdk_command(self):
        if self.kind == 'hold':
            return None
        if self.kind in ('takeoff', 'land', 'stop'):
            return self.kind
        return f'{self.kind} {self.value}'


class ViewImages(StrictModel):
    image_ids: Annotated[list[ImageID], Field(min_length=1, max_length=3)]


class PixelRectangle(StrictModel):
    left: Annotated[int, Field(ge=0)]
    top: Annotated[int, Field(ge=0)]
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class CropPhoto(PixelRectangle):
    source_id: Annotated[str, Field(pattern=r'^shot_[0-9]{6}$')]
    degradation_reason: ReviewText | SkipJsonSchema[None] = Field(
        default=None, description='Only usable when framing_policy=flexible: required for a crop smaller than the maximum native frame. max_native rejects smaller crops even with a reason. Omit otherwise; never null.',
        json_schema_extra=lambda schema: schema.pop('default', None))

    @field_validator('degradation_reason', mode='before')
    @classmethod
    def non_null_reason(cls, value):
        if value is None:raise ValueError('Omit degradation_reason instead of null')
        return value


class PhotoFrame(StrictModel):
    mode: Literal['set', 'clear', 'guides']
    guides: Literal['none', 'thirds', 'golden'] | SkipJsonSchema[None] = Field(
        default=None, description='Optional for set; required for guides mode, which changes annotation only. Omit for clear; never null.',
        json_schema_extra=lambda schema: schema.pop('default', None))
    aspect_ratio: AspectRatio | SkipJsonSchema[None] = Field(
        default=None, description='Required for mode=set: output width:height, e.g. 2:3. Omit for mode=clear. Never null.',
        json_schema_extra=lambda schema: schema.pop('default', None))
    rectangle: PixelRectangle | SkipJsonSchema[None] = Field(
        default=None, description='Omit to use the centered maximum native frame. In max_native mode an optional rectangle may reposition that same size only. In flexible mode a smaller frame requires degradation_reason. Must match aspect_ratio. Omit for mode=clear; never null.',
        json_schema_extra=lambda schema: schema.pop('default', None))
    degradation_reason: ReviewText | SkipJsonSchema[None] = Field(
        default=None, description='Only usable when framing_policy=flexible: required for smaller frames. max_native rejects smaller frames even with a reason. Omit for mode=clear; never null.',
        json_schema_extra=lambda schema: schema.pop('default', None))

    @field_validator('aspect_ratio', 'degradation_reason', 'guides', mode='before')
    @classmethod
    def non_null_setting(cls, value):
        if value is None:raise ValueError('Omit optional fields instead of null')
        return value

    @field_validator('aspect_ratio')
    @classmethod
    def normalized_ratio(cls, value):
        width,height=map(int,value.split(':'))
        divisor=math.gcd(width,height)
        return f'{width//divisor}:{height//divisor}'

    @field_validator('rectangle', mode='before')
    @classmethod
    def rectangle_object(cls, value):
        return PixelRectangle.model_validate(value)

    @model_validator(mode='after')
    def mode_arguments(self):
        if self.mode == 'set' and self.aspect_ratio is None:
            raise PydanticCustomError('frame_aspect_ratio_required', 'aspect_ratio is required for mode=set')
        if self.mode == 'clear' and any(v is not None for v in (self.aspect_ratio,self.rectangle,self.degradation_reason,self.guides)):
            raise PydanticCustomError('frame_settings_forbidden', 'Omit aspect_ratio, rectangle and degradation_reason for mode=clear')
        if self.mode == 'guides' and (self.guides is None or any(v is not None for v in (self.aspect_ratio,self.rectangle,self.degradation_reason))):
            raise PydanticCustomError('guide_settings_required', 'mode=guides requires only guides: none, thirds or golden')
        return self


class RequirementCheck(StrictModel):
    requirement: ReviewText
    status: Literal['satisfied', 'unsatisfied', 'unknown']
    evidence: ReviewText


class GenerateReference(StrictModel):
    source_id: Annotated[str, Field(pattern=r'^(frame|shot)_[0-9]{6}$')]
    guidance: ReviewText
    aspect_ratio: Literal['2:3', '4:3']


class ReferenceComparison(StrictModel):
    reference_id: Annotated[str, Field(pattern=r'^ref_[0-9]{6}$')]
    use_reference: bool
    reason: ReviewText
    differences: Annotated[list[ReviewText], Field(max_length=20)]


class ReviewPhoto(StrictModel):
    image_id: PhotoID
    checks: Annotated[list[RequirementCheck], Field(min_length=1, max_length=20)]
    quality_issues: Annotated[list[ReviewText], Field(max_length=20)]
    next_step: Literal['continue', 'finish']
    rationale: ReviewText
    reference_comparison: ReferenceComparison | SkipJsonSchema[None] = Field(
        default=None, description='Required object when composition_reference is active; otherwise omit.',
        json_schema_extra=lambda schema: schema.pop('default', None))

    @field_validator('reference_comparison', mode='before')
    @classmethod
    def comparison_object(cls, value):
        return ReferenceComparison.model_validate(value)


class Finish(StrictModel):
    shot_id: ImageID | None
    abandon: bool = False

    @model_validator(mode='after')
    def selection(self):
        if (self.shot_id is None) != self.abandon:
            raise ValueError('select a shot or explicitly abandon')
        if self.shot_id and not self.shot_id.startswith(('shot_', 'crop_')):
            raise ValueError('only captured photos or saved crops may be selected')
        return self


ARGUMENTS = {'act': Action, 'capture': Empty, 'crop_photo': CropPhoto,
             'photo_frame': PhotoFrame, 'generate_reference': GenerateReference, 'review_photo': ReviewPhoto,
             'view_images': ViewImages, 'finish': Finish}


class Decision(StrictModel):
    tool: Literal['act', 'capture', 'crop_photo', 'photo_frame', 'generate_reference', 'review_photo', 'view_images', 'finish']
    arguments: dict
    based_on_frame_id: Annotated[str, Field(pattern=r'^frame_[0-9]{6}$')]
    note: Annotated[str, Field(max_length=800)]

    @model_validator(mode='after')
    def tool_arguments(self):
        ARGUMENTS[self.tool].model_validate(self.arguments)
        return self


class Observation(StrictModel):
    frame_id: Annotated[str, Field(pattern=r'^frame_[0-9]{6}$')]
    captured_at: float
    received_at: float
    image_png: bytes
    battery_pct: Annotated[float, Field(ge=0, le=100)]
    connected: bool
    airborne: bool
    landed: bool

    def public(self, now: float) -> dict:
        return {'frame_id': self.frame_id, 'captured_at': self.captured_at,
                'image_age_s': max(0., now-self.received_at), 'battery_pct': self.battery_pct,
                'connected': self.connected, 'airborne': self.airborne, 'landed': self.landed}


class ActionResult(StrictModel):
    action_id: str
    status: Literal['completed', 'rejected', 'unknown']
    reason: str = ''


class Config(StrictModel):
    interaction_protocol: Literal['native-tools-v1'] = 'native-tools-v1'
    control_profile: Literal['tello-sdk-2-basic'] = 'tello-sdk-2-basic'
    speed_cm_s: Annotated[int, Field(ge=10, le=100)] = 50
    command_gap_s: Annotated[float, Field(ge=0.1)] = 0.1
    command_timeout_s: Annotated[float, Field(gt=0)] = 60.
    takeoff_timeout_s: Annotated[float, Field(gt=0)] = 20.
    landing_timeout_s: Annotated[float, Field(gt=0)] = 20.
    keepalive_interval_s: Annotated[float, Field(gt=0, lt=15)] = 5.
    # Simulation-only. Webots models takeoff height and battery drain because
    # nothing else can: the aircraft there is a rigid body with a PID, not a
    # Tello. TelloBackend ignores both and reads the real ToF and battery
    # instead, so setting these on a hardware run changes nothing.
    simulated_takeoff_height_m: Annotated[float, Field(gt=0.2, le=5)] = 1.
    simulated_battery_duration_s: Annotated[float, Field(gt=0)] = 663.
    # Hardware-only. The SDK reaches the aircraft over its own AP; djitellopy
    # defaults to this address, so it is only worth overriding on a fleet. On a
    # simulation run the field is inert -- WebotsBackend never dials anything.
    tello_ip: str = '192.168.10.1'
    video_width: Literal[960] = 960
    video_height: Literal[720] = 720
    video_fps: Literal[30] = 30
    model: str = 'gemini-3.6-flash'
    brief: str = '找到人物，拍一张全身照'
    scenario: Literal['facing', 'open', 'hidden', 'terrace'] = 'hidden'
    navigation_history: bool = True
    framing_policy: Literal['max_native', 'flexible'] = 'max_native'
    default_aspect_ratio: AspectRatio = '16:9'
    default_guides: Literal['none', 'thirds', 'golden'] = 'thirds'
    duration_s: Annotated[float, Field(gt=0)] = 900.
    api_timeout_s: Annotated[float, Field(gt=0)] = 90.
    max_api_attempts: Annotated[int, Field(gt=0)] = 80
    max_steps: Annotated[int, Field(gt=0)] = 160
    max_actions: Annotated[int, Field(gt=0)] = 160
    max_photos: Annotated[int, Field(gt=0)] = 3
    max_crops: Annotated[int, Field(ge=0)] = 6
    max_references: Annotated[int, Field(ge=0, le=3)] = 1
    reference_timeout_s: Annotated[float, Field(gt=0, le=90)] = 70.

    min_battery_pct: Annotated[float, Field(ge=0, le=100)] = 20.
    radius_m: Annotated[float, Field(gt=0)] = 35.
    ceiling_m: Annotated[float, Field(gt=0)] = 5.
    recovery_s: Annotated[float, Field(gt=0)] = 45.
    max_image_age_s: Annotated[float, Field(gt=0)] = 0.75
    seed: int = 0
    image_delay_s: Annotated[float, Field(ge=0)] = 0.
    lost_reply_probability: Annotated[float, Field(ge=0, le=1)] = 0.


TOOL_HELP = {
    'generate_reference': 'Generate a synthetic composition proposal from one real frame_ or original shot_ visible in THIS request. Pass source_id, guidance (visible composition goals, never telemetry) and aspect_ratio (2:3 or 4:3). The original user brief is always included. Use after the subject and relevant scene are visible when a visual goal would help. Optional, normally one attempt per task including failures; may take up to 70 seconds while flight and budgets continue. Returns ref_, never a photograph or navigation evidence. Generated identity, body, background, light or perspective may be wrong; assess fidelity against real images and adopt only achievable framing ideas. Cannot crop, review as a photo, navigate from or deliver ref_. view_images may recall it. An active reference is included in framing and real-photo review; review_photo must include reference_comparison and may set use_reference=false to stop using it. Blocked while a real photo review is pending. A failure permits continuing without a reference.',
    'act': 'One Tello SDK command. Integer centimetres [20,500] for forward/back/left/right/up/down; integer degrees [1,360] for cw/ccw; speed sets cm/s [10,100]. takeoff/land/stop use value=0 or omit it. stop hovers; it does not cut motors. hold is a host-side wait [0,30] integer seconds with automatic keepalive, not an SDK flight command. Left/right follow the camera view. completed means command acknowledged, not measured displacement accuracy or collision-free travel. unknown may have moved and must not be retried. No obstacle guard is available. While pending_review_id is set, only stop is accepted here; ordinary movement and landing wait for that image review. System recovery can still land immediately.',
    'capture': 'Save a fresh complete 960x720 video frame as PNG. This is a stream snapshot, not a separate high-resolution photo command. With an active photo frame, also save a crop_ delivery candidate from that exact exposure and frame version. Both start unreviewed. Sets pending_review_id to the framed crop when present, otherwise the original; review it before ordinary task actions. Uses one photo budget; the automatic framed image does not use the manual crop budget. No synthetic pixels or image compliance gate.',
    'crop_photo': 'Crop a saved original shot_ using integer source pixels: left/top zero-based, width/height positive, fully in bounds. With framing_policy=max_native, only the maximum native size at the locked output ratio is allowed; without a contract the first successful crop locks its ratio and size. A smaller crop is rejected even with degradation_reason. For example 2:3 on 960x720 requires 480x720. A failed source followed by motion returns fresh_capture_required: capture the new viewpoint, or keep the old photo for an honest partial delivery. With framing_policy=flexible only, smaller crops require degradation_reason. Returns crop_, resolution retention and original exposure provenance; no resize, padding or new exposure. Revisions use shot_, never crop_ or frame_. Available before or after landing, within the crop budget. Sets pending_review_id for the actual output.',
    'view_images': 'Read up to three known image IDs from this episode. Compare originals and saved crops using their exact pixels. Navigation history can be disabled; photos, crops and synthetic references remain available. References are advisory only and never expose historical navigation sources when history is disabled. The annotated current full RGB and an active reference stay pinned; during pending review, the candidate comes first and requested comparisons share the remaining slots. Requests exceeding the remaining four-image capacity are listed in omitted_requested_image_ids; compare across turns as needed.',
    'photo_frame': 'Choose the user-requested aspect_ratio before composition or capture using mode=set. Omit rectangle for the centered maximum native frame (2:3 = 480x720, 16:9 = 960x540 on 960x720). The initial default frame is provisional; explicit set or first capture/crop locks the ratio in max_native. A smaller frame, ratio change or clear cannot bypass a locked contract. Same-size in-bounds repositioning is permitted. Optional guides for set: none, thirds or golden. mode=guides requires only guides and changes annotations without moving the frame, locking a provisional ratio or flying. Thin guides are drawn inside the dashed final-photo boundary on the latest full RGB; compose the contents through viewpoint adjustments. Guides are optional aids, not acceptance targets. capture saves a clean new original plus its clean framed crop. In flexible mode only, smaller rectangles require degradation_reason; clear restores original-only capture. clear omits all other fields; optional fields are omitted, never null. All modes wait for pending review; errors preserve state. Viewfinder annotations cannot be delivered or reviewed.',
    'review_photo': 'Review a saved shot_ or crop_ image visible in THIS request. When pending_review_id is set, that exact image must be reviewed first; successful review clears the checkpoint without automatically executing your next step. If absent, use view_images first. Check every explicit user requirement, reporting satisfied/unsatisfied/unknown with visible evidence, remaining quality issues or opportunities (for example head/foot room, tangencies at the head, neck or hands, horizon and line placement, balance), and a reason to continue or finish. Checks refer to the delivered pixels, dimensions and aspect ratio. The runtime binds the review to immutable image/source hashes. New crops need their own review. A previously satisfactory image stays selectable after movement or landing. In max_native mode, a previously failed source cannot be newly marked satisfied after subsequent motion: save a fresh exposure, or retain an unsatisfied/unknown assessment for partial delivery. Failed or continue reviews persist as composition_feedback in subsequent observations. next_step=finish allows selecting it; unsatisfied or unknown checks produce an explicit partial delivery, not a forced retry. When composition_reference is active, include reference_comparison (reference_id, use_reference, reason, differences); the photo and reference must both be visible. Explain fidelity problems and achievable or unachievable differences. Reject a misleading reference with use_reference=false; user requirements still apply. Self-review is not independent evaluation.',
    'finish': 'Select an original shot_ ID or saved crop_ ID in shot_id, or use shot_id=null, abandon=true. Requires dimensions matching frame_contract, confirmed landing and a valid review_photo record with next_step=finish for the selected image. Missing review returns review_required and presents the actual image next turn. This does not issue landing or automatically select/review a photo. Partial compliance can be delivered with an explicit review; abandon needs no selected photo, but an outstanding post-capture review checkpoint must be completed first. System recovery bypasses that checkpoint.',
}


def tool_definitions():
    return [{'name': name, 'description': TOOL_HELP[name], 'parameters': model.model_json_schema()}
            for name, model in ARGUMENTS.items()]


def native_tool_definitions():
    """Attach frame provenance to each native function's existing argument schema."""
    metadata = Decision.model_json_schema()['properties']
    tools = []
    for tool in tool_definitions():
        schema = tool['parameters']
        definitions = schema.pop('$defs', {})
        def expand(node):
            if isinstance(node, list):return [expand(item) for item in node]
            if not isinstance(node, dict):return node
            if '$ref' in node:
                name=node['$ref'].removeprefix('#/$defs/')
                node=definitions[name] | {k:v for k,v in node.items() if k!='$ref'}
            return {key:expand(value) for key,value in node.items()}
        schema=expand(schema)
        schema['properties'].update({k: metadata[k] for k in ('based_on_frame_id', 'note')})
        schema['required'] = list(dict.fromkeys(schema.get('required', []) + ['based_on_frame_id', 'note']))
        tools.append({'type': 'function', 'function': {
            'name': tool['name'], 'description': tool['description'], 'parameters': schema}})
    return tools


def native_calls(message):
    """Validate the replayable wire envelope before interpreting tool arguments."""
    import json
    if not isinstance(message, dict) or message.get('role') != 'assistant':
        raise ValueError('invalid_assistant_message')
    calls = message.get('tool_calls')
    if not isinstance(calls, list) or not calls:
        raise ValueError('native_tool_call_required')
    parsed = []
    seen = set()
    for call in calls:
        if not isinstance(call, dict) or call.get('type') != 'function':
            raise ValueError('invalid_tool_call_type')
        identity = call.get('id')
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 256 or identity in seen:
            raise ValueError('invalid_tool_call_id')
        seen.add(identity)
        function = call.get('function')
        if (not isinstance(function, dict) or not isinstance(function.get('name'), str)
                or re.fullmatch(r'[A-Za-z0-9_-]{1,64}', function['name']) is None):
            raise ValueError('invalid_function_name')
        if not isinstance(function.get('arguments'), str):
            raise ValueError('tool_arguments_must_be_json_string')
        try:
            arguments = json.loads(function['arguments'])
        except json.JSONDecodeError as error:
            raise ValueError('invalid_tool_arguments_json') from error
        if not isinstance(arguments, dict):
            raise ValueError('tool_arguments_must_be_object')
        parsed.append((identity, function['name'], arguments))
    return parsed


def validation_feedback(error: ValidationError):
    expected_types={'model_type':'object','dict_type':'object','list_type':'array',
                    'string_type':'string','int_type':'integer','float_type':'number','bool_type':'boolean'}
    received_types={dict:'object',list:'array',str:'string',int:'integer',float:'number',bool:'boolean',type(None):'null'}
    feedback=[]
    for item in error.errors(include_input=True,include_context=False,include_url=False):
        row={'location':list(item['loc']),'type':item['type']}
        frame_errors={'frame_aspect_ratio_required':('aspect_ratio','aspect_ratio is required for mode=set, e.g. 2:3; omit rectangle to use the maximum native frame.'),
                      'frame_settings_forbidden':('mode','Omit aspect_ratio, rectangle and degradation_reason entirely for mode=clear; do not pass null.')}
        if item['type'] in frame_errors:
            field,message=frame_errors[item['type']]
            row.update(location=[field],message=message)
        expected=expected_types.get(item['type'])
        if expected:
            received=received_types.get(type(item.get('input')),'unknown')
            row.update(expected_type=expected,received_type=received,
                       message=f'Expected {expected}; received {received}.')
            if item['loc']==('rectangle',) and expected=='object':
                row['message']+=' For mode=set, pass a JSON object directly; for mode=clear, omit rectangle entirely.'
                row['example']={'left':0,'top':0,'width':400,'height':600}
        feedback.append(row)
    return feedback


def parse_tool_decision(message):
    calls = native_calls(message)
    if len(calls) != 1:
        raise ValueError('exactly_one_tool_call_required')
    identity, name, arguments = calls[0]
    metadata = {k: arguments.pop(k) for k in ('based_on_frame_id', 'note') if k in arguments}
    decision = Decision.model_validate({'tool': name, 'arguments': arguments, **metadata})
    return identity, decision
