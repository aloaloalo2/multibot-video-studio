"""Language audio delivery: translated narration plus enabled timeline sound."""
from __future__ import annotations
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path
import store


def duration_check(voice: dict, source_duration=None, actual_duration=None) -> dict:
    """Compare published audio to its source, allowing only encoder rounding."""
    def valid(value):
        return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>0
    source=source_duration if valid(source_duration) else voice.get('source_duration')
    actual=actual_duration if valid(actual_duration) else voice.get('duration')
    if not valid(source) or not valid(actual):return {'state':'unknown'}
    delta=actual-source
    state='too_long' if delta>.1 else 'too_short' if delta<-.1 else 'matched'
    return {'state':state,'source_duration':source,'duration':actual,'difference_seconds':round(delta,3),
            'label':{'too_long':'Тривалість перевищена','too_short':'Тривалість закоротка'}.get(state,'')}


@lru_cache(maxsize=256)
def has_audio(path: str, size: int, stamp: int) -> bool:
    result = subprocess.run(['ffprobe','-v','error','-select_streams','a','-show_entries','stream=index','-of','csv=p=0',path],
                            capture_output=True,text=True,timeout=30)
    if result.returncode:
        raise store.StudioError('Не вдалося прочитати звук матеріалу: '+Path(path).name)
    return bool(result.stdout.strip())


def voice_clip(clip: dict, assets: dict, planned_id: str | None) -> bool:
    name = str(clip.get('title') or '')
    label = name + ' ' + str(assets.get(clip.get('asset_id'),{}).get('name') or '')
    role = clip.get('audio_role')
    if role in {'music','sfx','sound'} or re.search(r'music_sfx|музик|музык|\bmusic\b|\bsfx\b',label,re.I):
        return False
    return clip.get('kind') == 'audio' and ((planned_id is not None and clip.get('asset_id') == planned_id) or role in {'voice','voiceover','narration'}
        or bool(re.fullmatch(r'озвучка|voiceover|narration',name.strip(),re.I)))


def destination(project: dict, code: str) -> Path:
    import languages
    languages.check_code(code)
    folder=Path(project.get('episode_path') or '')
    if not project.get('episode_path') or not folder.is_dir():
        raise store.StudioError('Папку випуску не знайдено. Спершу підключіть її до проєкту.',409)
    return folder/'Мови'/languages.LANGUAGES[code][0]/f'Озвучка зі звуком - {languages.LANGUAGES[code][0]}.mp3'


def snapshot(project: dict, code: str) -> dict:
    import languages
    languages.check_code(code)
    pid=project['id'];data=languages.load_state(pid)
    for report in (languages.translation_check(pid, code), languages.voice_language_check(pid, code)):
        if report['state'] != 'ok':
            raise store.StudioError(languages.language_quality.message(report), 409)
    voice=(data.get('languages',{}).get(code) or {}).get('voice') or {}
    if not languages.voice_current(pid,code,voice):
        raise store.StudioError('Озвучка не відповідає поточному тексту або голосу. Спершу оновіть її.',409)
    translated=languages.file_path(pid,code,'voice')
    target=destination(project,code)
    plan=store.load_project_narration(pid) or {}
    planned_id=((plan.get('timing') or {}).get('audio') or {}).get('asset_id')
    assets={a['id']:a for a in project.get('assets',[])}
    tracks=[];found_voice=False
    translated_duration=store.media_duration(translated)
    check=duration_check(voice,voice.get('source_duration') or project.get('duration'),translated_duration)
    if check['state'] in {'too_long','too_short'}:
        raise store.StudioError(check['label']+'. Готові фрази збережено в кеші. Файл випуску не збережено.',409)
    total=max(float(project.get('duration') or 0),max((float(c.get('start') or 0)+float(c.get('duration') or 0)
              for layer in project.get('tracks',[]) for c in layer.get('clips',[])),default=0))
    for layer in project.get('tracks',[]):
        for clip in layer.get('clips',[]):
            kind=clip.get('kind');narration=voice_clip(clip,assets,planned_id)
            if narration:
                found_voice=True
                if layer.get('muted') or float(clip.get('volume',1))<=0:
                    raise store.StudioError('Увімкніть доріжку озвучки перед збереженням аудіо.',409)
            if kind not in {'audio','video'} or layer.get('muted') or (layer.get('hidden') and kind!='audio'):
                continue
            volume=float(clip.get('volume',0 if kind=='video' else 1))
            if volume<=0:continue
            path=translated if narration else Path(store.resolve_asset(project,clip['asset_id'])['path'])
            stat=path.stat()
            if kind=='video' and not has_audio(str(path),stat.st_size,stat.st_mtime_ns):continue
            start=float(clip.get('start') or 0);trim=float(clip.get('trim_start') or 0)
            duration=float(clip['duration'])
            tracks.append({'source':str(path),'start':start,
                'trim_start':trim,'duration':duration,
                'volume':volume,'voice':narration,'size':stat.st_size,'stamp':stat.st_mtime_ns})
    if not found_voice:
        stat=translated.stat();length=store.media_duration(translated)
        tracks.insert(0,{'source':str(translated),'start':0,'trim_start':0,'duration':length,'volume':1,'voice':True,
                         'size':stat.st_size,'stamp':stat.st_mtime_ns})
        total=max(total,length)
    signature=hashlib.sha256(json.dumps({'version':1,'tracks':tracks,'total':total,'destination':str(target)},sort_keys=True).encode()).hexdigest()
    return {'tracks':tracks,'duration':total,'destination':target,'signature':signature}


def status(project: dict, code: str, saved: dict | None) -> dict:
    try:
        snap=snapshot(project,code)
    except (OSError,RuntimeError,ValueError,store.StudioError) as error:
        return {'state':'unavailable','error':str(error)}
    target=snap['destination'];saved=saved or {}
    if not target.is_file():return {'state':'missing','filename':target.name}
    stat=target.stat()
    current=(saved.get('signature')==snap['signature'] and saved.get('size')==stat.st_size
             and saved.get('stamp')==stat.st_mtime_ns)
    return {'state':'saved' if current else 'outdated','filename':target.name,'path':str(target),'saved_at':saved.get('saved_at')}


def ffmpeg_command(snap: dict, output: Path) -> list[str]:
    total=snap['duration'];cmd=['ffmpeg','-v','error','-nostdin','-y','-threads','2']
    for track in snap['tracks']:
        cmd+=['-ss',str(track['trim_start']),'-t',str(track['duration']),'-i',track['source']]
    cmd+=['-f','lavfi','-t',str(total),'-i','anullsrc=r=48000:cl=stereo']
    filters=[];labels=[]
    for n,track in enumerate(snap['tracks']):
        label=f'a{n}';labels.append(f'[{label}]')
        filters.append(f'[{n}:a]aresample=48000,atrim=duration={track["duration"]},asetpts=PTS-STARTPTS,'
                       f'volume={track["volume"]},adelay={round(track["start"]*48000)}S:all=1[{label}]')
    labels.append(f'[{len(snap["tracks"])}:a]')
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=longest:normalize=0:dropout_transition=0,'
                   f'alimiter=limit=0.891:level=false:latency=true,atrim=duration={total}[mix]')
    return cmd+['-filter_complex_threads','2','-filter_complex',';'.join(filters),'-map','[mix]','-t',str(total),
                '-ar','48000','-ac','2','-c:a','libmp3lame','-b:a','192k',str(output)]


def save(pid: str, code: str, job: dict) -> None:
    import languages
    project=store.load_project(pid);snap=snapshot(project,code);target=snap['destination']
    target.parent.mkdir(parents=True,exist_ok=True)
    automatic=job.get('kind') in {'voice','refit'}
    languages.progress(pid,job,max(job.get('progress',0),96) if automatic else 10,'Збираємо озвучку, музику й ефекти')
    with tempfile.TemporaryDirectory(prefix='.videokey-audio-',dir=target.parent) as directory:
        staged=Path(directory)/'mix.mp3'
        languages.run(ffmpeg_command(snap,staged),'зберегти аудіо випуску')
        duration=store.media_duration(staged)
        if duration is None or abs(duration-snap['duration'])>.1:
            raise RuntimeError('Тривалість аудіо не збігається з монтажем. Попередній файл збережено.')
        languages.progress(pid,job,99 if automatic else 95,'Перевіряємо й зберігаємо файл у папці випуску')
        with store.LOCK:
            if snapshot(store.load_project(pid),code)['signature']!=snap['signature']:
                raise store.StudioError('Монтаж або озвучка змінилися під час збереження. Натисніть «Зберегти» ще раз.',409)
            if target.exists():
                history=languages.work_dir(pid,code)/'mix-history'/str(time.time_ns());history.mkdir(parents=True)
                shutil.copy2(target,history/target.name)
            staged.replace(target)
        stat=target.stat()
        record={'signature':snap['signature'],'size':stat.st_size,'stamp':stat.st_mtime_ns,'saved_at':time.time(),
                'path':str(target),'duration':duration,'tracks':len(snap['tracks'])}
        languages.update(pid,lambda data:data.setdefault('languages',{}).setdefault(code,{}).update(saved_mix=record))
        job['path']=str(target)


def rebase_saved_after_move(pid: str, moves: dict) -> int:
    """A pure relocation does not make an otherwise current saved soundtrack stale."""
    import languages
    reverse={new:old for old,new in moves.items()};project=store.load_project(pid);updates={}
    data=languages.load_state(pid)
    for code,item in data.get('languages',{}).items():
        record=item.get('saved_mix')
        if not record:continue
        try:snap=snapshot(project,code)
        except (OSError,RuntimeError,ValueError,store.StudioError):continue
        original=[{**track,'source':reverse.get(track['source'],track['source'])} for track in snap['tracks']]
        signature=hashlib.sha256(json.dumps({'version':1,'tracks':original,'total':snap['duration'],'destination':str(snap['destination'])},sort_keys=True).encode()).hexdigest()
        if record.get('signature')==signature:updates[code]=snap['signature']
    if updates:
        def keep(current):
            for code,signature in updates.items():current['languages'][code]['saved_mix']['signature']=signature
        languages.update(pid,keep)
    return len(updates)
