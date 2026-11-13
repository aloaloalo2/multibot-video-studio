"""Bounded, local wall-time measurements. Observation never controls a job."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
import math
import re
import threading
import time
import uuid

import store
from storage_io import atomic_json, read_json

STAGES = {
    'preparation': 'Підготовка', 'queue': 'Черга', 'pause': 'Пауза', 'service': 'Очікування сервісу',
    'recognition': 'Розпізнавання', 'verification': 'Перевірки',
    'saving': 'Збереження', 'rendering': 'Рендер',
}
WORKFLOWS = {
    'openings': 'Зачини', 'script': 'Сценарій', 'metadata': 'Метадані',
    'narration': 'Озвучка', 'analysis': 'Аналіз озвучки', 'planning': 'План кадрів',
    'production': 'Створення кадрів', 'thumbnail': 'Прев’ю', 'export': 'Експорт',
    'translation': 'Переклад', 'language_voice': 'Озвучка перекладу',
    'language_sample': 'Зразок перекладу', 'language_save': 'Збереження перекладу',
    'language_refit': 'Вирівнювання перекладу', 'language_thumbnail': 'Прев’ю перекладу',
}
LANGUAGE_WORKFLOWS = {
    'translate': 'translation', 'voice': 'language_voice', 'sample': 'language_sample',
    'save-audio': 'language_save', 'refit': 'language_refit', 'thumbnail': 'language_thumbnail',
}
MAX_RUNS = 64
FLUSH_SECONDS = 2.0
CURRENT = ContextVar('studio_job_timing', default=None)
LOCK = threading.RLock()
ACTIVE = {}


def terminal(value):
    if value in {'done', 'complete', 'success'}:
        return 'complete'
    if value in {'cancelled', 'cancelling'}:
        return 'cancelled'
    if value in {'paused', 'stopped', 'limited'}:
        return 'stopped'
    return 'failed' if value in {'failed', 'error', 'interrupted'} else 'unknown'


class Measurement:
    def __init__(self, pid, workflow, job_id=None, language=None):
        self.project_id, self.workflow = pid, workflow
        self.id = uuid.uuid4().hex
        self.started_at = time.time()
        self.started = self.changed = time.monotonic()
        self.finished_at = None
        self.finished = None
        self.stage = 'preparation'
        self.stages = {'preparation': {'ms': 0.0, 'calls': 1}}
        self.status = 'running'
        self.last_flush = float('-inf')
        self.path = None
        self.job_id = job_id if isinstance(job_id, str) and re.fullmatch(r'[a-zA-Z0-9_|.:-]{1,100}', job_id) else None
        self.language = language if isinstance(language, str) and re.fullmatch('[a-z]{2}', language) else None
        try:
            folder = store.project_dir(pid) / 'performance'
            # A late observer cannot recreate a deleted project.
            folder.mkdir(exist_ok=True)
            self.path = folder / f'{time.time_ns():020d}-{self.id}.json'
            for old in sorted(folder.glob('*.json'), reverse=True)[MAX_RUNS - 1:]:
                old.unlink(missing_ok=True)
        except (OSError, store.StudioError):
            pass
        with LOCK:
            ACTIVE[self.id] = self
        self.flush(force=True)

    def snapshot(self):
        with LOCK:
            now = self.finished if self.finished is not None else time.monotonic()
            stages = {key: dict(value) for key, value in self.stages.items()}
            if self.finished is None:
                stages[self.stage]['ms'] += max(0, now - self.changed) * 1000
            return {
                'version': 1, 'id': self.id, 'project_id': self.project_id,
                'workflow': self.workflow, 'job_id': self.job_id, 'status': self.status,
                'language': self.language,
                'started_at': self.started_at, 'finished_at': self.finished_at,
                'elapsed_ms': round(max(0, now - self.started) * 1000, 2),
                'active_stage': self.stage if self.finished is None else None,
                'stages': {key: {'ms': round(value['ms'], 2), 'calls': value['calls']}
                           for key, value in stages.items()},
            }

    def switch(self, stage, *, count=True):
        with LOCK:
            previous = self.stage
            now = time.monotonic()
            self.stages[previous]['ms'] += max(0, now - self.changed) * 1000
            self.stage, self.changed = stage, now
            row = self.stages.setdefault(stage, {'ms': 0.0, 'calls': 0})
            row['calls'] += int(count)
        self.flush()
        return previous

    def flush(self, *, force=False):
        if self.path is None or not force and time.monotonic() - self.last_flush < FLUSH_SECONDS:
            return
        self.last_flush = time.monotonic()
        try:
            atomic_json(self.path, self.snapshot(), create_parents=False)
        except OSError:
            pass

    def finish(self, status):
        with LOCK:
            if self.finished is not None:
                return
            self.finished = time.monotonic()
            self.finished_at = time.time()
            self.stages[self.stage]['ms'] += max(0, self.finished - self.changed) * 1000
            self.status = terminal(status)
        try:
            self.flush(force=True)
        finally:
            with LOCK:
                ACTIVE.pop(self.id, None)


@contextmanager
def span(stage):
    trace = CURRENT.get()
    if trace is None:
        yield
        return
    if stage not in STAGES:
        raise ValueError('Unknown timing stage')
    previous = trace.switch(stage)
    try:
        yield
    finally:
        trace.switch(previous, count=False)


def advance(stage):
    trace = CURRENT.get()
    if trace is not None and stage in STAGES and trace.stage != stage:
        trace.switch(stage)


def measure(stage):
    """Measure synchronous work only when its owning worker is being observed."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with span(stage):
                return function(*args, **kwargs)
        return wrapped
    return decorate


@contextmanager
def queued_lock(lock):
    with span('queue'):
        lock.acquire()
    try:
        yield
    finally:
        lock.release()


def track(workflow, *, project, job=None):
    """Keep the existing worker signature, result, exceptions and lifecycle intact."""
    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        def wrapped(*args, **kwargs):
            values = signature.bind(*args, **kwargs).arguments
            owner = values.get(project)
            pid = owner.get('project_id', owner.get('id')) if isinstance(owner, dict) else owner
            kind = workflow(values) if callable(workflow) else workflow
            if not pid or kind not in WORKFLOWS:
                return function(*args, **kwargs)

            def state():
                try:
                    value = job(values) if callable(job) else values.get(job, {})
                    return value if isinstance(value, dict) else {}
                except (OSError, ValueError, store.StudioError):
                    return {}

            trace = Measurement(pid, kind, state().get('id'), values.get('code'))
            token = CURRENT.set(trace)
            status = 'failed'
            try:
                result = function(*args, **kwargs)
                status = state().get('status', 'unknown') if job is not None else 'complete'
                return result
            except BaseException as error:
                if type(error).__name__ in {'Stop', 'Cancelled', 'KeyboardInterrupt'}:
                    status = 'cancelled'
                raise
            finally:
                try:
                    trace.finish(status)
                finally:
                    CURRENT.reset(token)
        return wrapped
    return decorate


def overview(pid):
    """A bounded local read, with live monotonic time for this process's workers."""
    store.load_project(pid)
    folder = store.project_dir(pid) / 'performance'
    with LOCK:
        active = {trace.id: trace.snapshot() for trace in ACTIVE.values() if trace.project_id == pid}
    runs = dict(active)
    try:
        paths = sorted(folder.glob('*.json'), reverse=True)[:MAX_RUNS]
    except OSError:
        paths = []
    for path in paths:
        try:
            if path.stat().st_size > 16384:
                continue
            row = read_json(path)
            if not valid_record(row, pid):
                continue
            row = {key: row.get(key) for key in ('version', 'id', 'project_id', 'workflow', 'job_id',
                   'language', 'status', 'started_at', 'finished_at', 'elapsed_ms', 'active_stage', 'stages')}
            if row.get('id') in runs:
                continue
            if row.get('status') == 'running':
                row = {**row, 'status': 'interrupted', 'active_stage': None}
            runs[row['id']] = row
        except (OSError, ValueError, KeyError):
            continue
    ordered = sorted(runs.values(), key=lambda row: row.get('started_at', 0), reverse=True)[:MAX_RUNS]
    totals = {stage: round(sum((row.get('stages', {}).get(stage) or {}).get('ms', 0) for row in ordered), 2) for stage in STAGES}
    result = {'runs': ordered, 'stages': STAGES, 'workflows': WORKFLOWS,
              'stage_totals_ms': totals, 'retention': MAX_RUNS}
    try:
        import performance_summary
        result.update(performance_summary.project(ordered, store.project_dir(pid)))
    except Exception:
        pass  # A reporting failure cannot interrupt the job or hide the original measurements.
    return result


def valid_record(row, pid):
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    if not isinstance(row, dict) or row.get('version') != 1 or row.get('project_id') != pid or row.get('workflow') not in WORKFLOWS:
        return False
    if not isinstance(row.get('id'), str) or not re.fullmatch('[0-9a-f]{32}', row['id']):
        return False
    if not finite(row.get('started_at')) or not finite(row.get('elapsed_ms')):
        return False
    if row.get('language') is not None and (not isinstance(row['language'], str) or not re.fullmatch('[a-z]{2}', row['language'])):
        return False
    if row.get('status') not in {'running', 'complete', 'failed', 'cancelled', 'stopped', 'interrupted', 'unknown'}:
        return False
    stages = row.get('stages')
    return isinstance(stages, dict) and not set(stages) - STAGES.keys() and all(
        isinstance(value, dict) and finite(value.get('ms')) and type(value.get('calls')) is int and value['calls'] >= 0
        for value in stages.values())
