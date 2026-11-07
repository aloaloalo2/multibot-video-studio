"""Opt-in original-voice playground for one trial channel. No automatic paid work."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import threading
import time
import store
import languages
import eleven_api
import eleven_voices

TRIAL_CHANNEL = 'b012a0e49c3b1c18'
MODELS = {'eleven_v4_turbo': 'Eleven v4 Turbo', 'eleven_v4': 'Eleven v4'}
DELIVERY = {'neutral': '', 'conversational': '[Warm, conversational tone] ', 'calm': '[Calm, relaxed voice] '}
DEFAULT_TEXT = 'Давайте спокойно разберёмся, что здесь происходит. На первый взгляд всё кажется довольно простым. Но есть одна деталь, на которую стоит обратить внимание. Сейчас я объясню её на обычном примере.'
DEFAULTS = {'provider': 'elevenlabs', 'language': 'ru', 'model': 'eleven_v4_turbo', 'delivery': 'conversational',
            'stability': .5, 'similarity_boost': .75, 'fish_engine': languages.FISH_ENGINE,
            'temperature': .7, 'top_p': .7, 'chunk_length': 200, 'direction': '', 'noise_cleanup': True, 'text': DEFAULT_TEXT}
PREPARATION_VERSION = 1
NOISE_FILTER = 'highpass=f=60,afftdn=nr=8:nf=-25:gs=5,loudnorm=I=-18:TP=-3:LRA=11'
LOCK = threading.RLock()
ACTIVE = set()


def folder(cid):
    store.get_channel_folder(cid)
    if cid != TRIAL_CHANNEL:
        raise store.StudioError('Тест голосу поки доступний лише для каналу Валентина Чичваркіна', 404)
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
    if (data['provider'] not in {'elevenlabs', 'fishaudio'} or data['fish_engine'] not in languages.FISH_ENGINES
        or data['language'] not in languages.LANGUAGES or data['model'] not in MODELS or data['delivery'] not in DELIVERY):
        raise store.StudioError('Невідомі мова, модель або подача голосу')
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
            'stamp': file.stat().st_mtime_ns, 'sha256': meta.get('sha256') or hashlib.sha256(file.read_bytes()).hexdigest()}


def fingerprint(settings, ref):
    # Preparation affects the remote reference, never overwrite/reuse a sample of the original recording.
    reference_key = ref['sha256'] + (f':clean-{PREPARATION_VERSION}' if settings['noise_cleanup'] else '')
    if settings['provider'] == 'elevenlabs':
        # Retain existing ElevenLabs samples when adding a second provider.
        effective = {k: settings[k] for k in ['language', 'model', 'delivery', 'stability', 'similarity_boost', 'text']}
        if settings['direction']: effective['direction'] = settings['direction']
        return hashlib.sha256(json.dumps({'settings': effective, 'reference': reference_key, 'version': 1}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    fields = ['provider', 'language', 'text', 'fish_engine', 'temperature', 'top_p']
    effective = {k: settings[k] for k in fields}
    if settings['chunk_length'] != 200: effective['chunk_length'] = settings['chunk_length']
    return hashlib.sha256(json.dumps({'settings': effective, 'reference': reference_key, 'version': 2}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def delivery_prefix(settings):
    return '[' + settings['direction'] + '] ' if settings.get('direction') else DELIVERY[settings['delivery']]


def prepared_key(ref):
    return hashlib.sha256((ref['sha256'] + f':clean-{PREPARATION_VERSION}').encode()).hexdigest()


def prepared_source(cid, settings, ref):
    """Fast local denoise of a bounded clone reference. The complete original stays untouched."""
    root = folder(cid)
    if not settings['noise_cleanup']: return root / 'reference.mp3'
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


def estimate(settings):
    if settings['provider'] == 'fishaudio':
        spec = languages.FISH_ENGINES[settings['fish_engine']]
        rate = spec['promo'][0] if spec.get('promo') and time.time() < spec['promo'][1] else spec['per_char']
        return {'unit': 'usd', 'amount': len(settings['text'].encode('utf-8')) * rate}
    rate = eleven_api.STUDIO_ESTIMATE_RATES.get(settings['model'], .5)
    return {'unit': 'credits', 'amount': math.ceil(len(delivery_prefix(settings) + settings['text']) * rate)}


def snapshot(cid):
    root = folder(cid)
    settings = validated(store.read_json(root / 'settings.json', {}))
    ref = reference(cid)
    job = store.read_json(root / 'job.json', {})
    if job.get('status') == 'running' and cid not in ACTIVE:
        job = {**job, 'status': 'failed', 'error': 'Студію перезапустили. Автоматичної повторної оплати не буде.'}
    current = fingerprint(settings, ref) if ref else None
    if job.get('status') == 'done' and job.get('fingerprint') != current:
        job = {}
    receipt = store.read_json(root / 'samples' / (current + '.json'), {}) if current else {}
    prepared = root / 'prepared' / (prepared_key(ref) + '.mp3') if ref and settings['noise_cleanup'] else None
    return {'settings': settings, 'reference': ref, 'job': job,
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


def upload(cid, stream, size, filename):
    root = folder(cid)
    if not 0 < size <= 200 * 1024 * 1024:
        raise store.StudioError('Запис порожній або перевищує 200 МБ', 413)
    with LOCK:
        if cid in ACTIVE: raise store.StudioError('Дочекайтеся завершення зразка', 409)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            raw, converted = Path(tmp) / 'source', Path(tmp) / 'reference.mp3'
            with raw.open('wb') as out:
                left = size
                while left:
                    chunk = stream.read(min(left, 1024 * 1024))
                    if not chunk: raise store.StudioError('Файл завантажився не повністю')
                    out.write(chunk);left -= len(chunk)
            languages.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(raw), '-vn', '-af', languages.EXAMPLE_FILTER,
                           '-ac', '1', '-b:a', '128k', str(converted)], 'підготувати приклад голосу')
            duration = store.media_duration(converted) or 0
            if duration < 10: raise store.StudioError('Потрібно хоча б 10 секунд чистого голосу')
            digest = hashlib.sha256(converted.read_bytes()).hexdigest()
            converted.replace(root / 'reference.mp3')
            store.atomic_json(root / 'reference.json', {'filename': Path(filename).name[:200], 'duration': duration, 'sha256': digest})
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
            files = eleven_voices.clone_files(source, Path(tmp))
            body, mime = languages.multipart({'name': meta['name'][:90], 'description': meta['description'],
                'labels': json.dumps(meta['labels']), 'remove_background_noise': 'false'}, [('files', p, 'audio/mpeg') for p in files])
            result = languages.request(languages.ELEVEN + '/voices/add', body, {'xi-api-key': secret, 'Content-Type': mime}, 'ElevenLabs (клон голосу)')
        return json.loads(result).get('voice_id')
    voice = eleven_voices.resolve(secret, cid, settings['language'], source.read_bytes(), None, create)
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


def fish_synthesis(secret, voice, settings):
    body = {'text': settings['text'], 'references': [voice], 'format': 'mp3', 'mp3_bitrate': 128,
            'normalize': True, 'language': settings['language'], 'latency': 'normal', 'chunk_length': settings['chunk_length'],
            'temperature': settings['temperature'], 'top_p': settings['top_p']}
    return languages.request(languages.FISH + '/v1/tts', languages.msgpack(body),
        {'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/msgpack', 'model': settings['fish_engine']}, 'Fish Audio')


def run(cid, settings, ref, job):
    root = folder(cid)
    try:
        fish = settings['provider'] == 'fishaudio'
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
        audio = fish_synthesis(secret, voice, settings) if fish else synthesis(secret, voice, settings)
        target = root / 'samples' / (job['fingerprint'] + '.mp3')
        target.parent.mkdir(exist_ok=True)
        temporary = target.with_suffix('.pending.mp3');temporary.write_bytes(audio)
        duration = store.media_duration(temporary) or 0
        if duration <= 0: raise RuntimeError('Сервіс повернув неповний звук')
        temporary.replace(target)
        job.update(status='done', duration=duration, finished_at=time.time(), cached=False)
        store.atomic_json(target.with_suffix('.json'), job)
        if not fish: eleven_api.invalidate_balance()
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
        ref = reference(cid)
        if not ref: raise store.StudioError('Додайте приклад голосу')
        key = fingerprint(settings, ref)
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
        cost = estimate(settings)
        job = {'status': 'running', 'stage': 'cleanup' if settings['noise_cleanup'] else ('reference' if settings['provider'] == 'fishaudio' else 'clone'),
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
