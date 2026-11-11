"""Durable working scripts and bounded versions, separate from accepted narration."""
import hashlib
import re
import time
import uuid

import store

MAX_TEXT = 200000
MAX_HISTORY = 20


def root(pid):
    return store.project_dir(pid) / 'script-draft'


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def context(pid):
    project = store.load_project(pid)
    saved = project.get('voice_script') or {}
    job = store.read_json(store.project_dir(pid) / 'narration' / 'job.json', {}) or {}
    epoch = project.get('restarted_at') or 0
    if isinstance(job.get('script'), str) and job.get('started_at', 0) > saved.get('saved_at', 0) and job.get('started_at', 0) >= epoch:
        text = job['script']
    elif isinstance(saved.get('text'), str):
        text = saved['text']
    else:
        text = (store.load_project_narration(pid) or {}).get('script') or ''
    return {'text': text, 'sha256': digest(text), 'epoch': epoch}


def record(pid):
    value = store.read_json(root(pid) / 'current.json', {}) or {}
    if not isinstance(value, dict) or value and (not isinstance(value.get('text'), str) or type(value.get('version')) is not int):
        raise store.StudioError('Не вдалося прочитати чернетку. Попередні версії збережено.', 409)
    return value


def matches(value, active):
    return value.get('base_sha256') == active['sha256'] and value.get('epoch', 0) == active['epoch']


def view(pid, active, value):
    applicable = bool(value and matches(value, active))
    text = value['text'] if applicable else active['text']
    return {'text': text, 'sha256': digest(text), 'version': value.get('version', 0), 'base_sha256': active['sha256'],
            'epoch': active['epoch'], 'pending': text != active['text'],
            'stale': bool(value and not applicable and value['text'] != active['text']),
            'saved_at': value.get('saved_at'), 'writer_id': value.get('writer_id'),
            'client_sequence': value.get('client_sequence', 0), 'history_count': len(history_paths(pid))}


def current(pid):
    with store.LOCK:
        return view(pid, context(pid), record(pid))


def history_paths(pid):
    return sorted((root(pid) / 'history').glob('*.json'), key=lambda path: path.name if path.name != 'baseline.json' else '', reverse=True)[:MAX_HISTORY + 1]


def checkpoint(pid, value, *, baseline=False):
    folder = root(pid) / 'history'
    paths = history_paths(pid)
    if baseline and (folder / 'baseline.json').is_file():
        return
    if paths and not baseline:
        latest = store.read_json(paths[0], {})
        if latest.get('text') == value['text'] and latest.get('epoch', 0) == value.get('epoch', 0):
            return
    identity = 'baseline' if baseline else uuid.uuid4().hex
    item = {**value, 'id': identity, 'saved_at': value.get('saved_at') or time.time()}
    name = 'baseline.json' if baseline else f'{time.time_ns():020d}-{identity}.json'
    store.atomic_json(folder / name, item)
    ordinary = sorted((p for p in folder.glob('*.json') if p.name != 'baseline.json'), reverse=True)
    for path in ordinary[MAX_HISTORY:]:
        path.unlink(missing_ok=True)


def save(pid, body):
    text = body.get('text')
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise store.StudioError('Сценарій має містити до 200 000 символів')
    if type(body.get('expected_version')) is not int or body['expected_version'] < 0:
        raise store.StudioError('Не вказано версію чернетки')
    writer = body.get('writer_id')
    sequence = body.get('client_sequence', 0)
    if writer is not None and (not isinstance(writer, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{12,80}', writer)):
        raise store.StudioError('Невірний ідентифікатор чернетки')
    if type(sequence) is not int or sequence < 0:
        raise store.StudioError('Невірна послідовність правок')
    with store.LOCK:
        active, previous = context(pid), record(pid)
        if body.get('epoch') != active['epoch'] or body.get('base_sha256') != active['sha256']:
            raise store.StudioError('Основний сценарій уже змінено. Правки залишились у браузері.', 409)
        # A lost acknowledgement can safely repeat the exact same local write.
        if previous and matches(previous, active) and previous['text'] == text:
            return view(pid, active, previous)
        if writer is not None and writer == previous.get('writer_id') and matches(previous, active) and sequence <= previous.get('client_sequence', 0):
            raise store.StudioError('Новіша правка вже збережена. Ваш текст залишився в браузері.', 409)
        own_later = writer is not None and writer == previous.get('writer_id') and sequence > previous.get('client_sequence', 0) and matches(previous, active)
        if body['expected_version'] != previous.get('version', 0) and not own_later:
            raise store.StudioError('Чернетку змінено в іншій вкладці. Ваші правки збережено в браузері.', 409)
        checkpoint(pid, {'text': active['text'], 'epoch': active['epoch'], 'source': 'accepted'}, baseline=True)
        if previous:
            checkpoint(pid, previous)
        value = {'text': text, 'sha256': digest(text), 'version': previous.get('version', 0) + 1,
                 'base_sha256': active['sha256'], 'epoch': active['epoch'], 'saved_at': time.time(),
                 'writer_id': writer, 'client_sequence': sequence}
        store.atomic_json(root(pid) / 'current.json', value)
        return view(pid, active, value)


def history(pid):
    active, pending = context(pid), record(pid)
    result = []
    if pending and not matches(pending, active) and pending['text'] != active['text']:
        result.append({'id': 'stale', 'saved_at': pending.get('saved_at'), 'characters': len(pending['text']), 'stale': True})
    for path in history_paths(pid):
        try:value = store.read_json(path, {}) or {}
        except (OSError, ValueError):continue
        if isinstance(value, dict) and isinstance(value.get('text'), str) and isinstance(value.get('id'), str):
            result.append({'id': value['id'], 'saved_at': value.get('saved_at'),
                           'characters': len(value['text']), 'baseline': value['id'] == 'baseline'})
    return {'versions': result}


def version(pid, identity):
    store.load_project(pid)
    if not isinstance(identity, str) or not re.fullmatch(r'baseline|stale|[0-9a-f]{32}', identity):
        raise store.StudioError('Версію сценарію не знайдено', 404)
    if identity == 'stale':
        value = record(pid)
        if value and not matches(value, context(pid)):
            return value
        raise store.StudioError('Версію сценарію не знайдено', 404)
    path = root(pid) / 'history' / 'baseline.json' if identity == 'baseline' else next(
        (p for p in history_paths(pid) if p.name.endswith('-' + identity + '.json')), None)
    value = store.read_json(path) if path else None
    if not isinstance(value, dict) or not isinstance(value.get('text'), str):
        raise store.StudioError('Версію сценарію не знайдено', 404)
    return value


def restore(pid, body):
    with store.LOCK:
        value = version(pid, body.get('version_id'))
        return save(pid, {**body, 'text': value['text']})
