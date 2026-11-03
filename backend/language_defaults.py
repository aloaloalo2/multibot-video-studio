"""Saved channel narration choices and automatically available reference voices."""
from __future__ import annotations
import copy
import hashlib
import json
import shutil
import threading
import time
import uuid
from pathlib import Path
import store

LOCK=threading.RLock()


def signature(payload: dict) -> str:
    fingerprint=copy.deepcopy(payload)
    fingerprint['languages']=sorted(fingerprint.get('languages') or [])
    for voice in (fingerprint.get('voices') or {}).values():
        if voice:voice.pop('clone',None)
    return hashlib.sha256(json.dumps(fingerprint,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def root(cid: str) -> Path:
    store.get_channel_folder(cid)
    return store.DATA_ROOT/'language-defaults'/cid


def selection(pid: str) -> tuple[dict,dict]:
    import languages
    project=store.load_project(pid);data=languages.narration_settings(pid)
    codes=[code for code in languages.LANGUAGES if code in data.get('languages',{})]
    settings={'provider':data.get('provider') if data.get('provider') in languages.PROVIDERS else 'fishaudio',
              'eleven_engine':languages.eleven_engine(pid),'fish_engine':languages.fish_engine(pid),
              'fish_style':languages.fish_style(pid),'fish_styles':dict(data.get('fish_styles') or {})}
    settings['fish_styles'][settings['fish_engine']]=settings['fish_style']
    voices={};examples={}
    for code in codes:
        example=languages.voice_for(pid,code,original=False)
        if example:
            raw=example['path'].read_bytes();text=example['text']
            slot=f"elevenlabs-{code}-{example['from']}-{example['stamp']}"
            clone=(data.get('clones') or {}).get(slot)
            if not clone and example['from']=='defaults':clone=saved_clone(project['channel_id'],code)
            voices[code]={'sha256':hashlib.sha256(raw).hexdigest(),'text':text,'clone':clone}
            examples[code]=example
        else:voices[code]=None  # use each new episode's own original voice
    payload={'settings':settings,'languages':codes,'voices':voices}
    return {'payload':payload,'signature':signature(payload),'channel_id':project['channel_id']},examples


def status(pid: str) -> dict:
    try:
        selected,_=selection(pid)
        saved=store.read_json(root(selected['channel_id'])/'current.json',{}) or {}
        payload=selected['payload'];previous=saved.get('payload') or {}
        def effective(settings):
            provider=settings.get('provider','fishaudio')
            if provider=='elevenlabs':return (provider,settings.get('eleven_engine'))
            engine=settings.get('fish_engine')
            style=(settings.get('fish_styles') or {}).get(engine,settings.get('fish_style'))
            return (provider,engine,style)
        settings_match=bool(saved) and effective(previous.get('settings') or {})==effective(payload['settings'])
        # The button belongs to the open language. Extra language tabs and dormant engine preferences
        # do not change its selected voice or active synthesis parameters.
        by_language={code:settings_match and code in (previous.get('languages') or [])
                     and (voice or {}).get('sha256')==((previous.get('voices') or {}).get(code) or {}).get('sha256')
                     for code,voice in payload['voices'].items()}
        return {'saved':bool(by_language) and all(by_language.values()),'by_language':by_language,'exists':bool(saved)}
    except (OSError,RuntimeError,ValueError,store.StudioError):
        return {'saved':False,'exists':False}


def save(pid: str, code: str | None = None) -> dict:
    """Update the requested language, preserving other channel references and their clone IDs."""
    import languages
    with LOCK,languages.LOCK:
        selected,examples=selection(pid)
        previous=store.read_json(root(selected['channel_id'])/'current.json',{}) or {}
        if not selected['payload']['languages']:
            raise store.StudioError('Спершу додайте хоча б одну мову.',409)
        if code is not None:
            if not isinstance(code,str):raise store.StudioError('Вкажіть мову налаштувань.')
            languages.check_code(code)
            if code not in selected['payload']['languages']:
                raise store.StudioError('Цю мову ще не додано до проєкту.',409)
        affected=[code] if code is not None else selected['payload']['languages']
        old=previous.get('payload') or {}
        payload=copy.deepcopy(old)
        payload['settings']=selected['payload']['settings']
        payload['languages']=list(dict.fromkeys([*(old.get('languages') or []),*affected]))
        voices=payload.setdefault('voices',{})
        for language in affected:
            voice=copy.deepcopy(selected['payload']['voices'][language])
            earlier=voices.get(language) or {}
            if voice and not voice.get('clone') and voice.get('sha256')==earlier.get('sha256'):
                voice['clone']=earlier.get('clone')
            voices[language]=voice
        selected.update(payload=payload,signature=signature(payload))
        if previous and signature(old)==selected['signature']:
            return status(pid)
        base=root(selected['channel_id']);version=uuid.uuid4().hex;folder=base/version
        folder.mkdir(parents=True)
        for language,voice in voices.items():
            if not voice:continue
            dest=folder/language;dest.mkdir()
            if language not in affected:
                source=base/previous['version']/language
                for name in ('own-voice.mp3','own-voice.txt','own-voice.json'):
                    path=source/name
                    if path.is_file():shutil.copy2(path,dest/name)
                    elif name!='own-voice.json':
                        raise store.StudioError('Не знайдено збережений приклад голосу. Налаштування каналу не змінено.',409)
                continue
            example=examples[language]
            shutil.copy2(example['path'],dest/'own-voice.mp3')
            (dest/'own-voice.txt').write_text(example['text'],encoding='utf-8')
            # Retain normalization and Fish's existing model metadata, never API keys.
            meta=store.read_json(example['meta'],{}) or {}
            meta.update(example_level_version=languages.EXAMPLE_LEVEL_VERSION,example_source_stamp=languages.example_source_stamp(dest/'own-voice.mp3'),example_normalized_copy=False)
            store.atomic_json(dest/'own-voice.json',meta)
        saved={**selected,'version':version,'saved_at':time.time()}
        store.atomic_json(base/'current.json',saved)
    return status(pid)


def pin_narration(pid: str, code: str) -> None:
    """A run keeps its inherited voice/settings when another episode saves new defaults."""
    import languages
    with LOCK,languages.LOCK:
        data=languages.load_state(pid)
        resolved=languages.narration_settings(pid)
        for key in ('provider','eleven_engine','fish_engine','fish_style','fish_styles'):
            if key in resolved:data[key]=copy.deepcopy(resolved[key])
        example=languages.voice_for(pid,code,original=False)
        if example and example['from'] in ('defaults','channel'):
            project=store.load_project(pid)
            old_slot=f"elevenlabs-{code}-{example['from']}-{example['stamp']}"
            clone=(data.get('clones') or {}).get(old_slot)
            if not clone and example['from']=='defaults':clone=saved_clone(project['channel_id'],code)
            dest=languages.work_dir(pid,code);dest.mkdir(parents=True,exist_ok=True)
            shutil.copy2(example['path'],dest/'own-voice.mp3')
            (dest/'own-voice.txt').write_text(example['text'],encoding='utf-8')
            meta=store.read_json(example['meta'],{}) or {}
            meta.update(example_level_version=languages.EXAMPLE_LEVEL_VERSION,
                        example_source_stamp=languages.example_source_stamp(dest/'own-voice.mp3'),example_normalized_copy=False)
            store.atomic_json(dest/'own-voice.json',meta)
            if clone:
                data.setdefault('clones',{})[f"elevenlabs-{code}-episode-{(dest/'own-voice.mp3').stat().st_mtime_ns}"]=clone
        languages.save_state(pid,data)


def apply(project: dict, explicit: bool = False) -> bool:
    """Snapshot defaults at project creation; old projects retain their choices."""
    import languages
    cid=project['channel_id'];work=languages.work_dir(project['id'])
    if (work/'languages.json').exists() and not explicit:return False
    with LOCK:
        base=root(cid);saved=store.read_json(base/'current.json',{}) or {}
        if not saved:return False
        payload=saved['payload'];data=languages.load_state(project['id']) if explicit else {}
        data.update(copy.deepcopy(payload['settings']))
        for code in payload['languages']:
            if code in languages.LANGUAGES:data.setdefault('languages',{}).setdefault(code,{})
        data['defaults_signature']=saved['signature']
        for code,voice in payload['voices'].items():
            if code not in data['languages']:continue
            dest=work/code
            if explicit and dest.exists():
                existing=list(dest.glob('own-voice*'))
                if existing:
                    archive=dest/'reference-history'/str(time.time_ns());archive.mkdir(parents=True)
                    for path in existing:
                        if path.is_file():shutil.move(str(path),str(archive/path.name))
            if not voice:
                data['languages'][code]['use_original_voice']=True
                continue
            data['languages'][code].pop('use_original_voice',None)
            src=base/saved['version']/code;dest.mkdir(parents=True,exist_ok=True)
            for name in ('own-voice.mp3','own-voice.txt','own-voice.json'):
                if (src/name).is_file():shutil.copy2(src/name,dest/name)
            if voice.get('clone'):
                stamp=(dest/'own-voice.mp3').stat().st_mtime_ns
                data.setdefault('clones',{})[f'elevenlabs-{code}-episode-{stamp}']=voice['clone']
        languages.save_state(project['id'],data)
    return True


def apply_existing(pid: str) -> dict:
    import languages
    with LOCK,languages.LOCK:
        if languages.busy(pid,group='voice'):
            raise store.StudioError('Дочекайтеся завершення озвучення перед зміною голосу.',409)
        if not apply(store.load_project(pid),explicit=True):
            raise store.StudioError('Збережених налаштувань цього каналу ще немає.',404)
    return languages.overview(pid)


def reference(cid: str, code: str) -> dict | None:
    """An existing episode can use the channel's saved reference without an apply step."""
    import languages
    saved=store.read_json(root(cid)/'current.json',{}) or {}
    if not ((saved.get('payload') or {}).get('voices') or {}).get(code):return None
    version=saved.get('version','')
    if not __import__('re').fullmatch(r'[0-9a-f]{32}',version):return None
    return languages.read_example(root(cid)/version/code,'own-voice','defaults')


def saved_clone(cid: str, code: str) -> str | None:
    saved=store.read_json(root(cid)/'current.json',{}) or {}
    return (((saved.get('payload') or {}).get('voices') or {}).get(code) or {}).get('clone')


def settings(cid: str) -> dict:
    saved=store.read_json(root(cid)/'current.json',{}) or {}
    return copy.deepcopy((saved.get('payload') or {}).get('settings') or {})
