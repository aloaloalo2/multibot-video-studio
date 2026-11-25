"""Original narration with immutable phrase cache and explicit paid starts."""
import math
import re
import shutil
import planner
import script_timing
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
import heygen_voice as _heygen
HEYGEN_QUEUE = _heygen.JOB_QUEUE   # the shared queue, kept under its old names
HEYGEN_TURN = _heygen.JOB_TURN


def heygen_owner(pid):
    return 'narration:'+pid


def release_heygen(pid):
    import heygen_voice
    heygen_voice.queue_leave(heygen_owner(pid))


def wait_heygen(pid, job, record=None):
    """A HeyGen narration waits its turn behind the others (original and translations alike, heygen_voice.queue_wait),
    showing «HeyGen · у черзі · N» meanwhile in `record` (its own job file: a sentence's revision writes its
    revision-job.json, never the finished narration's job.json); a stop leaves the queue."""
    import heygen_voice
    if (root(pid)/'cancel').exists():raise Cancelled()
    def stop_check():
        if (root(pid)/'cancel').exists():raise Cancelled()
    def waiting(ahead):
        job.update(status='queued', queue_position=ahead)
        store.atomic_json(record or root(pid)/'job.json', job)
    heygen_voice.STOP.check=stop_check
    try:
        heygen_voice.queue_wait(heygen_owner(pid), waiting)
    finally:
        heygen_voice.STOP.check=None
    job.update(status='running', queue_position=None)


class Cancelled(Exception):pass

def root(pid):
    path = store.project_dir(pid) / 'narration';path.mkdir(exist_ok=True)
    return path

def phrases(text):
    """The script's sentences in order, the way the narration is read and revised; a sentence over 1800 characters is
    cut into parts within the providers' request limits."""
    return [unit['text'] for unit in units(text)]


GROUP_CHARS = 3000   # a group of sentences stays well inside one request (HeyGen takes up to 10 000 characters)


def _fit(texts, limit):
    """Sizes the group `texts` falls into so each part stays within `limit` characters: halved, as even as they come,
    until every part fits (a lone sentence always fits: sentences over 1800 are cut before)."""
    if len(texts) <= 1 or len(' '.join(texts)) <= limit:
        return [len(texts)]
    half = (len(texts) + 1) // 2
    return _fit(texts[:half], limit) + _fit(texts[half:], limit)


def units(text, group=1, join=False, limit=GROUP_CHARS):
    """What each request reads: up to `group` neighbouring sentences of one paragraph, joined by a space, the groups of
    a paragraph as even as they come (5 sentences by 3 are 3 and 2). A paragraph break starts a new request, so its
    pause stays, unless `join` lets groups run on across paragraphs. `sentences` is how many sentences of the script a unit holds: 0 for a part of a cut sentence."""
    if not isinstance(text, str) or not 10 <= len(text.strip()) <= 200000:
        raise store.StudioError('Введіть сценарій від 10 до 200 000 символів')
    group = max(1, int(group or 1))
    result = []
    for line in ([' '.join(text.strip().splitlines())] if join else text.strip().splitlines()):
        run = []
        def flush():
            count = max(1, math.ceil(len(run) / group)) if run else 0
            base, extra = divmod(len(run), count) if count else (0, 0)
            start = 0
            for index in range(count):
                part = run[start:start + base + (index < extra)]
                start += len(part)
                at = 0
                for size in _fit(part, limit):
                    piece = part[at:at + size];at += size
                    result.append({'text': ' '.join(piece), 'sentences': len(piece)})
            run.clear()
        for sentence in planner.split_sentences(line):
            if len(sentence) > 1800:   # very long sentences respect provider request limits
                flush()
                result.extend({'text': sentence[i:i + 1800], 'sentences': 0} for i in range(0, len(sentence), 1800))
                continue
            run.append(sentence)
        flush()
    return result

def _even(count, group):
    """Sizes of `count` sentences cut into groups of at most `group`, as even as they come."""
    parts = max(1, math.ceil(count / group)) if count else 0
    base, extra = divmod(count, parts) if parts else (0, 0)
    return [base + (index < extra) for index in range(parts)]


def _spans(sentences, start, end, group, join, limit=GROUP_CHARS):
    """(start, count) of the groups over sentences[start:end], each sentence a (paragraph, text) pair."""
    spans, at = [], start
    while at < end:
        stop = at
        while stop < end and (join or sentences[stop][0] == sentences[at][0]):
            stop += 1
        for size in _even(stop - at, group):
            texts = [text for _, text in sentences[at:at + size]]
            for piece in _fit(texts, limit):
                spans.append((at, piece));at += piece
    return spans


def reusing_units(text, group, join, made, limit=GROUP_CHARS):
    """units(), but a take already voiced for the same sentences is used again, whatever grouping made it: the
    sentences between such takes are grouped anew (user, 18 November 2026: «нажав продовжити озвучку і почалось
    заново?» after the paragraphs were joined mid-narration and none of the six paragraph takes matched the new groups)."""
    fresh = units(text, group, join, limit)
    if any(unit['sentences'] == 0 for unit in fresh):
        return fresh   # a sentence cut for its length: the plain grouping
    sentences = [(line, sentence) for line, row in enumerate(text.strip().splitlines()) for sentence in planner.split_sentences(row)]
    joined = lambda start, count: ' '.join(sentence for _, sentence in sentences[start:start + count])
    done = {}
    for size in range(1, max(lab.SENTENCES_MAX, lab.ELEVEN_SENTENCES_MAX) + 1):
        for together in (False, True):
            for start, count in _spans(sentences, 0, len(sentences), size, together, limit):
                if count > done.get(start, 0) and made(joined(start, count)):
                    done[start] = count
    if not done:
        return fresh
    result, at, pending = [], 0, None
    def flush(stop):
        if pending is not None:
            result.extend({'text': joined(a, c), 'sentences': c} for a, c in _spans(sentences, pending, stop, group, join, limit))
    while at < len(sentences):
        if at in done:
            flush(at); pending = None
            result.append({'text': joined(at, done[at]), 'sentences': done[at]})
            at += done[at]
        else:
            pending = at if pending is None else pending
            at += 1
    flush(len(sentences))
    return result


def spec(project, text):
    cid=project['channel_id'];profile=lab.snapshot(cid)
    settings=profile['settings'];ref=lab.effective_reference(cid,settings) if lab.selected_voice_id(settings) or settings['provider']=='heygen' else profile['reference']
    def made(part):
        params={**settings,'text':part}
        return (root(project['id'])/(lab.fingerprint(params,ref)+'.mp3')).is_file() or lab.original_path(params,ref).is_file() if ref else False
    parts=reusing_units(text,lab.sentences_per_request(settings),lab.joins_paragraphs(settings),made,lab.group_chars(settings))
    if settings['provider']=='heygen' and settings['heygen_model']=='starfish' and settings.get('heygen_starfish_ssml') and ('<' in text or '&' in text):
        if len(text)>5000:raise store.StudioError('Для сценарію SSML Starfish допускається до 5000 символів. Для довгого сценарію виберіть звичайний текст')
        parts=[{'text':text,'sentences':0}]
    if not ref:raise store.StudioError('Додайте або виберіть голос у налаштуваннях каналу')
    def entry(part,count):
        params={**settings,'text':part}
        key=lab.fingerprint(params,ref)
        return {'text':part,'key':key,'sentences':count,'cached':(root(project['id'])/(key+'.mp3')).is_file(), 'raw_cached':lab.original_path(params,ref).is_file() or (settings['provider']=='elevenlabs' and (root(project['id'])/(lab.fingerprint({**params,'speed':1.},ref)+'.mp3')).is_file())}
    # takes voiced before, by sentence or in other groups, are used again (reusing_units)
    entries=[entry(part['text'],part['sentences']) for part in parts]
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
    if job.get('status') in {'queued','running','cancelling'} and pid not in ACTIVE:
        job={**job,'status':'failed','error':'Роботу перервано. Готові фрази залишилися в кеші.'}
    if job.get('status')=='queued':
        import heygen_voice
        ahead=heygen_voice.queue_ahead(heygen_owner(pid))
        if ahead:job['queue_position']=ahead
    if pid in ACTIVE and (root(pid)/'cancel').exists():job={**job,'status':'cancelling'}
    revision=store.read_json(root(pid)/'revision-job.json',{}) or {}
    if pid in ACTIVE and revision.get('status') in {'queued','running','cancelling'}:
        job={**job,**revision,'revision_job':True}
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
    return {'job':job,'revision':revision,'source':project.get('narration_source'),
            'choices':[{'id':'script','label':'Озвучити сценарій','quote':f'/api/projects/{pid}/narration/quote','start':f'/api/projects/{pid}/narration/start','create_video':creation},
                       {'id':'file','label':'Додати аудіо або відео','upload':f'/api/projects/{pid}/assets/upload','analyze':creation}],
            'create_video_endpoint':creation,
            'source_endpoint':f'/api/projects/{pid}/narration/source'}

def work_job(pid):
    data=snapshot(pid);job=data.get('job') or {};revision=data.get('revision') or {}
    return revision if revision.get('started_at',0)>job.get('started_at',0) else job


def cancel(pid):
    store.load_project(pid)
    with LOCK:
        (root(pid)/'cancel').touch()
        revision=store.read_json(root(pid)/'revision-job.json',{}) or {}
        if pid in ACTIVE and revision.get('status') in {'queued','running','cancelling'}:
            revision['status']='cancelling';store.atomic_json(root(pid)/'revision-job.json',revision)
            with HEYGEN_TURN:HEYGEN_TURN.notify_all()
            return snapshot(pid)
        job=store.read_json(root(pid)/'job.json',{})
        if pid not in ACTIVE and job.get('status') in {'done','failed','cancelled'}:
            # a stop that comes after the end (the button lives until the next poll, a pause checks before it stops)
            # leaves a finished voice finished: «cancelled» over «done» hid the voice and refused revisions
            (root(pid)/'cancel').unlink(missing_ok=True)
            return snapshot(pid)
        job['status']='cancelling' if pid in ACTIVE else 'cancelled'
        with HEYGEN_TURN:HEYGEN_TURN.notify_all()
        store.atomic_json(root(pid)/'job.json',job)
    return snapshot(pid)


def start(project,text,resume=False):
    pid=project['id'];cid=project['channel_id']
    with LOCK,lab.LOCK:
        # the author's stop holds for the text it stopped; a new text (a new script, an episode started over) is free to
        # go (a leftover stop mark refused the automatic narration of every new script; 16 November 2026 stability pass)
        stopped_text=(store.read_json(root(pid)/'job.json',{}) or {}).get('script')
        if (root(pid)/'cancel').exists() and resume is not True and stopped_text==text:raise store.StudioError('Озвучення зупинено користувачем. Для нового запуску потрібне явне підтвердження resume=true.',409)
        if pid in ACTIVE:raise store.StudioError('Озвучення цього проєкту вже триває.',409)
        settings,ref,entries,quote=spec(project,text)
        job={'status':'running','completed':0,**quote,'started_at':time.time(),'script':text,'speed':settings['speed'],'render_settings':settings.copy()}
        try:
            (root(pid)/'cancel').unlink(missing_ok=True)
            store.atomic_json(root(pid)/'job.json',job)
        except Exception:
            release_heygen(pid)
            raise
        ACTIVE.add(pid);lab.NARRATIONS[pid]=cid
    try:
        script_record=store.save_voice_script(pid,text,source='narration')
        # with a script the director starts now, on its times estimated from the text (backend/script_timing.py)
        script_timing.start_soon(pid)
        threading.Thread(target=run,args=(project,text,settings.copy(),ref.copy(),entries,job),daemon=True).start()
    except Exception as error:
        release_heygen(pid)
        with LOCK,lab.LOCK:ACTIVE.discard(pid);lab.NARRATIONS.pop(pid,None)
        job.update(status='failed',error=str(error),finished_at=time.time())
        store.atomic_json(root(pid)/'job.json',job)
        raise
    return {'job':job,'voice_script':script_record}


def phrase_audio(project,settings,ref,entry,secret=None,voice=None):
    pid=project['id'];folder=root(pid);target=folder/(entry['key']+'.mp3');fish=settings['provider']=='fishaudio'
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
    return target

def voice_all(project,settings,ref,entries,secret,voice,folder,stop_check,progress):
    """Voices every entry into the project's phrase cache, in the script's order of starts. HeyGen takes
    heygen_voice.workers(model) phrases at once, ElevenLabs lab.ELEVEN_SLOTS (user, 23 November 2026: «одночасні
    запити»); the same cache, order and receipts as one by one. `progress(entry)` hears each finished entry, under a
    lock, and a stop or an error sends none of the phrases not started yet. Returns each entry's take, in order."""
    import heygen_voice
    workers=(heygen_voice.workers(settings.get('heygen_model')) if settings['provider']=='heygen' else
             lab.ELEVEN_SLOTS if settings['provider']=='elevenlabs' else 1)
    done=threading.Lock();takes={}
    def one(index,entry):
        heygen_voice.STOP.check=stop_check
        try:
            if (folder/'cancel').exists():raise Cancelled()
            for attempt in range(6):
                try:
                    takes[index]=phrase_audio(project,settings,ref,entry,secret,voice);break
                except RuntimeError as busy:
                    # ElevenLabs refuses a request over the plan's number at once (429): nothing was billed,
                    # it waits for the others and tries again
                    if settings['provider']!='elevenlabs' or attempt==5 or not re.search(r'помилка 429',str(busy)):raise
                    for _ in range(5*(attempt+1)):
                        if (folder/'cancel').exists():raise Cancelled()
                        time.sleep(1)
            with done:progress(entry)
        finally:
            heygen_voice.STOP.check=None
    if workers<=1 or len(entries)<=1:
        for index,entry in enumerate(entries):one(index,entry)
        heygen_voice.STOP.check=stop_check
        return [takes[index] for index in range(len(entries))]
    from concurrent.futures import ThreadPoolExecutor
    pool=ThreadPoolExecutor(max_workers=workers)
    try:
        for future in [pool.submit(job_timing.carry(one),index,entry) for index,entry in enumerate(entries)]:
            future.result()
    finally:   # a stop or an error: the phrases not started yet are not sent
        pool.shutdown(wait=True,cancel_futures=True)
    return [takes[index] for index in range(len(entries))]


@job_timing.track('narration', project='project', job='job')
def run(project,text,settings,ref,entries,job):
    pid=project['id'];cid=project['channel_id'];folder=None
    try:
        folder=root(pid)
        # a narration whose phrases are all in the cache asks HeyGen nothing: it does not wait behind whole narrations
        if settings['provider']=='heygen' and _heygen.queued(settings.get('heygen_model')) and not all(x['cached'] or x.get('raw_cached') for x in entries):wait_heygen(pid,job)
        job['cost_receipts_version']=1
        store.atomic_json(folder/'job.json',job)
        missing=any(not x['cached'] for x in entries)
        fish=settings['provider']=='fishaudio';secret=voice=None
        if missing and settings['provider']!='heygen':
            with lab.audio_guard(lab.folder(cid)/'reference.mp3'):
                if not lab.selected_voice_id(settings):ref={**ref,'prepared_path':str(lab.prepared_source(cid,settings,ref))}
                if fish:secret=languages.key('fishaudio');voice=lab.fish_reference(cid,settings,ref)
                else:secret,voice=lab.clone(cid,settings,ref)
        import heygen_voice
        def stop_check():
            if (folder/'cancel').exists():raise Cancelled()
        heygen_voice.STOP.check=stop_check
        # phrases already made count from the start: a narration that goes on after a stop reads 68%, not 0%
        made=sum(1 for x in entries if x['cached']);job['completed']=made;store.atomic_json(folder/'job.json',job)
        def progress(entry):
            nonlocal made
            if entry['cached']:return
            made+=1;job['completed']=made;store.atomic_json(folder/'job.json',job)
        voice_all(project,settings,ref,entries,secret,voice,folder,stop_check,progress)
        if (folder/'cancel').exists():raise Cancelled()
        with job_timing.span('saving'):
            listing=folder/'concat.txt';listing.write_text('\n'.join("file '"+x['key']+".mp3'" for x in entries))
            # assembled straight into the tempo baseline: «Озвучка.mp3» was a full copy of it that nothing read after the
            # import (470 MB over 27 projects; 17 November 2026 audit)
            target=folder/'speed-original.mp3'
            languages.run(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(target)],'зібрати озвучку')
            store.atomic_json(folder/'speed-original.json',{'speed':settings['speed']})
            (folder/'Озвучка.mp3').unlink(missing_ok=True)
            import narration_effects
            effect = narration_effects.normalize(settings.get('reverb'))
            noise = narration_effects.noise_options(settings.get('room_noise'))
            asset=narration_ending.import_audio(store.load_project(pid),target,'narration',reverb=effect,room_noise=noise) if narration_effects.identity(effect,noise) else narration_ending.import_audio(store.load_project(pid),target,'narration')
            store.atomic_json(folder/'phrases.json',entries)
            job.update(status='done',asset_id=asset['id'],duration=asset.get('duration'),reverb=effect,room_noise=noise,audio_processing_version=narration_effects.VERSION,ending_seconds=narration_ending.SECONDS,finished_at=time.time())
    except Cancelled:job.update(status='cancelled',finished_at=time.time())
    except Exception as error:
        if (folder is not None and (folder/'cancel').exists()):job.update(status='cancelled',finished_at=time.time())
        else:job.update(status='failed',error=str(error))
    finally:
        # Cancel and completion must publish under the same lock. Otherwise a
        # late cancel write can replace the worker's terminal status forever.
        try:
            if job.get('status') == 'done':
                import episode_automation
                episode_automation.after_voice(pid, job)
        finally:
            try:
                import heygen_voice
                heygen_voice.STOP.check=None
            except ImportError:
                pass
            with LOCK,lab.LOCK:
                try:
                    if folder is not None:store.atomic_json(folder/'job.json',job)
                finally:
                    release_heygen(pid)
                    ACTIVE.discard(pid);lab.NARRATIONS.pop(pid,None)
