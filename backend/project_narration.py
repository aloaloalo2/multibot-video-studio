"""Original narration with immutable phrase cache and explicit paid starts."""
import hashlib
import json
import re
import planner
import threading
import time
from pathlib import Path
import store
import languages
import channel_voice_lab as lab

LOCK = threading.Lock()
ACTIVE = set()

def root(pid):
    path = store.project_dir(pid) / 'narration';path.mkdir(exist_ok=True)
    return path

def phrases(text):
    if not isinstance(text, str) or not 10 <= len(text.strip()) <= 200000:
        raise store.StudioError('Введіть сценарій від 10 до 200 000 символів')
    result = [part for line in text.strip().splitlines() for part in planner.split_sentences(line)]
    # Very long paragraphs respect provider request limits.
    return [p[i:i+1800] for p in result for i in range(0,len(p),1800)]

def spec(project, text):
    parts = phrases(text);cid=project['channel_id'];profile=lab.snapshot(cid)
    if not profile.get('reference'):raise store.StudioError('Додайте голос у налаштуваннях каналу')
    settings=profile['settings'];ref=profile['reference']
    entries=[]
    for part in parts:
        params={**settings,'text':part}
        key=lab.fingerprint(params,ref)
        entries.append({'text':part,'key':key,'cached':(root(project['id'])/(key+'.mp3')).is_file()})
    count=sum(len(x['text']) for x in entries if not x['cached'])
    return settings,ref,entries,{'total':len(entries),'cached':sum(x['cached'] for x in entries),'characters':count,'provider':settings['provider'],'estimated_credits':round(count*.26) if settings['provider']=='elevenlabs' else None}

def snapshot(pid):
    job=store.read_json(root(pid)/'job.json',{})
    if job.get('status')=='running' and pid not in ACTIVE:
        job={**job,'status':'failed','error':'Роботу перервано. Готові фрази залишилися в кеші.'}
    return {'job':job}

def start(project,text):
    pid=project['id'];cid=project['channel_id']
    with LOCK,lab.LOCK:
        if pid in ACTIVE or cid in lab.ACTIVE:raise store.StudioError('Голос уже використовується. Дочекайтеся завершення.',409)
        settings,ref,entries,quote=spec(project,text)
        job={'status':'running','completed':0,**quote,'started_at':time.time(),'script':text}
        ACTIVE.add(pid);lab.ACTIVE.add(cid);store.atomic_json(root(pid)/'job.json',job)
    threading.Thread(target=run,args=(project,text,settings,ref,entries,job),daemon=True).start()
    return {'job':job}

def run(project,text,settings,ref,entries,job):
    pid=project['id'];cid=project['channel_id'];folder=root(pid)
    try:
        missing=any(not x['cached'] for x in entries)
        fish=settings['provider']=='fishaudio'
        if missing:
            ref={**ref,'prepared_path':str(lab.prepared_source(cid,settings,ref))}
            if fish:secret=languages.key('fishaudio');voice=lab.fish_reference(cid,settings,ref)
            else:secret,voice=lab.clone(cid,settings,ref)
        for i,entry in enumerate(entries):
            target=folder/(entry['key']+'.mp3')
            if not target.is_file():
                params={**settings,'text':entry['text']}
                audio=lab.fish_synthesis(secret,voice,params) if fish else lab.synthesis(secret,voice,params)
                pending=target.with_suffix('.pending.mp3');pending.write_bytes(audio)
                if not (store.media_duration(pending) or 0)>0:raise store.StudioError('Сервіс повернув порожню фразу')
                pending.replace(target)
            job['completed']=i+1;store.atomic_json(folder/'job.json',job)
        listing=folder/'concat.txt';listing.write_text('\n'.join("file '"+x['key']+".mp3'" for x in entries))
        target=folder/'Озвучка.mp3'
        languages.run(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(target)],'зібрати озвучку')
        asset=store.import_asset_file(store.load_project(pid),target,'narration')
        store.atomic_json(folder/'phrases.json',entries)
        job.update(status='done',asset_id=asset['id'],finished_at=time.time())
    except Exception as error:job.update(status='failed',error=str(error))
    finally:
        store.atomic_json(folder/'job.json',job)
        with LOCK,lab.LOCK:ACTIVE.discard(pid);lab.ACTIVE.discard(cid)
