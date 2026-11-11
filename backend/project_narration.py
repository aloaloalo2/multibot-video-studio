"""Original narration with immutable phrase cache and explicit paid starts."""
import math
import shutil
import planner
import threading
import time
import uuid
import project_costs
import narration_ending
from pathlib import Path
import store
import job_timing
import languages
import channel_voice_lab as lab

LOCK = threading.Lock()
ACTIVE = set()
HEYGEN_QUEUE = []
HEYGEN_TURN = threading.Condition()


def release_heygen(pid):
    with HEYGEN_TURN:
        if pid in HEYGEN_QUEUE:HEYGEN_QUEUE.remove(pid)
        HEYGEN_TURN.notify_all()


@job_timing.measure('queue')
def wait_heygen(pid, job):
    with HEYGEN_TURN:
        if pid not in HEYGEN_QUEUE:HEYGEN_QUEUE.append(pid)
        while HEYGEN_QUEUE[0] != pid:
            if (root(pid)/'cancel').exists():raise Cancelled()
            HEYGEN_TURN.wait(.25)
        if (root(pid)/'cancel').exists():raise Cancelled()
        job.update(status='running', queue_position=None)


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
    settings=profile['settings'];ref=lab.effective_reference(cid,settings) if lab.selected_voice_id(settings) or settings['provider']=='heygen' else profile['reference']
    if settings['provider']=='heygen' and settings['heygen_model']=='starfish' and settings.get('heygen_starfish_ssml') and ('<' in text or '&' in text):
        if len(text)>5000:raise store.StudioError('Для сценарію SSML Starfish допускається до 5000 символів. Для довгого сценарію виберіть звичайний текст')
        parts=[text]
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
            for pct in range(87,111):  # Includes historical settings when recovering old audio.
                if all(lab.fingerprint({**settings,'text':e['text'],'speed':pct/100},ref)==e['key'] for e in entries[:3]):return pct/100
    raise store.StudioError('Не вдалося визначити початковий темп готової озвучки')

def change_speed(pid, speed, reverb=None, room_noise=None):
    if isinstance(speed,bool) or not isinstance(speed,(int,float)) or not math.isfinite(speed) or not lab.MIN_SPEED<=speed<=lab.MAX_SPEED:
        raise store.StudioError('Швидкість має бути від 87 до 105%')
    import director,production
    with LOCK:
        if pid in ACTIVE or pid in director.ACTIVE or pid in production.ACTIVE:raise store.StudioError('Дочекайтеся завершення поточної роботи проєкту',409)
        folder=root(pid);job=store.read_json(folder/'job.json',{})
        if job.get('status')!='done':raise store.StudioError('Спочатку завершіть озвучення')
        if not completed_job_current(store.load_project(pid),job):raise store.StudioError('Цю озвучку вже прибрано з проєкту',409)
        current=recorded_speed(pid,job)
        import narration_effects
        effect = narration_effects.normalize(reverb if reverb is not None else job.get('reverb'))
        noise = narration_effects.noise_options(room_noise if room_noise is not None else job.get('room_noise'))
        current_effect=narration_effects.identity(effect,noise)
        if abs(current-speed)<.00001 and current_effect==narration_effects.identity(job.get('reverb'), job.get('room_noise')) and (not current_effect or job.get('audio_processing_version')==narration_effects.VERSION):return snapshot(pid)
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
        updated=narration_ending.import_audio(project,output,'narration',reverb=effect,room_noise=noise) if narration_effects.identity(effect,noise) else narration_ending.import_audio(project,output,'narration')
        with store.LOCK:
            project=store.load_project(pid)
            for track in project.get('tracks',[]):
                for clip in track.get('clips',[]):
                    if clip.get('asset_id')==asset['id']:
                        clip['asset_id']=updated['id']
                        length=clip.get('duration',asset['duration'])
                        full=abs(length-asset['duration'])<.05 and float(clip.get('trim_start') or 0)==0
                        clip['duration']=updated['duration'] if full else min(updated['duration'],length*current/speed)
            project['revision']+=1;store.save_project(project)
        job.update(asset_id=updated['id'],speed=speed,reverb=effect,room_noise=noise,audio_processing_version=narration_effects.VERSION,duration=updated['duration'],
                   tempo_derivation={'baseline_sha256':store.audio_fingerprint(baseline),'source_sha256':store.audio_fingerprint(output),
                                     'speed':speed,'baseline_speed':base_speed})
        store.atomic_json(folder/'job.json',job)
    return snapshot(pid)


def original_audio(pid):
    project = store.load_project(pid)
    job = store.read_json(root(pid) / 'job.json', {})
    if job.get('status') != 'done' or not completed_job_current(project, job):
        raise store.StudioError('Готову озвучку не знайдено', 404)
    source = root(pid) / 'speed-original.mp3'
    if source.is_file():
        return source
    return Path(next(a['path'] for a in project['assets'] if a['id'] == job['asset_id']))


def tempo_preview(pid, speed):
    import narration_tempo
    speed = narration_tempo.speed(speed)
    source = original_audio(pid)
    job = store.read_json(root(pid) / 'job.json', {})
    original_speed = store.read_json(root(pid) / 'speed-original.json', {}).get('speed', job.get('speed', 1.))
    return narration_tempo.preview(source, speed / original_speed)


def snapshot(pid):
    job=store.read_json(root(pid)/'job.json',{})
    if job.get('status') in {'queued','running'} and pid not in ACTIVE:
        job={**job,'status':'failed','error':'Роботу перервано. Готові фрази залишилися в кеші.'}
    if job.get('status')=='queued':
        with HEYGEN_TURN:
            if pid in HEYGEN_QUEUE:job['queue_position']=max(1,HEYGEN_QUEUE.index(pid))
    if pid in ACTIVE and (root(pid)/'cancel').exists():job={**job,'status':'cancelling'}
    project=store.load_project(pid)
    creation=f'/api/projects/{pid}/plan/analyze' if store.project_plan_mode(project)=='direct' else f'/api/projects/{pid}/create-video'
    if not completed_job_current(project,job):job={}
    if job.get('status')=='done' and 'speed' not in job:
        try:job['speed']=recorded_speed(pid,job)
        except store.StudioError:pass
    if job.get('status')=='done':
        job['local_preview_tempo'] = True
        job['original_speed'] = store.read_json(root(pid)/'speed-original.json',{}).get('speed',job.get('speed',1.))
        import narration_effects
        job['local_effects_version'] = narration_effects.VERSION
        job['audio_processing_stale']=bool(narration_effects.identity(job.get('reverb'),job.get('room_noise')) and job.get('audio_processing_version')!=narration_effects.VERSION)
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
        with HEYGEN_TURN:HEYGEN_TURN.notify_all()
        store.atomic_json(root(pid)/'job.json',job)
    return snapshot(pid)


def start(project,text,resume=False):
    pid=project['id'];cid=project['channel_id']
    with LOCK,lab.LOCK:
        if (root(pid)/'cancel').exists() and resume is not True:raise store.StudioError('Озвучення зупинено користувачем. Для нового запуску потрібне явне підтвердження resume=true.',409)
        if pid in ACTIVE:raise store.StudioError('Озвучення цього проєкту вже триває.',409)
        settings,ref,entries,quote=spec(project,text)
        job={'status':'running','completed':0,**quote,'started_at':time.time(),'script':text,'speed':settings['speed'],'render_settings':settings.copy()}
        if settings['provider']=='heygen':
            with HEYGEN_TURN:
                HEYGEN_QUEUE.append(pid);job.update(status='queued',queue_position=max(1,len(HEYGEN_QUEUE)-1))
        try:
            (root(pid)/'cancel').unlink(missing_ok=True)
            store.atomic_json(root(pid)/'job.json',job)
        except Exception:
            release_heygen(pid)
            raise
        ACTIVE.add(pid);lab.NARRATIONS[pid]=cid
    try:
        script_record=store.save_voice_script(pid,text,source='narration')
        threading.Thread(target=run,args=(project,text,settings.copy(),ref.copy(),entries,job),daemon=True).start()
    except Exception as error:
        release_heygen(pid)
        with LOCK,lab.LOCK:ACTIVE.discard(pid);lab.NARRATIONS.pop(pid,None)
        job.update(status='failed',error=str(error),finished_at=time.time())
        store.atomic_json(root(pid)/'job.json',job)
        raise
    return {'job':job,'voice_script':script_record}

@job_timing.track('narration', project='project', job='job')
def run(project,text,settings,ref,entries,job):
    pid=project['id'];cid=project['channel_id'];folder=None
    try:
        folder=root(pid)
        if settings['provider']=='heygen':wait_heygen(pid,job)
        job['cost_receipts_version']=1
        store.atomic_json(folder/'job.json',job)
        missing=any(not x['cached'] for x in entries)
        fish=settings['provider']=='fishaudio'
        if missing and settings['provider']!='heygen':
            with lab.audio_guard(lab.folder(cid)/'reference.mp3'):
                if not lab.selected_voice_id(settings):ref={**ref,'prepared_path':str(lab.prepared_source(cid,settings,ref))}
                if fish:secret=languages.key('fishaudio');voice=lab.fish_reference(cid,settings,ref)
                else:secret,voice=lab.clone(cid,settings,ref)
        for i,entry in enumerate(entries):
            if (folder/'cancel').exists():raise Cancelled()
            target=folder/(entry['key']+'.mp3')
            if not target.is_file():
                params={**settings,'text':entry['text']}
                with lab.audio_guard(lab.original_path(params,ref)):
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
        with job_timing.span('saving'):
            listing=folder/'concat.txt';listing.write_text('\n'.join("file '"+x['key']+".mp3'" for x in entries))
            target=folder/'Озвучка.mp3'
            languages.run(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(target)],'зібрати озвучку')
            shutil.copy2(target,folder/'speed-original.mp3');store.atomic_json(folder/'speed-original.json',{'speed':settings['speed']})
            import narration_effects
            effect = narration_effects.normalize(settings.get('reverb'))
            noise = narration_effects.noise_options(settings.get('room_noise'))
            asset=narration_ending.import_audio(store.load_project(pid),target,'narration',reverb=effect,room_noise=noise) if narration_effects.identity(effect,noise) else narration_ending.import_audio(store.load_project(pid),target,'narration')
            store.atomic_json(folder/'phrases.json',entries)
            job.update(status='done',asset_id=asset['id'],duration=asset.get('duration'),reverb=effect,room_noise=noise,audio_processing_version=narration_effects.VERSION,ending_seconds=narration_ending.SECONDS,finished_at=time.time())
    except Cancelled:job.update(status='cancelled',finished_at=time.time())
    except Exception as error:job.update(status='failed',error=str(error))
    finally:
        # Cancel and completion must publish under the same lock. Otherwise a
        # late cancel write can replace the worker's terminal status forever.
        try:
            if job.get('status') == 'done':
                import episode_automation
                episode_automation.after_voice(pid, job)
        finally:
            with LOCK,lab.LOCK:
                try:
                    if folder is not None:store.atomic_json(folder/'job.json',job)
                finally:
                    release_heygen(pid)
                    ACTIVE.discard(pid);lab.NARRATIONS.pop(pid,None)
