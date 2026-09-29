import json
from drone_agent.artifacts import write_json
from drone_agent.evaluation import evaluate_run


def run_fixture(tmp_path, *, photos=False):
    d=tmp_path/'run';d.mkdir();(d/'evaluation').mkdir()
    write_json(d/'configuration.json',{'radius_m':35.,'ceiling_m':5.})
    write_json(d/'summary.json',{'status':'aborted','reason':'unknown_action','selected_id':None,
                               'shots':[],'landed':False,'elapsed_s':10.,'landing':None})
    (d/'trace.jsonl').write_text('')
    return d


def test_no_photo_run_still_evaluates_collision_and_landing(tmp_path):
    d=run_fixture(tmp_path)
    rows=[{'wall_time':1.,'simulation_time':0.,'position':[0,0,.1],'contact_heights':[]},
          {'wall_time':11.,'simulation_time':10.,'position':[1,0,1.5],'contact_heights':[1.2]}]
    (d/'evaluation/truth.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    result=evaluate_run(d)
    assert result['flight']['legacy_collision_free'] is False
    assert result['flight']['landed'] is False
    assert result['complete_success'] is False
    assert (d/'report.html').exists()


def test_missing_truth_is_unknown_not_clean_flight(tmp_path):
    result=evaluate_run(run_fixture(tmp_path))
    assert result['flight']['legacy_collision_free'] is None
    assert result['flight']['landed'] is None
    assert result['timing']['comparable'] is False


def test_boundary_and_simulation_speed_are_independent_of_photo(tmp_path):
    d=run_fixture(tmp_path)
    rows=[{'wall_time':1.,'simulation_time':0.,'position':[0,0,.1],'contact_heights':[]},
          {'wall_time':11.,'simulation_time':30.,'position':[40,0,6.],'contact_heights':[]}]
    (d/'evaluation/truth.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    result=evaluate_run(d)
    assert result['flight']['bounds_ok'] is False
    assert result['timing']['sim_wall_ratio']==3.
    assert result['timing']['comparable'] is False


def test_baseline_primitives_and_missing_usage_are_distinct(tmp_path):
    d=run_fixture(tmp_path)
    (d/'backend-commands.jsonl').write_text(json.dumps({'event':'backend_command','wall_time':2.,'data':{'kind':'forward','value':1}})+'\n')
    (d/'api-metrics.jsonl').write_text(json.dumps({'call_id':'c1','attempt':1,'duration_s':3.,'ok':True,'usage':None})+'\n')
    result=evaluate_run(d)
    assert result['counts']['backend_commands']==1
    assert result['counts']['api_attempts']==1
    assert result['api']['prompt_tokens'] is None
    assert result['api']['missing_usage_attempts']==1


def test_terrace_report_recognizes_packaged_subject_collision_geometry(tmp_path):
    d=run_fixture(tmp_path)
    write_json(d/'configuration.json',{'scenario':'terrace','radius_m':35.,'ceiling_m':5.})
    assert evaluate_run(d)['flight']['human_collision_geometry_available'] is True
