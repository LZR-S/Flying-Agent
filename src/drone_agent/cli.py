"""Local launch, independent evaluation, and frozen benchmark commands."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from .protocol import Config
from .artifacts import write_json
from .provider import load_credentials

ROOT=Path(__file__).resolve().parents[2]
WEBOTS=Path('/Applications/Webots.app/Contents/MacOS/webots')


def source_manifest():
    folders=('src','webots','configs','scripts','baseline/v0/src')
    paths=[p for folder in folders for p in (ROOT/folder).rglob('*')
           if p.is_file() and '__pycache__' not in p.parts and '.DS_Store' not in p.name]
    paths.extend(ROOT/name for name in ('pyproject.toml','requirements.lock','baseline/v0/runner.py','baseline/v0/dependencies.json') if (ROOT/name).exists())
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def launch(config,directory,*,script=None,webots=WEBOTS,baseline_root=None):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=False)
    write_json(directory/'launch.json',config.model_dump())
    write_json(directory/'source-manifest.json',source_manifest())
    command=[str(webots),'--stdout','--stderr','--batch','--mode=realtime',
             str(ROOT/'webots/worlds'/f'bench_photo_{config.scenario}.wbt')]
    if platform.system()=='Darwin' and platform.machine()=='arm64':command=['arch','-arm64']+command
    env=dict(os.environ,DRONE_AGENT_RUN=str(directory),DRONE_AGENT_CONFIG=str(directory/'launch.json'),
             DRONE_AGENT_PYTHON=sys.executable,PYTHONPATH=str(ROOT/'src'),QT_LOGGING_RULES='*.debug=false')
    env.pop('DRONE_AGENT_SCRIPT',None)
    env.pop('DRONE_AGENT_BASELINE',None)
    if baseline_root:
        env['DRONE_AGENT_BASELINE']=str(baseline_root)
        env['DRONE_AGENT_PYTHON']=str(baseline_root/'.venv/bin/python')
        env['PYTHONPATH']=str(baseline_root/'src')
    if script:env['DRONE_AGENT_SCRIPT']=str(Path(script).resolve())
    completion=directory/('baseline.done' if baseline_root else 'summary.json')
    start=time.monotonic();deadline=start+config.duration_s+config.recovery_s+90
    stop_seen=False
    with (directory/'webots.log').open('w') as log:
        process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write_json(directory/'process.json',{'pid':process.pid,'command':command,'started_wall_time':time.time()})
        try:
            while process.poll() is None and not completion.exists() and time.monotonic()<deadline:
                if not stop_seen and (directory/'stop.request').exists():
                    stop_seen=True
                    deadline=min(deadline,time.monotonic()+config.recovery_s+5)
                time.sleep(.25)
        except KeyboardInterrupt:
            (directory/'stop.request').touch()
            end=time.monotonic()+config.recovery_s+5
            while process.poll() is None and not completion.exists() and time.monotonic()<end:time.sleep(.25)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
    if not (directory/'summary.json').exists():
        write_json(directory/'configuration.json',config.model_dump())
        write_json(directory/'summary.json',{'status':'aborted','reason':'operator_stop_no_summary' if stop_seen else 'launcher_no_summary','shots':[],
                    'selected':None,'landing':None,'elapsed_s':time.monotonic()-start})
    write_json(directory/'launcher.json',{'elapsed_s':time.monotonic()-start,'returncode':process.returncode})
    from .evaluation import evaluate_run
    return evaluate_run(directory)


def launch_tello(config,directory,*,script=None,env_file=None,preview=True):
    """Real-aircraft run, in-process: there is no Webots process to supervise.

    A local `subprocess` wrapper would add nothing here, because `tello_node`
    owns the same process the mission runs in. The evidence archive, the
    evaluator and the summary layout are identical to a simulation run, so a
    hardware flight still lands in `runs/` and reads back the same way.
    """
    from . import tello_node
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=False)
    write_json(directory/'launch.json',config.model_dump())
    write_json(directory/'source-manifest.json',source_manifest())
    env=dict(os.environ,DRONE_AGENT_RUN=str(directory),DRONE_AGENT_CONFIG=str(directory/'launch.json'))
    if env_file:env['DRONE_AGENT_ENV_FILE']=str(env_file)
    os.environ.update(env)
    started=time.monotonic()
    tello_node.run(config,directory,preview=preview)
    write_json(directory/'launcher.json',{'elapsed_s':time.monotonic()-started,'backend':'tello'})
    from .evaluation import evaluate_run
    return evaluate_run(directory)


def parser():
    p=argparse.ArgumentParser(description='RGB-driven photography agent')
    sub=p.add_subparsers(dest='command',required=True)
    dashboard=sub.add_parser('dashboard');dashboard.add_argument('--runs',type=Path,default=ROOT/'runs')
    dashboard.add_argument('--port',type=int,default=8766);dashboard.add_argument('--env-file',type=Path,default=ROOT/'.env')
    dashboard.add_argument('--open',action='store_true')
    run=sub.add_parser('run');run.add_argument('--scenario',choices=('facing','open','hidden','terrace'),default='hidden')
    run.add_argument('--brief',default='找到人物，拍一张全身照');run.add_argument('--model',default='gemini-3.6-flash')
    run.add_argument('--no-history',action='store_true');run.add_argument('--env-file')
    run.add_argument('--no-reference',action='store_true',help='Disable optional image generation')
    run.add_argument('--framing-policy',choices=('max_native','flexible'),default='max_native',
                     help='Keep maximum native framing, or explicitly allow resolution downgrades')
    run.add_argument('--default-aspect-ratio',default='16:9')
    run.add_argument('--guides',choices=('none','thirds','golden'),default='thirds')
    run.add_argument('--output',type=Path);run.add_argument('--script',type=Path)
    run.add_argument('--speed',type=int,default=50,help='Tello SDK speed in cm/s (10–100)')
    run.add_argument('--duration',type=float,default=900.);run.add_argument('--webots',type=Path,default=WEBOTS)
    run.add_argument('--backend',choices=('webots','tello'),default='webots',
                     help='webots launches the simulator; tello flies the real aircraft')
    run.add_argument('--tello-ip',default=None,help='Aircraft address (default 192.168.10.1)')
    run.add_argument('--no-preview',action='store_true',help='Skip the dashboard preview writer')
    evaluate=sub.add_parser('evaluate');evaluate.add_argument('directory',type=Path)
    bench=sub.add_parser('benchmark');bench.add_argument('--output',type=Path,required=True)
    bench.add_argument('--env-file');bench.add_argument('--dry-run',action='store_true')
    bench.add_argument('--phase',choices=('smoke','formal','all'),default='all')
    return p


def main():
    args=parser().parse_args()
    if args.command=='dashboard':
        from .dashboard import serve
        return serve(args.runs,port=args.port,env_file=args.env_file,open_browser=args.open)
    if args.command=='evaluate':
        from .evaluation import evaluate_run
        result=evaluate_run(args.directory)
    elif args.command=='benchmark':
        from .benchmark import benchmark
        load_credentials(args.env_file)
        return benchmark(args.output,dry_run=args.dry_run,phase=args.phase)
    else:
        load_credentials(args.env_file)
        config=Config(scenario=args.scenario,brief=args.brief,model=args.model,
                      framing_policy=args.framing_policy,default_aspect_ratio=args.default_aspect_ratio,default_guides=args.guides,
                      navigation_history=not args.no_history,duration_s=args.duration,speed_cm_s=args.speed,
                      max_references=0 if args.no_reference or args.script else 1,
                      **({'tello_ip':args.tello_ip} if args.tello_ip else {}))
        if not args.script and (not os.getenv('DRONE_PHOTO_VLM_BASE_URL') or not os.getenv('DRONE_PHOTO_VLM_API_KEY')):
            raise SystemExit('API credentials required; use --env-file or DRONE_PHOTO_VLM_* environment variables')
        output=args.output or ROOT/'runs'/datetime.now().strftime('%Y%m%d-%H%M%S')
        if args.backend=='tello':
            if args.script:
                raise SystemExit('--script drives the Webots controller only; it cannot fly hardware')
            result=launch_tello(config,output,env_file=args.env_file,preview=not args.no_preview)
        else:
            result=launch(config,output,script=args.script,webots=args.webots)
    print(json.dumps(result,ensure_ascii=False))
    return 0
