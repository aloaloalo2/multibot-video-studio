"""Small persistent unread completion marks, separate from the montage revision."""
import math
import threading
import time
from pathlib import Path
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


_STAGE_FILES = {}


def _stage_file(file):
    """Progress reads only changed small receipts, never scripts or full job histories."""
    try:
        stat = file.stat()
    except FileNotFoundError:
        _STAGE_FILES.pop(str(file), None)
        return {}
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _STAGE_FILES.get(str(file))
    if cached and cached[0] == key:
        return cached[1]
    value = store.read_json(file, {}) or {}
    _STAGE_FILES[str(file)] = (key, value)
    return value


def ready_stage(project, receipts, summary):
    """Last saved workflow milestone; opening a card never clears actual readiness."""
    if (receipts.get('export') or {}).get('at'):
        return 'export'
    request = project.get('production_request') or {}
    if request.get('status') == 'done' and request.get('frames', 0) > 0 and (request.get('quality') or {}).get('passed') is not False:
        return 'frames'
    plan = store.listed_plan(project) if project.get('plan_source') else None
    if summary.get('plan_stage') == 'audio_synced' and (plan or {}).get('frame_source') == 'razgon-direction' and (plan or {}).get('frames'):
        return 'plan'
    if summary.get('voice_duration', 0) > 0:
        return 'voice'
    job = _stage_file(store.project_dir(project['id']) / 'narration' / 'job.json')
    if job.get('status') == 'done' and project.get('restarted_at', 0) <= job.get('started_at', 0):
        asset = next((item for item in project.get('assets', []) if item.get('id') == job.get('asset_id')), {})
        if asset.get('path') and Path(asset['path']).is_file():
            return 'voice'
    if (project.get('voice_script') or {}).get('text', '').strip() or (plan or {}).get('script', '').strip():
        return 'script'
    draft = _stage_file(store.project_dir(project['id']) / 'episode-draft.json')
    if draft.get('project_id') == project['id'] and not draft.get('cancelled') and draft.get('status') != 'cancelled' \
            and any(isinstance(row, dict) and isinstance(row.get('text'), str) and row['text'].strip() for row in draft.get('openings') or []):
        return 'openings'
    return 'draft'
