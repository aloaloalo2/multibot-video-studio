"""Read-only cost attribution from saved OpenRouter usage, with no API requests."""
from __future__ import annotations
import json
import math
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=4096)
def _entry(path, stamp, size):
    try:
        data=json.loads(Path(path).read_text())
        cost=(data.get('usage') or {}).get('cost')
        if not isinstance(cost,(int,float)) or isinstance(cost,bool) or not math.isfinite(cost) or cost<0:
            return None
        messages=data.get('messages') or []
        prompt=messages[0].get('content','') if messages else ''
        if 'YouTube video title' in prompt:
            category='title'
        elif 'Independently compare' in prompt or 'Audit compact narration' in prompt:
            category='checks'
        elif 'Refine these translation units' in prompt or 'Revise only this ONE' in prompt or 'Prepare these NOT YET VOICED' in prompt:
            category='repairs'
        else:
            category='translation'
        return data.get('request_id'),category,str(data.get('requested_model') or data.get('returned_model') or 'Невідома модель'),float(cost)
    except (OSError,ValueError,TypeError,AttributeError):
        return None


def breakdown(folder: Path, saved_total=None):
    categories={key:0. for key in ('translation','title','checks','repairs')}
    models={};seen=set();requests=0;unknown=0
    for path in sorted((folder/'translation-attempts').glob('*/*.json')):
        try:
            stat=path.stat();row=_entry(str(path),stat.st_mtime_ns,stat.st_size)
        except OSError:
            continue
        if row is None:
            unknown+=1;continue
        identity,category,model,cost=row
        if identity and identity in seen:continue
        if identity:seen.add(identity)
        categories[category]+=cost;models[model]=models.get(model,0.)+cost;requests+=1
    total=sum(categories.values())
    if isinstance(saved_total,(int,float)) and math.isfinite(saved_total) and saved_total>total+.0001:
        categories['unattributed']=saved_total-total;total=saved_total
    return {'total_usd':round(total,8),'categories':{k:round(v,8) for k,v in categories.items()},
            'models':{k:round(v,8) for k,v in models.items()},'requests':requests,'unknown_usage':unknown,
            'scope':'project_language_history'}
