import copy
import pytest
from drone_agent.baseline_projection import project


def test_projection_removes_pose_but_keeps_image_geometry_and_requested_action():
    internal={'photo_frame':{'center_x':.5,'height_fraction':.8},'height_limits_m':[.3,5],
              'history':[{'proposal':{'action':{'kind':'forward','value':.4},'focus':'subject_scale'},
                          'status':'compared','yaw_deg':100}], 'camera_history':[{'pitch_deg':2}],
              'secret_future_field':23}
    expected={'photo_frame':{'center_x':.5,'height_fraction':.8},
              'history':[{'proposal':{'action':{'kind':'forward','value':.4},'focus':'subject_scale'},'status':'compared'}]}
    assert project(internal,'context')==expected


def test_private_sensor_changes_leave_public_perception_unchanged():
    perception={'observation_id':1,'people':[{'track_id':'p1','bbox':[.1,.2,.3,.4],'confidence':.9,
                 'keypoints':{'nose':[.2,.2,.9]}}],
                'scene':{'x_m':100,'y_m':50,'position_uncertainty_m':1,'clearance_m':{'forward':3},
                         'obstacles':[{'label':'wall','bbox':[.1,.1,.9,.9],'ground_distance_m':5}]}}
    before=project(perception,'perception')
    changed=copy.deepcopy(perception);changed['scene'].update(x_m=-100,y_m=600,clearance_m={'forward':800})
    assert before==project(changed,'perception')
    assert before['people'][0]['keypoints']['nose']==[.2,.2,.9]
    assert before['scene']=={'obstacles':[{'label':'wall','bbox':[.1,.1,.9,.9]}]}


def test_memory_yaw_and_position_buckets_never_transmit():
    memory={'state':'searching','exploration_yaw_deg':20,'memory':{'views':[{'node_id':'a','yaw_deg':5,
             'position_bucket':[4,5],'forward_clearance_m':1}],'last_target_bearing_deg':30,'keyframes':1}}
    assert project(memory,'memory')=={'state':'searching'}


def test_final_v0_payload_invariant_to_telemetry_and_private_memory():
    import sys
    from pathlib import Path
    from dataclasses import replace
    import numpy as np
    baseline=Path(__file__).resolve().parents[1]/'baseline/v0/src'
    if not (baseline/'drone_photography').is_dir():
        pytest.skip('Optional frozen v0 snapshot is not included in the standalone v1 repository')
    sys.path.insert(0,str(baseline))
    from drone_photography.contracts import Observation,Telemetry,CameraCalibration,Person,PhotoIntent,PerceptionFrame,SceneState,Action
    from drone_photography.vlm import CloudClient,PhotoPolicy
    captured=[]
    class Captured(Exception):pass
    def transport(**kwargs):
        captured.append(kwargs['payload']);raise Captured()
    client=CloudClient(api_key='test',base_url='https://test.invalid',transport=transport,max_attempts=1)
    policy=PhotoPolicy(client)
    observation=Observation(1,np.zeros((64,64,3),np.uint8),1.,Telemetry(90,1.5,20,1.),CameraCalibration.from_hfov(64,64))
    person=Person('p1',(.2,.2,.8,.8),.9)
    intent=PhotoIntent('全身照')
    contexts=[{'height_limits_m':[.3,5],'camera_history':[{'pitch_deg':20}],'remaining_s':100},
              {'height_limits_m':[.3,9],'camera_history':[{'pitch_deg':90}],'remaining_s':100}]
    for n in range(2):
        o=replace(observation,telemetry=replace(observation.telemetry,height_m=1.5+n*50,yaw_deg=20+n*100,pitch_deg=n*40))
        try:policy.improve(o,person,intent,contexts[n])
        except Captured:pass
    assert captured[0]==captured[1]
    captured.clear()
    for n in range(2):
        scene=SceneState(x_m=n*100,y_m=n*200,clearance_m={'forward':n+1})
        frame=PerceptionFrame(1,(person,),scene)
        memory={'memory':{'views':[{'node_id':'v1','yaw_deg':n*50,'position_bucket':[n,n]}]}}
        try:policy.choose_search(observation,frame,intent,[Action('forward',.2,action_id='same')],memory)
        except Captured:pass
    assert captured[0]==captured[1]


def test_pose_derived_topological_memory_is_removed():
    a={'state':'searching','boundary_side':'left','detouring':True,'memory':{'keyframes':2,
       'current_node_id':'a','edges':3,'revisits':8,'visited_heading_bins':[1,2],
       'initial_sweep_complete':False,'views':[{'node_id':'a','observed_people_ids':['p1']}]}}
    b={'state':'searching','boundary_side':'right','detouring':False,'memory':{'keyframes':9,
       'current_node_id':'z','edges':20,'revisits':0,'visited_heading_bins':[5,6],
       'initial_sweep_complete':True,'views':[{'node_id':'z','observed_people_ids':['p1']}]}}
    assert project(a,'memory')==project(b,'memory')=={'state':'searching'}
