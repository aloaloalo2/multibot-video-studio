"""Small persistent unread completion marks, separate from the montage revision."""
import math
import threading
import time
import store

LOCK = threading.RLock()
INDEXED = set()


def path(pid):
    return store.project_dir(pid) / 'completion-notices.json'


def record(job, at=None):
    if job.get('status') != 'complete' or not job.get('project_id'):
        return
    kind = 'export' if job.get('output_path') else 'process'
    with LOCK:
        target = path(job['project_id'])
        data = store.read_json(target, {})
        previous = data.get(kind) or {}
        if previous.get('id') == job.get('id'):
            return
        stamp = float(at if at is not None else time.time())
        if stamp < previous.get('at', 0):
            return
        data[kind] = {'id': job['id'], 'at': stamp}
        store.atomic_json(target, data)


def index_exports(root):
    """Read old receipts once; overview polling never rereads the whole job history."""
    with LOCK:
        if str(root) in INDEXED:
            return
        for file in root.glob('*.json'):
            try:
                job = store.read_json(file, {})
                if job.get('output_path') and job.get('status') == 'complete':
                    record(job, file.stat().st_mtime)
            except (OSError, ValueError, TypeError, store.StudioError):
                continue
        INDEXED.add(str(root))


def notice(project, data=None):
    pid = project['id']
    if data is None:
        with LOCK:
            data = store.read_json(path(pid), {})
    seen = data.get('seen_at', 0)
    exported = data.get('export') or {}
    if exported.get('at', 0) > seen:
        return {'kind': 'export', 'label': 'Експортовано', 'at': exported['at']}
    stamps = [data.get('process', {}).get('at', 0)]
    request = project.get('production_request') or {}
    if request.get('status') == 'done':
        stamps.append(float(request.get('finished_at') or 0))
    for filename, states in [('director.json', {'done', 'ready'}), ('thumbnail-job.json', {'done'}), ('sound.json', {'done'})]:
        task = store.read_json(store.project_dir(pid) / filename, {}) or {}
        if task.get('status') in states:
            stamps.append(float(task.get('finished_at') or task.get('completed_at') or 0))
    latest = max(stamps)
    return {'kind': 'process', 'label': 'Роботу завершено', 'at': latest} if latest > seen else None


def seen(pid, through=None):
    if through is not None and (type(through) not in (int, float) or not math.isfinite(through) or through < 0):
        raise store.StudioError('Некоректна позначка завершення')
    with LOCK:
        target = path(pid)
        data = store.read_json(target, {})
        stamp = time.time() if through is None else min(float(through), time.time())
        data['seen_at'] = max(float(data.get('seen_at') or 0), stamp)
        store.atomic_json(target, data)
