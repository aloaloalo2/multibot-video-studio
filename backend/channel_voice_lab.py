"""Saved original-voice settings for Studio channels. No automatic paid work."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
import store
import languages
import eleven_api
import heygen_voice
import eleven_voices
import voice_reference_drafts as reference_drafts

TRIAL_CHANNEL = 'b012a0e49c3b1c18'
MODELS = {'eleven_v4_turbo': 'Eleven v4 Turbo', 'eleven_v4': 'Eleven v4'}
DELIVERY = {'neutral': '', 'conversational': '[Warm, conversational tone] ', 'calm': '[Calm, relaxed voice] '}
DEFAULT_TEXT = 'Давайте спокойно разберёмся, что здесь происходит. На первый взгляд всё кажется довольно простым. Но есть одна деталь, на которую стоит обратить внимание. Сейчас я объясню её на обычном примере.'
DEFAULTS = {'heygen_model':'heygen-voice-1-turbo-free', 'heygen_voice_id':'', 'provider': 'elevenlabs', 'language': 'ru', 'model': 'eleven_v4_turbo', 'delivery': 'conversational',
            'stability': .5, 'similarity_boost': .75, 'fish_engine': languages.FISH_ENGINE,
            'temperature': .7, 'top_p': .7, 'speed': 1., 'chunk_length': 200, 'direction': '', 'noise_cleanup': True, 'text': DEFAULT_TEXT}
PREPARATION_VERSION = 1
NOISE_FILTER = 'highpass=f=60,afftdn=nr=8:nf=-25:gs=5,loudnorm=I=-18:TP=-3:LRA=11'
LOCK = threading.RLock()
ACTIVE = set()


def folder(cid):
    store.get_channel_folder(cid)
    target = store.DATA_ROOT / 'channels' / cid / 'voice-lab'
    target.mkdir(parents=True, exist_ok=True)
    return target


def validated(raw):
    if raw is not None and not isinstance(raw, dict):
        raise store.StudioError('Невірні налаштування голосу')
    data = {**DEFAULTS, **{k: v for k, v in (raw or {}).items() if k in DEFAULTS}}
    if type(data['noise_cleanup']) is not bool:
        raise store.StudioError('Очищення шуму має бути увімкнене або вимкнене')
    if type(data['chunk_length']) is not int or not 100 <= data['chunk_length'] <= 300:
        raise store.StudioError('Розмір частини Fish має бути від 100 до 300')
    if not isinstance(data['direction'], str) or len(data['direction']) > 160 or re.search(r'[\[\]\r\n]', data['direction']):
        raise store.StudioError('Опишіть подачу одним рядком, до 160 символів, без квадратних дужок')
    data['direction'] = data['direction'].strip()
    if (data['provider'] not in {'elevenlabs', 'fishaudio', 'heygen'} or data['fish_engine'] not in languages.FISH_ENGINES
        or data['language'] not in languages.LANGUAGES or data['model'] not in MODELS or data['delivery'] not in DELIVERY):
        raise store.StudioError('Невідомі мова, модель або подача голосу')
    if data['heygen_model'] not in heygen_voice.MODELS or not isinstance(data['heygen_voice_id'],str) or (data['heygen_voice_id'] and not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}',data['heygen_voice_id'])):raise store.StudioError('Невірна модель або голос HeyGen')
    speed=data['speed']
    if isinstance(speed,bool) or not isinstance(speed,(int,float)) or not math.isfinite(speed) or not .9 <= speed <= 1.1:
        raise store.StudioError('Швидкість має бути від 90% до 110%')
    for key in ['stability', 'similarity_boost', 'temperature', 'top_p']:
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise store.StudioError('Параметри голосу мають бути від 0 до 100%')
    if not isinstance(data['text'], str) or not 10 <= len(data['text'].strip()) <= 2000:
        raise store.StudioError('Для зразка введіть від 10 до 2000 символів')
    data['text'] = data['text'].strip()
    return data


def reference(cid):
    root = folder(cid)
    file = root / 'reference.mp3'
    if not file.is_file(): return None
    meta = store.read_json(root / 'reference.json', {})
    return {'filename': meta.get('filename', 'Приклад голосу.mp3'), 'duration': meta.get('duration', 0),
            'approved': bool(meta.get('approved')), 'cleanup_applied': bool(meta.get('cleanup_applied')),
            'stamp': file.stat().st_mtime_ns, 'sha256': meta.get('sha256') or hashlib.sha256(file.read_bytes()).hexdigest()}


def fingerprint(settings, ref):
    if settings['provider']=='heygen':
        effective={k:settings[k] for k in ['heygen_model','heygen_voice_id','language','text','speed']}
        return hashlib.sha256(json.dumps(effective,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    # Preparation affects the remote reference, never overwrite/reuse a sample of the original recording.
    reference_key = ref['sha256'] + (f':clean-{PREPARATION_VERSION}' if settings['noise_cleanup'] else '')
    if settings['provider'] == 'elevenlabs':
        # Retain existing ElevenLabs samples when adding a second provider.
        effective = {k: settings[k] for k in ['language', 'model', 'delivery', 'stability', 'similarity_boost', 'text']}
        if settings['direction']: effective['direction'] = settings['direction']
        if settings.get('speed',1.) != 1.:effective['speed']=settings['speed']
        return hashlib.sha256(json.dumps({'settings': effective, 'reference': reference_key, 'version': 1}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    fields = ['provider', 'language', 'text', 'fish_engine', 'temperature', 'top_p']
    effective = {k: settings[k] for k in fields}
    if settings.get('speed',1.) != 1.:effective['speed'] = settings['speed']
    if settings['chunk_length'] != 200: effective['chunk_length'] = settings['chunk_length']
    return hashlib.sha256(json.dumps({'settings': effective, 'reference': reference_key, 'version': 3}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def delivery_prefix(settings):
    return '[' + settings['direction'] + '] ' if settings.get('direction') else DELIVERY[settings['delivery']]


def prepared_key(ref):
    return hashlib.sha256((ref['sha256'] + f':clean-{PREPARATION_VERSION}').encode()).hexdigest()


def prepared_source(cid, settings, ref):
    """Fast local denoise of a bounded clone reference. The complete original stays untouched."""
    root = folder(cid)
    if ref.get('approved') or not settings['noise_cleanup']: return root / 'reference.mp3'
    target = root / 'prepared' / (prepared_key(ref) + '.mp3')
    receipt = store.read_json(target.with_suffix('.json'), {})
    if target.is_file() and receipt.get('status') == 'done': return target
    target.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        source = eleven_voices.clone_files(root / 'reference.mp3', Path(tmp))[0]
        pending = Path(tmp) / 'clean.mp3'
        languages.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(source), '-t', '70', '-vn',
                       '-af', NOISE_FILTER, '-ar', '44100', '-ac', '1', '-b:a', '128k', '-map_metadata', '-1', str(pending)],
                      'очистити шум прикладу голосу')
        duration = store.media_duration(pending) or 0
        expected = min(store.media_duration(source) or 0, 70)
        if duration < 5 or abs(duration - expected) > .2:
            raise RuntimeError('Не вдалося перевірити очищений запис. Оригінал збережено.')
        pending.replace(target)
        store.atomic_json(target.with_suffix('.json'), {'status': 'done', 'duration': duration,
            'source_sha256': ref['sha256'], 'version': PREPARATION_VERSION})
    return target


def effective_reference(cid, settings):
    if settings['provider']=='heygen':
        if not settings['heygen_voice_id']:return None
        return {'sha256':hashlib.sha256(settings['heygen_voice_id'].encode()).hexdigest(),'duration':0,'filename':'Голос HeyGen'}
    return reference(cid)


def estimate(settings):
    if settings['provider']=='heygen':return {'unit':'usd','amount':len(settings['text'])*heygen_voice.RATES[settings['heygen_model']]}

    if settings['provider'] == 'fishaudio':
        spec = languages.FISH_ENGINES[settings['fish_engine']]
        rate = spec['promo'][0] if spec.get('promo') and time.time() < spec['promo'][1] else spec['per_char']
        return {'unit': 'usd', 'amount': len(settings['text'].encode('utf-8')) * rate}
    rate = eleven_api.STUDIO_ESTIMATE_RATES.get(settings['model'], .5)
    return {'unit': 'credits', 'amount': math.ceil(len(delivery_prefix(settings) + settings['text']) * rate)}


def snapshot(cid):
    root = folder(cid)
    saved = store.read_json(root / 'settings.json', {})
    if isinstance(saved.get('speed'), (int,float)) and not isinstance(saved.get('speed'),bool):saved['speed']=max(.9,min(1.1,saved['speed']))
    settings = validated(saved)
    local_ref=reference(cid)
    ref = effective_reference(cid,settings)
    job = store.read_json(root / 'job.json', {})
    if job.get('status') == 'running' and cid not in ACTIVE:
        job = {**job, 'status': 'failed', 'error': 'Студію перезапустили. Автоматичної повторної оплати не буде.'}
    current = fingerprint(settings, ref) if ref else None
    if job.get('status') == 'done' and job.get('fingerprint') != current:
        job = {}
    receipt = store.read_json(root / 'samples' / (current + '.json'), {}) if current else {}
    prepared = root / 'prepared' / (prepared_key(ref) + '.mp3') if ref and settings['provider']!='heygen' and settings['noise_cleanup'] else None
    return {'settings': settings, 'reference': local_ref, 'job': job,
            'heygen_models':[{'id':k,'name':v,'rate':heygen_voice.RATES[k]} for k,v in heygen_voice.MODELS.items()],
            'cached_original': bool(ref and (original_path(settings,ref).is_file() or (settings['provider']=='elevenlabs' and (root/'samples'/(fingerprint({**settings,'speed':1.},ref)+'.mp3')).is_file()))),
            'cached_fish_original': bool(ref and settings['provider']=='fishaudio' and fish_raw_path(settings,ref).is_file()),
            'sample_matches_settings': bool(current and job.get('fingerprint') == current),
            'cached_sample': bool(current and receipt.get('status') == 'done' and (root / 'samples' / (current + '.mp3')).is_file()),
            'models': [{'id': k, 'name': v} for k, v in MODELS.items()],
            'fish_models': [{'id': k, 'name': v['name'], 'rate': estimate({**settings, 'provider': 'fishaudio', 'fish_engine': k})['amount'] / max(1, len(settings['text'].encode('utf-8')))} for k, v in languages.FISH_ENGINES.items()],
            'languages': [{'code': k, 'name': v[0]} for k, v in languages.LANGUAGES.items()],
            'estimate': estimate(settings),
            'prepared_reference': {'key': prepared.stem} if prepared and prepared.is_file() else None,
            'estimate_rate': eleven_api.STUDIO_ESTIMATE_RATES.get(settings['model'], .5)}


def save(cid, settings):
    data = validated(settings)
    with LOCK:
        store.atomic_json(folder(cid) / 'settings.json', data)
    return snapshot(cid)


def copy_profile(source_cid, target_cid):
    """Explicitly reuse a voice and its existing cloud identity in another channel. No API calls."""
    source, target = folder(source_cid), folder(target_cid)
    with LOCK:
        if source_cid in ACTIVE or target_cid in ACTIVE:
            raise store.StudioError('Дочекайтеся завершення зразка', 409)
        if (target / 'reference.mp3').exists():
            raise store.StudioError('У каналі вже є голос', 409)
        ref = reference(source_cid)
        if not ref: raise store.StudioError('У вихідному каналі немає прикладу голосу')
        for name in ['settings.json', 'reference.mp3', 'reference.json']:
            shutil.copy2(source / name, target / name)
        meta = store.read_json(target / 'reference.json', {})
        meta['clone_owner'] = meta.get('clone_owner') or source_cid
        store.atomic_json(target / 'reference.json', meta)
        for name in ['prepared', 'samples']:
            if (source / name).is_dir(): shutil.copytree(source / name, target / name, dirs_exist_ok=True)
        for file in source.glob('fish-reference-*'):
            if file.is_file(): shutil.copy2(file, target / file.name)
        job = store.read_json(source / 'job.json', {})
        if job.get('status') == 'done': store.atomic_json(target / 'job.json', {**job, 'cached': True})
    return snapshot(target_cid)


def upload(cid, stream, size, filename):
    with LOCK:
        if cid in ACTIVE: raise store.StudioError('Дочекайтеся завершення зразка', 409)
        return {'draft': reference_drafts.upload(folder(cid), stream, size, filename)}


def preview_reference(cid, token):
    with LOCK:
        if cid in ACTIVE: raise store.StudioError('Дочекайтеся завершення зразка', 409)
        return {'draft': reference_drafts.clean(folder(cid), token)}


def accept_reference(cid, token, cleaned):
    with LOCK:
        if cid in ACTIVE: raise store.StudioError('Дочекайтеся завершення зразка', 409)
        root = folder(cid)
        reference_drafts.accept(root, token, cleaned)
        settings = validated(store.read_json(root/'settings.json', {}))
        settings['noise_cleanup'] = False  # the approved file is final; never process it again
        store.atomic_json(root/'settings.json', settings)
    return snapshot(cid)


def remove(cid):
    root = folder(cid)
    with LOCK:
        if cid in ACTIVE: raise store.StudioError('Дочекайтеся завершення зразка', 409)
        for name in ['reference.mp3', 'reference.json']:
            file = root / name
            if file.exists():
                archive = root / 'previous';archive.mkdir(exist_ok=True)
                file.replace(archive / f'{time.time_ns()}-{name}')
        (root / 'job.json').unlink(missing_ok=True)
    return snapshot(cid)


def clone(cid, settings, ref):
    root = folder(cid)
    source = Path(ref.get('prepared_path') or root / 'reference.mp3')
    secret = languages.key('elevenlabs')
    def create(ordinal):
        meta = languages.eleven_voice_metadata({'channel_id': cid}, settings['language'], ordinal)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            files = (reference_drafts.transport(source, Path(tmp)) if ref.get('approved') else eleven_voices.clone_files(source, Path(tmp)))
            body, mime = languages.multipart({'name': meta['name'][:90], 'description': meta['description'],
                'labels': json.dumps(meta['labels']), 'remove_background_noise': 'false'}, [('files', p, 'audio/mpeg') for p in files])
            result = languages.request(languages.ELEVEN + '/voices/add', body, {'xi-api-key': secret, 'Content-Type': mime}, 'ElevenLabs (клон голосу)')
        return json.loads(result).get('voice_id')
    owner = store.read_json(root / 'reference.json', {}).get('clone_owner') or cid
    voice = eleven_voices.resolve(secret, owner, settings['language'], source.read_bytes(), None, create)
    return secret, voice


def synthesis(secret, voice, settings):
    text = delivery_prefix(settings) + settings['text']
    params = {k: settings[k] for k in ['stability', 'similarity_boost']}
    if settings['model'] == 'eleven_v4_turbo':
        return eleven_api.streamed_dialogue(secret, voice, text, settings['model'], voice_settings=params)
    body = {'model_id': settings['model'], 'inputs': [{'text': text, 'voice_id': voice}], 'settings': params, 'language_code': settings['language']}
    return languages.request(languages.ELEVEN + '/text-to-dialogue/stream?output_format=mp3_44100_128',
        json.dumps(body, ensure_ascii=False).encode(), {'xi-api-key': secret, 'Content-Type': 'application/json', 'Accept': 'audio/mpeg'}, 'ElevenLabs')


def fish_reference(cid, settings, ref):
    """One short local reference, recognised once. No remote model creation or fallback billing."""
    root = folder(cid)
    source = Path(ref.get('prepared_path') or root / 'reference.mp3')
    source_key = prepared_key(ref) if settings['noise_cleanup'] else ref['sha256']
    key = hashlib.sha256((source_key + ':' + settings['language']).encode()).hexdigest()
    target = root / ('fish-reference-' + key + '.mp3')
    meta = store.read_json(target.with_suffix('.json'), {})
    if not target.is_file() or not meta.get('text'):
        languages.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(source),
                       '-t', '30', '-vn', '-ac', '1', '-b:a', '128k', str(target)], 'підготувати приклад Fish Audio')
        text = languages.heard(target, store.media_duration(target) or 30, settings['language'])
        if not text:
            raise RuntimeError('Не вдалося розпізнати приклад голосу для Fish Audio. Додайте чистіший запис мовлення.')
        meta = {'text': text};store.atomic_json(target.with_suffix('.json'), meta)
    return {'audio': target.read_bytes(), 'text': meta['text']}


def original_path(settings, ref):
    provider='heygen' if settings['provider']=='heygen' else 'fish' if settings['provider']=='fishaudio' else 'eleven'
    return store.DATA_ROOT/(provider+'-originals')/(fingerprint({**settings,'speed':1.},ref)+'.mp3')


def paced_audio(source, speed):
    if speed==1.:return source.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        output=Path(tmp)/'paced.mp3'
        languages.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(source),'-af',f'atempo={speed:.6f}','-b:a','128k',str(output)],'змінити темп без зміни тону')
        return output.read_bytes()


def eleven_local_synthesis(secret, voice, settings, ref):
    source=original_path(settings,ref);source.parent.mkdir(parents=True,exist_ok=True)
    if not source.is_file():
        audio=synthesis(secret,voice,{**settings,'speed':1.})
        pending=source.with_suffix('.pending.mp3');pending.write_bytes(audio)
        if not (store.media_duration(pending) or 0)>0:raise RuntimeError('ElevenLabs повернув неповний звук')
        pending.replace(source)
    return paced_audio(source,settings.get('speed',1.))


def heygen_synthesis(settings,ref):
    source=original_path(settings,ref);source.parent.mkdir(parents=True,exist_ok=True)
    if not source.is_file():
        audio=heygen_voice.synthesize(settings)
        pending=source.with_suffix('.pending.mp3');pending.write_bytes(audio)
        if not (store.media_duration(pending) or 0)>0:raise RuntimeError('HeyGen повернув неповний звук')
        pending.replace(source)
    return paced_audio(source,settings.get('speed',1.))


def fish_raw_path(settings, ref):
    key=fingerprint({**settings,'speed':1.},ref)
    return store.DATA_ROOT/'fish-originals'/(key+'.mp3')


def fish_synthesis(secret, voice, settings, raw_key=None):
    body = {'text': settings['text'], 'references': [voice], 'prosody': {'speed': 1.}, 'format': 'mp3', 'mp3_bitrate': 128,
            'normalize': True, 'language': settings['language'], 'latency': 'normal', 'chunk_length': settings['chunk_length'],
            'temperature': settings['temperature'], 'top_p': settings['top_p']}
    packed=languages.msgpack(body)
    target=store.DATA_ROOT/'fish-originals'/((raw_key or hashlib.sha256(packed).hexdigest())+'.mp3')
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.is_file():
        audio=languages.request(languages.FISH+'/v1/tts',packed,
            {'Authorization':'Bearer '+secret,'Content-Type':'application/msgpack','model':settings['fish_engine']},'Fish Audio')
        pending=target.with_suffix('.pending.mp3');pending.write_bytes(audio)
        if not (store.media_duration(pending) or 0)>0:raise RuntimeError('Fish повернув неповний звук')
        pending.replace(target)
    speed=settings.get('speed',1.)
    if speed==1.:return target.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        output=Path(tmp)/'paced.mp3'
        languages.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(target),'-af',f'atempo={speed:.6f}','-b:a','128k',str(output)],'змінити темп без зміни тону')
        return output.read_bytes()


def run(cid, settings, ref, job):
    root = folder(cid)
    try:
        fish = settings['provider'] == 'fishaudio'
        if settings['provider']=='heygen':
            audio=heygen_synthesis(settings,ref)
        else:
            ref = {**ref, 'prepared_path': str(prepared_source(cid, settings, ref))}
            with LOCK:
                job['stage'] = 'reference' if fish else 'clone';store.atomic_json(root / 'job.json', job)
            if fish:
                secret = languages.key('fishaudio')
                voice = fish_reference(cid, settings, ref)
            else:
                secret, voice = clone(cid, settings, ref)
            with LOCK:
                job['stage'] = 'speech';store.atomic_json(root / 'job.json', job)
            audio = fish_synthesis(secret, voice, settings, raw_key=fish_raw_path(settings,ref).stem) if fish else eleven_local_synthesis(secret, voice, settings,ref)
        target = root / 'samples' / (job['fingerprint'] + '.mp3')
        target.parent.mkdir(exist_ok=True)
        temporary = target.with_suffix('.pending.mp3');temporary.write_bytes(audio)
        duration = store.media_duration(temporary) or 0
        if duration <= 0: raise RuntimeError('Сервіс повернув неповний звук')
        temporary.replace(target)
        job.update(status='done', duration=duration, finished_at=time.time(), cached=False)
        store.atomic_json(target.with_suffix('.json'), job)
        if settings['provider']=='elevenlabs': eleven_api.invalidate_balance()
    except Exception as error:
        job.update(status='failed', error=str(error), finished_at=time.time())
    finally:
        with LOCK:
            store.atomic_json(root / 'job.json', job)
            ACTIVE.discard(cid)


def start(cid, raw, client_id):
    settings = validated(raw);root = folder(cid)
    if not isinstance(client_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', client_id):
        raise store.StudioError('Немає ідентифікатора запиту')
    with LOCK:
        old = store.read_json(root / 'job.json', {})
        ref = effective_reference(cid,settings)
        if not ref: raise store.StudioError('Виберіть голос HeyGen' if settings['provider']=='heygen' else 'Додайте приклад голосу')
        key = fingerprint(settings, ref)
        original=original_path(settings,ref)
        # Existing 100% samples are already valid originals. Preserve their paid generation.
        previous=root/'samples'/(fingerprint({**settings,'speed':1.},ref)+'.mp3')
        if settings['provider']=='elevenlabs' and previous.is_file() and not original.is_file():
            original.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(previous,original)
        if cid in ACTIVE:
            if old.get('fingerprint') != key:
                raise store.StudioError('Ще створюється зразок із попередніми налаштуваннями. Дочекайтеся його завершення й створіть новий.', 409)
            return snapshot(cid)
        if old.get('client_id') == client_id:
            if old.get('fingerprint') != key:
                raise store.StudioError('Цей запит уже використано з іншими налаштуваннями', 409)
            return snapshot(cid)
        languages.language_quality.require(settings['language'], settings['text'])
        store.atomic_json(root / 'settings.json', settings)
        target = root / 'samples' / (key + '.mp3')
        cached = store.read_json(target.with_suffix('.json'), {})
        if target.is_file() and cached.get('status') == 'done':
            store.atomic_json(root / 'job.json', {**cached, 'client_id': client_id, 'cached': True})
            return snapshot(cid)
        # Save the reservation before either cloning or speech. Restart never replays a paid call.
        cost = {'unit':'credits' if settings['provider']=='elevenlabs' else 'usd','amount':0} if original_path(settings,ref).is_file() else estimate(settings)
        prepared = root / 'prepared' / (prepared_key(ref) + '.mp3')
        needs_cleanup = settings['provider']!='heygen' and settings['noise_cleanup'] and not (prepared.is_file() and store.read_json(prepared.with_suffix('.json'), {}).get('status') == 'done')
        job = {'status': 'running', 'stage': 'speech' if settings['provider']=='heygen' else 'cleanup' if needs_cleanup else ('reference' if settings['provider'] == 'fishaudio' else 'clone'),
               'provider': settings['provider'], 'client_id': client_id, 'fingerprint': key, 'started_at': time.time(),
               'settings': settings.copy(),
               'estimate': cost, 'estimated_credits': cost['amount'] if cost['unit'] == 'credits' else None}
        store.atomic_json(root / 'settings.json', settings)
        store.atomic_json(root / 'job.json', job)
        ACTIVE.add(cid)
        threading.Thread(target=run, args=(cid, settings.copy(), ref.copy(), job), daemon=True).start()
    return snapshot(cid)


def audio_file(cid, kind, fingerprint=None):
    root = folder(cid)
    if kind == 'reference': target = root / 'reference.mp3'
    elif kind == 'sample' and re.fullmatch(r'[0-9a-f]{64}', fingerprint or ''):
        target = root / 'samples' / (fingerprint + '.mp3')
    elif kind == 'prepared' and re.fullmatch(r'[0-9a-f]{64}', fingerprint or ''):
        target = root / 'prepared' / (fingerprint + '.mp3')
    else: raise store.StudioError('Аудіо не знайдено', 404)
    if not target.is_file(): raise store.StudioError('Аудіо не знайдено', 404)
    return target
