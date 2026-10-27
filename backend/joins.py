"""Validated transitions attached to actual touching scene/clip boundaries."""
import copy
import uuid
import json
from pathlib import Path

GRAPHIC_PRESETS=json.loads((Path(__file__).resolve().parents[1]/'frontend'/'graphic-transitions.json').read_text())
TYPES={'cut','crossfade','slide_left','slide_right','slide_up','slide_down','zoom_in','zoom_out'}|set(GRAPHIC_PRESETS)
def members(project,ref):
    clips={c['id']:c for t in project.get('tracks',[]) for c in t.get('clips',[])}
    if isinstance(ref,str) and ref.startswith('group:'):
        group=next((g for g in project.get('scene_groups',[]) if g['id']==ref[6:] and g.get('role')!='overlay'),None)
        if not group:raise ValueError('Scene not found')
        result=[clips[cid] for cid in group['clip_ids'] if cid in clips]
    elif isinstance(ref,str) and ref.startswith('clip:') and ref[5:] in clips:result=[clips[ref[5:]]]
    else:raise ValueError('Invalid transition endpoint')
    if not result or any(c['kind']=='audio' for c in result):raise ValueError('A transition requires visual clips')
    return result

def boundary(project,left,right):
    if not isinstance(left,str) or not isinstance(right,str) or left==right or left.split(':')[0]!=right.split(':')[0]:raise ValueError('Choose two adjacent frames')
    a,b=members(project,left),members(project,right)
    start=min(c['start'] for c in a);seam=max(c['start']+c['duration'] for c in a);following=min(c['start'] for c in b);end=max(c['start']+c['duration'] for c in b)
    if abs(seam-following)>1/max(1,project.get('fps',25))+.001:raise ValueError('Transitions can only be dropped onto touching frame edges')
    return seam,min(seam-start,end-following),a,b

def set_transition(project,payload):
    kind=payload.get('type')
    if kind not in TYPES:raise ValueError('Unknown transition')
    seam,maximum,a,b=boundary(project,payload.get('from_ref'),payload.get('to_ref'))
    duration=float(payload.get('duration',.35))
    if kind!='cut' and not .05<=duration<=min(2,maximum):raise ValueError('Transition is longer than an adjacent frame')
    old=project.get('join_transitions',[])
    project['join_transitions']=[j for j in old if j['id']!=payload.get('move_from') and j['from_ref']!=payload['from_ref'] and j['to_ref']!=payload['to_ref']]
    if kind!='cut':project['join_transitions'].append(dict(id=uuid.uuid4().hex[:12],from_ref=payload['from_ref'],to_ref=payload['to_ref'],type=kind,duration=duration,seam=seam))

def reconcile(project):
    valid=[]
    for join in project.get('join_transitions',[]):
        try:seam,maximum,_,_=boundary(project,join['from_ref'],join['to_ref'])
        except (ValueError,KeyError,TypeError):continue
        if join['duration']<=maximum:valid.append({**join,'seam':seam})
    if 'join_transitions' in project:project['join_transitions']=valid

def transport(project,layers):
    rendered={c['id']:c for layer in layers for c in layer['clips']}
    protected_text_ids=set()
    overlay_ids={cid for group in project.get('scene_groups',[]) if group.get('role')=='overlay' for cid in group['clip_ids']}
    brand_index=next((i for i,layer in enumerate(layers) if any(c['id'] in overlay_ids for c in layer['clips'])),len(layers))
    for join in project.get('join_transitions',[]):
        _,_,outgoing,incoming=boundary(project,join['from_ref'],join['to_ref'])
        effect={key:join[key] for key in ('type','duration','seam')}
        for source in incoming:
            if source['id'] not in rendered:continue
            if source.get('kind')=='text' and source.get('text_role')=='full_frame':
                protected_text_ids.add(source['id'])
            else:rendered[source['id']]['join_in']=effect
        for source in outgoing:
            if source['id'] not in rendered or abs(source['start']+source['duration']-join['seam'])>.05:continue
            clip=rendered[source['id']];clip['join_out']=effect;old=clip['duration'];clip['native_duration']=old;clip['duration']=old+join['duration']
            points=clip.get('keyframes',[])
            if points:
                extra={'time':clip['duration']}
                for prop in ('x','y','scale','opacity'):
                    known=[{'time':0,prop:clip.get(prop,1 if prop in {'scale','opacity'} else .5)}]+[p for p in points if prop in p]
                    last=known[-1];previous=known[-2] if len(known)>1 else last
                    value=last[prop]+(last[prop]-previous[prop])/max(.001,last['time']-previous['time'])*join['duration']
                    extra[prop]=max(0,min(1,value)) if prop=='opacity' else value
                clip['keyframes']=[*points,extra]
        if join['type'] in GRAPHIC_PRESETS:
            layers.append(dict(id='graphic-'+join['id'],z=brand_index-.5,clips=[dict(id='graphic-'+join['id'],type='animation',content_type='graphic_transition',graphic_style=join['type'],start=join['seam'],duration=join['duration'],trim_start=0,x=.5,y=.5,width=1.,height=1.,opacity=1,volume=0,easing='linear')]))
    for layer in list(layers):
        moved=[clip for clip in layer['clips'] if clip['id'] in protected_text_ids]
        if moved:
            layer['clips']=[clip for clip in layer['clips'] if clip['id'] not in protected_text_ids]
            layers.append(dict(id='transition-text-'+layer.get('id','layer'),z=brand_index-.25,clips=moved))
