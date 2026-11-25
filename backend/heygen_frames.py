"""Generate and reuse HeyGen presenter clips for the director's timed frames."""
import hashlib
import json
import math
import os
import shutil
import subprocess
import threading
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
    if not audio_asset(project, plan):
        raise store.StudioError('Для HeyGen відео додайте аудіофайл озвучки до проєкту.', 409)


def audio_asset(project, plan):
    """The voice the plan is timed on: its asset id, or, when the plan kept only the voice's hash (a director plan on
    a voice the studio made, 25 November 2026), the project's audio with that hash. None when there is none."""
    audio = (plan.get('timing') or {}).get('audio') or {}
    if audio.get('asset_id'):
        try:
            return store.resolve_asset(project, audio['asset_id'])
        except store.StudioError:
            pass
    digest = audio.get('sha256')
    if not digest:
        return None
    sounds = [a for a in project.get('assets', []) if a.get('kind') == 'audio']
    for asset in sounds:   # the levelled narration carries its own hash: no file is read
        if (asset.get('narration_ending') or {}).get('sha256') == digest:
            return store.resolve_asset(project, asset['id'])
    for asset in sounds:
        try:
            found = store.resolve_asset(project, asset['id'])
            if store.audio_fingerprint(Path(found['path'])) == digest:
                return found
        except (store.StudioError, OSError, KeyError):
            continue
    return None


def _upload(path):
    request = urllib.request.Request('https://upload.heygen.com/v1/asset', data=path.read_bytes(),
        headers={'X-Api-Key': heygen_voice.key(), 'Content-Type': 'audio/x-wav'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        # HeyGen names the reason (25 November 2026: «Content type not match audio/wav != audio/x-wav»)
        try:
            reason = json.load(error).get('message') or ''
        except (OSError, ValueError):
            reason = ''
        raise store.StudioError('HeyGen не прийняв аудіофрагмент' + (': ' + str(reason)[:200] if reason else '.')) from error
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


# One HeyGen run a project at a time: a second request waits and then finds the frames made, so no video is bought twice.
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
# HeyGen allows 30 requests a minute; submissions keep under it, polls share the rest.
SUBMIT_GAP = 2.2
POLL_EVERY = 5


def _lock(pid):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(pid, threading.Lock())


def pending(pid, request):
    """Numbers of the host frames this request still needs from HeyGen (none when the voice is a video of the host)."""
    project = store.load_project(pid)
    plan = store.load_project_plan(pid) or {}
    hosts = [f for f in plan.get('frames', []) if isinstance(f, dict) and f.get('format') == 'host']
    if not hosts or host_from_voice.voice_video(project, plan):
        return []
    made = set(store.made_frames(project, plan))
    return [f['number'] for f in hosts
            if f['number'] <= int(request['frames']) and f['number'] not in made]


def make(pid, request):
    """All host frames go to HeyGen at once, render there side by side, and each goes on the timeline as soon as it is
    ready (user, 25 November 2026: «він буде паралельно створюватись?»). A frame that fails stops only itself; the first
    error is raised after every other frame is placed."""
    with _lock(pid):
        _make(pid, request)


def _make(pid, request):
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
    offered = heygen_avatars.engines(look)
    if 'avatar_iii' not in offered:
        raise store.StudioError('Вибраний образ HeyGen не підтримує Avatar III. Виберіть інший образ у налаштуваннях каналу.', 409)
    audio = plan['timing']['audio']
    source = Path(audio_asset(project, plan)['path'])
    digest = store.audio_fingerprint(source)
    if audio.get('sha256') and audio['sha256'] != digest:
        raise store.StudioError('Озвучка змінилася. Оновіть таймінги перед створенням HeyGen відео.')
    root = store.project_dir(pid) / 'heygen-frames'
    root.mkdir(parents=True, exist_ok=True)
    fps = int(project.get('fps') or 25)
    if ONE_VIDEO:
        first = first_frame_settings(project) if 'avatar_iv' in offered else {'enabled': False}
        opening = next((f for f in plan['frames'] if f.get('format') == 'host'), None)
        errors, special = [], None
        if first['enabled'] and opening and opening['number'] in {f['number'] for f in frames}:
            special = opening
            try:
                job, _ = _submit(pid, request, special, root, source, digest, look, fps, 0.0, 'avatar_iv',
                                 {'expressiveness': first['expressiveness'], 'motion_prompt': first['motion_prompt'] or DEFAULT_MOTION})
                special = job
            except heygen_voice.RateLimited:
                errors.append(store.StudioError('HeyGen обмежив кількість запитів. Продовжіть створення пізніше.'))
            except store.StudioError as error:
                errors.append(error)
        rest = [f for f in frames if not opening or f['number'] != opening['number'] or not special]
        single = []
        try:
            if len(rest) > 1:
                _make_one_video(pid, request, rest, root, source, digest, look, fps)
            elif rest:   # one frame has nothing to join: its own video
                job, _ = _submit(pid, request, rest[0], root, source, digest, look, fps, time.monotonic())
                single.append(job)
        except heygen_voice.RateLimited:
            errors.append(store.StudioError('HeyGen обмежив кількість запитів. Продовжіть створення пізніше.'))
        except store.StudioError as error:
            errors.append(error)
        waiting = single + ([special] if isinstance(special, dict) and 'receipt' in special else [])
        if waiting:
            _wait_jobs(pid, request, waiting, errors)
        if errors:
            raise errors[0]
        return
    errors = []
    jobs = []
    last_submit = 0.0
    for frame in frames:
        if _cancelled(pid, request['id']):
            raise InterruptedError('Створення HeyGen відео на паузі.')
        try:
            job, submitted = _submit(pid, request, frame, root, source, digest, look, fps, last_submit)
        except heygen_voice.RateLimited as error:
            errors.append(store.StudioError('HeyGen обмежив кількість запитів. Продовжіть створення пізніше.'))
            break
        except store.StudioError as error:
            errors.append(error)
            continue
        if submitted:
            last_submit = time.monotonic()
        jobs.append(job)
    _wait_jobs(pid, request, jobs, errors)
    if errors:
        raise errors[0]


def _wait_jobs(pid, request, jobs, errors):
    """Ask HeyGen about each video until it is ready, then download and place it; errors are collected."""
    deadline = time.monotonic() + 3600
    waiting = list(jobs)
    while waiting:
        if _cancelled(pid, request['id']):
            raise InterruptedError('Створення HeyGen відео на паузі.')
        for job in list(waiting):
            try:
                if _ready(job):
                    waiting.remove(job)
                    _place(pid, request, job)
            except heygen_voice.RateLimited:
                break
            except (heygen_voice.NotSent, heygen_voice.Lost, heygen_voice.Gateway, OSError):
                continue   # a status read or a download that failed is asked again next round: nothing is bought
            except store.StudioError as error:
                waiting.remove(job)
                errors.append(error)
        if not waiting:
            break
        if time.monotonic() >= deadline:
            errors.append(store.StudioError('HeyGen ще створює відео. Натисніть «Продовжити» пізніше.'))
            break
        # each poll is a request: with many videos at once a round is spread out to stay under HeyGen's limit
        time.sleep(max(POLL_EVERY, len(waiting) * 2.5))



def _frame_files(frame, root, digest, look, fps, engine='avatar_iii', options=None):
    """The frame's identity and its receipt, voice piece and video paths; refuses a frame left half sent before."""
    start = math.floor(float(frame['start']) * fps + .5 + 1e-8) / fps
    end = math.floor(float(frame['end']) * fps + .5 + 1e-8) / fps
    identity = {'audio': digest, 'look': look, 'start': start, 'end': end, 'fps': fps}
    old_fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    old_record = store.read_json(root / (old_fingerprint + '.json'), {}) or {}
    if old_record.get('state') in {'submitting', 'submitted'}:
        raise store.StudioError('Раніше для цього кадру було запущено відео HeyGen. Перевірте його стан перед створенням Avatar III, щоб уникнути повторної оплати.')
    identity['engine'] = engine
    identity.update(options or {})
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return identity, root / (fingerprint + '.json'), root / (fingerprint + '.wav'), root / (fingerprint + '.mp4')


def _cut_voice(source, start, end, wav, tail=0.0):
    """The frame's piece of the voice; `tail` seconds of silence after it give the video a tail for the transition out."""
    if wav.is_file():
        return
    pad = ['-af', f'apad=pad_dur={tail:.3f}'] if tail else []
    result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', str(start), '-i', str(source), '-t', str(end-start),
                             '-vn', *pad, '-ac', '1', '-ar', '48000', '-c:a', 'pcm_s16le', str(wav)], capture_output=True, timeout=120)
    if result.returncode:
        raise store.StudioError('Не вдалося вирізати фрагмент озвучки для HeyGen.')


def _send(pid, request, wav, receipt, identity, look, last_submit):
    """Upload the voice and start one Avatar III video; the receipt is written before the paid request."""
    wait = last_submit + SUBMIT_GAP - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    audio_id = _upload(wav)
    if _cancelled(pid, request['id']):
        raise InterruptedError('Створення HeyGen відео на паузі.')
    record = {'state': 'submitting', 'identity': identity, 'audio_asset_id': audio_id}
    engine = identity.get('engine') or 'avatar_iii'
    # the project's costs show what this video cost; no request for the rate
    rate = heygen_avatars.known_rate_iv(look) if engine == 'avatar_iv' else heygen_avatars.known_rate(look)
    if rate:
        record['usd_per_minute'] = rate
    store.atomic_json(receipt, record)
    payload = {'type': 'avatar', 'avatar_id': look, 'audio_asset_id': audio_id, 'engine': {'type': engine},
               'resolution': '1080p', 'aspect_ratio': '16:9'}
    if engine == 'avatar_iv':
        payload.update(motion_prompt=identity.get('motion_prompt') or DEFAULT_MOTION, expressiveness=identity.get('expressiveness') or 'medium')
    try:
        response = heygen_voice._call('/v3/videos', payload, timeout=90)
    except heygen_voice.NotSent:
        record['state'] = 'not_sent'
        store.atomic_json(receipt, record)
        raise store.StudioError('Запит до HeyGen не відправлено. Продовжіть створення.') from None
    except heygen_voice.RateLimited:
        record['state'] = 'not_sent'
        store.atomic_json(receipt, record)
        raise
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
    return record


def _submit(pid, request, frame, root, source, digest, look, fps, last_submit, engine='avatar_iii', options=None):
    """The frame's receipt, with a video id at HeyGen: cut, uploaded and submitted unless the receipt has it already.
    Returns (job, whether a new video was submitted)."""
    identity, receipt, wav, output = _frame_files(frame, root, digest, look, fps, engine, options)
    record = store.read_json(receipt, {}) or {}
    job = {'frame': frame, 'record': record, 'receipt': receipt, 'output': output}
    if record.get('state') == 'failed':
        raise store.StudioError('HeyGen повідомив про помилку створення відео для кадру ' + str(frame['number']))
    if record.get('state') == 'submitting' and not record.get('video_id'):
        raise store.StudioError('Відповідь HeyGen загублена після запуску відео. Перевірте HeyGen перед повторним створенням, щоб уникнути повторної оплати.')
    if record.get('video_id') or output.is_file():
        return job, False
    _cut_voice(source, identity['start'], identity['end'], wav, identity.get('tail', 0.0))
    job['record'] = _send(pid, request, wav, receipt, identity, look, last_submit)
    return job, True


# One video for all the host frames (user, 25 November 2026: «Аватар 3 і одним запитом»): Avatar III plays the same
# motion from the start of every clip, so twenty clips began with the same gesture; in one long video each frame takes
# the motion from another moment. The pieces of the voice are joined with a short silence between them, so a mouth
# never carries a sound over into the next frame, and the video is cut back at the same places.
ONE_VIDEO = True
# The film's first host frame goes alone to Avatar IV, which moves by a prompt (user, 25 November 2026: «Перший кадр буде
# через HeyGen 4»): in one long Avatar III video only its first piece starts with the engine's opening gesture.
DEFAULT_MOTION = ('Talks to the camera in a calm, friendly way; a slight nod and a small open-hand gesture near the start, '
                  'then natural small head movements while speaking.')
FIRST_DEFAULTS = {'enabled': True, 'expressiveness': 'medium', 'motion_prompt': ''}


def first_frame_settings(project):
    """The channel's «Перший кадр ведучого» settings (`heygen_first_frame`), filled with the defaults."""
    try:
        folder = store.get_channel_folder(project['channel_id'], include_disabled=True)
        saved = store.read_channel_settings(folder, {}).get('heygen_first_frame') or {}
    except (store.StudioError, OSError, KeyError):
        saved = {}
    result = dict(FIRST_DEFAULTS)
    if isinstance(saved, dict):
        result.update({key: saved[key] for key in FIRST_DEFAULTS if key in saved})
    return result
ONE_VIDEO_GAP = 0.4
ONE_VIDEO_MAX = 600.0   # seconds of voice in one video; a longer film's host frames go in several


def _batches(frames, fps):
    batches, current, length = [], [], 0.0
    for frame in frames:
        seconds = float(frame['end']) - float(frame['start'])
        if current and length + seconds > ONE_VIDEO_MAX:
            batches.append(current)
            current, length = [], 0.0
        current.append(frame)
        length += seconds + ONE_VIDEO_GAP
    if current:
        batches.append(current)
    return batches


def _join_voice(pieces, gap, target):
    """Join the WAV pieces (48 kHz mono 16-bit) with `gap` seconds of silence between them; returns each piece's
    start in the joined voice."""
    import wave
    offsets, at = [], 0
    temporary = target.with_suffix('.part.wav')
    with wave.open(str(temporary), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(48000)
        silence = b'\0\0' * int(round(gap * 48000))
        for index, piece in enumerate(pieces):
            if index:
                out.writeframes(silence)
                at += len(silence) // 2
            with wave.open(str(piece), 'rb') as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 48000):
                    raise store.StudioError('Фрагмент озвучки для HeyGen має незвичний формат.')
                offsets.append(at / 48000)
                frames = source.readframes(source.getnframes())
                out.writeframes(frames)
                at += len(frames) // 2
    os.replace(temporary, target)
    return offsets


def _cut_video(video, offset, seconds, output):
    """One frame's piece of the long video, re-encoded so it starts and ends exactly where its voice does."""
    temporary = output.with_suffix('.part.mp4')
    result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', f'{offset:.3f}', '-i', str(video), '-t', f'{seconds:.3f}',
                             '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                             '-movflags', '+faststart', str(temporary)], capture_output=True, timeout=600)
    if result.returncode or not store.media_duration(temporary):
        temporary.unlink(missing_ok=True)
        raise store.StudioError('Не вдалося вирізати кадр із відео HeyGen.')
    os.replace(temporary, output)


def _make_one_video(pid, request, frames, root, source, digest, look, fps):
    """The host frames of a film as one Avatar III video a batch, cut back into the frames and placed."""
    errors = []
    jobs = []
    last_submit = 0.0
    for batch in _batches(frames, fps):
        rows = []
        for frame in batch:
            identity, receipt, wav, output = _frame_files(frame, root, digest, look, fps)
            rows.append({'frame': frame, 'identity': identity, 'receipt': receipt, 'wav': wav, 'output': output})
        todo = [row for row in rows if not row['output'].is_file()]
        done = [row for row in rows if row['output'].is_file()]
        for row in done:   # cut already, from an earlier run: only placed
            jobs.append({'rows': [row]})
        if not todo:
            continue
        spans = [[row['identity']['start'], row['identity']['end']] for row in todo]
        identity = {'audio': digest, 'look': look, 'spans': spans, 'gap': ONE_VIDEO_GAP, 'fps': fps, 'engine': 'avatar_iii', 'one_video': True}
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        receipt, wav, video = root / ('one-' + fingerprint + '.json'), root / ('one-' + fingerprint + '.wav'), root / ('one-' + fingerprint + '.mp4')
        record = store.read_json(receipt, {}) or {}
        if record.get('state') == 'failed':
            errors.append(store.StudioError('HeyGen повідомив про помилку створення відео ведучого.'))
            continue
        if record.get('state') == 'submitting' and not record.get('video_id'):
            errors.append(store.StudioError('Відповідь HeyGen загублена після запуску відео. Перевірте HeyGen перед повторним створенням, щоб уникнути повторної оплати.'))
            continue
        if not record.get('video_id') and not video.is_file():
            if _cancelled(pid, request['id']):
                raise InterruptedError('Створення HeyGen відео на паузі.')
            try:
                for row in todo:
                    _cut_voice(source, row['identity']['start'], row['identity']['end'], row['wav'])
                offsets = _join_voice([row['wav'] for row in todo], ONE_VIDEO_GAP, wav)
                identity['offsets'] = offsets
                record = _send(pid, request, wav, receipt, identity, look, last_submit)
                last_submit = time.monotonic()
            except heygen_voice.RateLimited:
                errors.append(store.StudioError('HeyGen обмежив кількість запитів. Продовжіть створення пізніше.'))
                break
            except store.StudioError as error:
                errors.append(error)
                continue
        offsets = (record.get('identity') or {}).get('offsets')
        if not offsets or len(offsets) != len(todo):
            errors.append(store.StudioError('Квитанція спільного відео HeyGen не містить місць кадрів.'))
            continue
        for row, offset in zip(todo, offsets):
            row['offset'] = offset
        jobs.append({'frame': {'number': ', '.join(str(row['frame']['number']) for row in todo)}, 'record': record,
                     'receipt': receipt, 'output': video, 'rows': todo})
    deadline = time.monotonic() + 3600
    waiting = list(jobs)
    while waiting:
        if _cancelled(pid, request['id']):
            raise InterruptedError('Створення HeyGen відео на паузі.')
        for job in list(waiting):
            try:
                if 'record' in job and not _ready(job):
                    continue
                waiting.remove(job)
                for row in job['rows']:
                    if not row['output'].is_file():
                        _cut_video(job['output'], row['offset'], row['identity']['end'] - row['identity']['start'], row['output'])
                        store.atomic_json(row['receipt'], {'state': 'completed', 'identity': row['identity'],
                                                           'one_video': job['receipt'].name, 'offset': row['offset']})
                    _place(pid, request, {'frame': row['frame'], 'receipt': row['receipt'], 'output': row['output'],
                                          'record': store.read_json(row['receipt'], {}) or {}})
            except heygen_voice.RateLimited:
                break
            except (heygen_voice.NotSent, heygen_voice.Lost, heygen_voice.Gateway, OSError):
                continue
            except store.StudioError as error:
                if job in waiting:
                    waiting.remove(job)
                errors.append(error)
        if not waiting:
            break
        if time.monotonic() >= deadline:
            errors.append(store.StudioError('HeyGen ще створює відео. Натисніть «Продовжити» пізніше.'))
            break
        time.sleep(POLL_EVERY * 2)
    if errors:
        raise errors[0]


def _ready(job):
    """True once the frame's video is downloaded; one status request while HeyGen still renders it."""
    record, receipt, output, frame = job['record'], job['receipt'], job['output'], job['frame']
    if output.is_file():
        return True
    if not record['video_id'].replace('-', '').replace('_', '').isalnum():
        raise store.StudioError('Збережений ID відео HeyGen некоректний.')
    data = _data(heygen_voice._call('/v3/videos/' + record['video_id'], timeout=45))
    if data.get('status') == 'failed':
        record['state'] = 'failed'
        store.atomic_json(receipt, record)
        raise store.StudioError('HeyGen не зміг створити відео для кадру ' + str(frame['number']))
    if data.get('status') != 'completed':
        return False
    url = data.get('video_url')
    if not isinstance(url, str) or not url.startswith('https://'):
        raise store.StudioError('HeyGen не повернув готове відео.')
    temporary = output.with_suffix('.part')
    with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as target:
        shutil.copyfileobj(response, target)
    if not store.media_duration(temporary):
        temporary.unlink(missing_ok=True)
        raise store.StudioError('Не вдалося прочитати готове відео HeyGen.')
    os.replace(temporary, output)
    record['state'] = 'completed'
    store.atomic_json(receipt, record)
    return True


def _place(pid, request, job):
    if _cancelled(pid, request['id']):
        raise InterruptedError('Створення HeyGen відео на паузі.')
    record, receipt, output, frame = job['record'], job['receipt'], job['output'], job['frame']
    project = store.load_project(pid)
    if frame['number'] in store.made_frames(project, store.load_project_plan(pid)):
        return
    aid = record.get('asset_id')
    try:
        asset = store.resolve_asset(project, aid) if aid else None
    except store.StudioError:
        asset = None
    if not asset:
        asset = store.import_asset_file(project, output, 'heygen')
        record['asset_id'] = asset['id']
        store.atomic_json(receipt, record)
    move, percent = host_zoom(store.load_project_plan(pid), frame)
    montage_ops.run(pid, [{'op': 'place', 'frame': frame['number'], 'asset_id': asset['id'], 'trim_start': 0,
                           'motion': move, 'zoom_percent': percent}])


def zoom_percent(seconds):
    """How far a host frame zooms over its length (user, 25 November 2026: «чим коротший… тим менше відсотків», then «на шаг
    менше… 15 це 12, 12 це 9» but «той, що длінний… залиш»): 3% up to 15% at nine seconds by 1.5% a second, less by up
    to 3 points on short frames, the cut fading out towards nine seconds; never under 2%."""
    seconds = float(seconds)
    base = min(15.0, max(3.0, 3.0 + (seconds - 1.0) * 1.5))
    cut = 3.0 * (1 - min(1.0, max(0.0, (seconds - 1.0) / 8.0)))
    return round(max(2.0, base - cut), 2)


def host_zoom(plan, frame):
    """The host frame's move: zoom in and zoom out in turn along the film's host frames, by its length."""
    hosts = [f['number'] for f in (plan or {}).get('frames', []) if f.get('format') == 'host']
    index = hosts.index(frame['number']) if frame['number'] in hosts else 0
    return ('zoom_in' if index % 2 == 0 else 'zoom_out'), zoom_percent(float(frame['end']) - float(frame['start']))
