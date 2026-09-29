"""Post-run evaluation; never imported by the agent or flight policy."""
import csv
import html
import json
import math
from pathlib import Path
from .artifacts import write_json


def read_rows(path):
    if not path.exists():return []
    rows=[]
    for line in path.read_text().splitlines():
        try:rows.append(json.loads(line))
        except json.JSONDecodeError:continue
    return rows


def evaluate_run(directory):
    d=Path(directory);summary=json.loads((d/'summary.json').read_text())
    config=json.loads((d/'configuration.json').read_text())
    truth=read_rows(d/'evaluation/truth.jsonl');events=read_rows(d/'trace.jsonl')
    metrics=read_rows(d/'api-metrics.jsonl')
    reference_metrics=[json.loads(p.read_text()) for p in sorted((d/'reference-metrics').glob('*.json'))]
    primitives=read_rows(d/'backend-commands.jsonl')
    known=bool(truth) and all(isinstance(r.get('contact_heights'),list) for r in truth)
    legacy=not any(h>.5 for r in truth for h in r['contact_heights']) if known else None
    flight_contact=any(r['position'][2]>.3 and bool(r['contact_heights']) for r in truth) if known else None
    landed=None;bounds=None;ratio=None;sim=None;wall=None
    if truth:
        origin=truth[0]['position'];last=truth[-1]
        safety=config.get('safety',config)
        radius=safety.get('max_radius_m',safety.get('radius_m',35.))
        ceiling=safety.get('max_height_m',safety.get('ceiling_m',5.))
        bounds=all(math.hypot(r['position'][0]-origin[0],r['position'][1]-origin[1])<=radius+.15
                   and r['position'][2]<=ceiling+.15 for r in truth)
        tail=[r for r in truth if last['simulation_time']-r['simulation_time']<=.5]
        stable=len(tail)>=2 and last['simulation_time']-tail[0]['simulation_time']>=.3
        if stable:
            dt=last['simulation_time']-tail[0]['simulation_time']
            speed=math.dist(last['position'],tail[0]['position'])/dt
            landed=all(r['position'][2]<=.2 for r in tail) and speed<=.15
        else:landed=last['position'][2]<=.2 if last['position'][2]>.2 else None
        sim=last['simulation_time']-truth[0]['simulation_time']
        wall=last['wall_time']-truth[0]['wall_time']
        ratio=sim/wall if wall>0 else None
    actions=[e['data'] for e in events if e['event']=='action_result']
    actions.extend(dict(e['data']['result'],action=e['data']['action'],source='workflow',phase=e['data'].get('phase'))
                   for e in events if e['event']=='action')
    api_usage=[r.get('usage') for r in metrics]
    def token_total(name):
        values=[u.get(name) if name!='cached_tokens' else (u.get('prompt_tokens_details') or {}).get(name)
                for u in api_usage if isinstance(u,dict)]
        return sum(values) if len(values)==len(metrics) and values and all(v is not None for v in values) else None
    captures=[e for e in events if e['event']=='capture']
    task_start=summary.get('completed_wall_time',0)-summary.get('elapsed_s',0)
    if task_start<=0:
        starts=[e['wall_time'] for e in events if e['event']=='phase' and e['data'].get('phase')=='intent']
        task_start=starts[0] if starts else events[0]['wall_time'] if events else None
    process=json.loads((d/'process.json').read_text()) if (d/'process.json').exists() else {}
    flight_s=sum(b['simulation_time']-a['simulation_time'] for a,b in zip(truth,truth[1:]) if a['position'][2]>.3)
    # A flight clearance result is deliberately separate from photo compliance.
    review_path=d/'photo-review.json'
    review=json.loads(review_path.read_text()) if review_path.exists() else {'compliant':None,'aesthetic_preference':None,'status':'pending_blind_review'}
    flight_ok=None if flight_contact is None else not flight_contact
    selected=summary.get('selected')
    success=(False if not selected or landed is False or bounds is False or flight_ok is False or summary.get('status')!='completed'
             else True if landed is True and bounds is True and flight_ok is True and review.get('compliant') is True
             else False if review.get('compliant') is False else None)
    result={'flight':{'legacy_collision_free':legacy,'airborne_contact_free':flight_ok,
                     'all_contact_samples':sum(bool(r.get('contact_heights')) for r in truth),
                     'bounds_ok':bounds,'landed':landed,'landing_source':(summary.get('landing') or {}).get('source'),
                     'human_collision_geometry_available':config.get('scenario')=='terrace'},
            'timing':{'mission_wall_s':summary.get('elapsed_s'),'truth_wall_s':wall,'simulation_s':sim,
                      'startup_s':None if task_start is None or not process else task_start-process['started_wall_time'],
                      'airborne_simulation_s':flight_s if truth else None,
                      'first_capture_s':captures[0]['wall_time']-task_start if captures and task_start else None,
                      'delivery_s':summary.get('elapsed_s') if summary.get('selected') else None,
                      'sim_wall_ratio':ratio,'comparable':ratio is not None and .9<=ratio<=1.1},
            'photo_review':review,'agent_review':summary.get('selected_review'),
            'reference_generation':{'attempts':len(reference_metrics),
                'duration_s':sum(r['duration_s'] for r in reference_metrics),
                'generated':len(summary.get('references',[])),
                'metrics':reference_metrics},
            'pending_review_id':summary.get('pending_review_id'),
            'composition':{k:summary.get(k) for k in ('framing_policy','frame_contract','composition_feedback','motion_context')},
            'delivery_status':summary.get('status'),'complete_success':success,'selected':selected,
            'delivery':next((p for p in summary.get('shots',[])+summary.get('crops',[])
                             if p['id']==summary.get('selected_id')),None),
            'counts':{'decisions':sum(e['event']=='decision' for e in events),
                      'tool_calls':sum(e['event']=='tool_result' for e in events),
                      'action_requests':summary.get('action_requests',sum(e['event']=='action_started' for e in events)),
                      'backend_commands':sum(e['event']=='backend_command' for e in primitives) if primitives else sum(e['event']=='action_started' for e in events),
                      'photos':len(summary.get('shots',[])), 'crops':len(summary.get('crops',[])),
                      'manual_crops':sum(p.get('derivation','crop_photo')=='crop_photo' for p in summary.get('crops',[])),
                      'framed_photos':sum(p.get('derivation')=='photo_frame' for p in summary.get('crops',[])),
                      'photo_reviews':len(summary.get('photo_reviews',[])),
                      'api_attempts':max(summary.get('api_attempts',0),len(metrics)) if metrics else 0,
                      'rejected':sum(r['status']=='rejected' for r in actions),
                      'unknown':sum(r['status']=='unknown' for r in actions),
                      'recovery_commands':sum(e['event']=='action_started' and e['data'].get('source')=='recovery' for e in events)},
            'api':{'duration_s':sum(r['duration_s'] for r in metrics),
                   'retries':sum(r.get('attempt',1)>1 for r in metrics),
                   'missing_usage_attempts':sum(not isinstance(u,dict) for u in api_usage),
                   **{k:token_total(k) for k in ('prompt_tokens','completion_tokens','total_tokens','cached_tokens')}}}
    from .audit import audit_requests
    audit=audit_requests(d)
    write_json(d/'model-visible-audit.json',audit)
    result['model_input_audit']=audit['status']
    write_json(d/'evaluation.json',result)
    action_rows=[]
    for e in events:
        if e['event']=='action_result':action_rows.append(e['data'])
        elif e['event']=='action':
            data=e['data'];action_rows.append(dict(data['result'],action=data['action'],source='workflow',phase=data.get('phase')))
    with (d/'actions.csv').open('w',newline='') as f:
        fields=['action_id','kind','value','status','reason','source','based_on_frame_id','execution_frame_id','sdk_command','value_unit']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in action_rows:
            action=row.get('action',{});w.writerow({key:(action.get(key) if key in ('kind','value') else row.get(key)) for key in fields})
    metrics=read_rows(d/'api-metrics.jsonl')
    context_builds={e['data']['round']:e['data'] for e in events if e['event']=='context_built'}
    with (d/'api-metrics.csv').open('w',newline='') as f:
        context_fields=['round','image_count','deduplicated_image_count','image_bytes','image_data_url_chars',
                        'fixed_messages_chars','tool_schema_chars','history_chars','state_chars','image_metadata_chars']
        fields=['call_id','attempt','model','duration_s','ok','prompt_tokens','completion_tokens','total_tokens','cached_tokens',
                'context_build_s',*context_fields]
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in metrics:
            context=row.get('context') or {}
            usage=row.get('usage') or {}; w.writerow({**{k:row.get(k) for k in fields[:5]},
              **{k:usage.get(k) for k in fields[5:8]},'cached_tokens':(usage.get('prompt_tokens_details') or {}).get('cached_tokens'),
              'context_build_s':context_builds.get(context.get('round'),{}).get('build_duration_s'),
              **{k:context.get(k) for k in context_fields}})
    render_report(d,summary,result,events)
    return result


def render_report(directory,summary,evaluation,events):
    esc=html.escape
    cards=[]
    for photo in summary.get('shots',[])+summary.get('crops',[]):
        path=Path(photo['path']);path=path.relative_to(directory) if path.is_absolute() else path
        identity=photo.get('id',path.stem)
        label=identity+(' · selected' if identity==summary.get('selected_id') else '')
        cards.append(f'<figure><img src="{esc(path.as_posix())}"><figcaption>{esc(label)}</figcaption>'
                     '<pre>'+esc(json.dumps(photo,ensure_ascii=False,indent=2))+'</pre></figure>')
    rows=[]
    for event in events:
        if event['event'] in ('decision','tool_result','action_result','error','landing','observation','crop',
                              'photo_frame','frame_preview','photo_review','review_checkpoint',
                              'frame_contract','composition_motion','viewfinder',
                              'reference','reference_attempt'):
            data=event['data'];image=(data.get('image',{}).get('path') or data.get('frame_path')) if isinstance(data,dict) else None
            if event['event'] in ('crop','frame_preview','viewfinder','reference'):image=data['path']
            if image and Path(image).is_absolute():image=str(Path(image).relative_to(directory))
            rows.append('<details><summary>'+esc(event['event'])+'</summary>'+
                        (f'<img src="{esc(image)}">' if image else '')+
                        '<pre>'+esc(json.dumps(data,ensure_ascii=False,indent=2))+'</pre></details>')
    report='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>Drone photography run</title>
<style>body{max-width:1100px;margin:40px auto;font:16px/1.5 system-ui;padding:0 20px}img{max-width:100%;max-height:75vh}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{border-top:1px solid #ddd;padding:10px}figure{margin:20px 0}</style>
<h1>Drone Photography — Run evidence</h1>'''
    report+='<p>'+esc(summary['status']+' / '+summary['reason'])+'</p>'+''.join(cards)
    if summary.get('references'):
        report+='<h2>Synthetic composition references — not deliverable photographs</h2>'
        for reference in summary['references']:
            report+=f'<figure><img src="{esc(reference["path"])}"><figcaption>'+esc(
                reference['id']+' · synthetic · source '+reference['source_image_id'])+'</figcaption><pre>'+esc(
                json.dumps(reference,ensure_ascii=False,indent=2))+'</pre></figure>'
    report+='<h2>Agent self-review (not independent evaluation)</h2><pre>'+esc(
        json.dumps(summary.get('photo_reviews',[]),ensure_ascii=False,indent=2))+'</pre>'
    report+='<h2>Independent evaluation</h2><pre>'+esc(json.dumps(evaluation,ensure_ascii=False,indent=2))+'</pre>'
    report+='<h2>Trace</h2>'+''.join(rows)
    (directory/'report.html').write_text(report,encoding='utf-8')
