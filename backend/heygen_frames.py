"""Generate and reuse HeyGen presenter clips for the director's timed frames."""
import hashlib
import json
import math
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import heygen_voice
import heygen_avatars
import host_from_voice
import montage_ops
import store


def configured_look(project):
    folder = store.get_channel_folder(project['channel_id'], include_disabled=True)
    avatar = store.read_channel_settings(folder, {}).get('heygen_avatar') or {}
    return (avatar.get('look') or {}).get('id')


def validate(project, plan):
    if host_from_voice.voice_video(project, plan):
        return
    if not configured_look(project):
        raise store.StudioError('Для HeyGen відео виберіть аватар і його образ у налаштуваннях каналу або додайте відео з озвучкою.', 409)
    audio = (plan.get('timing') or {}).get('audio') or {}
    if not audio.get('asset_id'):
        raise store.StudioError('Для HeyGen відео додайте аудіофайл озвучки до проєкту.', 409)
    store.resolve_asset(project, audio['asset_id'])


def _upload(path):
    request = urllib.request.Request('https://upload.heygen.com/v1/asset', data=path.read_bytes(),
        headers={'X-Api-Key': heygen_voice.key(), 'Content-Type': 'audio/wav'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except (OSError, ValueError) as error:
        raise store.StudioError('Не вдалося завантажити аудіофрагмент у HeyGen.') from error
    asset_id = (result.get('data') or {}).get('id')
    if not asset_id:
        raise store.StudioError('HeyGen не підтвердив завантаження аудіо.')
    return asset_id


def _data(result):
    data = result.get('data') if isinstance(result, dict) else None
    if not isinstance(data, dict):
        raise store.StudioError('HeyGen повернув незрозумілу відповідь.')
    return data


def _cancelled(pid, request_id):
    import director
    import episode_pause
    current = store.load_project(pid).get('production_request') or {}
    return (current.get('id') != request_id or current.get('paused') or
            director.stop_asked(pid, 'production') or episode_pause.paused(pid))


def make(pid, request):
    project = store.load_project(pid)
    plan = store.load_project_plan(pid)
    if host_from_voice.voice_video(project, plan):
        host_from_voice.place(pid)
        return
    made = set(store.made_frames(project, plan))
    frames = [f for f in plan['frames'] if f.get('format') == 'host' and f['number'] <= request['frames'] and f['number'] not in made]
    if not frames:
        return
    validate(project, plan)
    look = configured_look(project)
    if not heygen_avatars.supports_avatar_iii(look):
        raise store.StudioError('Вибраний образ HeyGen не підтримує Avatar III. Виберіть інший образ у налаштуваннях каналу.', 409)
    audio = plan['timing']['audio']
    source = Path(store.resolve_asset(project, audio['asset_id'])['path'])
    digest = store.audio_fingerprint(source)
    if audio.get('sha256') and audio['sha256'] != digest:
        raise store.StudioError('Озвучка змінилася. Оновіть таймінги перед створенням HeyGen відео.')
    root = store.project_dir(pid) / 'heygen-frames'
    root.mkdir(parents=True, exist_ok=True)
    fps = int(project.get('fps') or 25)
    for frame in frames:
        if _cancelled(pid, request['id']):
            raise InterruptedError('Створення HeyGen відео на паузі.')
        start = math.floor(float(frame['start']) * fps + .5 + 1e-8) / fps
        end = math.floor(float(frame['end']) * fps + .5 + 1e-8) / fps
        identity = {'audio': digest, 'look': look, 'start': start, 'end': end, 'fps': fps}
        old_fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        old_record = store.read_json(root / (old_fingerprint + '.json'), {}) or {}
        if old_record.get('state') in {'submitting', 'submitted'}:
            raise store.StudioError('Раніше для цього кадру було запущено відео HeyGen. Перевірте його стан перед створенням Avatar III, щоб уникнути повторної оплати.')
        identity['engine'] = 'avatar_iii'
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        receipt = root / (fingerprint + '.json')
        wav = root / (fingerprint + '.wav')
        output = root / (fingerprint + '.mp4')
        record = store.read_json(receipt, {}) or {}
        if record.get('state') == 'failed':
            raise store.StudioError('HeyGen повідомив про помилку створення відео для кадру ' + str(frame['number']))
        if record.get('state') == 'submitting' and not record.get('video_id'):
            raise store.StudioError('Відповідь HeyGen загублена після запуску відео. Перевірте HeyGen перед повторним створенням, щоб уникнути повторної оплати.')
        if not record.get('video_id'):
            if not wav.is_file():
                result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', str(start), '-i', str(source), '-t', str(end-start), '-vn', '-ac', '1', '-ar', '48000', str(wav)], capture_output=True, timeout=120)
                if result.returncode:
                    raise store.StudioError('Не вдалося вирізати фрагмент озвучки для HeyGen.')
            audio_id = _upload(wav)
            if _cancelled(pid, request['id']):
                raise InterruptedError('Створення HeyGen відео на паузі.')
            record = {'state': 'submitting', 'identity': identity, 'audio_asset_id': audio_id}
            store.atomic_json(receipt, record)
            try:
                response = heygen_voice._call('/v3/videos', {'type': 'avatar', 'avatar_id': look,
                    'audio_asset_id': audio_id, 'engine': {'type': 'avatar_iii'},
                    'resolution': '1080p', 'aspect_ratio': '16:9'}, timeout=90)
            except heygen_voice.NotSent:
                record['state'] = 'not_sent'
                store.atomic_json(receipt, record)
                raise store.StudioError('Запит до HeyGen не відправлено. Продовжіть створення.') from None
            except heygen_voice.RateLimited as error:
                record['state'] = 'not_sent'
                store.atomic_json(receipt, record)
                raise store.StudioError('HeyGen обмежив кількість запитів. Продовжіть створення пізніше.') from error
            except store.StudioError:
                record['state'] = 'not_sent'
                store.atomic_json(receipt, record)
                raise
            except (heygen_voice.Lost, heygen_voice.Gateway) as error:
                raise store.StudioError('HeyGen не підтвердив запуск відео. Перевірте HeyGen перед повтором, щоб уникнути повторної оплати.') from error
            data = _data(response)
            video_id = data.get('video_id') or data.get('id')
            if not video_id:
                raise store.StudioError('HeyGen не повернув ID відео. Перевірте HeyGen перед повтором, щоб уникнути повторної оплати.')
            if not isinstance(video_id, str) or not video_id.replace('-', '').replace('_', '').isalnum():
                raise store.StudioError('HeyGen повернув некоректний ID відео. Перевірте HeyGen перед повтором.')
            record.update(state='submitted', video_id=video_id)
            store.atomic_json(receipt, record)
        if not output.is_file():
            if not record['video_id'].replace('-', '').replace('_', '').isalnum():
                raise store.StudioError('Збережений ID відео HeyGen некоректний.')
            deadline = time.monotonic() + 3600
            while True:
                if _cancelled(pid, request['id']):
                    raise InterruptedError('Створення HeyGen відео на паузі.')
                data = _data(heygen_voice._call('/v3/videos/' + record['video_id'], timeout=45))
                if data.get('status') == 'failed':
                    record['state'] = 'failed'
                    store.atomic_json(receipt, record)
                    raise store.StudioError('HeyGen не зміг створити відео для кадру ' + str(frame['number']))
                if data.get('status') == 'completed':
                    url = data.get('video_url')
                    if not isinstance(url, str) or not url.startswith('https://'):
                        raise store.StudioError('HeyGen не повернув готове відео.')
                    temporary = output.with_suffix('.part')
                    with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as target:
                        import shutil
                        shutil.copyfileobj(response, target)
                    if not store.media_duration(temporary):
                        temporary.unlink(missing_ok=True)
                        raise store.StudioError('Не вдалося прочитати готове відео HeyGen.')
                    os.replace(temporary, output)
                    record['state'] = 'completed'
                    store.atomic_json(receipt, record)
                    break
                if time.monotonic() >= deadline:
                    raise store.StudioError('HeyGen ще створює відео. Натисніть «Продовжити» пізніше.')
                time.sleep(5)
        if _cancelled(pid, request['id']):
            raise InterruptedError('Створення HeyGen відео на паузі.')
        project = store.load_project(pid)
        if frame['number'] in store.made_frames(project, store.load_project_plan(pid)):
            continue
        aid = record.get('asset_id')
        try:
            asset = store.resolve_asset(project, aid) if aid else None
        except store.StudioError:
            asset = None
        if not asset:
            asset = store.import_asset_file(project, output, 'heygen')
            record['asset_id'] = asset['id']
            store.atomic_json(receipt, record)
        montage_ops.run(pid, [{'op': 'place', 'frame': frame['number'], 'asset_id': asset['id'], 'trim_start': 0}])
