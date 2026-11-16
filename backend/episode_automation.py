"""Opt-in channel handoffs. Repeated completion events never repeat paid work."""
import hashlib
import threading
import time

import store

LOCK = threading.RLock()
JOB_CALLBACKS = None


def settings(project):
    folder = store.get_channel_folder(project['channel_id'])
    return store.read_channel_settings(folder, {})


def handoff(pid, stage, identity, action):
    path = store.project_dir(pid) / 'automation.json'
    with LOCK:
        data = store.read_json(path, {}) or {}
        if (data.get(stage) or {}).get('identity') == identity:
            return
        data[stage] = {'identity': identity, 'status': 'starting', 'started_at': time.time()}
        store.atomic_json(path, data)
    try:
        action()
        result = {'status': 'started'}
    except Exception as error:
        result = {'status': 'failed', 'error': str(error)[:400]}
    with LOCK:
        data = store.read_json(path, {}) or {}
        if (data.get(stage) or {}).get('identity') == identity:
            data[stage].update(result)
            store.atomic_json(path, data)
    if result['status'] == 'failed' and stage == 'voice':
        # Existing narration UI offers its ordinary manual retry; no paid auto-retry.
        import project_narration
        with project_narration.LOCK:
            if pid not in project_narration.ACTIVE:
                store.atomic_json(store.project_dir(pid) / 'narration' / 'job.json', result)


def after_script(pid, draft):
    import episode_pause
    if episode_pause.paused(pid):
        return
    project = store.load_project(pid)
    if settings(project).get('auto_narration') is not True or not draft.get('completed') or draft.get('cancelled'):
        return
    text = (project.get('voice_script') or {}).get('text', '')
    if not text.strip():
        return
    def launch():
        import project_narration
        if pid in project_narration.ACTIVE:
            return
        current = project_narration.snapshot(pid).get('job') or {}
        if current.get('status') == 'done' and current.get('script') == text:
            return
        project_narration.start(project, text)
    handoff(pid, 'voice', hashlib.sha256(text.encode()).hexdigest(), launch)


def after_voice(pid, job):
    if job.get('status') != 'done' or not job.get('asset_id'):
        return
    import episode_pause
    if episode_pause.note(pid, 'montage', job=job):
        return   # the episode is paused: «Продовжити» hands the voice on
    try:
        translate_all(pid, job)
    except Exception:   # the translations never hold up the film
        import traceback
        traceback.print_exc()
    project = store.load_project(pid)
    if (store.project_dir(pid) / 'narration' / 'cancel').exists() or project.get('restarted_at', 0) > job.get('started_at', 0):
        return
    if job.get('script') and job['script'] != (project.get('voice_script') or {}).get('text'):
        return
    if settings(project).get('auto_montage') is not True:
        return
    def launch():
        if not JOB_CALLBACKS:
            raise store.StudioError('Автомонтаж поки недоступний. Натисніть «Створити відео».')
        import analysis_jobs
        analyze = analysis_jobs.start if store.project_plan_mode(project) == 'direct' else analysis_jobs.create_video
        analyze(project, job['asset_id'], *JOB_CALLBACKS, script=(project.get('voice_script') or {}).get('text'))
    handoff(pid, 'montage', job['asset_id'], launch)


def translate_all(pid, job):
    """The voiced script goes on to every language of the episode (user, 16 November 2026: «Якщо ми зробили озвучку
    сценарія, то далі ми робимо переклад авто… І після перекладу автоматичного, якщо все окей, запускаємо і озвучку»).
    The languages are the episode's own, or the channel's defaults when the episode has none yet."""
    project = store.load_project(pid)
    if settings(project).get('auto_translation') is not True:
        return
    if job.get('script') and job['script'] != (project.get('voice_script') or {}).get('text'):
        return
    import language_defaults
    import languages
    language_defaults.apply(project)
    codes = sorted((languages.load_state(pid).get('languages') or {}))
    identity = hashlib.sha256(str(job.get('script') or job.get('asset_id')).encode()).hexdigest()
    for code in codes:
        handoff(pid, 'translation-' + code, identity, lambda code=code: languages.start(pid, 'translate', code))


def after_translation(pid, code, job):
    """A finished translation goes on to its voice when the channel asks for it and the text passed its checks
    (languages.start('voice') refuses a translation whose language check failed)."""
    if job.get('kind') != 'translate' or job.get('status') != 'done':
        return
    project = store.load_project(pid)
    if settings(project).get('auto_translation_voice') is not True:
        return
    import episode_pause
    if episode_pause.paused(pid):
        return
    import languages
    try:
        text = languages.read_text(pid, code)
    except (RuntimeError, OSError):
        return
    handoff(pid, 'translation-voice-' + code, hashlib.sha256(text.encode()).hexdigest(),
            lambda: languages.start(pid, 'voice', code))
