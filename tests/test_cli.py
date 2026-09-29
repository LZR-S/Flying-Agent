from drone_agent.cli import parser
from drone_agent.benchmark import episode_matrix


def test_run_defaults_select_requested_model_and_history():
    args=parser().parse_args(['run','--scenario','hidden'])
    assert args.model=='gemini-3.6-flash'
    assert not args.no_history


def test_matrix_contains_smoke_and_interleaved_formal_arms():
    rows=episode_matrix()
    assert len(rows)==12
    assert [r['scenario'] for r in rows[:3]]==['facing','open','hidden']
    assert [r['arm'] for r in rows[3:]]==['v0','v1','v1_no_history']*3
    assert all(r['scenario']=='hidden' for r in rows[3:])


def test_terrace_can_be_selected_for_v1_run():
    from drone_agent.protocol import Config
    args=parser().parse_args(['run','--scenario','terrace'])
    assert Config(scenario=args.scenario).scenario=='terrace'
