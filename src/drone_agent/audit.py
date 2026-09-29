"""Offline audit of the bytes actually sent to the model."""
import base64
import hashlib
import json
import re
from pathlib import Path
import cv2
import numpy as np

PRIVATE_KEYS = frozenset('x_m y_m z_m height_m altitude_m yaw_deg pitch_deg roll_deg position orientation velocity actual_displacement position_bucket clearance_m ground_distance_m forward_clearance_m visited_heading_bins current_node_id'.split())


def _viewfinder_matches(directory, records, label, transmitted):
    annotation=label['viewfinder']
    try:
        record=records[annotation['id']]
        source=records[label['image_id']]
        if record['source_frame_id']!=source['id'] or record['source_sha256']!=source['sha256']:return False
        if any(annotation.get(k)!=record[k] for k in ('id','kind','source_frame_id','captured_at',
                'frame_version','crop_box_px','guides','width_px','height_px','sha256')):return False
        for item in (record,source):
            path=directory/item['path']
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):return False
            if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:return False
        pixels=cv2.imdecode(np.frombuffer((directory/record['path']).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        if pixels is None:return False
        ok,jpeg=cv2.imencode('.jpg',pixels,[cv2.IMWRITE_JPEG_QUALITY,95])
        return ok and jpeg.tobytes()==transmitted
    except (KeyError,TypeError,OSError,cv2.error):
        return False


def audit_requests(directory):
    directory=Path(directory)
    config=json.loads((directory/'launch.json').read_text()) if (directory/'launch.json').exists() else {}
    records=json.loads((directory/'images.json').read_text()) if (directory/'images.json').exists() else {}
    requests=[]
    violations=[]
    for path in sorted((directory/'api').glob('*.request.json')):
        payload=json.loads(path.read_text())
        images=[]
        labels=[]
        preceding_label={}
        texts=[json.dumps(payload.get('tools',[]))]
        for message in payload.get('messages',payload.get('input',[])):
            if message.get('type')=='function_call':texts.append(message['arguments'])
            if message.get('type')=='function_call_output':texts.append(message['output'])
            for call in message.get('tool_calls') or []:
                arguments=call.get('function',{}).get('arguments')
                if isinstance(arguments,str):texts.append(arguments)
            content=message.get('content') or ''
            if isinstance(content,str):
                texts.append(content)
                continue
            for part in content:
                if part.get('type') in ('text','input_text','output_text'):
                    text=part['text'];texts.append(text)
                    try:
                        label=json.loads(text)
                    except (ValueError,TypeError):
                        continue
                    if isinstance(label,dict) and 'image_id' in label:
                        preceding_label=label
                        labels.append({k:v for k,v in label.items() if k!='aliases'})
                        labels.extend(label.get('aliases',[]))
                elif part.get('type') in ('image_url','input_image'):
                    url=part['image_url']['url'] if part['type']=='image_url' else part['image_url']
                    if not url.startswith('data:image/'):
                        violations.append({'request':path.name,'kind':'non_embedded_image'})
                    else:
                        data=base64.b64decode(url.split(',',1)[1],validate=True)
                        images.append({'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
                        if 'viewfinder' in preceding_label and not _viewfinder_matches(directory,records,preceding_label,data):
                            violations.append({'request':path.name,'kind':'viewfinder_evidence_changed',
                                               'frame_id':preceding_label.get('image_id')})
        # Match serialized field names, not model-authored guesses or tool documentation.
        keys={key for text in texts for key in re.findall(r'"([A-Za-z_]+)"\s*:',text)}
        leaked=sorted(keys&PRIVATE_KEYS)
        if leaked:violations.append({'request':path.name,'kind':'private_field','keys':leaked})
        if config.get('navigation_history') is False:
            old=[p for p in labels if p.get('kind')=='navigation' and not p.get('current')]
            if old:violations.append({'request':path.name,'kind':'old_navigation_image','labels':old})
        requests.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'images':images,'image_labels':labels,'private_keys':leaked})
    reference_requests=[]
    for path in sorted((directory/'reference-api').glob('*.request.json')):
        payload=json.loads(path.read_text())
        leaked=sorted(set(re.findall(r'"([A-Za-z_]+)"\s*:',json.dumps(payload)))&PRIVATE_KEYS)
        if leaked:violations.append({'request':path.name,'kind':'private_reference_field','keys':leaked})
        source=directory/'reference-api'/path.name.replace('.request.json','.source.png')
        valid_path=payload.get('source_path')==str(source.relative_to(directory)) and not source.is_symlink()
        digest=hashlib.sha256(source.read_bytes()).hexdigest() if valid_path and source.is_file() else None
        if digest is None or digest!=payload.get('source_sha256'):
            violations.append({'request':path.name,'kind':'reference_source_evidence_changed'})
        reference_requests.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                   'source_sha256':digest,'private_keys':leaked})
    return {'status':'passed' if not violations else 'failed','requests':requests,
            'reference_requests':reference_requests,'violations':violations,
            'scope':'Actual payload field scan and image-byte hashes; complements typed allowlists and counterfactual projection tests. Free text is not proven free of inferred spatial claims.'}
