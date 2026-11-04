"""Channel logos are live references to channel settings, with immutable render snapshots."""
from __future__ import annotations
import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
import channel_branding
import store

LOGO_TITLE = "Логотип каналу"
LOCK = threading.RLock()


def clips(project: dict):
    assets={a.get('id'):a for a in project.get('assets',[])}
    def managed(clip):
        asset=assets.get(clip.get('asset_id'),{})
        return (clip.get('channel_logo') is True or clip.get('title')==LOGO_TITLE
                or asset.get('source')=='channel-logo'
                or (clip.get('title')=='Плашка каналу' and Path(asset.get('path','')).name=='channel_logo.png'))
    return [(track,clip) for track in project.get('tracks',[]) for clip in track.get('clips',[]) if managed(clip)]


def bind(project: dict) -> dict:
    """Resolve the latest channel logo without writing project history or changing a running export.

    A prepared export already holds an immutable PNG path. A fresh project read
    resolves the current source and placement, including old copied channel_logo.png layers.
    """
    cid=project.get('channel_id')
    if not cid:return project
    try:
        folder=store.get_channel_folder(cid,include_disabled=True)
    except store.StudioError:
        return project
    spec=channel_branding.placement((store.read_json(folder/store.PLAN_CONFIG,{}) or {}).get('logo'))
    source=channel_branding.logo_path(cid)
    current=clips(project)
    duration=float(project.get('duration') or 0)
    visible=spec['enabled'] and source.is_file() and duration>0 and bool(current or store.film_clips(project))
    stamp=None
    if visible:
        stat=source.stat()
        width,height=int(project.get('width') or 1920),int(project.get('height') or 1080)
        stamp=hashlib.sha256(json.dumps([stat.st_mtime_ns,stat.st_size,spec,width,height],sort_keys=True).encode()).hexdigest()[:24]
        target=store.DATA_ROOT/'channels'/cid/'overlays'/f'{stamp}.png'
        with LOCK:
            if not target.is_file():
                temp=target.with_name(f'.{uuid.uuid4().hex}.png')
                try:
                    channel_branding.overlay_png(cid,spec,(width,height),temp)
                    os.replace(temp,target)
                finally:
                    temp.unlink(missing_ok=True)
    project['branding_version']=stamp or 'off'
    if not current and not visible:return project
    # Keep one stable clip/row identity so selection and saved references survive replacement.
    track,clip=current[0] if current else ({'id':'channel-logo-layer','name':LOGO_TITLE,'type':'universal','clips':[]},
        {'id':'channel-logo-clip','kind':'image','start':0,'duration':duration,'trim_start':0,'volume':1,
         'x':.5,'y':.5,'width':1,'height':1,'scale':1,'opacity':1,'keyframes':[],
         'transition':{'type':'cut','duration':0}})
    removed={c['id'] for _,c in current}
    for row in project.get('tracks',[]):
        row['clips']=[c for c in row.get('clips',[]) if c['id'] not in removed]
    project['tracks']=[row for row in project.get('tracks',[]) if row.get('clips') or row not in [t for t,_ in current]]
    if visible:
        asset=store.asset_record(target,project['id'],'channel-logo')
        asset['name']=LOGO_TITLE+'.png'
        # Old assets stay available for historical export snapshots; live clips use this version.
        if not any(a['id']==asset['id'] for a in project.get('assets',[])):
            project.setdefault('assets',[]).append(asset)
        clip.update(asset_id=asset['id'],title=LOGO_TITLE,channel_logo=True,start=0,duration=duration)
        if track.get('clips'):
            track={'id':'channel-logo-layer','name':LOGO_TITLE,'type':'universal','clips':[]}
        track['clips']=[clip]
        project['tracks'].append(track)
        groups=project.setdefault('scene_groups',[])
        found=next((g for g in groups if clip['id'] in g.get('clip_ids',[])),None)
        if found:found['role']='overlay'
        else:groups.append({'id':'channel-logo-group','title':LOGO_TITLE,'role':'overlay','clip_ids':[clip['id']]})
    store.reconcile_scene_groups(project)
    for index,row in enumerate(project['tracks']):row['z_index']=index
    return project


def place(pid: str) -> bool:
    project=store.load_project(pid)
    return bool(clips(project))
