"""Local audition and explicit acceptance of a voice reference. Never calls a speech API."""
import hashlib
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import store
import languages
import voice_cleanup

CLEANUP_VERSION = voice_cleanup.VERSION


def folder(root, token):
    if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{32}', token):
        raise store.StudioError('Невірний запис для прослуховування')
    path = root / 'drafts' / token
    if not (path / 'metadata.json').is_file(): raise store.StudioError('Запис не знайдено', 404)
    return path


def upload(root, stream, size, filename):
    if not 0 < size <= 200 * 1024 * 1024: raise store.StudioError('Запис порожній або перевищує 200 МБ', 413)
    token = uuid.uuid4().hex
    path = root / 'drafts' / token;path.mkdir(parents=True)
    raw = path / 'upload'
    try:
        with raw.open('wb') as out:
            left = size
            while left:
                chunk = stream.read(min(left, 1024 * 1024))
                if not chunk: raise store.StudioError('Файл завантажився не повністю')
                out.write(chunk);left -= len(chunk)
        # Preserve level: no loudness normalization or automatic makeup gain.
        languages.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(raw), '-vn', '-ac', '1',
                       '-ar', '48000', '-b:a', '160k', '-map_metadata', '-1', str(path/'original.mp3')], 'підготувати запис для прослуховування')
        duration = store.media_duration(path/'original.mp3') or 0
        if duration < 10: raise store.StudioError('Потрібно хоча б 10 секунд голосу')
        meta = {'id': token, 'filename': Path(filename).name[:200], 'duration': duration, 'clean_ready': False}
        store.atomic_json(path/'metadata.json', meta)
        return meta
    finally:
        raw.unlink(missing_ok=True)


def clean(root, token):
    path = folder(root, token);meta = store.read_json(path/'metadata.json', {})
    if (path/'clean.mp3').is_file() and meta.get('clean_ready') and meta.get('cleanup_version') == CLEANUP_VERSION: return meta
    with tempfile.TemporaryDirectory(dir=path) as tmp:
        output = Path(tmp)/'clean.mp3'
        voice_cleanup.enhance(path/'original.mp3', output)
        duration = store.media_duration(output) or 0
        if abs(duration-meta['duration']) > .2 or duration < 10:
            raise store.StudioError('Очищення не пройшло перевірку. Оригінал збережено.')
        output.replace(path/'clean.mp3')
    meta['clean_ready'] = True;meta['cleanup_version'] = CLEANUP_VERSION;store.atomic_json(path/'metadata.json', meta)
    return meta


def accept(root, token, cleaned):
    if type(cleaned) is not bool: raise store.StudioError('Виберіть версію запису')
    path = folder(root, token);meta = store.read_json(path/'metadata.json', {})
    selected = path/('clean.mp3' if cleaned else 'original.mp3')
    if cleaned and not meta.get('clean_ready'): raise store.StudioError('Спочатку дочекайтеся очищення')
    if not selected.is_file(): raise store.StudioError('Вибраний запис не готовий')
    if meta.get('accepted'): raise store.StudioError('Цей запис уже прикріплено', 409)
    audio = selected.read_bytes();digest = hashlib.sha256(audio).hexdigest()
    # Stage everything before switching the active reference; retain the previous recording.
    old = root/'reference.mp3'
    if old.is_file():
        previous=root/'previous';previous.mkdir(exist_ok=True)
        (previous/(uuid.uuid4().hex+'.mp3')).write_bytes(old.read_bytes())
    pending=root/'accepted.pending.mp3';pending.write_bytes(audio);pending.replace(old)
    store.atomic_json(root/'reference.json', {'filename': meta['filename'], 'duration': meta['duration'],
                      'sha256': digest, 'approved': True, 'cleanup_applied': cleaned})
    meta['accepted'] = True;store.atomic_json(path/'metadata.json', meta)


def audio_file(root, token, cleaned):
    path = folder(root, token)/('clean.mp3' if cleaned else 'original.mp3')
    if not path.is_file(): raise store.StudioError('Аудіо ще не готове', 404)
    return path


def discard(root, token):
    path = folder(root, token)
    if not store.read_json(path/'metadata.json', {}).get('accepted'):
        shutil.rmtree(path)


def transport(source, root):
    """A compact API upload of the approved file, retaining its level and speaking rate."""
    if source.stat().st_size <= 900_000: return [source]
    target = root/'approved-upload.mp3'
    languages.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(source), '-t', '70', '-vn',
                   '-ac', '1', '-ar', '44100', '-b:a', '96k', '-map_metadata', '-1', str(target)], 'підготувати файл для API')
    if target.stat().st_size > 900_000: raise store.StudioError('Приклад завеликий для API')
    return [target]
