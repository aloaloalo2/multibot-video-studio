"""Explicit sentence-only TTS edits, fitted into immutable montage audio slots."""
import copy
import hashlib
import math
from pathlib import Path
import re
import threading
import time
import wave

import channel_voice_lab as lab
import languages
import narration_sequence
import number_text
import planner
import project_narration as narration
import store


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def path(pid):
    return narration.root(pid)/'revision-job.json'


def snapshot(pid):
    project=store.load_project(pid)
    job=store.read_json(narration.root(pid)/'job.json',{}) or {}
    revision=store.read_json(path(pid),{}) or {}
    if revision.get('status') in {'queued','running','cancelling'} and pid not in narration.ACTIVE:
        revision={**revision,'status':'failed','error':'Переозвучення перервано. Попередня озвучка збережена.'}
    text=job.get('script') or (project.get('voice_script') or {}).get('text') or ''
    return {'text':text,'sha256':digest(text),'job':revision}


def prepare(pid,text,expected):
    project=store.load_project(pid)
    old=store.read_json(narration.root(pid)/'job.json',{}) or {}
    if old.get('status')!='done' or not narration.completed_job_current(project,old):
        raise store.StudioError('Спочатку завершіть озвучення сценарію.',409)
    original=old.get('script') or ''
    if expected!=digest(original):raise store.StudioError('Озвучку вже змінено. Відкрийте редактор знову.',409)
    parts,before=narration.phrases(text),narration.phrases(original)
    if len(parts)!=len(before):raise store.StudioError('Для точкової переозвучки збережіть кількість речень. Змініть текст усередині речення.')
    changed=[i for i,(a,b) in enumerate(zip(before,parts)) if a!=b]
    if not changed:raise store.StudioError('Внесіть зміни до сценарію.')
    asset=next((a for a in project.get('assets',[]) if a['id']==old.get('asset_id')),None)
    proof=narration_sequence.verify(project,asset,original) if asset else None
    timings=(proof or {}).get('sentence_timings') or []
    if len(timings)!=len(parts):raise store.StudioError('Не знайдено точні межі речень цієї озвучки. Попередній звук збережено.',409)
    previous_end=0
    for span in timings:
        start,end=span.get('start'),span.get('end')
        if (type(start) not in (int,float) or type(end) not in (int,float) or not math.isfinite(start) or not math.isfinite(end)
                or start<previous_end-.00001 or end<=start or end>asset['duration']):
            raise store.StudioError('Пошкоджені межі речень. Попередню озвучку збережено.',409)
        previous_end=end
    if not any(c.get('kind')=='audio' and c.get('asset_id')==asset['id'] for t in project.get('tracks',[]) for c in t.get('clips',[])):
        raise store.StudioError('Ця озвучка вже замінена на таймлайні. Оновіть випуск.',409)
    settings=copy.deepcopy(old.get('render_settings') or {})
    if not settings:raise store.StudioError('Не збережені налаштування голосу цієї озвучки.',409)
    # Use the recorded identity rather than the channel's current selection.
    ref=lab.effective_reference(project['channel_id'],settings)
    rows=store.read_json(narration.root(pid)/'phrases.json',[]) or []
    if not ref or len(rows)!=len(before):raise store.StudioError('Не знайдено збережений голос для цієї озвучки.',409)
    if any(lab.fingerprint({**settings,'text':part},ref)!=row.get('key') for part,row in zip(before,rows)):
        raise store.StudioError('Початковий приклад голосу змінено. Відновіть його для точкової переозвучки.',409)
    return {'project':project,'old':old,'asset':asset,'text':text,'parts':parts,'before':before,'changed':changed,
            'timings':timings,'settings':settings,'ref':ref,'revision':project.get('revision',0),'proof':proof}


def start(pid,body):
    identity=body.get('client_id')
    if not isinstance(identity,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',identity):raise store.StudioError('Не вказано ідентифікатор переозвучення.')
    with narration.LOCK,lab.LOCK,store.LOCK:
        previous=store.read_json(path(pid),{}) or {}
        if previous.get('id')==identity:return {'job':previous}
        if pid in narration.ACTIVE:raise store.StudioError('Озвучення вже триває.',409)
        ctx=prepare(pid,body.get('text'),body.get('expected_sha256'))
        cid=ctx['project']['channel_id']
        job={'id':identity,'status':'running','completed':0,'total':len(ctx['changed']),'started_at':time.time()}
        narration.ACTIVE.add(pid);lab.NARRATIONS[pid]=cid
        try:
            (narration.root(pid)/'cancel').unlink(missing_ok=True)
            store.atomic_json(path(pid),job)
            threading.Thread(target=run,args=(pid,ctx,job),daemon=True).start()
        except Exception:
            narration.ACTIVE.discard(pid);lab.NARRATIONS.pop(pid,None);narration.release_heygen(pid)
            job.update(status='failed',error='Не вдалося запустити переозвучення.');store.atomic_json(path(pid),job)
            raise
    return {'job':job}


def fit(source,target,seconds,rate,channels):
    measured=store.media_duration(source) or 0
    ratio=measured/seconds if seconds>0 else 0
    if not .65<=ratio<=1.5:raise store.StudioError('Змінене речення суттєво відрізняється за тривалістю. Скоротіть або уточніть правку.')
    languages.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(source),'-af',f'atempo={ratio:.9f},apad,atrim=duration={seconds:.9f}',
                   '-ar',str(rate),'-ac',str(channels),'-c:a','pcm_s16le',str(target)],'підготувати змінене речення')


def splice(original,output,replacements):
    """Copy every unchanged PCM sample verbatim, replacing only measured slots."""
    with wave.open(str(original),'rb') as source,wave.open(str(output),'wb') as result:
        result.setparams(source.getparams())
        rate,channels=source.getframerate(),source.getnchannels()
        def copy_until(end):
            while source.tell()<end:result.writeframes(source.readframes(min(65536,end-source.tell())))
        for start,end,replacement in replacements:
            first,last=round(start*rate),round(end*rate)
            if first<source.tell() or last>source.getnframes() or last<=first:raise store.StudioError('Некоректні межі зміненого речення.')
            copy_until(first)
            with wave.open(str(replacement),'rb') as chunk:
                if (chunk.getframerate(),chunk.getnchannels(),chunk.getsampwidth())!=(rate,channels,source.getsampwidth()):raise store.StudioError('Формат зміненої озвучки не збігається.')
                data=chunk.readframes(chunk.getnframes());size=(last-first)*channels*source.getsampwidth()
                result.writeframes(data[:size]+b'\0'*max(0,size-len(data)))
            source.setpos(last)
        copy_until(source.getnframes())


def patched_plan(plan,ctx,audio):
    plan=copy.deepcopy(plan)
    if not plan:return plan
    locale=number_text.detect_locale(ctx['text'])
    numeric=plan.get('number_format')=='digits_after_whisper'
    fixes=plan.get('number_fixes')
    by_number={i+1:planner.sentence_digits(ctx['parts'][i],locale,fixes) if numeric else ctx['parts'][i] for i in ctx['changed']}
    def key(text):return tuple(number_text.comparison_tokens(text,locale))
    originals=[key(text) for text in ctx['before']]
    unique={originals[i]:by_number[i+1] for i in ctx['changed'] if originals.count(originals[i])==1}
    def row(value):
        value=copy.deepcopy(value)
        n=value.get('number')
        if n in by_number and key(value.get('text',''))==originals[n-1]:value['text']=by_number[n]
        elif n is None:value['text']=unique.get(key(value.get('text','')),value.get('text',''))
        return value
    for frame in plan.get('frames',[]):
        anchors=frame.get('sentence_timings') or []
        if 'sentences' in frame:
            sentences=[]
            for i,text in enumerate(frame['sentences']):
                number=anchors[i].get('number') if i<len(anchors) else None
                sentences.append(row({'number':number,'text':text})['text'])
            frame['sentences']=sentences
        if anchors:frame['sentence_timings']=[row(value) for value in anchors]
    timing=plan.get('timing') or {}
    timing['sentences']=[row(value) for value in timing.get('sentences',[])]
    timing['audio']={**timing.get('audio',{}),'asset_id':audio['id'],'sha256':store.audio_fingerprint(Path(audio['path'])),'duration':audio['duration']}
    plan['timing']=timing
    plan['spoken_script']=ctx['text'];plan['spoken_script_sha256']=digest(ctx['text'])
    plan['script']=planner.script_digits(ctx['text'],fixes) if numeric else ctx['text']
    plan['script_sha256']=digest(plan['script'])
    return plan


def sync_razgon_voice(project,plan,asset):
    """Update the existing animation's voice without prepare, scene edits or a new review."""
    import shutil
    linked=store.read_json(store.project_dir(project['id'])/'razgon-link.json',{}) or {}
    if not linked.get('project'):return
    root=Path(linked['project']).resolve();path=root/'story/studio_frames.json'
    link=store.read_json(path,{}) or {}
    if link.get('project_id')!=project['id']:raise store.StudioError('Анімацію прив’язано до іншого випуску.',409)
    config=store.read_json(root/'config.json',{}) or {}
    voice=(root/(config.get('voiceover') or 'input/voiceover.flac')).resolve()
    if root not in voice.parents:raise store.StudioError('Файл озвучки анімації має бути всередині її проєкту.',409)
    voice.parent.mkdir(parents=True,exist_ok=True)
    pending=voice.with_name(voice.name+'.pending')
    shutil.copy2(asset['path'],pending);pending.replace(voice)
    link.update(script_sha256=plan['script_sha256'],audio_sha256=store.audio_fingerprint(Path(asset['path'])),voice_asset_id=asset['id'])
    store.atomic_json(path,link)


def run(pid,ctx,job):
    folder=narration.root(pid)/'revisions'/job['id'];folder.mkdir(parents=True,exist_ok=True)
    settings,ref=ctx['settings'],ctx['ref']
    try:
        if settings['provider']=='heygen':narration.wait_heygen(pid,job)
        job.update(status='running',stage='preparing');store.atomic_json(path(pid),job)
        original=folder/'original.wav'
        languages.run(['ffmpeg','-v','error','-nostdin','-y','-i',ctx['asset']['path'],'-c:a','pcm_s16le',str(original)],'відкрити готову озвучку')
        with wave.open(str(original),'rb') as f:rate,channels=f.getframerate(),f.getnchannels()
        secret=voice=None
        if settings['provider']!='heygen':
            if not lab.selected_voice_id(settings):ref={**ref,'prepared_path':str(lab.prepared_source(ctx['project']['channel_id'],settings,ref))}
            if settings['provider']=='fishaudio':secret=languages.key('fishaudio');voice=lab.fish_reference(ctx['project']['channel_id'],settings,ref)
            else:secret,voice=lab.clone(ctx['project']['channel_id'],settings,ref)
        # Keep the tempo-preview baseline in sync too, without applying room
        # effects or adding the closing pause twice on the next speed change.
        baseline=narration.root(pid)/'speed-original.mp3'
        if not baseline.is_file():raise store.StudioError('Не знайдено початкову озвучку для збереження налаштувань темпу.',409)
        meta=store.read_json(narration.root(pid)/'speed-original.json',{}) or {}
        current_speed=ctx['old'].get('speed',settings['speed']);ratio=current_speed/meta.get('speed',settings['speed'])
        speech_end=ctx['timings'][-1]['end'];raw_original=folder/'raw-original.wav'
        languages.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(baseline),'-af',f'atempo={ratio:.9f},apad,atrim=duration={speech_end:.9f}',
                       '-ar',str(rate),'-ac',str(channels),'-c:a','pcm_s16le',str(raw_original)],'підготувати оригінал для темпу')
        replacements=[];raw_replacements=[];rows=store.read_json(narration.root(pid)/'phrases.json',[])

        for count,i in enumerate(ctx['changed'],1):
            job.update(stage='synthesizing',current_sentence=i+1);store.atomic_json(path(pid),job)
            if (narration.root(pid)/'cancel').exists():raise narration.Cancelled()
            params={**settings,'text':ctx['parts'][i]};entry={'text':ctx['parts'][i],'key':lab.fingerprint(params,ref)}
            audio=narration.phrase_audio(ctx['project'],settings,ref,entry,secret,voice)
            span=ctx['timings'][i];raw_chunk=folder/f'{i}-raw.wav'
            fit(audio,raw_chunk,span['end']-span['start'],rate,channels)
            raw_replacements.append((span['start'],span['end'],raw_chunk))
            import narration_effects
            reverb,noise=ctx['old'].get('reverb'),ctx['old'].get('room_noise')
            if narration_effects.identity(reverb,noise):
                effected=folder/f'{i}-effects.flac'
                narration_effects.render(audio,reverb,effected,noise,closing_pause=0)
                audio=effected
            span=ctx['timings'][i];chunk=folder/f'{i}.wav'
            fit(audio,chunk,span['end']-span['start'],rate,channels)
            replacements.append((span['start'],span['end'],chunk));rows[i]=entry
            job['completed']=count;store.atomic_json(path(pid),job)
        job['stage']='assembling';store.atomic_json(path(pid),job)
        splice(raw_original,folder/'raw-patched.wav',raw_replacements)
        raw_output=folder/'speed-original.mp3'
        languages.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(folder/'raw-patched.wav'),'-b:a','128k',str(raw_output)],'зберегти оновлений оригінал')
        splice(original,folder/'patched.wav',replacements)
        output=folder/'Озвучка.flac'
        languages.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(folder/'patched.wav'),'-c:a','flac',str(output)],'зберегти оновлену озвучку')
        if abs((store.media_duration(output) or 0)-ctx['asset']['duration'])>.003:raise store.StudioError('Змінилася тривалість запису. Попередню озвучку збережено.')
        job['stage']='saving';store.atomic_json(path(pid),job)
        with store.LOCK:
            current=store.load_project(pid)
            if (narration.root(pid)/'cancel').exists():raise narration.Cancelled()
            if current.get('revision',0)!=ctx['revision']:raise store.StudioError('Випуск змінено під час переозвучення. Готове речення збережене в кеші.',409)
            plan=store.load_project_plan(pid)
            store.atomic_json(folder/'previous-job.json',ctx['old']);store.atomic_json(folder/'previous-plan.json',plan or {})
            asset=store.import_asset_file(current,output,'narration-revision');current=store.load_project(pid)
            for track in current.get('tracks',[]):
                for clip in track.get('clips',[]):
                    if clip.get('kind')=='audio' and clip.get('asset_id')==ctx['asset']['id']:clip['asset_id']=asset['id']
            record={'text':ctx['text'],'sha256':digest(ctx['text']),'saved_at':time.time(),'source':'narration-revision'}
            store.atomic_json(store.project_dir(pid)/'script-history'/(job['id']+'.json'),current.get('voice_script') or {})
            current['voice_script']=record;current['revision']=current.get('revision',0)+1
            proof={**ctx['proof'],'source':'revised_takes','audio_sha256':store.audio_fingerprint(output),'script_sha256':digest(ctx['text']),
                   'revision_id':job['id'],'changed_sentences':[i+1 for i in ctx['changed']]}
            store.atomic_json(folder/'proof.json',proof)
            if plan:
                spoken_path=store.project_dir(pid)/'source-history'/('Озвученный сценарий '+digest(ctx['text'])[:12]+'.txt')
                spoken_path.parent.mkdir(exist_ok=True);spoken_path.write_text(ctx['text'])
                plan['spoken_script_file']=str(spoken_path)
                target=store.project_dir(pid)/'imported-plan.json';store.atomic_json(target,patched_plan(plan,ctx,asset));current['plan_source']=str(target);current['plan_updated_at']=time.time()
            source=store.project_dir(pid)/'source-timing.json'
            if source.is_file():store.atomic_json(source,patched_plan(store.read_json(source,{}),ctx,asset))
            store.save_project(current)
            if plan:sync_razgon_voice(current,store.load_project_plan(pid),asset)
            old={**ctx['old'],'script':ctx['text'],'asset_id':asset['id'],'revision_id':job['id'],'finished_at':time.time()}
            import shutil
            shutil.copy2(baseline,folder/'previous-speed-original.mp3')
            shutil.copy2(raw_output,baseline)
            store.atomic_json(narration.root(pid)/'speed-original.json',{'speed':current_speed})
            store.atomic_json(narration.root(pid)/'job.json',old);store.atomic_json(narration.root(pid)/'phrases.json',rows)
            job.update(status='done',stage='done',asset_id=asset['id'],finished_at=time.time())
    except narration.Cancelled:job.update(status='cancelled',error='Переозвучення зупинено. Попередня озвучка збережена.')
    except Exception as error:job.update(status='failed',error=str(error),finished_at=time.time())
    finally:
        with narration.LOCK,lab.LOCK:
            store.atomic_json(path(pid),job);narration.ACTIVE.discard(pid);lab.NARRATIONS.pop(pid,None);narration.release_heygen(pid)
