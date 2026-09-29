"""Fixed, interleaved smoke and formal experiment protocol."""
from pathlib import Path
from .protocol import Config
from .artifacts import write_json


def episode_matrix():
    rows=[{'id':f'smoke-{s}','arm':'v1','scenario':s,'phase':'smoke','repeat':0} for s in ('facing','open','hidden')]
    rows.extend({'id':f'formal-{i}-{arm}','arm':arm,'scenario':'hidden','phase':'formal','repeat':i}
                for i in range(1,4) for arm in ('v0','v1','v1_no_history'))
    return rows


def benchmark(output,*,dry_run=False,phase='all'):
    import json
    from .cli import launch,source_manifest
    output=Path(output).resolve()
    rows=[r for r in episode_matrix() if phase=='all' or r['phase']==phase]
    if dry_run:
        print(json.dumps(rows,ensure_ascii=False,indent=2));return 0
    output.mkdir(parents=True,exist_ok=True)
    frozen=output/'source-manifest.json';current=source_manifest()
    if frozen.exists() and json.loads(frozen.read_text())!=current:
        raise RuntimeError('source changed: start a new experiment directory')
    write_json(frozen,current)
    write_json(output/'protocol.json',{'config':Config().model_dump(),'episodes':episode_matrix()})
    ledger=[]
    for row in rows:
        directory=output/row['id']
        if (directory/'evaluation.json').exists():result=json.loads((directory/'evaluation.json').read_text())
        elif directory.exists():raise RuntimeError('partial episode exists; retain it and resolve explicitly')
        else:
            print('START '+row['id'],flush=True)
            config=Config(scenario=row['scenario'],navigation_history=row['arm']!='v1_no_history',seed=row['repeat'])
            if row['arm']=='v0':
                from .baseline import launch_baseline
                result=launch_baseline(config,directory)
            else:result=launch(config,directory)
        ledger.append(dict(row,result=result))
        write_json(output/f'{phase}-ledger.json',ledger)
        print('DONE '+row['id'],flush=True)
    return 0
