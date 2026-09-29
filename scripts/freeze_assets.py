"""Hash available pinned Webots dependencies, traversing literal resource references."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin
ROOT=Path(__file__).resolve().parents[1]
CACHE=Path.home()/'Library/Caches/Cyberbotics/Webots/assets'
manifest=json.loads((ROOT/'configs/assets.json').read_text())
pending=list(manifest['remote_resources']);resources={};missing=[]
while pending:
    url=pending.pop()
    if url in resources or url in missing:continue
    path=CACHE/hashlib.sha1(url.encode()).hexdigest()
    if not path.exists():missing.append(url);continue
    data=path.read_bytes();resources[url]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    if url.endswith('.proto'):
        for ref in re.findall(r'["\']([^"\'\n]+\.(?:proto|png|jpg|jpeg|hdr|obj|dae))["\']',data.decode()):
            if ref.startswith('webots://'):ref=ref.replace('webots://','https://raw.githubusercontent.com/cyberbotics/webots/R2025a/')
            child=urljoin(url,ref)
            if child.startswith('https://raw.githubusercontent.com/cyberbotics/webots/R2025a/'):
                pending.append(child)
manifest['cached_resource_hashes']=resources
manifest['unresolved_literal_references']=missing
manifest['resource_scope']='Literal PROTO references; dynamic template resource paths are resolved by Webots R2025a.'
(ROOT/'configs/assets.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'hashed_dependencies':len(resources),'unresolved_literals':len(missing)}))
