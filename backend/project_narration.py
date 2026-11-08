"""Original narration with immutable phrase cache and explicit paid starts."""
import math
import shutil
import planner
import threading
import time
import uuid
import project_costs
from pathlib import Path
import store
import languages
import channel_voice_lab as lab

LOCK = threading.Lock()
ACTIVE = set()

class Cancelled(Exception):pass

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
    settings=profile['settings'];ref=lab.effective_reference(cid,settings) if settings['provider']=='heygen' else profile['reference']
    if not ref:raise store.StudioError('Додайте або виберіть голос у налаштуваннях каналу')
    entries=[]
    for part in parts:
        params={**settings,'text':part}
        key=lab.fingerprint(params,ref)
        entries.append({'text':part,'key':key,'cached':(root(project['id'])/(key+'.mp3')).is_file(), 'raw_cached':lab.original_path(params,ref).is_file() or (settings['provider']=='elevenlabs' and (root(project['id'])/(lab.fingerprint({**params,'speed':1.},ref)+'.mp3')).is_file())})
    missing={x['key']:x for x in entries if not x['cached'] and not x['raw_cached']}.values()
    count=sum(len(x['text']) for x in missing)
    amount=sum(lab.estimate({**settings,'text':x['text']})['amount'] for x in missing)
    credits=amount if settings['provider']=='elevenlabs' else None
    usd=amount if credits is None else None
    if credits is not None:
        rate=store.read_json(store.DATA_ROOT/'eleven-credit-usd.json',{}).get('credit_usd_rate')
        if not rate:rate=lab.eleven_api.balance().get('credit_usd_rate')
        if rate:usd=credits*rate*1.20
        if credits==0:usd=0
    return settings,ref,entries,{'total':len(entries),'cached':sum(x['cached'] for x in entries),'characters':count,'provider':settings['provider'],'estimated_credits':credits,'estimated_usd':round(usd,6) if usd is not None else None,'tax_included':credits is not None}

def select_source(pid, mode):
    if mode not in {'script','file'}:raise store.StudioError('Виберіть script або file')
    with LOCK,store.LOCK:
        if pid in ACTIVE:raise store.StudioError('Дочекайтеся завершення озвучення',409)
        project=store.load_project(pid);project['narration_source']=mode;project['revision']+=1;store.save_project(project)
    return snapshot(pid)


def completed_job_current(project, job):
    if job.get('status')!='done':return True
    if project.get('restarted_at',0)>job.get('started_at',0):return False
    asset=next((a for a in project.get('assets',[]) if a['id']==job.get('asset_id')),None)
    return bool(asset and asset.get('path') and Path(asset['path']).is_file())


def recorded_speed(pid, job):
    if job.get('speed') is not None:return job['speed']
    project=store.load_project(pid);cid=project['channel_id']
    candidates=[job.get('render_settings') or lab.snapshot(cid)['settings']]
    # Legacy jobs predate stored rendering settings. Sample receipts retain the exact profile
    # even when the user has since adjusted the channel sliders.
    for path in (lab.folder(cid)/'samples').glob('*.json'):
        saved=store.read_json(path,{}).get('settings')
        if saved:candidates.append(lab.validated(saved))
    entries=store.read_json(root(pid)/'phrases.json',[])
    for settings in candidates:
        ref=lab.effective_reference(cid,settings)
        if entries and ref:
            for pct in range(90,111):
                if all(lab.fingerprint({**settings,'text':e['text'],'speed':pct/100},ref)==e['key'] for e in entries[:3]):return pct/100
    raise store.StudioError('Не вдалося визначити початковий темп готової озвучки')

def change_speed(pid, speed):
    if isinstance(speed,bool) or not isinstance(speed,(int,float)) or not math.isfinite(speed) or not .9<=speed<=1.1:
        raise store.StudioError('Швидкість має бути від 90 до 110%')
    import director,production
    with LOCK:
        if pid in ACTIVE or pid in director.ACTIVE or pid in production.ACTIVE:raise store.StudioError('Дочекайтеся завершення поточної роботи проєкту',409)
        folder=root(pid);job=store.read_json(folder/'job.json',{})
        if job.get('status')!='done':raise store.StudioError('Спочатку завершіть озвучення')
        if not completed_job_current(store.load_project(pid),job):raise store.StudioError('Цю озвучку вже прибрано з проєкту',409)
        current=recorded_speed(pid,job)
        if abs(current-speed)<.00001:return snapshot(pid)
        project=store.load_project(pid)
        asset=next((a for a in project.get('assets',[]) if a['id']==job.get('asset_id')),None)
        if not asset or not Path(asset['path']).is_file():raise store.StudioError('Готовий аудіофайл не знайдено')
        # Always derive from one immutable completed take, never compound re-encodes.
        baseline=folder/'speed-original.mp3';metadata=folder/'speed-original.json'
        if not baseline.is_file():
            shutil.copy2(asset['path'],baseline);store.atomic_json(metadata,{'speed':current})
        base_speed=store.read_json(metadata,{})['speed']
        output=folder/f'Озвучка-{round(speed*100)}.mp3'
        output.write_bytes(lab.paced_audio(baseline,speed/base_speed))
        if not (store.media_duration(output) or 0)>0:raise store.StudioError('Не вдалося змінити темп')
        updated=store.import_asset_file(project,output,'narration')
        with store.LOCK:
            project=store.load_project(pid)
            for track in project.get('tracks',[]):
                for clip in track.get('clips',[]):
                    if clip.get('asset_id')==asset['id']:
                        clip['asset_id']=updated['id']
                        clip['duration']=min(updated['duration'],clip.get('duration',asset['duration'])*current/speed)
            project['revision']+=1;store.save_project(project)
        job.update(asset_id=updated['id'],speed=speed,duration=updated['duration'])
        store.atomic_json(folder/'job.json',job)
    return snapshot(pid)


def snapshot(pid):
    job=store.read_json(root(pid)/'job.json',{})
    if job.get('status')=='running' and pid not in ACTIVE:
        job={**job,'status':'failed','error':'Роботу перервано. Готові фрази залишилися в кеші.'}
    if pid in ACTIVE and (root(pid)/'cancel').exists():job={**job,'status':'cancelling'}
    project=store.load_project(pid)
    creation=f'/api/projects/{pid}/plan/analyze' if store.project_plan_mode(project)=='direct' else f'/api/projects/{pid}/create-video'
    if not completed_job_current(project,job):job={}
    if job.get('status')=='done' and 'speed' not in job:
        try:job['speed']=recorded_speed(pid,job)
        except store.StudioError:pass
    return {'job':job,'source':project.get('narration_source'),
            'choices':[{'id':'script','label':'Озвучити сценарій','quote':f'/api/projects/{pid}/narration/quote','start':f'/api/projects/{pid}/narration/start','create_video':creation},
                       {'id':'file','label':'Додати аудіо або відео','upload':f'/api/projects/{pid}/assets/upload','analyze':creation}],
            'create_video_endpoint':creation,
            'source_endpoint':f'/api/projects/{pid}/narration/source'}

def cancel(pid):
    store.load_project(pid)
    with LOCK:
        (root(pid)/'cancel').touch()
        job=store.read_json(root(pid)/'job.json',{})
        job['status']='cancelling' if pid in ACTIVE else 'cancelled'
        store.atomic_json(root(pid)/'job.json',job)
    return snapshot(pid)


def start(project,text,resume=False):
    pid=project['id'];cid=project['channel_id']
    with LOCK,lab.LOCK:
        if (root(pid)/'cancel').exists() and resume is not True:raise store.StudioError('Озвучення зупинено користувачем. Для нового запуску потрібне явне підтвердження resume=true.',409)
        if pid in ACTIVE or cid in lab.ACTIVE:raise store.StudioError('Голос уже використовується. Дочекайтеся завершення.',409)
        settings,ref,entries,quote=spec(project,text)
        job={'status':'running','completed':0,**quote,'started_at':time.time(),'script':text,'speed':settings['speed'],'render_settings':settings.copy()}
        (root(pid)/'cancel').unlink(missing_ok=True)
        ACTIVE.add(pid);lab.ACTIVE.add(cid);store.atomic_json(root(pid)/'job.json',job)
    threading.Thread(target=run,args=(project,text,settings,ref,entries,job),daemon=True).start()
    return {'job':job}

def run(project,text,settings,ref,entries,job):
    pid=project['id'];cid=project['channel_id'];folder=root(pid)
    try:
        job['cost_receipts_version']=1
        store.atomic_json(folder/'job.json',job)
        missing=any(not x['cached'] for x in entries)
        fish=settings['provider']=='fishaudio'
        if missing and settings['provider']!='heygen':
            ref={**ref,'prepared_path':str(lab.prepared_source(cid,settings,ref))}
            if fish:secret=languages.key('fishaudio');voice=lab.fish_reference(cid,settings,ref)
            else:secret,voice=lab.clone(cid,settings,ref)
        for i,entry in enumerate(entries):
            if (folder/'cancel').exists():raise Cancelled()
            target=folder/(entry['key']+'.mp3')
            if not target.is_file():
                params={**settings,'text':entry['text']}
                raw_cached=lab.original_path(params,ref).is_file()
                if settings['provider']=='elevenlabs' and not raw_cached:
                    previous=folder/(lab.fingerprint({**params,'speed':1.},ref)+'.mp3')
                    if previous.is_file():
                        source=lab.original_path(params,ref);source.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(previous,source);raw_cached=True
                audio=lab.heygen_synthesis(params,ref) if settings['provider']=='heygen' else lab.fish_synthesis(secret,voice,params,raw_key=lab.fish_raw_path(params,ref).stem) if fish else lab.eleven_local_synthesis(secret,voice,params,ref)
                cost={'unit':'credits' if settings['provider']=='elevenlabs' else 'usd','amount':0} if raw_cached else lab.estimate(params);identity='narration-'+uuid.uuid4().hex
                receipt={'identity':identity,'provider':settings['provider'],'amount':cost['amount'],'estimated':True,'phrase_key':entry['key'],'created_at':time.time()}
                receipts=folder/'receipts';receipts.mkdir(exist_ok=True)
                store.atomic_json(receipts/(identity+'.json'),receipt)
                project_costs.record_at(store.project_dir(pid),settings['provider'],cost['amount'],identity=identity,category='narration',estimated=True)
                pending=target.with_suffix('.pending.mp3');pending.write_bytes(audio)
                if not (store.media_duration(pending) or 0)>0:raise store.StudioError('Сервіс повернув порожню фразу')
                pending.replace(target)
            job['completed']=i+1;store.atomic_json(folder/'job.json',job)
        if (folder/'cancel').exists():raise Cancelled()
        listing=folder/'concat.txt';listing.write_text('\n'.join("file '"+x['key']+".mp3'" for x in entries))
        target=folder/'Озвучка.mp3'
        languages.run(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(target)],'зібрати озвучку')
        asset=store.import_asset_file(store.load_project(pid),target,'narration')
        shutil.copy2(target,folder/'speed-original.mp3');store.atomic_json(folder/'speed-original.json',{'speed':settings['speed']})
        store.atomic_json(folder/'phrases.json',entries)
        job.update(status='done',asset_id=asset['id'],finished_at=time.time())
    except Cancelled:job.update(status='cancelled',finished_at=time.time())
    except Exception as error:job.update(status='failed',error=str(error))
    finally:
        store.atomic_json(folder/'job.json',job)
        with LOCK,lab.LOCK:ACTIVE.discard(pid);lab.ACTIVE.discard(cid)
