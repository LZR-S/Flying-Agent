"""Model-input-only projections for the frozen v0 comparator (Python 3.9 compatible)."""
from dataclasses import asdict,is_dataclass

# Explicit image-space and model-authored evidence vocabulary. Unregistered fields are dropped.
IMAGE_KEYS=set('''observation_id track_id bbox confidence detector_confidence keypoints appearance
subject_fraction center_x center_y horizontal_error vertical_error subject_bbox height_fraction
body_height_fraction source_dimensions crop_bounds bounds dimensions aspect_ratio native_pixel_count
retained_pixel_fraction native_detail eye_separation_px shoulder_span_px sensor_portrait_ceiling
projected_keypoints shot_size detected_frame_margins top bottom left right crop_geometry visual_review
size completeness aspect brief horizontal_placement vertical_placement compliant criteria measurements issues
head_visible feet_visible margin satisfied evidence body_complete composition_satisfied blocking_issues refinements
preferred rationale reason accepted judgment status focus focus_region techniques intended_photo visible_support
preserve risk_or_loss expected_effect action kind value candidate_id incumbent_id observation_id proposal experiment
confidence options id selected_option_id chosen_option_id benefit cost risk alternatives tool arguments
photo_frame incumbent_frame candidate_frame incumbent candidate comparison source_id source_path delivery path
call frame feedback review measurements frame_attempts refinement_attempted resolution_refinement_available
remaining_candidates remaining_s remaining_frame_changes remaining_camera_changes frame_history frame_feedback
history generated_reference synthetic model source_analysis composition_notes photo_frame_before photo_frame_after
scale translation_px old_bounds new_bounds before_frame after_frame target_region_complete native_pixel_gain
subject_scale placement_balance gaze_space background_separation lines_horizon light_color style_match
nose left_eye right_eye left_ear right_ear left_shoulder right_shoulder left_elbow right_elbow left_wrist right_wrist
left_hip right_hip left_knee right_knee left_ankle right_ankle'''.split())
CONTEXT_KEYS=set('''photo_frame frame_history frame_feedback resolution_refinement_available remaining_frame_changes
remaining_candidates remaining_s generated_reference history'''.split())
MEMORY_KEYS=set('state visible_track_ids confirmed_track_id'.split())


def plain(value):
    return asdict(value) if is_dataclass(value) else value


def filter_tree(value,keys):
    value=plain(value)
    if isinstance(value,dict):return {k:filter_tree(v,keys) for k,v in value.items() if k in keys}
    if isinstance(value,(list,tuple)):return [filter_tree(v,keys) for v in value]
    return value


def project(value,kind):
    value=plain(value)
    if value is None:return None
    if kind=='telemetry':return {k:value[k] for k in ('battery_pct','connected','airborne') if k in value}
    if kind=='context':return {k:filter_tree(v,IMAGE_KEYS) for k,v in value.items() if k in CONTEXT_KEYS}
    if kind=='memory':return filter_tree(value,MEMORY_KEYS)
    if kind=='perception':
        scene=plain(value.get('scene',{}))
        return {'observation_id':value.get('observation_id'),'people':filter_tree(value.get('people',[]),IMAGE_KEYS),
                'scene':{'obstacles':[{'label':o['label'],'bbox':list(o['bbox'])} for o in scene.get('obstacles',[])]}}
    if kind=='evidence':return filter_tree(value,IMAGE_KEYS)
    raise ValueError('unregistered projection kind')
