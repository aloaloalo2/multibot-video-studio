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


def handoff(pid, stage, identity, action, retry_failed=False):
    path = store.project_dir(pid) / 'automation.json'
    with LOCK:
        data = store.read_json(path, {}) or {}
        done = data.get(stage) or {}
        if done.get('identity') == identity and not (retry_failed and done.get('status') == 'failed'):
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
    if episode_pause.note(pid, 'voice', draft={'completed': bool(draft.get('completed')), 'cancelled': bool(draft.get('cancelled'))}):
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
        traceback.print_exc()   # (it waits by itself while the plan is not yet timed by this voice)
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


def translate_all(pid, job=None):
    """The voiced script goes on to every language of the episode (user, 16 November 2026: «Якщо ми зробили озвучку
    сценарія, то далі ми робимо переклад авто… І після перекладу автоматичного, якщо все окей, запускаємо і озвучку»).
    The languages are the episode's own, or the channel's defaults when the episode has none yet.

    A translation is cut from the plan's sentences and times, so it starts only once the plan follows this voice
    (timing «audio_synced» for the current script): called when the narration ends and again when the recognition has
    timed the plan. A plan estimated from the script, or an older voice's plan, waits."""
    project = store.load_project(pid)
    if settings(project).get('auto_translation') is not True:
        return
    import episode_pause
    if episode_pause.paused(pid):
        episode_pause.note(pid, 'translations')
        return
    script = (project.get('voice_script') or {}).get('text') or ''
    if job and job.get('script') and job['script'] != script:
        return
    plan = store.load_project_plan(pid) or {}
    import number_text
    spoken = plan.get('spoken_script') or plan.get('script') or ''
    if (plan.get('timing') or {}).get('status') != 'audio_synced' or number_text.to_digits(spoken.strip()) != number_text.to_digits(script.strip()):
        return
    import language_defaults
    import languages
    language_defaults.apply(project)
    codes = sorted((languages.load_state(pid).get('languages') or {}))
    identity = hashlib.sha256((script + '|' + str((plan.get('timing') or {}).get('audio', {}).get('sha256') or '')).encode()).hexdigest()
    for code in codes:
        handoff(pid, 'translation-' + code, identity, lambda code=code: languages.start(pid, 'translate', code), retry_failed=True)


def after_translation(pid, code, job):
    """A finished translation goes on to its voice when the channel asks for it and the text passed its checks
    (languages.start('voice') refuses a translation whose language check failed)."""
    if job.get('kind') != 'translate' or job.get('status') != 'done':
        return
    project = store.load_project(pid)
    if settings(project).get('auto_translation_voice') is not True:
        return
    import episode_pause
    if episode_pause.note(pid, 'translation_voice:' + code):
        return
    import languages
    try:
        text = languages.read_text(pid, code)
    except (RuntimeError, OSError):
        return
    handoff(pid, 'translation-voice-' + code, hashlib.sha256(text.encode()).hexdigest(),
            lambda: languages.start(pid, 'voice', code))
