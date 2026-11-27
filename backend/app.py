#!/usr/bin/env python3
"""Local HTTP API and static shell for VideoKey Studio."""

from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import math
import mimetypes
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import joins
import store
import job_timing
import script_drafts
import status_views
import thumbnail_compare
import script_editing
import technical_files
import covers
import channel_transfer
import channel_api
import trending_videos
import title_translation
import channel_translation_voices
import style_lab
import director
import spend_report
import project_costs
import production_context
import director_plan
import episode_restart
import export_delivery
import process_cleanup
from work_guard import MUTEX as UPDATE_MUTEX
import frame_progress
import space
import production
import thumbnail_gen
import image_delivery
import languages
import language_mix
import agent_runtime
import agent_storage
import credentials
import analysis_jobs
import razgon_live
import razgon_export
import razgon_sound
import published
import episode_pause
import topics
import audio_level
import waveforms
import export_names
import completion_notices
import project_narration
import narration_revision
import channel_voice_lab
import agent_view
import channel_activity
import montage_ops
from timeline_manifest import build as timeline_manifest, valid_local_source
import thumbnails
import updater


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(APP_ROOT / "engine"))
FRONTEND_ROOT = APP_ROOT / "frontend"
ENGINE_SCRIPT = APP_ROOT / "engine" / "render.py"
JOBS_ROOT = store.DATA_ROOT / "jobs"
JOBS_LOCK = threading.RLock()
ACTIVE_EXPORTS = {}
EXPORT_CONDITION = threading.Condition(JOBS_LOCK)
EXPORT_RUNNING = None
UPDATE_MANAGER = updater.Updater(APP_ROOT)
UPDATE_BOOT = uuid.uuid4().hex
UPDATE_RESTARTING = False
LOCAL_RESTART_PROCESS = None
LOCAL_RESTART_ERROR = None
# Changes run side by side; the mutex only guards this count and the restart flag, so a slow still, picker or upload
# no longer holds every other edit (the export's cancel button among them). An update waits until the count is its own.
IN_FLIGHT = 0
IN_FLIGHT_DONE = threading.Condition(UPDATE_MUTEX)


def restart_after_update():
    global UPDATE_RESTARTING
    try:
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except OSError:
        traceback.print_exc()
        UPDATE_MANAGER.state = {'status': 'restart_failed'}
        UPDATE_RESTARTING = False


BUSY_WORDS = {"режисура": "режисер", "створення кадрів": "агент кадрів", "музика й ефекти": "збирання музики й ефектів",
              "прев'ю": "агент прев’ю", "агент студії": "агент студії",
              "розпізнавання озвучки": "розпізнавання озвучки", "експорт": "експорт",
              "перенесення службових файлів після запуску": "перенесення файлів після запуску"}


def busy_words(busy: list[str]) -> str:
    """«Зараз працює режисер» from the busy list's «режисура: What If / … (id)» lines."""
    names = list(dict.fromkeys(BUSY_WORDS.get(line.split(":")[0].split(" ")[0] if line.startswith("експорт") else line.split(":")[0], "агент")
                               for line in busy))
    return "Зараз працює " + " і ".join(names[:2])


def check_local_restart():
    """Check restart blockers while holding UPDATE_MUTEX."""
    if UPDATE_RESTARTING:raise store.StudioError('Студія вже готується до перезапуску.',409)
    if IN_FLIGHT>1:raise store.StudioError('Студія зараз зберігає зміни. Дочекайтеся завершення.',409)
    if channel_voice_lab.ACTIVE:raise store.StudioError('Генерується зразок голосу. Дочекайтеся завершення.',409)
    with JOBS_LOCK:exports=[dict(x['job']) for x in ACTIVE_EXPORTS.values()]
    busy=studio_work_status(exports)['busy']
    if busy:raise store.StudioError(busy_words(busy)+'. Перезапуск доступний після завершення.',409)


def prepare_local_restart():
    """Close the mutation gate atomically with the final busy check."""
    global UPDATE_RESTARTING
    with UPDATE_MUTEX:
        check_local_restart()
        UPDATE_RESTARTING=True
        def expire():
            global UPDATE_RESTARTING
            with UPDATE_MUTEX:UPDATE_RESTARTING=False
        timer=threading.Timer(30,expire);timer.daemon=True;timer.start()
        return {'prepared':True,'pid':os.getpid()}


def local_restart_status():
    global LOCAL_RESTART_PROCESS, LOCAL_RESTART_ERROR
    with UPDATE_MUTEX:
        process = LOCAL_RESTART_PROCESS
        if process is not None and process.poll() is not None:
            _, detail = process.communicate()
            LOCAL_RESTART_PROCESS = None
            if process.returncode:
                LOCAL_RESTART_ERROR = detail.strip() or 'Перезапуск студії не вдався.'
        return {'boot': UPDATE_BOOT, 'restarting': LOCAL_RESTART_PROCESS is not None, 'error': LOCAL_RESTART_ERROR}


def begin_local_restart():
    global LOCAL_RESTART_PROCESS, LOCAL_RESTART_ERROR
    with UPDATE_MUTEX:
        if LOCAL_RESTART_PROCESS is not None and LOCAL_RESTART_PROCESS.poll() is None:
            return {'boot': UPDATE_BOOT}
        check_local_restart()
        try:
            LOCAL_RESTART_PROCESS = subprocess.Popen(
                [sys.executable, str(APP_ROOT / 'tools' / 'studio_restart.py')],
                cwd=APP_ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True, start_new_session=True,
            )
        except OSError:
            raise store.StudioError('Не вдалося запустити перезапуск студії.',500) from None
        LOCAL_RESTART_ERROR = None
        return {'boot': UPDATE_BOOT}


def begin_update():
    global UPDATE_RESTARTING
    with UPDATE_MUTEX:
        if UPDATE_RESTARTING:
            raise store.StudioError('Студія вже оновлюється.', 409)
        if channel_voice_lab.ACTIVE:raise store.StudioError('Генерується зразок голосу. Дочекайтеся завершення.',409)
        if not IN_FLIGHT_DONE.wait_for(lambda: IN_FLIGHT <= 1, timeout=30):
            raise store.StudioError('Зараз студія зберігає зміни', 409)
        with JOBS_LOCK:
            if ACTIVE_EXPORTS:
                raise store.StudioError('Зараз іде експорт', 409)
            if analysis_jobs.ACTIVE_JOBS:
                raise store.StudioError('Зараз розпізнається озвучка', 409)
        # the restart would also cut the director, the frame agent, a thumbnail or the studio's agent mid-run, the same
        # work studio_restart.py waits for
        busy = studio_work_status([])["busy"]
        if busy:
            # a short line by the update button, without episode names or ids (user, 1 November 2026)
            raise store.StudioError(busy_words(busy), 409)
        try:
            UPDATE_MANAGER.apply()
        except updater.UpdateError as error:
            raise store.StudioError(str(error), 409) from error
        UPDATE_RESTARTING = True
        timer = threading.Timer(1.0, restart_after_update)
        timer.daemon = True
        timer.start()
        return True


# An update asked for while the director, an agent or an export works waits here, on the server, and starts by itself
# once the work ends: the page may be reloaded or closed meanwhile (user, 1 November 2026).
UPDATE_QUEUED = None   # the reason it waits («Зараз працює режисер»), or None


def queue_update(reason: str) -> None:
    global UPDATE_QUEUED
    with UPDATE_MUTEX:
        start = UPDATE_QUEUED is None
        UPDATE_QUEUED = reason
    if start:
        threading.Thread(target=_queued_update, daemon=True).start()


def _queued_update() -> None:
    global UPDATE_QUEUED
    while UPDATE_QUEUED is not None:
        time.sleep(15)
        try:
            begin_update()
            UPDATE_QUEUED = None
        except store.StudioError as error:
            if str(error).startswith('Зараз '):
                UPDATE_QUEUED = str(error)
            else:
                UPDATE_QUEUED = None   # a stopped update shows its own reason on the button


# The studio updates itself (user, 26 November 2026: «автооновлення, щоб не нажимати ту кнопку… не обов'язково навіть її
# показувати»): a new version on GitHub is applied once nothing runs (the same wait as the button's: exports, recognition,
# the director, the agents, a voice sample) and the author has changed nothing for a while, then the studio restarts.
# A version that failed to apply is not tried again by itself; the button still retries it.
LAST_CHANGE = 0.0
AUTO_UPDATE_QUIET = 120   # seconds without an edit before the studio restarts under the author


def auto_update() -> None:
    if UPDATE_MANAGER.state.get('status') != 'available' or UPDATE_QUEUED is not None or UPDATE_RESTARTING:
        return
    if time.time() - LAST_CHANGE < AUTO_UPDATE_QUIET:
        return
    try:
        begin_update()
    except store.StudioError as error:
        if str(error).startswith('Зараз '):
            queue_update(str(error))   # waits for the work to end, as a pressed button does


def update_loop():
    while True:
        UPDATE_MANAGER.refresh()
        try:
            auto_update()
        except Exception:   # noqa: BLE001 — the check goes on every two minutes
            traceback.print_exc()
        time.sleep(120)


def active_export(project_id):
    with JOBS_LOCK:
        for entry in ACTIVE_EXPORTS.values():
            if entry['job']['project_id'] == project_id:
                return dict(entry['job'])
    return None


STOP_GRACE = 8   # seconds a cancelled export has to stop on SIGTERM before its whole group is killed


def cancel_export(jid):
    with JOBS_LOCK:
        entry = ACTIVE_EXPORTS.get(jid)
        if not entry:
            job = load_job(jid)
            if job['status'] in {'cancelled', 'complete', 'failed'}:
                return job
            raise store.StudioError('Активний експорт не знайдено', 409)
        if entry['job']['status'] in {'complete', 'failed', 'cancelled'}:
            return dict(entry['job'])
        entry['cancel'] = True
        entry['job']['status'] = 'cancelling'
        save_job(entry['job'])
        _export_queue_positions()
        EXPORT_CONDITION.notify_all()
        process = entry.get('process')
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            def force_stop():
                # the whole group, even when its leader is gone: a Razgon render left behind by razgon_bridge.py export
                # outlives a SIGTERM and holds the job's output open, so the export would read as stopping for ever
                try: os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError): pass
            timer = threading.Timer(STOP_GRACE, force_stop)
            timer.daemon = True
            timer.start()
        return dict(entry['job'])


def choose_local_folder(prompt: str) -> Path:
    result = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{prompt}")'], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise store.StudioError("Папку не вибрано")
    return Path(result.stdout.strip()).expanduser().resolve()


def choose_local_file(prompt: str) -> Path:
    result = subprocess.run(["osascript", "-e", f'POSIX path of (choose file with prompt "{prompt}")'], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise store.StudioError("Файл не вибрано")
    return Path(result.stdout.strip()).expanduser().resolve()


def update_studio_settings(settings):
    # Share the start/restart mutex: no worker can launch between this check and the directory switch.
    with UPDATE_MUTEX:
        if isinstance(settings, dict) and 'youtube_root' in settings and settings['youtube_root'] != str(store.YOUTUBE_ROOT):
            if IN_FLIGHT > 1:
                raise store.StudioError('Дочекайтеся збереження поточних змін перед зміною папки', 409)
            with JOBS_LOCK:
                exports = [dict(entry['job']) for entry in ACTIVE_EXPORTS.values()]
            if channel_voice_lab.ACTIVE or studio_work_status(exports)['busy']:
                raise store.StudioError('Дочекайтеся завершення поточної роботи перед зміною папки YouTube', 409)
        return store.update_global_settings(settings)


def pixabay_module():
    if str(store.APP_ROOT / "tools") not in sys.path:
        sys.path.append(str(store.APP_ROOT / "tools"))   # after backend: tools/ holds same-named CLI wrappers (music_library)
    import pixabay  # type: ignore
    return pixabay


def search_pixabay(query: str, kind: str, limit=12) -> list[dict]:
    if kind not in {"video", "image"} or not 1 <= len(query) <= 100 or not 1 <= limit <= 30:
        raise store.StudioError("Невірний запит Pixabay")
    pixabay = pixabay_module()
    try:
        data = pixabay.api_get(kind, q=query, per_page=max(3, limit), safesearch="true")
    except RuntimeError as exc:
        raise store.StudioError(str(exc), 503) from None
    results = []
    for hit in data.get("hits", [])[:limit]:
        result = pixabay.summary(hit, kind)
        result["pixabay_id"] = hit.get("id")
        result["name"] = hit.get("name") or hit.get("heading") or hit.get("tags") or ("Pixabay #" + str(hit.get("id")))
        result["source"] = "Pixabay"
        if kind == "video":
            result["duration"] = hit.get("duration")
            # Pixabay API video results have media URLs but no image thumbnail.
            # A video URL in an <img> would display as a broken preview.
            result["preview_url"] = None
            result["thumbnail_url"] = None
            result["preview_video_url"] = hit.get("videos", {}).get("tiny", {}).get("url")
        else:
            result["preview_url"] = hit.get("webformatURL") or hit.get("previewURL")
            result["thumbnail_url"] = hit.get("previewURL")
        results.append(result)
    return results


def from_pixabay(project: dict, kind: str, asset_id: int, quality: str | None = None) -> dict:
    if kind not in {"video", "image"}:
        raise store.StudioError("Невідомий тип матеріалу")
    quality = quality or ("medium" if kind == "video" else "large")
    if quality not in ({"medium", "large"} if kind == "video" else {"large", "fullhd"}):
        raise store.StudioError("Недоступна якість матеріалу")
    dest = store.media_dir(project)
    pixabay = pixabay_module()
    try:
        record = pixabay.download(kind, asset_id, quality, dest)
    except RuntimeError as exc:
        raise store.StudioError(str(exc), 503) from None
    asset = store.asset_record(Path(record["local_file"]), project["id"], "pixabay")
    asset["source_page"] = record["source_page"]
    asset["author"] = record["author"]
    asset["review_status"] = record["review_status"]
    with store.LOCK:
        latest = store.load_project(project["id"])
        latest.setdefault("assets", []).append(asset)
        latest["revision"] += 1
        store.save_project(latest)
    return asset


def normalize_for_engine(project: dict) -> dict:
    """Convert UI manifest to deterministic scene/track render manifest."""
    if project.get("schema_version") == 2:
        return timeline_manifest(project)
    if not project.get("scenes"):
        raise store.StudioError("Додайте кадри перед експортом")
    assets = {asset["id"]: asset for asset in store.discover_assets(project)}
    rendered_scenes = []
    for scene in project["scenes"]:
        kind = scene.get("type")
        if kind not in {"video", "image", "text", "color"}:
            raise store.StudioError("Невідомий тип кадру")
        source = None
        if kind in {"video", "image"}:
            aid = scene.get("asset_id")
            asset = assets.get(aid)
            if asset is None:
                raise store.StudioError("Для кадру «%s» ще не вибрано матеріал" % scene.get("title", ""))
            source = Path(asset["path"]).resolve()
            if not valid_local_source(source, project):
                raise store.StudioError("Матеріал кадру недоступний")
        transition = scene.get("transition", {"type": "cut", "duration": 0})
        transition_kind = transition.get("type", "cut")
        if transition_kind not in {"cut", "crossfade", "swipe", "wipe"}:
            raise store.StudioError("Цей перехід ще не підтримує експорт: " + str(transition_kind))
        layers = copy.deepcopy(scene.get("layers", []))
        rendered_scenes.append({"id": scene["id"], "type": kind, "source": str(source) if source else None, "duration": float(scene["duration"]), "trim_start": float(scene.get("trim_start", 0)), "transition_out": {"type": transition_kind, "duration": float(transition.get("duration", 0))}, "text": scene.get("text", scene.get("title", "")) if kind == "text" else None, "color": scene.get("color", "#101114"), "layers": layers})
    for track in project.get("tracks", []):
        if track.get("type") != "text":
            continue
        for clip in track.get("clips", []):
            absolute_start = float(clip["start"])
            absolute_end = absolute_start + float(clip["duration"])
            for original, rendered in zip(project["scenes"], rendered_scenes):
                scene_start = float(original["start"])
                scene_end = scene_start + float(original["duration"])
                overlap_start = max(absolute_start, scene_start)
                overlap_end = min(absolute_end, scene_end)
                if overlap_end > overlap_start:
                    rendered["layers"].append({"type": "text", "text": clip["text"], "x": 0.5, "y": 0.5, "width": 0.8, "height": 0.3, "opacity": 1.0, "start": overlap_start - scene_start, "duration": overlap_end - overlap_start, "keyframes": []})
    rendered_tracks = []
    for track in project.get("tracks", []):
        if track.get("type") not in {"voice", "music", "sfx"}:
            continue
        for clip in track.get("clips", []):
            aid = clip.get("asset_id")
            asset = assets.get(aid)
            if asset is None:
                raise store.StudioError("У звуковій доріжці бракує файлу")
            source = Path(asset["path"]).resolve()
            if not valid_local_source(source, project):
                raise store.StudioError("Аудіофайл недоступний")
            rendered_tracks.append({"kind": track["type"], "source": str(source), "volume": float(clip.get("volume", 1.0)), "start": float(clip.get("start", 0)), "duration": float(clip.get("duration", 0)), "trim_start": float(clip.get("trim_start", 0))})
    return {"width": int(project.get("width", 1920)), "height": int(project.get("height", 1080)), "fps": int(project.get("fps", 30)), "scenes": rendered_scenes, "tracks": rendered_tracks}


def job_path(jid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{24}", jid):
        raise store.StudioError("Завдання не знайдено", 404)
    return JOBS_ROOT / (jid + ".json")


def load_job(jid: str) -> dict:
    path = job_path(jid)
    if not path.is_file():
        raise store.StudioError("Завдання не знайдено", 404)
    with JOBS_LOCK:   # an export is saved and registered under this lock: read it the same way
        job = store.read_json(path)
        stale = job.get("id") not in ACTIVE_EXPORTS if isinstance(job, dict) else False
    # an export this server does not run (the studio restarted under it) is not running any more; speech jobs, saved
    # in the same folder, answer for themselves (analysis_jobs.owner_alive)
    if stale and not job.get("type") and job.get("status") in {"queued", "running", "cancelling"}:
        job = {**job, "status": "failed", "error": job.get("error") or "Експорт перервано: студію перезапустили. Запустіть його знову"}
    return job


def save_job(job: dict) -> None:
    with JOBS_LOCK:
        store.atomic_json(job_path(job["id"]), job)
        try:
            completion_notices.record(job)
        except (OSError, ValueError, store.StudioError) as error:
            print(f'Completion notice not saved: {error}', flush=True)
        if job.get("status") == "done":
            auto_pipeline.kick()   # the channel's «Автопублікація» takes the finished export now


import episode_automation
import auto_pipeline
episode_automation.JOB_CALLBACKS = (save_job, load_job)


@job_timing.measure('verification')
def _check_render(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 1024:
        raise RuntimeError("Рендер не створив повний відеофайл")
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError("Готовий файл не пройшов перевірку відео")
        info = json.loads(result.stdout)
        if not info.get("streams") or float(info.get("format", {}).get("duration", 0)) <= 0:
            raise RuntimeError("Готовий файл має порожній відеопотік")


def _render_razgon_blocks(job: dict, entry: dict, mixed: dict, render_manifest: Path) -> None:
    """A mixed episode's export, first part: razgon_bridge.py frames renders the Razgon code blocks (or reuses the clips
    rendered from the same code), then the manifest draws each block from its clip for the engine that follows."""
    started_at, clips, error, heads = time.monotonic(), None, None, {}
    with JOBS_LOCK:
        if entry['cancel']:
            return
        planned = store.read_json(render_manifest) or {}
        early, after = razgon_export.leads(planned, mixed), razgon_export.tails(planned, mixed)
        process = subprocess.Popen(razgon_export.frames_command(mixed, early, after), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        entry['process'] = process
    try:
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue   # render.mjs's own lines
            if event.get('stage') == 'error':
                error = str(event.get('message') or '')[:2000]
            elif event.get('stage') == 'razgon_frames_done':
                clips = event.get('clips') or {}
                heads = event.get('heads') or {}
            elif event.get('stage') == 'razgon':
                with JOBS_LOCK:
                    if entry['cancel']:
                        break
                    share = max(0.0, min(1.0, float(event.get('progress', 0))))
                    job.update(stage='razgon_frames', progress=max(job['progress'], round(40 * share)), razgon_completed=int(event.get('completed', 0)), razgon_total=int(event.get('total', 0)))
                    elapsed = time.monotonic() - started_at
                    job['remaining_seconds'] = round(elapsed * (1 - share) / share) if share >= .02 else None
                    save_job(job)
        returncode = process.wait()
    finally:
        process.stdout.close()
    if entry['cancel']:
        return
    if returncode or clips is None:
        raise RuntimeError('Кадри Razgon: ' + (error or f'код {returncode}'))
    manifest = store.read_json(render_manifest)
    razgon_export.point_blocks_at_clips(manifest, mixed, clips, heads)
    store.atomic_json(render_manifest, manifest)
    with JOBS_LOCK:
        # Code frames are the first 40% of this export; the engine continues from here.
        job.update(stage='preparing', progress=max(job['progress'],40), remaining_seconds=None)
        save_job(job)


def _export_queue_positions() -> None:
    """Called under JOBS_LOCK; queued jobs are ordered by their accepted submission."""
    waiting = [entry['job'] for entry in ACTIVE_EXPORTS.values()
               if entry['job']['status'] == 'queued' and not entry['cancel']]
    for position, job in enumerate(waiting, 1):
        if job.get('queue_position') != position:
            job['queue_position'] = position
            save_job(job)


@job_timing.track('export', project='job', job='job')
def _queued_render_worker(job: dict, *args) -> None:
    """A single render slot across channels, with cancellable FIFO waiting."""
    global EXPORT_RUNNING
    try:
        with job_timing.span('queue'), EXPORT_CONDITION:
            entry = ACTIVE_EXPORTS[job['id']]
            while not entry['cancel']:
                first = next((item['job']['id'] for item in ACTIVE_EXPORTS.values()
                              if item['job']['status'] == 'queued' and not item['cancel']), None)
                if EXPORT_RUNNING is None and first == job['id']:
                    EXPORT_RUNNING = job['id']
                    job.update(status='running', stage='preparing', queue_position=None)
                    save_job(job)
                    break
                EXPORT_CONDITION.wait()
            _export_queue_positions()
        # A cancelled waiting job follows the existing cleanup path without starting an encoder.
        _render_worker(job, *args)
    except Exception as error:
        with JOBS_LOCK:
            entry = ACTIVE_EXPORTS.pop(job['id'], None)
            if entry:
                job.update(status='failed', error=str(error), queue_position=None)
                try:
                    save_job(job)
                finally:
                    guard = entry.pop('project_guard', None)
                    if guard:
                        guard.close()
            for file in args[:2]:
                file.unlink(missing_ok=True)
    finally:
        with EXPORT_CONDITION:
            if EXPORT_RUNNING == job['id']:
                EXPORT_RUNNING = None
            try:
                _export_queue_positions()
            finally:
                EXPORT_CONDITION.notify_all()


@job_timing.measure('rendering')
def _render_worker(job: dict, render_manifest: Path, staging: Path, destination: Path, command: list[str] | None = None, mixed: dict | None = None) -> None:
    with JOBS_LOCK:
        entry = ACTIVE_EXPORTS[job['id']]
        if not entry['cancel']:
            job['status'] = 'running'
            save_job(job)
    try:
        if entry['cancel']:
            return
        if mixed:
            _render_razgon_blocks(job, entry, mixed, render_manifest)
            if entry['cancel']:
                return
        started_at = time.monotonic()
        if command is None and not ENGINE_SCRIPT.is_file():
            raise RuntimeError("Рушій експорту ще не встановлено")
        command = command or [sys.executable, str(ENGINE_SCRIPT), "--project", str(render_manifest), "--output", str(staging)]
        render_data = store.read_json(render_manifest)
        scene_total = len(render_data.get("scenes", [])) or sum(len(layer.get("clips", [])) for layer in render_data.get("timeline_layers", []))
        with JOBS_LOCK:
            if entry['cancel']:
                return
            # the engine's render cache lives with the episode (next to its renders/), so it goes with the episode folder
            # an export never draws a still's window: a CapCut window left over in this process drew every other seam as a cut
            env = {**{k: v for k, v in os.environ.items() if k not in STILL_ONLY_ENV}, "MULTIBOT_RENDER_CACHE": str(render_manifest.parent.parent / "render-cache")}
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True, env=env)
            entry['process'] = process
        def terminate_group():
            try: os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError): pass
        timeout = threading.Timer(4 * 3600, terminate_group)
        timeout.daemon = True
        timeout.start()
        render_error = None
        verification_started_at = None
        current_scene = None
        render_floor = 40 if mixed else 0
        # the last lines the render printed that are not progress: a crash's traceback ends there (an export failed with
        # only «код 1» on 23 November 2026, its cause thrown away with the other lines)
        plain_tail = collections.deque(maxlen=12)
        try:
            progress_from = render_floor if mixed else None
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    if line.strip():
                        plain_tail.append(line.strip()[:400])
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get('stage') == 'scene_start':
                    current_scene = event.get('scene')
                elif event.get('stage') == 'error':
                    render_error = str(event.get('message') or 'Помилка обробки відео')
                total = max(1, int(event.get("total", scene_total)))
                if event.get('stage') == 'preparing_cloud':
                    progress=0
                    stage='preparing_cloud'
                    job['cloud_total']=total
                    job['cloud_completed']=max(0,min(total,int(event.get('completed',0))))
                    if job['cloud_completed']==total:
                        started_at=time.monotonic()
                elif event.get('stage') == 'validated':
                    progress=0
                    stage='rendering'
                elif event.get('stage') == 'gpu_start':
                    progress=0
                    stage='rendering'
                    job['render_mode']='gpu'
                elif event.get('stage') == 'gpu_fallback':
                    progress=0
                    stage='rendering'
                    job['render_mode']='standard'
                    job['gpu_fallback']=True
                    job['gpu_fallback_reason']=str(event.get('message') or '')[:2000]
                    render_floor = max(render_floor,job['progress'])
                    progress_from = render_floor
                    started_at=time.monotonic()
                elif event.get("stage") == "scene_done":
                    rendered = float(event.get('rendered_duration', 0))
                    total_duration = float(event.get('total_duration', 0))
                    progress = min(80, round(80 * rendered / total_duration)) if total_duration > 0 else min(80, round(80 * int(event.get("completed", event.get("scene", 0))) / total))
                    stage = 'rendering'
                elif event.get("stage") == "compose":
                    progress = min(98, 80 + round(18 * float(event.get("progress", 0))))
                    stage = 'composing'
                elif event.get('stage') == 'razgon':
                    # razgon_bridge.py export: Razgon draws the frames, then the glue and the sound mix (razgon_export.py)
                    progress = min(99, round(99 * float(event.get('progress', 0))))
                    stage = str(event.get('phase') or 'rendering')
                    # frames rendered by an earlier export count from the start: the time left follows this run's own pace
                    progress_from = progress if progress_from is None else progress_from
                    if 'total' in event:
                        job['razgon_completed'], job['razgon_total'] = int(event.get('completed', 0)), int(event['total'])
                elif event.get('stage') == 'verify':
                    if verification_started_at is None:
                        verification_started_at = time.monotonic()
                    verification_progress = max(0.0,min(1.0,float(event.get('progress',0))))
                    progress = min(99,98+int(verification_progress*2))
                    stage = 'verifying'
                else:
                    continue
                if event.get('stage') != 'verify':
                    progress = round(render_floor + (98-render_floor)*max(0,min(98,progress))/98)
                with JOBS_LOCK:
                    if not entry['cancel']:
                        job['progress'] = max(job['progress'],progress)
                        job_timing.advance('verification' if stage == 'verifying' else 'rendering')
                        job['stage'] = stage
                        elapsed = max(0.0, time.monotonic() - started_at)
                        if stage == 'verifying':
                            verify_elapsed=max(0.0,time.monotonic()-verification_started_at)
                            job['remaining_seconds']=round(verify_elapsed*(1-verification_progress)/verification_progress) if verification_progress>=.02 else None
                        else:
                            made=job['progress']-(progress_from or 0)
                            job['remaining_seconds']=round(elapsed*(100-job['progress'])/made) if made>=1 else None
                        save_job(job)
            returncode = process.wait()
        finally:
            timeout.cancel()
            process_cleanup.stop_group(process)
            process.stdout.close()
        if entry['cancel']:
            return
        if returncode:
            prefix = f'Сцена {current_scene}: ' if current_scene and not (render_error or '').startswith('Сцена ') else ''
            cause = next((l for l in reversed(plain_tail) if re.search(r'Error|error|Exception|failed|Помилка', l)), plain_tail[-1] if plain_tail else '')
            fallback = (f'процес зупинено сигналом {-returncode}' if returncode < 0 else f'код {returncode}') + (f': {cause}' if cause else '')
            raise RuntimeError(prefix + (render_error or fallback))
        _check_render(staging)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with JOBS_LOCK:
            job.update(stage='saving', remaining_seconds=None)
            save_job(job)
        with job_timing.span('saving'), export_delivery.prepared(staging, destination, lambda: entry['cancel']) as ready:
            with JOBS_LOCK:
                if entry['cancel']:
                    return
                export_delivery.publish(ready, destination)
                job["status"] = "complete"
                job["output_path"] = str(destination)
                job["progress"] = 100
        # the film is final: its language soundtracks follow the timeline's sound (music, effects, video sound)
        try:
            language_mix.refresh_later(job["project_id"], "export")
        except Exception as error:
            print(f'Export saved; language soundtrack refresh not started: {error}', flush=True)
    except Exception as exc:
        with JOBS_LOCK:
            if not entry['cancel']:
                job["status"] = "failed"
                job["error"] = str(exc)
    finally:
        process_cleanup.stop_group(entry.get('process'))
        if staging.exists():
            staging.unlink()
        render_manifest.unlink(missing_ok=True)   # the job file keeps what was exported; the manifest was only its input
        with JOBS_LOCK:
            if entry['cancel']:
                job.update(status='cancelled', error=None, output_path=None)
            try:
                save_job(job)
            finally:
                ACTIVE_EXPORTS.pop(job['id'], None)
                guard = entry.pop('project_guard', None)
                if guard:
                    guard.close()


def start_export(project: dict, confirmation: bool, bitrate=None) -> dict:
    if confirmation is not True:
        raise store.StudioError("Підтвердіть фінальний експорт після перегляду проєкту")
    # an export writes its scenes and the film before it publishes: on a nearly full disk it failed after an hour with
    # «No space left on device» and filled the disk for everything else (25 November 2026); the button and the
    # channel's automatic export both stop here
    free = shutil.disk_usage(store.DATA_ROOT).free
    if free < EXPORT_MIN_FREE:
        raise store.StudioError(f"Мало місця на диску: вільно {free / 1024 ** 3:.1f} ГБ, для експорту потрібно хоча б "
                                f"{EXPORT_MIN_FREE // 1024 ** 3} ГБ. Звільніть місце й запустіть експорт ще раз.", 507)
    # the export window's three choices for this episode's size and frame rate (store.video_bitrates)
    choices = store.video_bitrates(int(project.get("width") or 1920), int(project.get("height") or 1080), int(project.get("fps") or 25))
    if bitrate is not None and bitrate not in choices:
        raise store.StudioError("Невідома якість відео", 400)
    readiness = store.plan_readiness(project)
    if not readiness["export_ready"]:
        raise store.StudioError(readiness["reason"], 409)
    if project["id"] in production.ACTIVE or project["id"] in director.ACTIVE:
        # the export locks the project: the agent's next frame would fail and the film would miss what it is making
        raise store.StudioError("Над випуском зараз працює режисер або агент кадрів. Експортуйте, коли він закінчить", 409)
    razgon = razgon_export.export_job(project)
    # a mixed episode: the bridge renders its Razgon code blocks first, then the engine exports the timeline
    mixed = razgon if razgon and razgon.get("mixed") else None
    razgon = None if mixed else razgon
    manifest = razgon or normalize_for_engine(project)
    if not razgon:
        # the quality picked in the export window; an all-Razgon film keeps the bridge's own encoding
        manifest["video_bitrate"] = bitrate or choices[0]
    jid = uuid.uuid4().hex[:24]
    output_folder = Path(project["episode_path"])
    channel = store.get_channel_folder(project["channel_id"], include_disabled=True)
    if not store.under(output_folder, channel):
        raise store.StudioError("Папка експорту поза каналом")
    export_subfolder = store.global_settings()["export_subfolder"]
    if export_subfolder:
        output_folder = output_folder / export_subfolder
    if not store.under(output_folder, Path(project["episode_path"])):
        raise store.StudioError("Папка експорту поза випуском")
    render_dir = store.cache_dir(project) / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    # An export needs room for its chunks, the joined picture and the final file (about three times the film) and the
    # episode folder for the result: say so before an hour of rendering, not after.
    seconds = float(project.get("duration") or 0)
    need = 2 * 1024 ** 3 + int(seconds * 3 * 1024 ** 2)
    for place in {render_dir, output_folder if output_folder.exists() else Path(project["episode_path"])}:
        try:
            free = shutil.disk_usage(place).free
        except OSError:
            continue
        if free < need:
            raise store.StudioError(f"Для експорту бракує місця на диску: вільно {free / 1024 ** 3:.1f} ГБ, потрібно близько "
                                    f"{need / 1024 ** 3:.1f} ГБ. Звільніть місце (кнопка «Звільнити місце» на картці випуску) і спробуйте ще раз.", 507)
    manifest_path = render_dir / (jid + ".json")
    staging = render_dir / (jid + ".mp4")
    store.atomic_json(manifest_path, manifest)
    job = {"id": jid, "project_id": project["id"], "status": "queued", "progress": 0, "stage": "preparing", "remaining_seconds": None, "output_path": None, "error": None}
    if razgon:
        # every frame of the film; the ones the timeline already holds rendered are done (the bridge adds its cached ones)
        job.update(razgon_completed=len(razgon["clips"]) - razgon["render"], razgon_total=len(razgon["clips"]))
    if mixed:
        job.update(razgon_completed=0, razgon_total=len(set(mixed["blocks"].values())))
    with JOBS_LOCK:
        existing = active_export(project['id'])
        if existing:
            manifest_path.unlink(missing_ok=True)
            return existing
        # what a killed or crashed export of this project left behind: GPU work folders and old manifests
        for stale in render_dir.glob(".mbvs-gpu-*"):
            shutil.rmtree(stale, ignore_errors=True)
        for stale in render_dir.glob("*.json"):
            if stale != manifest_path:
                stale.unlink(missing_ok=True)
        guard = agent_runtime.acquire_project_guard(project['id'], 'export')
        if guard is None:
            manifest_path.unlink(missing_ok=True)
            raise store.StudioError("Дочекайтеся завершення роботи агента або експорту.", 409)
        try:
            if store.load_project(project['id']).get('revision', 0) != project.get('revision', 0):
                raise store.StudioError("Проєкт змінився перед експортом. Спробуйте ще раз.", 409)
            destination = export_names.destination(output_folder, project.get('name'),
                [entry['destination'] for entry in ACTIVE_EXPORTS.values() if entry.get('destination')])
            job['export_filename'] = destination.name
            save_job(job)
            ACTIVE_EXPORTS[jid] = {'job': job, 'process': None, 'cancel': False, 'project_guard': guard,
                                   'destination': str(destination)}
            _export_queue_positions()
            command = razgon_export.command(manifest_path, staging) if razgon else None
            threading.Thread(target=_queued_render_worker, args=(job, manifest_path, staging, destination, command, mixed), daemon=True).start()
        except Exception:
            ACTIVE_EXPORTS.pop(jid, None)
            guard.close()
            manifest_path.unlink(missing_ok=True)
            _export_queue_positions()
            EXPORT_CONDITION.notify_all()
            raise
    return job


STILL_SCRIPT = APP_ROOT / "engine" / "still.py"
STILL_LOCK = threading.Lock()


def busy_candidates() -> set[str]:
    """Projects whose work runs in this server now: only these can be busy, the rest need not be read."""
    # .copy() is one step under the interpreter lock: a set changing while it is iterated would throw
    return (project_narration.ACTIVE.copy() | director.ACTIVE.copy() | director.RETIMING.copy() | production.ACTIVE.copy() | razgon_sound.ACTIVE.copy() | event_sounds_running() | thumbnail_gen.ACTIVE.copy() | languages.active_projects() | set(agent_runtime.JOBS.copy())
            | set(analysis_jobs.ACTIVE_PROJECTS.copy().values()))


def cleanup_blocked(pid):
    if active_export(pid):
        return "Зараз іде експорт"
    if pid in busy_candidates() and any(value in agent_view.BUSY for value in project_jobs(pid).values()):
        return "У проєкті триває робота"
    import episode_ideas
    if any(job.get('project_id') == pid for job in episode_ideas.active_work()):
        return "Створюється сценарій"
    return space.busy(pid)


def listed(pid: str) -> dict:
    """A project's own fields as saved, read once per version of its file (store.listed_project): for a status that
    needs only a field or two. Read only; raises as store.load_project does for a missing or deleted project."""
    try:
        data = store.listed_project(store.project_path(pid))
    except FileNotFoundError:
        data = None
    if not isinstance(data, dict):
        raise store.StudioError("Пошкоджено файл проєкту", 500)
    if data.get("deleted_at"):
        raise store.StudioError("Проєкт видалено зі списку", 404)
    return data


def project_jobs(pid: str) -> dict:
    """{what: status} of the work that runs for one project besides its export."""
    # only the saved request is needed here, not the whole read; a project unreadable for a moment still reports the
    # rest of its work, so a restart keeps waiting for it
    try:
        request = listed(pid).get("production_request")
    except (store.StudioError, OSError, ValueError):
        request = None
    def status(read):
        try:
            return (read() or {}).get("status")
        except (store.StudioError, OSError, ValueError, KeyError):
            return None
    jobs = {"озвучення сценарію": status(lambda: project_narration.work_job(pid)),
            "розпізнавання озвучки": status(lambda: analysis_jobs.latest(pid, load_job, compact=True, include_report=False).get("job")),
            "режисура": status(lambda: director.state(pid)),
            "створення кадрів": request.get("status") if isinstance(request, dict) else None,
            "музика й ефекти": status(lambda: razgon_sound.state(pid)),
            "прев'ю": status(lambda: thumbnail_gen.state(pid)),
            "мови": 'running' if languages.busy(pid) else status(lambda: next((job for job in (languages.load_state(pid).get("jobs") or {}).values() if job.get("status") == "running"),
                                        languages.load_state(pid).get("job"))),
            "агент студії": status(lambda: agent_runtime.snapshot(pid))}
    # A worker owns its slot until cleanup and the next-stage registration finish,
    # even if its terminal receipt was already written.
    # the move of a direction onto the real voice is the director's work too: the card and the channel spin, and a
    # restart waits for it (it took up to 10 minutes unseen; 16 November 2026 stability pass)
    for kind, owned in {'озвучення сценарію': project_narration.ACTIVE,
                        'режисура': director.ACTIVE | director.RETIMING, 'створення кадрів': production.ACTIVE,
                        'музика й ефекти': razgon_sound.ACTIVE | event_sounds_running(), "прев'ю": thumbnail_gen.ACTIVE,
                        'розпізнавання озвучки': set(analysis_jobs.ACTIVE_PROJECTS.copy().values())}.items():
        if pid in owned and jobs[kind] not in agent_view.BUSY:
            jobs[kind] = 'running'
    return jobs


def event_sounds_running() -> set:
    """Projects whose sounds are being laid from their frames' code (event_sounds.py): a restart waits for them."""
    import event_sounds
    with event_sounds.LOCK:
        return set(event_sounds.RUNNING)


def channel_task_outcome(task):
    kind, cid, pid = task['kind'], task['channel_id'], task.get('project_id')
    if kind == 'експорт':
        return load_job(task['job_id']).get('status')
    if kind == 'публікація':   # on YouTube: done with its blue check, otherwise it stopped
        return 'done' if (store.read_json(published.path(pid), {}) or {}).get('at') else 'stopped'
    if kind == 'зразок голосу':
        return store.read_json(channel_voice_lab.folder(cid) / 'job.json', {}).get('status')
    if kind == 'зразок перекладу':
        return store.read_json(channel_translation_voices.folder(cid, task['language']) / 'job.json', {}).get('status')
    if kind in {'створення зачинів', 'створення сценарію', 'створення метаданих', 'редактура сценарію', 'ідеї'}:
        import episode_ideas
        data = episode_ideas.read_project(pid) if pid else episode_ideas.read(cid)
        return 'cancelled' if data.get('cancelled') else data.get('status')
    if kind == 'створення кадрів':
        request = listed(pid).get('production_request') or {}
        if request.get('paused') and (request.get('paused_by') == 'user' or
                                      request.get('paused_by') is None and str(request.get('error') or '').startswith('Призупинено на ваше прохання')):
            return 'paused_by_user'
    result = project_jobs(pid).get(kind)
    if result == 'paused' and episode_pause.paused(pid) is not None:
        return 'paused_by_user'   # the author's round pause stopped it, not a failure (it read «зупинилась сама»)
    return result


def channel_completion_status(result, exports):
    tasks = list(result['activities'])
    for job in exports:
        if job.get('status') in agent_view.BUSY:
            try:
                cid = store.listed_project(store.project_dir(job['project_id']) / 'project.json').get('channel_id')
                tasks.append({'channel_id': cid, 'project_id': job['project_id'], 'kind': 'експорт', 'job_id': job['id']})
            except (OSError, ValueError, store.StudioError):
                pass
    for cid in channel_voice_lab.ACTIVE.copy():
        result['active_channels'] = sorted(set(result['active_channels']) | {cid})
        tasks.append({'channel_id': cid, 'kind': 'зразок голосу'})
    for cid, code in channel_translation_voices.ACTIVE.copy():
        tasks.append({'channel_id': cid, 'kind': 'зразок перекладу', 'language': code})
    for pid, cid in published.active_projects().items():
        tasks.append({'channel_id': cid, 'project_id': pid, 'kind': 'публікація'})
    try:
        published.ensure_session()   # a queue nobody takes opens a publishing session
    except Exception:
        pass
    result['channel_notices'] = channel_activity.notices.update(result['active_channels'], tasks, channel_task_outcome)
    return result


def paused_view(pid):
    """The project as the cards read it: with whether the episode waits for play and what it waits with."""
    project = store.load_project(pid)
    return {**project, "episode_paused": episode_pause.resumable(pid), "episode_pause_label": episode_pause.label(pid)}


def studio_work_status(exports):
    result = agent_view.studio_status(exports, project_jobs, busy_candidates())
    # an episode on the author's pause shows «на паузі» at once while the phrase being made still finishes: its channel
    # does not spin for that tail (user, 17 November 2026: «тут спінер крутить, а на проектах нічого нема»). The busy list
    # keeps it, so a restart still waits for it.
    paused = {pid for pid in {a.get('project_id') for a in result.get('activities', [])} if pid and episode_pause.paused(pid)}
    def started_after_pause(activity):
        # work the author starts by hand on a paused episode (a language's voice) is its own and shows on the card (user,
        # 18 November 2026: «корбин перекладає мову, але його зміни нема на проєкті»: Russian voiced while the episode
        # held its pause from the day before)
        if activity.get('kind') != 'мови':
            return False
        since = (episode_pause.paused(activity['project_id']) or {}).get('paused_at') or 0
        try:
            jobs = (languages.load_state(activity['project_id']).get('jobs') or {}).values()
        except (OSError, ValueError, store.StudioError):
            return False
        return any(isinstance(job, dict) and job.get('status') == 'running' and (job.get('started_at') or 0) > since for job in jobs)
    # only the work the pause stopped is hidden; another part that runs meanwhile shows as it is (user, 19 November 2026:
    # «озвучка на паузі, але план створюється… краще показати те, що створюється»)
    parts = {'озвучення сценарію': 'narration', 'режисура': 'director', 'створення кадрів': 'production', 'мови': 'languages',
             'створення зачинів': 'writing', 'створення сценарію': 'writing', 'створення метаданих': 'writing',
             'редактура сценарію': 'writing'}
    def held(activity):
        stopped = (episode_pause.paused(activity['project_id']) or {}).get('stopped') or {}
        part = parts.get(activity.get('kind'))
        return not stopped or part is None or part in stopped or (part == 'director' and 'retime' in stopped)
    if paused:
        result['activities'] = [a for a in result['activities'] if a.get('project_id') not in paused or started_after_pause(a) or not held(a)]
        result['active_channels'] = sorted(set(result.get('exporting_channels', [])) | {a.get('channel_id') for a in result['activities'] if a.get('channel_id')})
    # A live frame worker must block an update even when its project metadata
    # is temporarily unreadable or its final receipt was already written.
    visible={item['project_id'] for item in result.get('activities',[]) if item.get('kind')=='створення кадрів'}
    for pid in production.ACTIVE.copy()-visible:
        result['busy'].append('створення кадрів: '+pid)
        result.setdefault('activities',[]).append({'project_id':pid,'kind':'створення кадрів','status':'running'})

    # what a language lane does now, so the project card can say «Перекладаємо · DE» (user, 15 November 2026)
    for item in result.get('activities', []):
        if item.get('kind') == 'мови':
            try:
                state = languages.load_state(item['project_id'])
                jobs = [job for job in (state.get('jobs') or {}).values() if isinstance(job, dict) and job.get('status') == 'running']
                item['jobs'] = [{'kind': job.get('kind'), 'code': job.get('code'),
                                 **({'queued': True, 'queue_position': job.get('queue_position')} if job.get('queued') else {})} for job in jobs]
            except (OSError, ValueError, store.StudioError):
                item['jobs'] = []
        elif item.get('kind') == 'режисура':
            # the director's run makes the film's kit after the plan: the card reads «Підготовка» then
            item['stage'] = ('retime' if item['project_id'] in director.RETIMING and item['project_id'] not in director.ACTIVE
                             else (director.state(item['project_id']) or {}).get('stage'))
    if STARTUP_STATE.get('current') == 'migrate_at_start':   # project files are moved right after a start
        result['busy'].append('перенесення службових файлів після запуску')
    if trending_videos.busy():
        result['busy'].append('оновлення добірки конкурентів')
    if title_translation.busy():
        result['busy'].append('переклад заголовка')
    if channel_translation_voices.busy():
        result['busy'].append('зразки голосів перекладу')
        result['active_channels']=sorted(set(result['active_channels'])|{cid for cid,code in channel_translation_voices.ACTIVE.copy()})
    import episode_ideas
    result.setdefault('activities', [])
    result.setdefault('active_channels', [])
    for data in episode_ideas.active_work():
        cid = data['channel_id']
        kind = 'редактура сценарію' if data.get('editing_status')=='running' or data['stage']=='editing' else {'openings': 'створення зачинів', 'metadata': 'створення метаданих'}.get(data['stage'], 'створення сценарію')
        result['busy'].append(kind + ': ' + (data.get('project_id') or cid))
        result['active_channels'] = sorted(set(result['active_channels']) | {cid})
        result['activities'].append({'project_id': data.get('project_id'), 'channel_id': cid, 'kind': kind if data.get('project_id') else 'ідеї', 'status': 'running'})
    # how many episodes of each channel are at work now, a grey number by the channel's spinner (user, 15 November 2026)
    working = {}
    for item in result['activities']:
        if item.get('project_id'):
            working.setdefault(item['project_id'], item.get('channel_id'))
    for job in exports:
        if job.get('status') in agent_view.BUSY and job.get('project_id'):
            working.setdefault(job['project_id'], None)
    for pid, cid in published.active_projects().items():   # queued for or going through its YouTube publication
        working.setdefault(pid, cid)
    counts = {}
    for pid, cid in working.items():
        if not cid:
            try:
                cid = store.listed_project(store.project_dir(pid) / 'project.json').get('channel_id')
            except (OSError, ValueError, store.StudioError):
                continue
        if cid:
            counts[cid] = counts.get(cid, 0) + 1
    result['channel_projects'] = counts
    # the channel's own work has no episode card to spin: the channel page names it, or the sidebar spinner reads as
    # a stuck episode (user, 17 November 2026: «спінери не сходяться… там крутиться, тут нічого не крутиться»)
    channel_work = {}
    for cid in channel_voice_lab.ACTIVE.copy():
        sample = store.read_json(channel_voice_lab.folder(cid) / 'job.json', {}) or {}
        channel_work.setdefault(cid, []).append('Зразок голосу' if sample.get('status') in agent_view.BUSY else 'Голос каналу')
    for cid, code in channel_translation_voices.ACTIVE.copy():
        channel_work.setdefault(cid, []).append('Зразок голосу перекладу · ' + str(code).upper())
    result['channel_work'] = channel_work
    return result


def channel_transfer_idle(cid):
    store.get_channel_folder(cid)
    with JOBS_LOCK:
        exports = [dict(entry['job']) for entry in ACTIVE_EXPORTS.values()]
    if cid in studio_work_status(exports)['active_channels'] or channel_voice_lab.in_use(cid):
        raise store.StudioError('Дочекайтеся завершення роботи в цьому каналі перед перенесенням налаштувань.', 409)


def recent_exports(pid: str, limit: int = 5) -> list[dict]:
    """The project's latest export jobs, newest first (running, finished, failed or cancelled)."""
    found = []
    for path in sorted(JOBS_ROOT.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:400]:
        try:
            job = store.read_json(path)
            if isinstance(job, dict) and job.get("project_id") == pid and job.get("id"):
                job = load_job(job["id"])   # an export cut by a restart reads as stopped, not «running 37%»
        except (OSError, ValueError, store.StudioError):
            continue
        if isinstance(job, dict) and job.get("project_id") == pid and "output_path" in job:
            found.append({key: job.get(key) for key in ("id", "status", "progress", "stage", "remaining_seconds", "output_path", "error",
                                                         "razgon_completed", "razgon_total", "render_mode")})
            found[-1]["updated_at"] = round(path.stat().st_mtime)
            if len(found) >= limit:
                break
    return found


STILL_ONLY_ENV = {"STUDIO_CAPCUT_WINDOW", "STUDIO_GPU_WINDOW_START"}   # set only for a still, never handed to an export


def export_still(project: dict, moment: float, frames: int = 1, cpu: bool = False) -> dict:
    """A still of the export at `moment` (the first of `frames` frames), drawn by the export's own renderer on a
    window of the render manifest (engine/still.py), to hold against the preview at the same moment. Razgon code
    frames are not rendered here: they stay code until «Експорт MP4» (user, 30 October 2026)."""
    manifest = normalize_for_engine(project)
    from render_cache import renderer_version
    key = hashlib.sha256(json.dumps([manifest, round(float(moment), 4), int(frames), bool(cpu), renderer_version(APP_ROOT / "engine")],
                                    sort_keys=True, default=str).encode()).hexdigest()[:20]
    folder = store.cache_dir(project) / "stills"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"still-{key}.png"
    info_path = folder / f"still-{key}.json"
    notes = [f"«{clip.get('title')}» тут код Razgon: на стоп-кадрі його немає, його малює тільки «Експорт MP4»"
             for track in project.get("tracks", []) for clip in track.get("clips", [])
             if str(clip.get("title", "")).startswith("Razgon") and float(clip["start"]) <= moment < float(clip["start"]) + float(clip["duration"])]
    if info_path.is_file() and all(Path(path).is_file() for path in store.read_json(info_path, {}).get("outputs", [])):
        return {**store.read_json(info_path), "cached": True, "notes": notes}
    with STILL_LOCK:
        manifest_path = folder / f"still-{key}-manifest.json"
        store.atomic_json(manifest_path, manifest)
        try:
            result = subprocess.run(["nice", "-n", "10", sys.executable, str(STILL_SCRIPT), "--project", str(manifest_path), "--time", str(moment),
                                     "--output", str(output), "--frames", str(int(frames))] + (["--cpu"] if cpu else []),
                                    capture_output=True, text=True, timeout=900,
                                    env={**os.environ, "MULTIBOT_RENDER_CACHE": str(folder.parent / "render-cache")})
        finally:
            manifest_path.unlink(missing_ok=True)
        try:
            info = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            info = {"error": (result.stdout + result.stderr)[-1500:]}
        if result.returncode or info.get("error"):
            raise store.StudioError("Стоп-кадр не вийшов: " + str(info.get("error") or "")[-600:], 500)
        info["urls"] = [f"/api/projects/{project['id']}/stills/{Path(path).name}" for path in info["outputs"]]
        store.atomic_json(info_path, info)
        # about the last twenty stills of a project: a 1080p PNG takes some 3 MB
        stills = sorted(folder.glob("still-*"), key=lambda item: item.stat().st_mtime, reverse=True)
        for old in stills[40:]:
            old.unlink(missing_ok=True)
    return {**info, "cached": False, "notes": notes}


CAPCUT_SCRIPT = APP_ROOT / "engine" / "capcut_fx.py"
CAPCUT_LOCK = threading.Lock()
# two seams drawn at once: one at a time took ten minutes to prepare a film's fifty transitions (25 November 2026)
CAPCUT_SLOTS = threading.BoundedSemaphore(2)
CAPCUT_JOIN_LOCKS: dict = {}
EFFECT_PREVIEWS: dict = {}   # effect name → its drawn looping preview


def capcut_run(arguments: list[str], timeout: int = 900) -> Path:
    """engine/capcut_fx.py in its own process (the CapCut drawing loads numpy, scipy and the packages)."""
    result = subprocess.run(["nice", "-n", "10", sys.executable, str(CAPCUT_SCRIPT), *arguments],
                            capture_output=True, text=True, timeout=timeout)
    try:
        info = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        info = {"error": (result.stdout + result.stderr)[-1500:]}
    if result.returncode or info.get("error"):
        raise store.StudioError("CapCut: " + str(info.get("error") or "")[-600:], 500)
    return Path(info["output"])


RAZGON_BLOCK = re.compile(r"Razgon · кадр \d{3}")


def capcut_touches_code(project: dict, join: dict) -> bool:
    """True when a side of the seam is a Razgon code block, which only the export draws."""
    groups = {g.get("id"): set(g.get("clip_ids") or []) for g in project.get("scene_groups", [])}
    sides = set()
    for ref in (join.get("from_ref"), join.get("to_ref")):
        kind, _, ident = str(ref or "").partition(":")
        sides |= groups.get(ident, set()) if kind == "group" else {ident}
    return any(c.get("id") in sides and c.get("kind") == "animation" and RAZGON_BLOCK.fullmatch(c.get("title") or "")
               for t in project.get("tracks", []) for c in t.get("clips", []))


# a CapCut seam's preview at 1280 px wide: 640 px stretched over the editor's picture looked blurred, «криво» (user,
# 25 November 2026); it is drawn once a seam and kept
PREVIEW_WIDTH = 1280


def razgon_windows(project: dict, join: dict, manifest: dict, width: int) -> None:
    """The Razgon code blocks on the seam's sides as small videos of the transition's window, put into the manifest in
    their place (only this preview's manifest)."""
    import hashlib
    link = store.razgon_link(project)
    if not link:
        raise store.StudioError("Немає проєкту Razgon", 404)
    razgon = Path(link["project"])
    fps = int(manifest.get("fps") or project.get("fps") or 25)
    begin, end = joins.window(join)
    sides = set()
    groups = {g.get("id"): set(g.get("clip_ids") or []) for g in project.get("scene_groups", [])}
    for ref in (join.get("from_ref"), join.get("to_ref")):
        kind, _, ident = str(ref or "").partition(":")
        sides |= groups.get(ident, set()) if kind == "group" else {ident}
    blocks = {c["id"]: c for t in project.get("tracks", []) for c in t.get("clips", [])
              if c.get("id") in sides and c.get("kind") == "animation" and RAZGON_BLOCK.fullmatch(c.get("title") or "")}
    if not blocks:
        return
    home = razgon.parents[1]   # the renderer and the engine draw the picture too: a change of them makes new windows
    watched = [razgon / "config.json", razgon / "story" / "shots.json", *sorted((razgon / "scenes").rglob("*.js")),
               home / "render.mjs", *sorted((home / "engine").glob("*.js"))]
    stamp = hashlib.sha256("|".join(f"{p}:{p.stat().st_mtime_ns}" for p in watched if p.is_file()).encode()).hexdigest()[:12]
    folder = store.cache_dir(project) / "capcut"
    folder.mkdir(parents=True, exist_ok=True)
    # whole frames counted as CapCut's own window counts them (floor of x + 0.5), with one frame to spare each side:
    # round() made 160.5 into 160 while the transition drew frame 160 too, and that last frame had no Razgon picture,
    # the black frame after the transition (user, 25 November 2026: «чорні якісь появляються фрейми… після переходів»)
    a, b = max(0, math.floor(begin * fps + .5 + 1e-8) - 1), math.floor(end * fps + .5 + 1e-8) + 1
    for layer in manifest.get("timeline_layers", []):
        for clip in layer.get("clips", []):
            block = blocks.get(clip.get("id"))
            if not block:
                continue
            first, last = round(float(block["start"]) * fps), round((float(block["start"]) + float(block["duration"])) * fps)
            out = folder / f"razgon-{stamp}-{first}-{last}-{a}-{b}-{width}.mp4"
            if not out.is_file():
                part = out.with_name(out.stem + ".part.mp4")
                command = ["nice", "-n", "10", "node", "render.mjs", "--project", str(razgon), "--from", repr(a / fps), "--to", repr(b / fps),
                           "--within", f"{first / fps!r},{last / fps!r}", "--scale", f"{width / int(manifest.get('width', 1920)):.4f}",
                           "--format", "jpeg", "--out", str(part)] + (["--gl", "gpu"] if sys.platform == "darwin" else [])
                subprocess.run(command, cwd=str(razgon.parents[1]), check=True, capture_output=True, timeout=300)
                part.replace(out)
            clip.update(type="video", source=str(out), content_type=None, start=a / fps, duration=(b - a) / fps, trim_start=0.0,
                        opacity=1, volume=0.0, keyframes=[])


JOIN_ACTIONS = {"set_join_transition", "undo", "redo", "delete_group", "move_group"}
SOUND_OPS = {"transition_sounds", "typing_sounds", "drawing_sounds", "appear_sounds", "soundtrack"}
SOUND_SYNC: dict = {}   # project → a timer of the pending sync
SOUND_SYNC_LOCK = threading.Lock()


def changes_joins(body: dict) -> bool:
    """Whether an action (or a batch) adds, changes or removes a transition, or moves the frames it stands between."""
    if body.get("type") in JOIN_ACTIONS:
        return True
    if body.get("type") == "batch":
        return any(isinstance(a, dict) and a.get("type") in JOIN_ACTIONS for a in (body.get("payload") or {}).get("actions") or [])
    return False


def sync_transition_sounds(pid: str, delay: float = 2.0) -> None:
    """The transitions' sounds follow the transitions by themselves: a moment after a transition is added, changed or
    removed, every transition of the film has its sound and a cut none (user, 25 November 2026: «озвучку переходів
    ставити там, де дійсно переход… щоб автоматично ставилось»). Several edits in a row make one pass."""
    def run():
        with SOUND_SYNC_LOCK:
            SOUND_SYNC.pop(pid, None)
        try:
            if active_export(pid):
                return
            montage_ops.run(pid, [{"op": "transition_sounds"}, {"op": "typing_sounds"}, {"op": "drawing_sounds"}])
        except Exception as error:   # a sound pass never breaks the edit it follows
            try:
                print(f"Transition sounds {pid}: {error}", file=sys.stderr, flush=True)
            except OSError:
                pass
    with SOUND_SYNC_LOCK:
        previous = SOUND_SYNC.pop(pid, None)
        if previous:
            previous.cancel()
        timer = threading.Timer(delay, run)
        timer.daemon = True
        SOUND_SYNC[pid] = timer
        timer.start()


CAPCUT_WARMING: set[str] = set()
CAPCUT_DEMAND = 0   # previews the editor is waiting for right now


CAPCUT_WARMED: dict = {}   # project → the revision whose seams are all drawn
# the warm-up filled the Mac's disk (25 November 2026): it waits while less than this is free
WARM_MIN_FREE = 6 * 1024 ** 3
EXPORT_MIN_FREE = 4 * 1024 ** 3   # the least free space an export starts with


def warm_capcut(pid: str, project: dict | None = None) -> None:
    """Every CapCut transition of an episode drawn ahead in the background, one at a time and at the lowest priority,
    once the editor has asked for one: a seam the author jumps to played a plain dissolve while its picture was drawn,
    and its sound already glitched (user, 25 November 2026: «звук… гліч. Хоча переход просто прозорість»). Drawn ones come
    from the cache; an export or a change of the project stops the pass and the next request starts it again."""
    if project is not None and CAPCUT_WARMED.get(pid) == project.get("revision"):
        return
    try:   # drawing ahead takes space; with a little left the editor draws a seam only when it is played
        if shutil.disk_usage(store.DATA_ROOT).free < WARM_MIN_FREE:
            return
    except OSError:
        return
    if project is not None and not any(j.get("type") in joins.CAPCUT for j in project.get("join_transitions", [])):
        return
    with CAPCUT_LOCK:
        if pid in CAPCUT_WARMING:
            return
        CAPCUT_WARMING.add(pid)

    def run():
        try:
            project = store.load_project(pid)
            revision = project.get("revision")
            todo = [j for j in sorted(project.get("join_transitions", []), key=lambda j: j["seam"]) if j.get("type") in joins.CAPCUT]
            stopped = threading.Event()

            def worker():
                while todo and not stopped.is_set():
                    if UPDATE_RESTARTING or active_export(pid) or store.load_project(pid).get("revision") != revision \
                            or shutil.disk_usage(store.DATA_ROOT).free < WARM_MIN_FREE:
                        stopped.set()
                        return
                    while CAPCUT_DEMAND:   # the editor's own request draws first
                        time.sleep(.2)
                    try:
                        join = todo.pop(0)
                    except IndexError:
                        return
                    try:
                        capcut_transition_preview(project, join["id"])
                    except Exception as error:   # noqa: BLE001 - one seam failing never stops the others
                        print(f"CapCut warm-up {pid} {join['id']}: {error}", file=sys.stderr, flush=True)

            workers = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
            for thread in workers:
                thread.start()
            for thread in workers:
                thread.join()
            if not stopped.is_set():
                CAPCUT_WARMED[pid] = revision
        finally:
            with CAPCUT_LOCK:
                CAPCUT_WARMING.discard(pid)

    threading.Thread(target=run, name=f"capcut-warm-{pid}", daemon=True).start()


def capcut_transition_preview(project: dict, join_id: str) -> dict:
    """The CapCut transition of one seam drawn small by the export's own code, for the editor's preview. One seam is
    drawn by one caller at a time; a second asking for it waits and takes the drawn file."""
    with CAPCUT_JOIN_LOCKS.setdefault(join_id, threading.Lock()):
        return _capcut_transition_preview(project, join_id)


_PREVIEW_MANIFESTS: dict = {}
_PREVIEW_MANIFEST_LOCK = threading.Lock()


def preview_manifest(project: dict) -> dict:
    """The engine's manifest of a project, built once per version of it for the transition previews: it took 0.3–1 s
    of the server's own time for every one of 106 seams, and the timeline, pictures and sounds of the open episode waited
    behind it (user, 25 November 2026: «таймлайн… дуже сильно висне»). A fresh copy each time: a Razgon side changes it."""
    key = (project.get("revision"), project.get("branding_version"), project.get("updated_at"))
    with _PREVIEW_MANIFEST_LOCK:
        hit = _PREVIEW_MANIFESTS.get(project["id"])
    if hit and hit[0] == key:
        return json.loads(hit[1])
    text = json.dumps(normalize_for_engine(project), ensure_ascii=False)
    with _PREVIEW_MANIFEST_LOCK:
        _PREVIEW_MANIFESTS[project["id"]] = (key, text)
    return json.loads(text)


def _capcut_transition_preview(project: dict, join_id: str) -> dict:
    join = next((j for j in project.get("join_transitions", []) if j.get("id") == join_id), None)
    if not join or join.get("type") not in joins.CAPCUT:
        raise store.StudioError("Перехід CapCut на цьому стику не знайдено", 404)
    manifest = preview_manifest(project)
    width = PREVIEW_WIDTH
    height = max(2, round(width * int(manifest.get("height", 1080)) / int(manifest.get("width", 1920)) / 2) * 2)
    if capcut_touches_code(project, join):
        # A Razgon frame is code until «Експорт MP4» renders it: the seam's Razgon sides are drawn here for the
        # transition's own time only, small, each kept to its frame and alive past its edge (renderFrame within), so the
        # preview shows the real CapCut transition (user, 25 November 2026: «бачу лише… прозорість… не бачу самого
        # переходу»); with the empty backing alone it showed a dark gradient (Antropov's seam 1→2)
        try:
            razgon_windows(project, join, manifest, width)
        except (store.StudioError, OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
            print(f"CapCut preview: Razgon side not drawn: {error}", file=sys.stderr, flush=True)
            capcut_mark_ready(project["id"], join)
            return {"live": True, "seam": join["seam"], "duration": join["duration"], "type": join["type"]}
    folder = store.cache_dir(project) / "capcut"
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / f"preview-{join_id}.json"
    with CAPCUT_SLOTS:
        store.atomic_json(manifest_path, manifest)
        try:
            output = capcut_run(["--manifest", str(manifest_path), "--clip", "capcut-" + join_id, "--width", str(width), "--height", str(height)])
        finally:
            manifest_path.unlink(missing_ok=True)
    url = f"/api/capcut/media/{output.name}"
    capcut_mark_ready(project["id"], join, url, project)
    return {"url": url, "seam": join["seam"], "duration": join["duration"], "type": join["type"]}


CAPCUT_READY: dict = {}   # {project id: {join id: (type, duration, seam)}}: the CapCut transitions drawn for the preview
CAPCUT_READY_LOCK = threading.Lock()   # its own: CAPCUT_LOCK is held while an effect's preview is drawn
CAPCUT_URLS: dict = {}    # {project id: {join id: (sides, url)}}: the drawn film of a seam and the two frames it was drawn from


def capcut_sides(project: dict, join: dict) -> str:
    """The clips of the two frames at a seam as they are now (time, trim, source, place and motion): a preview drawn
    from other pictures is not handed out as ready."""
    clips = {c["id"]: c for t in project.get("tracks", []) for c in t.get("clips", [])}
    groups = {g["id"]: g for g in project.get("scene_groups", [])}
    sides = []
    for ref in (join.get("from_ref"), join.get("to_ref")):
        group = groups.get(str(ref or "").split(":")[-1]) or {}
        sides.append([[c.get(k) for k in ("id", "start", "duration", "trim_start", "asset_id", "x", "y", "scale", "opacity", "keyframes", "code")]
                      for c in (clips.get(i) for i in group.get("clip_ids", [])) if c])
    return hashlib.sha256(json.dumps(sides, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _capcut_ready_file(pid: str) -> Path:
    return store.project_dir(pid) / "capcut" / "ready.json"


def _capcut_load(pid: str) -> None:
    """The drawn seams of an episode as the last server left them: after a restart the editor played them only once the
    warm-up had confirmed each one again, a minute later (26 November 2026). A film whose file is gone is not taken."""
    if pid in CAPCUT_READY:
        return
    CAPCUT_READY[pid], CAPCUT_URLS[pid] = {}, {}
    try:
        saved = store.read_json(_capcut_ready_file(pid), {}) or {}
    except (OSError, ValueError, store.StudioError):
        return
    for jid, item in saved.items():
        try:
            name = str(item["url"]).rsplit("/", 1)[-1]
            if not (store.DATA_ROOT / "capcut-cache" / name).is_file():
                continue
            CAPCUT_READY[pid][jid] = tuple(item["key"])
            CAPCUT_URLS[pid][jid] = (item["sides"], item["url"])
        except (KeyError, TypeError, ValueError):
            continue


def capcut_mark_ready(pid: str, join: dict, url: str | None = None, project: dict | None = None) -> None:
    with CAPCUT_READY_LOCK:
        _capcut_load(pid)
        key = (join.get("type"), round(float(join.get("duration", 0)), 3), round(float(join.get("seam", 0)), 3))
        CAPCUT_READY.setdefault(pid, {})[join["id"]] = key
        if url and project is not None:
            CAPCUT_URLS.setdefault(pid, {})[join["id"]] = (capcut_sides(project, join), url)
            saved = {jid: {"key": list(CAPCUT_READY[pid][jid]), "sides": sides, "url": film}
                     for jid, (sides, film) in CAPCUT_URLS[pid].items() if jid in CAPCUT_READY[pid]}
            try:
                _capcut_ready_file(pid).parent.mkdir(parents=True, exist_ok=True)
                store.atomic_json(_capcut_ready_file(pid), saved)
            except OSError:
                pass


def capcut_ready(project: dict) -> list:
    """The ids of the project's CapCut transitions whose preview is drawn as they are now (type, length and seam): the
    timeline marks the others white until they are (user, 25 November 2026: «переходи, які сині… зроби їх білі, якщо вони
    не показуються ще такими, як вони мають бути»)."""
    with CAPCUT_READY_LOCK:
        _capcut_load(project["id"])
    drawn = CAPCUT_READY.get(project["id"], {})
    return [j["id"] for j in project.get("join_transitions", []) if j.get("type") in joins.CAPCUT
            and drawn.get(j["id"]) == (j.get("type"), round(float(j.get("duration", 0)), 3), round(float(j.get("seam", 0)), 3))]


def capcut_ready_urls(project: dict, ready: list) -> dict:
    """{join id: url} of the drawn seams whose two frames are unchanged since: the editor plays them at once, with no
    request a seam (user, 26 November 2026: «переходи в прев'ю, щоб моментально я міг їх просто подивитися»)."""
    films = CAPCUT_URLS.get(project["id"], {})
    by_id = {j["id"]: j for j in project.get("join_transitions", [])}
    answer = {}
    for jid in ready:
        hit = films.get(jid)
        if hit and jid in by_id and hit[0] == capcut_sides(project, by_id[jid]):
            answer[jid] = hit[1]
    return answer


_DERIVED = {}
_SUMMARIES = {}
_DERIVED_LOCK = threading.Lock()


def _derived_key(project: dict) -> tuple:
    """Everything plan_readiness and voice_gains read: the project's timing fields and audio clips, the plan file's
    version and the version of every audio file on the timeline."""
    try:
        plan = store.project_plan_file(project)
        plan_key = store.plan_file_key(plan) if plan else None
    except (store.StudioError, OSError):
        plan_key = "unreadable"
    try:
        source_path = store.project_dir(project["id"]) / "source-timing.json"
        source_key = store.plan_file_key(source_path) if source_path.is_file() else None
    except (store.StudioError, OSError, KeyError):
        source_key = None
    paths = {asset.get("id"): asset.get("path") for asset in project.get("assets", [])}
    audio = []
    for track in project.get("tracks", []):
        for clip in track.get("clips", []):
            if clip.get("kind") != "audio":
                continue
            path = paths.get(clip.get("asset_id"))
            try:
                stat = os.stat(path) if path else None
            except OSError:
                stat = None
            audio.append((clip.get("asset_id"), path, stat and (stat.st_size, stat.st_mtime_ns), clip.get("start"), clip.get("duration"),
                          clip.get("trim_start"), clip.get("volume"), bool(track.get("muted"))))
    return (project.get("revision"), project.get('branding_version'), project.get("duration"), project.get("fps"), project.get("episode_path"), plan_key, source_key, tuple(audio), store.project_plan_mode(project))


def razgon_kit_at_start() -> None:
    """The Razgon 2D studio in the YOUTUBE folder follows the kit this Studio ships (tools/razgon_sync.py): an update of
    the Studio from GitHub reaches the animation tools too, while hand-changed files, projects and the prop library stay."""
    try:
        if str(APP_ROOT / "tools") not in sys.path:
            # appended, never first: tools/music_library.py, a CLI wrapper, would shadow backend/music_library.py and the
            # film's music fails with «no attribute selected» (27 November 2026)
            sys.path.append(str(APP_ROOT / "tools"))
        import razgon_sync
        razgon_sync.at_start()
    except Exception as error:   # never let it stop the Studio
        sys.stderr.write(f"[video-studio] Razgon kit sync skipped: {error}\n")


def derived_state(project: dict, tokens: bool = False):
    """(production readiness, voice gains) of a project, computed once per version of what they read: every project
    response carries both, and measuring them again took most of a request on a long episode. With tokens=True also the
    voice files' tokens (audio_level.voice_state), decided with the gains."""
    key = _derived_key(project)
    with _DERIVED_LOCK:
        hit = _DERIVED.get(project["id"])
    if not (hit and hit[0] == key):
        readiness = store.plan_readiness(project)
        gains, files = audio_level.voice_state(project)
        hit = (key, readiness, gains, files)
        with _DERIVED_LOCK:
            _DERIVED[project["id"]] = hit
    result = (copy.deepcopy(hit[1]), dict(hit[2]))
    return result + (dict(hit[3]),) if tokens else result


_STATIC_VERSIONS = {}


def versioned_index(body: bytes) -> bytes:
    """index.html with each local script and stylesheet stamped by its own content (?v=<hash>): a changed file reaches
    the browser on the next reload without anyone bumping its version by hand."""
    def stamp(match):
        target = (FRONTEND_ROOT / match.group(2)).resolve()
        try:
            stat = target.stat()
        except OSError:
            return match.group(0)
        key = (str(target), stat.st_size, stat.st_mtime_ns)
        if _STATIC_VERSIONS.get(str(target), (None,))[0] != key:
            _STATIC_VERSIONS[str(target)] = (key, hashlib.sha256(target.read_bytes()).hexdigest()[:12])
        return f'{match.group(1)}="/{match.group(2)}?v={_STATIC_VERSIONS[str(target)][1]}"'
    return re.sub(r'(src|href)="/([A-Za-z0-9_./-]+\.(?:js|css|svg))\?v=[^"]*"', stamp, body.decode("utf-8")).encode("utf-8")


SLOW_REQUEST = 2.0


class Handler(BaseHTTPRequestHandler):
    server_version = "MultiBotVideoStudio/0.1"

    def log_message(self, fmt, *args):
        # successful reads are the UI's polling (studio/status, export/active…): 99% of a log that grew to 89 MB; errors
        # and every change stay (17 November 2026 audit)
        if self.command == "GET" and len(args) >= 2 and str(args[1]).startswith(("2", "3")):
            return
        try:
            sys.stderr.write("[video-studio] " + fmt % args + "\n")
        except OSError:   # a full disk must not break the request whose line it is (deleting a project failed so)
            pass

    def json_response(self, value, status=200):
        if isinstance(value, dict) and isinstance(value.get("project"), dict):
            project = dict(value["project"])
            if (project.get("production_request") or {}).get("status") in {"requested", "in_progress"}:
                # no «Створюємо кадри» for a run that no longer exists
                # the project just read is the one settle would read again (0.25 s on a long episode)
                request = production.settle(project["id"], project)
                if request and request.get("status") != project["production_request"].get("status"):
                    project = dict(store.load_project(project["id"]))
            project.update(store.history_state(project["id"]))
            # the preview plays the voice at the export's level (audio_gain)
            project["production"], project["audio_gain"], project["voice_files"] = derived_state(project, tokens=True)
            project["plan_mode"] = project["production"].get("plan_mode", store.project_plan_mode(project))
            project["plan_mode_editable"] = True
            project["video_bitrates"] = store.video_bitrates(int(project.get("width") or 1920), int(project.get("height") or 1080),
                                                             int(project.get("fps") or 25))
            value = {**value, "project": project}
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def text_response(self, text, status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise store.StudioError("Очікується JSON-запит", 415)
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 8 * 1024 * 1024:
            raise store.StudioError("Завеликий або порожній запит")
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise store.StudioError("Запит завантажено не повністю")
            def invalid_constant(value):
                raise ValueError('Non-finite JSON number')
            def finite_float(value):
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError('Non-finite JSON number')
                return number
            body = json.loads(raw, parse_constant=invalid_constant, parse_float=finite_float)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise store.StudioError("Невірний JSON") from None
        if not isinstance(body, dict):
            raise store.StudioError("Очікується JSON-об’єкт")
        return body

    def check_request_origin(self):
        host = self.headers.get("Host", "")
        allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in allowed_hosts:
            raise store.StudioError("Невірна адреса запиту", 403)
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + item for item in allowed_hosts}:
            raise store.StudioError("Запит з іншої сторінки заблоковано", 403)

    def handle_request(self, method):
        try:
            self.check_request_origin()
            parsed = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parsed.path)
            query = urllib.parse.parse_qs(parsed.query)
            if method == "GET":
                return self.route_get(path, query)
            global IN_FLIGHT, LAST_CHANGE
            # drawing a preview (a CapCut seam, a still, a motion check) changes nothing in a project: it neither counts
            # as a change in flight nor holds back a restart (the editor asked for seams for minutes, 25 November 2026)
            if method == "POST" and re.fullmatch(r"/api/projects/[0-9a-f]{24}/(capcut-preview|still|motion-check)", path):
                return self.route_mutation(method, path, self.read_json_body() or {})
            with UPDATE_MUTEX:
                if UPDATE_RESTARTING:
                    raise store.StudioError('Студія перезапускається після оновлення.', 503)
                IN_FLIGHT += 1
                LAST_CHANGE = time.time()
            try:
                project_match = re.match(r'^/api/projects/([0-9a-f]{24})(?:/|$)', path)
                # the live preview only starts a viewer of the Razgon code and changes nothing in the project
                # a still only reads the project, as the live preview does
                # the «Мови» tab works beside the montage: a translated voice and thumbnail change nothing in it
                # Original covers also live separately from the frozen export manifest and media.
                thumbnail_only = method == 'POST' and re.fullmatch(r'/api/projects/[0-9a-f]{24}/thumbnail(?:/choose|/logo)?', path)   # a logo laid on a cover too (17 November 2026)
                notice_only = method == 'POST' and path.endswith('/completion/seen')
                if project_match and not (thumbnail_only or notice_only) and not path.endswith(('/export', '/razgon-live', '/still')) and '/languages' not in path and active_export(project_match.group(1)):
                    raise store.StudioError('Проєкт заблоковано під час експорту. Дочекайтеся завершення або скасуйте експорт.', 423)
                if project_match and not notice_only and not path.endswith(('/agent/cancel', '/still')) and agent_runtime.active(project_match.group(1)):
                    raise store.StudioError('Дочекайтеся завершення агента або зупиніть його перед зміною проєкту.', 423)
                transfer = re.fullmatch(r'/api/channels/([0-9a-f]{16})/settings-import', path)
                if method == 'POST' and transfer:
                    if self.headers.get('Content-Type', '').split(';')[0] not in {'application/zip', 'application/octet-stream'}:
                        raise store.StudioError('Оберіть ZIP налаштувань', 415)
                    try: size = int(self.headers.get('Content-Length', '0'))
                    except ValueError: raise store.StudioError('Невірний розмір архіву') from None
                    if not 0 < size <= channel_transfer.MAX_BYTES:
                        raise store.StudioError('Оберіть ZIP до 128 МБ', 413)
                    raw = self.rfile.read(size)
                    if len(raw) != size: raise store.StudioError('Архів завантажено не повністю')
                    return self.json_response(channel_transfer.import_bundle(transfer.group(1), raw, channel_transfer_idle))
                shared = re.fullmatch(r"/api/channels/([0-9a-f]{16})/voices/([a-z]{2})", path)
                voice_reference = re.fullmatch(r'/api/channels/([0-9a-f]{16})/voice-lab/reference', path)
                if method == 'POST' and voice_reference:
                    return self.json_response(channel_voice_lab.upload(voice_reference.group(1), self.rfile,
                        int(self.headers.get('Content-Length', '0')), urllib.parse.unquote(self.headers.get('X-File-Name', 'Приклад голосу'))))
                if method == "POST" and shared:
                    size = int(self.headers.get("Content-Length", "0"))
                    return self.json_response(languages.save_channel_voice(shared.group(1), shared.group(2), self.rfile, size,
                                                                           urllib.parse.unquote(self.headers.get("X-Said-Text", "")),
                                                                           urllib.parse.unquote(self.headers.get("X-File-Name", ""))))
                own = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/([a-z]{2})/own-voice", path)
                if method == "POST" and own:
                    size = int(self.headers.get("Content-Length", "0"))
                    said = urllib.parse.unquote(self.headers.get("X-Said-Text", ""))
                    return self.json_response(languages.save_own_voice(own.group(1), own.group(2), self.rfile, size, said,
                                                                     urllib.parse.unquote(self.headers.get("X-File-Name", ""))))
                upload = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/upload", path)
                if method == "POST" and upload:
                    return self.route_upload(upload.group(1))
                body = self.read_json_body() if method in {"POST", "PATCH"} else None
                return self.route_mutation(method, path, body or {})
            finally:
                with UPDATE_MUTEX:
                    IN_FLIGHT -= 1
                    IN_FLIGHT_DONE.notify_all()
        except store.StudioError as exc:
            return self.json_response({"error": str(exc)}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            # A video element drops a range request it no longer needs while seeking; there is nobody left to answer.
            self.close_connection = True
            return None
        except (KeyError, TypeError, ValueError) as exc:
            # mostly a request that misses a field, but a bug looks the same from here: keep its trace in the server log
            sys.stderr.write(f"[video-studio] {self.command} {self.path}: {type(exc).__name__}: {exc}\n")
            traceback.print_exc()
            return self.json_response({"error": "Невірні параметри запиту"}, 400)
        except OSError as exc:
            if exc.errno == 28:   # ENOSPC: say what is wrong instead of «Внутрішня помилка» (17 November 2026 audit)
                return self.json_response({"error": "На диску Mac закінчилось місце. Звільніть місце (кнопка «Звільнити місце» "
                                                    "в налаштуваннях студії) і спробуйте ще раз."}, 507)
            traceback.print_exc()
            return self.json_response({"error": "Внутрішня помилка студії"}, 500)
        except Exception:
            traceback.print_exc()
            return self.json_response({"error": "Внутрішня помилка студії"}, 500)

    def timed_request(self, method):
        # a request slower than SLOW_REQUEST seconds is written to the log with its time, so a page that hangs can be
        # traced to the call that held it (user, 25 November 2026: «Андромеда відкривалась… біля хвилини»)
        started = time.monotonic()
        try:
            self.handle_request(method)
        finally:
            spent = time.monotonic() - started
            if spent > SLOW_REQUEST:
                try:
                    sys.stderr.write(f"[video-studio] slow {method} {self.path.split('?', 1)[0]} {spent:.1f} s\n")
                except OSError:
                    pass

    def do_GET(self):
        self.timed_request("GET")

    def do_POST(self):
        self.timed_request("POST")

    def do_PATCH(self):
        self.timed_request("PATCH")

    def do_DELETE(self):
        self.timed_request("DELETE")

    def route_upload(self, pid):
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
            raise store.StudioError("Очікується медіафайл", 415)
        size = int(self.headers.get("Content-Length", "0"))
        filename = urllib.parse.unquote(self.headers.get("X-File-Name", ""))
        project = store.load_project(pid)
        asset = store.import_asset_stream(project, self.rfile, size, filename)
        return self.json_response({"asset": asset}, 201)

    def route_get(self, path, query):
        provider = re.fullmatch(r'/api/projects/([0-9a-f]{24})/image-provider', path)
        if provider:
            import openrouter_images
            return self.json_response({**openrouter_images.setting(provider.group(1)), 'spent': openrouter_images.spent(provider.group(1))})
        if path == '/api/title-translation':
            return self.json_response(title_translation.options())
        picture = re.fullmatch(r"/api/trending-videos/icon/([A-Za-z0-9_-]{6,64})", path)
        if picture:
            found = trending_videos.icon(picture.group(1))
            if not found:
                raise store.StudioError("Немає картинки", 404)
            data, kind = found
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")   # the link changes with the picture
            self.end_headers()
            self.wfile.write(data)
            return None
        if path == "/api/trending-videos":
            return self.json_response(trending_videos.view())
        editing = re.fullmatch(r'/api/projects/([0-9a-f]{24})/script-editing(?:/(status|[0-9a-f]{32}))?', path)
        if editing:
            return self.json_response(script_editing.availability(editing.group(1)) if editing.group(2)=='status' else script_editing.view(*editing.groups()))

        draft = re.fullmatch(r'/api/projects/([0-9a-f]{24})/script-draft(?:/(history|baseline|stale|[0-9a-f]{32}))?', path)
        if draft:
            pid, kind = draft.groups()
            return self.json_response(script_drafts.current(pid) if kind is None else script_drafts.history(pid) if kind == 'history' else script_drafts.version(pid, kind))
        performance = re.fullmatch(r'/api/projects/([0-9a-f]{24})/performance', path)
        if performance:
            return self.json_response(job_timing.overview(performance.group(1)))
        # the four thumbnails «Адаптувати під мій стиль» copies, shown small beside the box
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/style-thumbnails", path)
        if match:
            store.get_channel_folder(match.group(1))
            return self.json_response({"thumbnails": [f"/api/projects/{pid}/cover" for pid in thumbnail_gen.style_sources(match.group(1))]})
        if path == "/api/channels" or path.startswith("/api/channels/"):
            return channel_api.get(self, path, query, ensure_idle=channel_transfer_idle)
        reverb = re.fullmatch(r'/api/audio-effects/([a-z-]+)-v[1234]\.wav', path)
        if reverb:
            import narration_effects
            return self.serve_media(narration_effects.microphone_noise(reverb.group(1)[6:]) if reverb.group(1).startswith('noise-') else narration_effects.microphone_noise() if reverb.group(1)=='microphone' else narration_effects.impulse(reverb.group(1)), cache=True)
        dry_narration = re.fullmatch(r'/api/projects/([0-9a-f]{24})/narration/original', path)
        if dry_narration:
            speed = (query.get('speed') or [None])[0]
            return self.serve_media(project_narration.tempo_preview(dry_narration.group(1), speed) if speed is not None else project_narration.original_audio(dry_narration.group(1)))
        if path == '/api/space':
            return self.json_response(space.all_usage(cleanup_blocked))
        if path == '/api/limits':
            import ai_limits   # Claude Code's and Codex's 5-hour limits, from their own local logs
            import spending   # and what the paid services cost today, this week and this month
            return self.json_response({**ai_limits.cached(store.DATA_ROOT), 'spending': spending.summary()})
        revision=re.fullmatch(r'/api/projects/([0-9a-f]{24})/narration/revision',path)
        if revision:
            return self.json_response(narration_revision.snapshot(revision.group(1)))
        narration = re.fullmatch(r'/api/projects/([0-9a-f]{24})/narration', path)
        if narration:
            listed(narration.group(1))
            return self.json_response(project_narration.snapshot(narration.group(1)))
        edit_match=re.fullmatch(r'/api/projects/([0-9a-f]{24})/production-edits',path)
        if edit_match:
            import production_edits
            return self.json_response(production_edits.overview(edit_match.group(1)))
        if path == '/api/update':
            return self.json_response({**UPDATE_MANAGER.public_state(), 'boot': UPDATE_BOOT, 'restarting': UPDATE_RESTARTING, 'queued': UPDATE_QUEUED})
        if path == '/api/studio/restart':
            return self.json_response(local_restart_status())
        if path in {"/api/health", "/health"}:
            return self.json_response({"service": "multibot-video-studio", "status": "ok", "api_version": 2, "project_schema": 2, "layer_mode": "item", "plan_workflow": "audio_required", "manual_project_openings": True, "topic_premise_novelty": True, "trending_videos": True, "trending_use_idea": True, "export_queue": True, "create_video": True})
        draft_match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/episode-draft", path)
        if draft_match:
            import episode_ideas
            draft = episode_ideas.public(episode_ideas.read_project(draft_match.group(1)))
            stopped = (episode_pause.paused(draft_match.group(1)) or {}).get("stopped") or {}
            if "writing" in stopped and draft.get("status") not in {"queued", "running", "cancelling"}:
                draft["writing_paused"] = episode_pause.WRITING.get(stopped["writing"].get("stage"), "Сценарій на паузі")
            return self.json_response(draft)
        if path == "/api/sound-effects":
            import sound_settings
            return self.json_response({"categories": sound_settings.catalog(), "transitions": sound_settings.transition_catalog(), "music_styles": sound_settings.music_catalog(), "library": __import__("sfx_library").catalog(), "library_selection": True, "music_library": __import__("music_library").public()})
        library_match = re.fullmatch(r"/api/sfx-library/([0-9]+)\.wav", path)
        if library_match:
            import sfx_library
            row = next((r for r in sfx_library.catalog() if r['mixkit_id'] == library_match.group(1)), None)
            if row is None:
                raise store.StudioError('Звук не знайдено', 404)
            return self.serve_media(sfx_library.leveled(row), cache=True)
        sound_match = re.fullmatch(r"/api/sound-effects/([a-z_]+)\.wav", path)
        if sound_match:
            import sound_settings
            return self.serve_media(sound_settings.preview(sound_match.group(1)), cache=True)
        music_track = re.fullmatch(r"/api/music-library/([A-Za-z0-9_-]{6,40})\.mp3", path)
        if music_track:
            import music_library
            return self.serve_media(music_library.track_path(music_track.group(1)), cache=True)
        music_style = re.fullmatch(r"/api/music-styles/([a-z]+)\.mp3", path)
        if music_style:
            import sound_settings
            return self.serve_media(sound_settings.music_preview(music_style.group(1)), cache=True)
        transition_sound = re.fullmatch(r"/api/transition-sounds/([a-z]+)\.wav", path)
        if transition_sound:
            import sound_settings
            return self.serve_media(sound_settings.preview(transition_sound.group(1), transition=True), cache=True)
        if path == "/api/extension":
            import extension
            return self.json_response(extension.state())
        if path == "/api/claude-login":
            # Claude Code's sign-in on this Mac, for the settings' «Claude Code» section (backend/claude_login.py)
            import claude_login
            return self.json_response(claude_login.view())
        if path == "/api/settings":
            return self.json_response({"settings": store.global_settings()})
        if path == "/api/service-keys":
            return self.json_response({"providers": credentials.providers()})
        if path == '/api/elevenlabs/balance':
            return self.json_response(languages.eleven_api.balance(refresh=(query.get('refresh') or [''])[0]=='1'))
        if path == "/api/projects":
            completion_notices.index_exports(JOBS_ROOT)
            projects = store.list_projects((query.get("channel") or [None])[0])
            auto_settings = {}
            for item in projects:
                item["freeable"] = space.freeable(item["id"])   # «Звільнити місце» only when there is something to free
                receipts = store.read_json(completion_notices.path(item['id']), {}) or {}
                item['last_export_at'] = (receipts.get('export') or {}).get('at', 0)
                project = store.listed_project(store.project_dir(item['id']) / 'project.json')
                item['completion_notice'] = completion_notices.notice(project, receipts)
                item['ready_stage'] = completion_notices.ready_stage(project, receipts, item)
                item['published'] = published.check(item)   # the blue Finder tag, kept even without the folder
                item['publishing'] = published.publishing(item)   # tools/youtube_publish.py prepare is at work
                if item['publishing'] == 'stopped':
                    item['publishing_note'] = published.stopped_note(item['id'])
                # the step the channel's automation is about to do: the card shows it coming, not a button to press
                try:
                    if item.get('channel_id') not in auto_settings:
                        auto_settings[item.get('channel_id')] = store.read_channel_settings(store.get_channel_folder(item['channel_id']), {}) or {}
                    item['auto_due'] = auto_pipeline.listed(item, project, auto_settings[item.get('channel_id')])
                except (store.StudioError, OSError, KeyError, ValueError):
                    item['auto_due'] = None
                item['episode_paused'] = episode_pause.resumable(item['id'])
                item['episode_pause_label'] = episode_pause.label(item['id']) if item['episode_paused'] else None
                if (item.get('production_request') or {}).get('status') in {'requested', 'in_progress'} and item['id'] not in production.ACTIVE:
                    # a card must not read «Створюємо кадри» for a run no agent works on (it was put right only when
                    # the project was opened; 16 November 2026 stability pass)
                    try:
                        settled = production.settle(item['id'])
                        if settled is not None:
                            item['production_request'] = {**item['production_request'], **{k: settled.get(k) for k in ('status', 'paused', 'paused_by', 'error', 'limit')}}
                    except (store.StudioError, OSError, ValueError):
                        pass
            return self.json_response({"projects": projects})
        if path == "/api/exports/active":
            with JOBS_LOCK:
                jobs=[dict(entry['job']) for entry in ACTIVE_EXPORTS.values()
                      if entry['job'].get('status') in {'queued','running','cancelling'}]
            return self.json_response({'jobs':jobs})
        if path == "/api/studio/status":
            with JOBS_LOCK:
                jobs = [dict(entry['job']) for entry in ACTIVE_EXPORTS.values()]
            result = channel_completion_status(studio_work_status(jobs), jobs)
            result['busy'] += ['озвучення: тест голосу каналу' for _ in channel_voice_lab.ACTIVE.copy()]
            return self.json_response(result)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/export/active", path)
        if match:
            return self.json_response({'job': active_export(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/branding", path)
        if match:
            project=store.load_project(match.group(1))
            if (query.get('version') or [''])[0]==project.get('branding_version','off'):
                return self.json_response({'unchanged':True})
            return self.json_response({'project':project})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/exports", path)
        if match:
            listed(match.group(1))
            return self.json_response({"active": active_export(match.group(1)), "jobs": recent_exports(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/summary", path)
        if match:
            project = store.load_project(match.group(1))
            key = _derived_key(project)
            with _DERIVED_LOCK:
                hit = _SUMMARIES.get(project["id"])
            if hit and hit[0] == key:
                summary = copy.deepcopy(hit[1])
            else:
                readiness, gains = derived_state(project)
                summary = agent_view.project_summary({**project, "audio_gain": gains}, readiness)
                with _DERIVED_LOCK:
                    _SUMMARIES[project["id"]] = (key, copy.deepcopy(summary))
            wanted = (query.get("frames") or [""])[0]
            if wanted:
                low, _, high = wanted.partition("-")
                low, high = float(low), float(high or low)
                summary["frames"] = [row for row in summary["frames"] if isinstance(row["n"], int) and low <= row["n"] <= high]
            if (query.get("issues") or [""])[0] in {"1", "true"}:
                summary["frames"] = [row for row in summary["frames"] if row["issues"]]
            if (query.get("format") or [""])[0] == "text":
                lines = summary["head"] + [row["line"] + "".join("\n       ! " + issue for issue in row["issues"]) for row in summary["frames"]]
                lines += ["Проблеми: " + ("немає" if not summary["issues"] else str(len(summary["issues"])))] + ["  " + issue for issue in summary["issues"] if not issue.startswith("кадр ")]
                return self.text_response("\n".join(lines) + "\n")
            return self.json_response(summary)
        match = re.fullmatch(r"/api/capcut/effects/(capcut_e\d{2})/preview\.webm", path)
        if match:
            if match.group(1) not in store.capcut_effects():
                raise store.StudioError("Ефект не знайдено", 404)
            # a drawn effect is served at once: behind the lock it waited for transitions being drawn (11 s each) and
            # the effects showed late on the frames (user, 25 November 2026: «довго грузяться… ефекти не видно»)
            target = EFFECT_PREVIEWS.get(match.group(1))
            if target is None or not target.is_file():
                with CAPCUT_LOCK:
                    target = capcut_run(["--effect", match.group(1)], timeout=300)
                EFFECT_PREVIEWS[match.group(1)] = target
            return self.serve_media(target)
        match = re.fullmatch(r"/api/capcut/media/(transition-direct-capcut-[0-9a-f]{24}\.mp4)", path)
        if match:
            target = store.DATA_ROOT / "capcut-cache" / match.group(1)
            if not target.is_file():
                raise store.StudioError("Прев'ю переходу не знайдено", 404)
            return self.serve_media(target)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/stills/(still-[0-9a-f]{20}(?:-\d{2})?\.png)", path)
        if match:
            target = store.cache_dir(store.listed_project(store.project_dir(match.group(1)) / "project.json")) / "stills" / match.group(2)
            if not target.is_file():
                raise store.StudioError("Стоп-кадр не знайдено", 404)
            return self.serve_media(target)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/analysis", path)
        if match:
            return self.json_response(analysis_jobs.latest(match.group(1), load_job, compact=(query.get('compact') or [''])[0]=='1'))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/razgon-live", path)
        if match:
            return self.json_response(razgon_live.status(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/agent", path)
        if match:
            project_id = match.group(1)
            conversation = agent_storage.get_conversation(project_id)
            return self.json_response({"messages": conversation["messages"], "costs": agent_storage.cost_summary(conversation["costs"]), "job": agent_runtime.snapshot(project_id), "settings": agent_storage.get_settings(project_id)})
        if path == "/api/pixabay/search":
            q = (query.get("q") or [""])[0].strip()
            kind = (query.get("kind") or ["video"])[0]
            limit = int((query.get("limit") or ["12"])[0])
            return self.json_response({"results": search_pixabay(q, kind, limit)})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})", path)
        if match:
            answer = paused_view(match.group(1))
            warm_capcut(match.group(1), answer)   # the episode is opened: its CapCut seams are drawn ahead
            return self.json_response({"project": answer})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/plan", path)
        if match:
            pid = match.group(1)
            project = store.load_project(pid)
            if store.project_plan_mode(project) == "direct":
                return self.json_response({"plan": None, "source": store.load_project_narration(pid), "settings_match": None})
            plan = store.load_project_plan(pid)
            return self.json_response({"plan": plan, "source": None, "settings_match": store.plan_settings_match(pid, plan)})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets", path)
        if match:
            project = store.load_project(match.group(1))
            return self.json_response({"assets": [asset for asset in store.discover_assets(project) if store.asset_available(project, asset)]})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/([0-9a-f]{20})/waveform", path)
        if match:
            project=store.load_project(match.group(1));asset=store.resolve_asset(project,match.group(2))
            if asset.get('kind') not in {'audio','video'}:raise store.StudioError('Waveform requires audio')
            return self.json_response(waveforms.read_peaks(asset['path'],store.project_dir(project['id'])/'waveforms'))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/thumbnail", path)
        if match:
            if (query.get('compact') or [''])[0]=='1':
                listed(match.group(1))
                return self.json_response({'compact':True,'job':status_views.job(thumbnail_gen.state(match.group(1))),
                                           'thumbnail_jobs':languages.thumbnail_status(match.group(1))})
            return self.json_response({**thumbnail_gen.defaults(match.group(1)), **languages.thumbnail_gallery(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/thumbnails/([^/]+\.png)", path)
        if match:
            return self.serve_thumbnail(thumbnail_gen.version_file(*match.groups()), download=(query.get('download') or [None])[0])
        match = re.fullmatch(r'/api/projects/([0-9a-f]{24})/thumbnail-reference/([0-9a-f]{64}\.jpg)', path)
        if match:
            return self.serve_media(thumbnail_compare.source(*match.groups()), cache=True)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages", path)
        if match:
            return self.json_response(languages.overview(match.group(1), compact=True))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/voices", path)
        if match:
            return self.json_response(languages.voice_options(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/([a-z]{2})/cost", path)
        if match:
            return self.json_response(languages.cost_breakdown(*match.groups()))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/([a-z]{2})/alignment", path)
        if match:
            return self.json_response(languages.alignment_timeline(*match.groups()))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/original", path)
        if match:
            return self.serve_media(languages.original_file(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/original/thumbnail", path)
        if match:
            cover = languages.cover(store.load_project(match.group(1)))
            if not cover:
                raise store.StudioError("Прев'ю ще немає", 404)
            return self.serve_thumbnail(cover, download=(query.get("download") or [None])[0])
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/([a-z]{2})/waveform", path)
        if match:
            pid, code = match.groups()
            voice=(languages.load_state(pid).get('languages',{}).get(code) or {}).get('voice') or {}
            if not languages.voice_matches_text(pid,code,voice):
                raise store.StudioError('Текст змінено. Спершу оновіть озвучку.',409)
            return self.json_response(waveforms.read_peaks(languages.file_path(pid, code, 'voice'), store.project_dir(pid) / 'waveforms'))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/([a-z]{2})/file/(sample-[a-z0-9_.\-]+|voice|thumbnail|own)", path)
        if match:
            if match.group(3)=='voice':
                pid,code=match.groups()[:2]
                voice=(languages.load_state(pid).get('languages',{}).get(code) or {}).get('voice') or {}
                if not languages.voice_matches_text(pid,code,voice):
                    raise store.StudioError('Текст змінено. Попередню озвучку збережено в кеші; спершу оновіть її.',409)
            if match.group(3) == 'voice' and query.get('download'):
                for report in (languages.translation_check(*match.groups()[:2]), languages.voice_language_check(*match.groups()[:2])):
                    if report['state'] != 'ok':
                        raise store.StudioError(languages.language_quality.message(report), 409)
            serve = self.serve_thumbnail if match.group(3) == 'thumbnail' else self.serve_media
            return serve(languages.file_path(*match.groups()), download=(query.get("download") or [None])[0])
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/([a-z]{2})/thumbnails/(v[1-9][0-9]*\.png)",path)
        if match:
            return self.serve_thumbnail(languages.language_thumbnails.version_file(*match.groups()),download=(query.get('download') or [None])[0],cache=True)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/work", path)
        if match:
            project = store.load_project(match.group(1))
            plan = store.load_project_plan(project["id"]) or {}
            request = project.get("production_request") or {"id": "view", "frames": len(plan.get("frames", []))}
            data = production_context.build(project, request)
            if (query.get("format") or [""])[0] == "text":
                return self.text_response(production_context.text(data))
            return self.json_response(data)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/costs", path)
        if match:
            pid = match.group(1)
            listed(pid)
            # Card hover is entirely local; balance refresh retains the conversion basis separately.
            balance = store.read_json(store.DATA_ROOT/'eleven-credit-usd.json', {}) or {}
            data = project_costs.summary(pid, credit_rate=balance.get('credit_usd_rate'))
            data['elevenlabs_basis'] = (balance.get('credit_usd_basis') or 'Орієнтовна вартість кредитів').replace('без податків і знижок', 'без знижок') + ' · податок 20% включено'
            return self.json_response(data)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/spend", path)
        if match:
            # where the director's and frame agent's runs spent the Claude limits (backend/spend_report.py)
            data = spend_report.reports(match.group(1))
            if (query.get("format") or [""])[0] == "text":
                shown = data["reports"][:int((query.get("limit") or ["0"])[0] or 0) or None]
                body = "\n\n".join(spend_report.text(r) for r in shown) or "Звітів про витрати ще немає"
                return self.text_response(body + f"\n\nУсього за випуск: ${data['total_usd']} у {len(data['reports'])} запусках")
            return self.json_response(data)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/activity/(director|production)", path)
        if match:
            listed(match.group(1))
            return self.json_response({"activity": store.read_json(director.activity_path(*match.groups()), [])})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/director", path)
        if match:
            listed(match.group(1))
            return self.json_response({"director": director.state(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/number-fixes", path)
        if match:
            return self.json_response(store.number_fixes(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/director-sentences", path)
        if match:
            return self.json_response(director_plan.sentences(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/frames-drawn", path)
        if match:
            project = store.load_project(match.group(1))
            return self.json_response({"drawn": frame_progress.drawn(match.group(1)),
                                       "made": store.made_frames(project, store.load_project_plan(project["id"]))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/space", path)
        if match:
            return self.json_response({**space.usage(match.group(1)), "exporting": bool(active_export(match.group(1)))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/disk", path)
        if match:
            return self.json_response({"bytes": store.project_bytes(match.group(1))})
        match = re.fullmatch(r"/api/style-cards/([0-9a-f]{20})/([a-z0-9_-]+-0\.jpg)", path)
        if match:
            try:
                return self.serve_media(style_lab.card_file(*match.groups()), cache=True)
            except style_lab.StyleLabError as error:
                raise store.StudioError(str(error), 404) from None
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/cover", path)
        if match:
            try:
                cover = covers.get(store.load_project(match.group(1)))
            except (OSError, ValueError, subprocess.TimeoutExpired):
                cover = None
            if not cover:
                raise store.StudioError("Обкладинки ще немає", 404)
            return self.serve_media(cover, cache=True)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/([0-9a-f]{20})/thumbnail", path)
        if match:
            project=store.load_project(match.group(1));asset=store.resolve_asset(project,match.group(2))
            try:path=thumbnails.get(asset['path'],asset['kind'],store.project_dir(project['id'])/'thumbnails')
            except (ValueError,OSError,subprocess.TimeoutExpired):raise store.StudioError('Прев’ю недоступне',404)
            return self.serve_media(path,cache=True)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/([0-9a-f]{20})/file", path)
        if match:
            import media_delivery
            project, asset = media_delivery.resolve(*match.groups())
            # the voice plays its copy at the standard level once it is made (audio_level.leveled)
            token = str((query.get("lv") or [""])[0])
            file = (audio_level.token_file(Path(asset["path"]), token) if token
                    else audio_level.voice_file(project, match.group(2), Path(asset["path"])))
            # ?download=1 saves it under the episode's name (user, 21 November 2026: «озвучка… хочу її скачати»)
            download = None
            if query.get("download"):
                stem = re.sub(r'[\\/:*?"<>|]+', " ", str(project.get("name") or "Озвучка")).strip() or "Озвучка"
                download = f"Озвучка - {stem}{file.suffix}"
            return self.serve_media(file, download=download)
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{24})", path)
        if match:
            return self.json_response({"job": load_job(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/capcut-ready", path)
        if match:
            project = store.load_project(match.group(1))
            warm_capcut(project["id"], project)   # the rest is drawn ahead in the background
            ready = capcut_ready(project)
            return self.json_response({"ready": ready, "urls": capcut_ready_urls(project, ready), "revision": project.get("revision")})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/create-video", path)
        if match:
            return self.json_response(analysis_jobs.creation_status(store.load_project(match.group(1)), load_job))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/razgon-link", path)
        if match:
            return self.json_response(store.razgon_link(store.load_project(match.group(1))) or {})
        if path.startswith("/api/"):
            raise store.StudioError("Сторінку не знайдено", 404)
        if path in ("/trending", "/trending/"):
            return self.serve_static("/")
        if re.fullmatch(r"/channels/[0-9a-f]{16}(?:/projects/[0-9a-f]{24}(?:/(?:plan|agent|preview|languages))?)?/?", path):
            return self.serve_static("/")
        return self.serve_static(path)

    def route_mutation(self, method, path, body):
        # prop sheets through OpenRouter for an episode while Codex's limit is out (backend/openrouter_images.py)
        provider = re.fullmatch(r'/api/projects/([0-9a-f]{24})/image-provider(/draw)?', path)
        if provider and method == 'POST':
            import openrouter_images
            if provider.group(2):
                return self.json_response(openrouter_images.draw(provider.group(1), body.get('prompt'), body.get('aspect_ratio') or '3:2', body.get('quality') or 'medium'))
            return self.json_response(openrouter_images.set_provider(provider.group(1), body.get('provider'), body.get('model'), body.get('all') is True))
        if path == '/api/title-translation' and method == 'POST':
            return self.json_response(title_translation.translate(body))
        if path == "/api/trending-videos/use" and method == "POST":
            return self.json_response(trending_videos.use_idea(body), 202)
        if path == "/api/trending-videos/dismiss" and method == "POST":
            return self.json_response(trending_videos.dismiss(body))
        if path == "/api/trending-videos/refresh" and method == "POST":
            return self.json_response(trending_videos.refresh())
        draft = re.fullmatch(r'/api/projects/([0-9a-f]{24})/script-draft(/restore)?', path)
        if draft and method == ('POST' if draft.group(2) else 'PATCH'):
            return self.json_response(script_drafts.restore(draft.group(1), body) if draft.group(2) else script_drafts.save(draft.group(1), body))
        # the channel's signature closing, written once by the frame agent of its first film that ends on the host and kept
        # for the channel's next films (user, 26 November 2026: «щоб в канала була своя особливість… не як шаблон»)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/closing-signature", path)
        if match and method == "POST":   # an empty text only reads it
            cid = store.load_project(match.group(1))["channel_id"]
            current = str(store.read_channel_settings(store.get_channel_folder(cid), {}).get("closing_signature") or "")
            if (body or {}).get("text") and not current:
                text = " ".join(str((body or {}).get("text") or "").split())[:600]
                if len(text) < 20:
                    raise store.StudioError("Опишіть фірмову кінцівку каналу одним-двома реченнями", 400)
                store.update_channel_settings(cid, {"closing_signature": text})
                current = text
            return self.json_response({"signature": current})
        # the music or SFX row's volume set on a film, kept as the channel's default for its next films (26 November 2026)
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/sound-level", path)
        if match and method == "POST":
            family, volume = (body or {}).get("family"), (body or {}).get("volume")
            if family not in ("music", "sfx") or isinstance(volume, bool) or not isinstance(volume, (int, float)):
                raise store.StudioError("Невірна гучність", 400)
            channel = store.update_channel_settings(match.group(1), {"sound": {"levels": {family: float(volume)}}})
            return self.json_response({"levels": ((channel.get("settings") or {}).get("sound") or {}).get("levels", {})})
        # «Власна ідея» of a new episode: five DeepSeek titles for the author's idea (22 November 2026)
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/idea-titles", path)
        if match and method == "POST":
            import episode_ideas
            try:
                return self.json_response(episode_ideas.idea_titles(match.group(1), (body or {}).get("idea"), (body or {}).get("exclude") if isinstance((body or {}).get("exclude"), list) else None))
            except (ValueError, RuntimeError) as error:
                raise store.StudioError(str(error), 400 if isinstance(error, ValueError) else 502) from None
        if path == "/api/channels" or path.startswith("/api/channels/"):
            return channel_api.mutate(self, method, path, body, ensure_idle=channel_transfer_idle, choose_folder=choose_local_folder)
        if path == '/api/space' and method == 'POST':
            return self.json_response(space.free_all(cleanup_blocked))
        revision=re.fullmatch(r'/api/projects/([0-9a-f]{24})/narration/revision',path)
        if revision and method=='POST':
            pid=revision.group(1)
            current=narration_revision.snapshot(pid).get('job') or {}
            if current.get('id')!=body.get('client_id'):
                reason=cleanup_blocked(pid)
                if reason:raise store.StudioError(reason,409)
            return self.json_response(narration_revision.start(pid,body),202)
        narration = re.fullmatch(r'/api/projects/([0-9a-f]{24})/narration/(quote|start|source|cancel|speed)', path)
        if narration and method == 'POST':
            pid, mode = narration.groups(); project = store.load_project(pid)
            if mode == 'speed':return self.json_response(project_narration.change_speed(pid, body.get('speed'), body.get('reverb'), body.get('room_noise')))
            if mode == 'cancel':return self.json_response(project_narration.cancel(pid))
            if mode == 'source':return self.json_response(project_narration.select_source(pid, body.get('source')))
            if mode == 'quote':return self.json_response(project_narration.spec(project, body.get('text'))[3])
            result = project_narration.start(project, body.get('text'), body.get('resume') is True)
            episode_pause.started_by_hand(project['id'], "narration")
            return self.json_response(result, 202)

        match = re.fullmatch(r'/api/projects/([0-9a-f]{24})/completion/seen', path)
        if match and method == 'POST':
            listed(match.group(1))
            completion_notices.seen(match.group(1), body.get('through'))
            return self.json_response({'seen': True})
        if method=='POST' and path=='/api/studio/restart/prepare':
            return self.json_response(prepare_local_restart())
        if method=='POST' and path=='/api/studio/restart':
            return self.json_response(begin_local_restart(),202)
        if method == 'POST' and path == '/api/update/check':
            # «Перевірити оновлення» in the studio's settings: ask GitHub now, not at the next two-minute round
            UPDATE_MANAGER.refresh()
            return self.json_response({**UPDATE_MANAGER.public_state(), 'version': UPDATE_MANAGER.version(), 'boot': UPDATE_BOOT, 'restarting': UPDATE_RESTARTING, 'queued': UPDATE_QUEUED})
        if method == 'POST' and path == '/api/update/apply':
            try:
                begin_update()
            except store.StudioError as error:
                if not str(error).startswith('Зараз '):
                    raise
                queue_update(str(error))
                return self.json_response({'status': 'queued', 'reason': str(error)}, 202)
            return self.json_response({'status': 'restarting'}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/tidy", path)
        if match and method == "POST":
            listed(match.group(1))
            threading.Thread(target=tidy_project, args=(match.group(1),), daemon=True).start()
            return self.json_response({"started": True}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/razgon-link", path)
        if match and method == "POST":
            return self.json_response(technical_files.save_link(match.group(1), body))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/razgon-live", path)
        if match and method == "POST":
            return self.json_response(razgon_live.start(match.group(1), bool(body.get("restart"))))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/production-request", path)
        if match and method == "POST":
            project = store.request_production(match.group(1), body.get("frames"))
            production.start(project["id"])   # Claude Opus starts on the frames at once
            episode_pause.started_by_hand(project["id"], "production")
            return self.json_response({"project": store.load_project(project["id"])})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/create-video", path)
        if match and method == "POST":
            project = store.load_project(match.group(1))
            if store.project_plan_mode(project) == 'direct':
                raise store.StudioError('У цьому проєкті вибрано монтаж без плану. Додайте матеріали на таймлайн.', 409)
            job = analysis_jobs.create_video(project, body.get('asset_id'), save_job, load_job, body.get('script'))
            return self.json_response({'job': job}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/plan/analyze", path)
        if match and method == "POST":
            project = store.load_project(match.group(1))
            return self.json_response({"job": analysis_jobs.start(project, body.get("asset_id"), save_job, load_job, body.get("script"))}, 202)
        if method == "POST" and path == "/api/projects/generate-plan":
            if "settings" in body:
                raise store.StudioError("План використовує збережені налаштування каналу у студії")
            result = store.generate_project_plan(body["channel_id"], body["name"], body["episode_path"],
                script=body.get("script"), script_path=body.get("script_path"), duration=body.get("duration"), hints=body.get("hints"), narration=body.get("narration"), timings=body.get("timings"), weights=body.get("weights"), use_channel_weights=body.get("use_channel_weights") is True)
            return self.json_response(result)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/plan/generate", path)
        if match and method == "POST":
            if "settings" in body:
                raise store.StudioError("План використовує збережені налаштування каналу у студії")
            project = store.load_project(match.group(1))
            result = store.generate_project_plan(project["channel_id"], project["name"], project["episode_path"],
                script=body.get("script"), script_path=body.get("script_path"), duration=body.get("duration"), hints=body.get("hints"), project_id=project["id"], narration=body.get("narration"), timings=body.get("timings"), weights=body.get("weights"), use_channel_weights=body.get("use_channel_weights") is True)
            if body.get("timings") or body.get("narration"):
                director.retime_soon(project["id"])   # an animated direction made on the script follows the voice
            return self.json_response(result)
        if method == "POST" and path == "/api/service-keys/copy":
            return self.json_response({"key": credentials.copy_provider_key(body.get("provider_id"))})
        if method == "POST" and path == "/api/service-keys":
            return self.json_response({"provider": credentials.save_provider(body.get("provider_id"), body.get("name"), body.get("key"))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/agent/settings", path)
        if match and method == "POST":
            return self.json_response({"settings": agent_storage.set_settings(match.group(1), body.get("reasoning_effort"))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/agent/start", path)
        if match and method == "POST":
            callbacks = {"search": search_pixabay, "import": from_pixabay, "export_active": active_export}
            return self.json_response({"job": agent_runtime.start(match.group(1), body.get("message"), callbacks, body.get("allow_images") is True)}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/agent/cancel", path)
        if match and method == "POST":
            return self.json_response({"job": agent_runtime.cancel(match.group(1))}, 202)
        if method == "POST" and path in {"/api/claude-login/start", "/api/claude-login/code", "/api/claude-login/cancel"}:
            import claude_login
            action = path.rsplit("/", 1)[1]
            if action == "start":
                return self.json_response(claude_login.start())
            if action == "code":
                return self.json_response(claude_login.submit_code(body.get("code")))
            return self.json_response(claude_login.cancel())
        if method == "POST" and path == "/api/extension/update":
            import extension
            return self.json_response(extension.update())
        if method == "PATCH" and path == "/api/settings":
            return self.json_response({"settings": update_studio_settings(body.get("settings", {}))})
        if method == 'POST' and path == '/api/settings/youtube-root/pick':
            return self.json_response({'path': str(choose_local_folder('Оберіть папку YouTube з каналами'))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/thumbnail", path)
        if match and method == "POST":
            return self.json_response({"job": thumbnail_gen.start(match.group(1), body.get("title"), body.get("script"), body.get("wishes"), body.get("writer") or "claude", body.get("base") or None, use_hero=body.get("use_hero"), reference_id=body.get("reference_id"), channel_wishes=body.get("channel_wishes") is True, drawer=body.get("drawer") or "openrouter")}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/cancel", path)
        if match and method == "POST":
            return self.json_response(languages.cancel(match.group(1), body.get("slot") or None))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/defaults/apply", path)
        if match and method == "POST":
            return self.json_response(languages.language_defaults.apply_existing(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/defaults", path)
        if match and method == "POST":
            return self.json_response(languages.language_defaults.save(match.group(1),body.get('code')))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/provider", path)
        if match and method == "POST":
            return self.json_response(languages.set_provider(match.group(1), str(body.get("provider") or ""), body.get("engine") or None, body.get("style") or None, body.get("code") or None, body.get("voice_id")))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/thumbnail-options", path)
        if match and method == "POST":
            return self.json_response(languages.save_thumbnail_options(match.group(1),body.get('add_flag')))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/([a-z]{2})/thumbnail/recover",path)
        if match and method=='POST':
            return self.json_response(languages.recover_thumbnail(*match.groups()))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/([a-z]{2})/translation-model", path)
        if match and method == "POST":
            return self.json_response(languages.set_translation_model(*match.groups(), body.get("model")))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/languages/([a-z]{2})(?:/(text|remove|translate|sample|voice|thumbnail|save-audio|refit|own-voice/remove))?", path)
        if match and method == "POST":
            pid, code, action = match.groups()
            if not action:
                return self.json_response(languages.add(pid, code))
            if action == "remove":
                return self.json_response(languages.remove(pid, code))
            if action == "own-voice/remove":
                return self.json_response(languages.remove_own_voice(pid, code))
            if action == "text":
                return self.json_response(languages.save_text(pid, code, body.get("text"), body.get("title")))
            job = languages.start(pid, action, code, body.get("provider"), body.get("wishes"), body.get("sentences"),body.get('add_flag'),body.get('preserve_text',False),cache_only=body.get('cache_only',False),use_hero=body.get('use_hero'),base=body.get('base'),expected_provider=body.get('expected_provider'))
            episode_pause.started_by_hand(pid, "languages", kind=action, code=code)   # no more «paused» on the card
            return self.json_response({"job": job}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/thumbnail/logo", path)
        if match and method == "POST":
            import thumbnail_logo
            return self.json_response(thumbnail_logo.place(match.group(1), str(body.get("base") or ""), body.get("x"), body.get("y"), body.get("width")))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/thumbnail/choose", path)
        if match and method == "POST":
            return self.json_response(thumbnail_gen.choose(match.group(1), str(body.get("name") or "")))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/production-fix", path)
        if match and method == "POST":
            return self.json_response({"project": production.fix(match.group(1), body.get("notes"),frame_numbers=body.get('frame_numbers'))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/production-edits(?:/([0-9a-f]{16})/cancel)?", path)
        if match and method=='POST':
            import production_edits
            return self.json_response(production_edits.cancel(match.group(1),match.group(2)) if match.group(2) else
                production_edits.enqueue(match.group(1),body.get('notes'),body.get('frame_numbers'),body.get('client_id')),202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/youtube-publish", path)
        if match and method == "POST":
            return self.json_response(published.enqueue(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/youtube-publish/cancel", path)
        if match and method == "POST":
            return self.json_response(published.cancel(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/production-pause", path)
        if match and method == "POST":
            limit = body.get("codex_limit") if isinstance(body, dict) else None
            note = production.codex_limit_note(limit.get("reset"), limit.get("openrouter") == "no_funds") if isinstance(limit, dict) else None
            part = body.get("part") if isinstance(body, dict) and body.get("part") in episode_pause.PARTS else None
            if note is None and part and part != "production":
                episode_pause.pause(match.group(1), {part})   # the plan page's own button: only that work
                return self.json_response({"project": paused_view(match.group(1))})
            if note is None and episode_pause.running(match.group(1)):
                episode_pause.pause(match.group(1))   # the author's pause holds the whole episode still
                return self.json_response({"project": paused_view(match.group(1))})
            if note is None and (store.load_project(match.group(1)).get("production_request") or {}).get("status") not in {"requested", "in_progress"}:
                raise store.StudioError("Зараз над випуском немає роботи, яку можна призупинити", 409)
            production.pause(match.group(1), note)
            return self.json_response({"project": paused_view(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/production-resume", path)
        if match and method == "POST":
            part = body.get("part") if isinstance(body, dict) and body.get("part") in episode_pause.PARTS else None
            if part and part != "production":
                episode_pause.resume(match.group(1), {part})
            elif episode_pause.resumable(match.group(1)):
                episode_pause.resume(match.group(1))
            else:
                production.resume(match.group(1))
            return self.json_response({"project": paused_view(match.group(1))})
        # one pause for the whole episode: narration, director, «Підготовка» and frames (backend/episode_pause.py)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/(pause|resume)", path)
        if match and method == "POST":
            result = episode_pause.pause(match.group(1)) if match.group(2) == "pause" else episode_pause.resume(match.group(1))
            return self.json_response({"result": result, "project": paused_view(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/space", path)
        if match and method == "POST":
            # the same guard as «Звільнити місце» for all projects: a thumbnail or a still in work keeps its cache
            # (it deleted razgon/build/thumbnail-stills under a running thumbnail; 17 November 2026 audit)
            blocked = cleanup_blocked(match.group(1))
            if blocked:
                raise store.StudioError(f"{blocked}. Звільніть місце, коли робота закінчиться", 409)
            return self.json_response(space.free(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/restart", path)
        if match and method == "POST":
            if active_export(match.group(1)):
                raise store.StudioError("Зачекайте, доки закінчиться експорт, і почніть заново", 409)
            return self.json_response({"project": episode_restart.restart(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/number-fixes", path)
        if match and method == "POST":
            return self.json_response(store.number_fixes(match.group(1), body.get("fixes") or {}, bool(body.get("dry_run"))))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/director-frames", path)
        if match and method == "POST":
            return self.json_response(director_plan.apply(match.group(1), body.get("frames"), bool(body.get("dry_run"))))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/director", path)
        if match and method == "POST":
            run = director.start(match.group(1), "manual")
            episode_pause.started_by_hand(match.group(1), "director")   # a director started by hand is no longer paused
            return self.json_response({"director": run})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})", path)
        if match and method == "PATCH":
            pid = match.group(1)
            # the episode folder takes the new name too (episode_folder.py), so nothing may be working in it
            import episode_folder
            current = store.load_project(pid)
            moving = (episode_folder.folder_name(body.get("name")) != episode_folder.folder_name(current.get("name"))
                      and Path(current.get("episode_path") or "/nonexistent").is_dir())
            running = moving and (space.busy(pid) or ("Зараз іде експорт" if active_export(pid) else None)
                                  or next((f"Зараз триває {what}" for what, status in project_jobs(pid).items() if status in agent_view.BUSY), None))
            if running:
                raise store.StudioError(f"{running}. Перейменувати випуск разом із папкою можна, коли вона закінчиться", 409)
            store.apply_action(pid, "rename_project", {"name": body.get("name")}, body.get("expected_revision"))
            folder = episode_folder.follow(pid) if moving else {"moved": False, "note": ""}
            return self.json_response({"project": store.load_project(pid), "folder": folder})
        if match and method == "DELETE":
            pid = match.group(1)
            running = (space.busy(pid) or ("Зараз іде експорт" if active_export(pid) else None)
                       or next((f"Зараз триває {what}" for what, status in project_jobs(pid).items() if status in agent_view.BUSY), None))
            if running:
                raise store.StudioError(f"{running}. Видалити проєкт можна, коли вона закінчиться", 409)
            return self.json_response({"ok": True, "freed": store.delete_project(pid)})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/restore", path)
        if match and method == "POST":
            return self.json_response({"project": store.restore_project(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/plan", path)
        if match and method == "POST":
            return self.json_response({"project": store.attach_plan(match.group(1), body["plan"])})
        if method == "POST" and path == "/api/projects/from-plan":
            project = store.project_from_plan(body["channel_id"], body["name"], body["episode_path"], body["plan"])
            return self.json_response({"project": project, "plan_url": f"/channels/{project['channel_id']}/projects/{project['id']}/plan"})
        draft_match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/episode-draft", path)
        if draft_match and method == "POST":
            import episode_ideas
            return self.json_response(episode_ideas.public(episode_ideas.start_project(draft_match.group(1), body)), 202)
        if method == "POST" and path == "/api/projects":
            project = store.create_project(body["channel_id"], body["name"], body.get("episode_path"))
            return self.json_response({"project": project}, 201)
        if method == "POST" and path == "/api/projects/import":
            project = store.import_plan(body["channel_id"], body["plan_path"], body.get("name"))
            return self.json_response({"project": project}, 201)
        if method == "POST" and path == "/api/projects/import/data":
            project = store.import_plan_data(body["channel_id"], body["plan"], body.get("name") or "Імпортований план")
            return self.json_response({"project": project}, 201)
        if method == "POST" and path == "/api/projects/import/pick":
            selected = Path(body["path"]).expanduser().resolve() if body.get("path") else choose_local_file("Оберіть JSON-план випуску")
            project = store.import_plan(body["channel_id"], str(selected), body.get("name"))
            return self.json_response({"project": project}, 201)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/ops", path)
        if match and method == "POST":
            result = montage_ops.run(match.group(1), body.get("ops"), body.get("expected_revision"), body.get("dry_run") is True)
            if result.get("applied") and store.prune_razgon_renders(match.group(1))["removed"]:
                result["revision"] = store.load_project(match.group(1)).get("revision", 0)
            if result.get("applied"):
                warm_capcut(match.group(1))   # new seams are drawn ahead at once
                # accents and transitions an op laid get their pencil and transition sounds a moment later (the sound
                # ops themselves start no further pass)
                if any(isinstance(op, dict) and op.get("op") not in SOUND_OPS for op in body.get("ops") or []):
                    sync_transition_sounds(match.group(1))
            return self.json_response(result)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/event-sounds", path)
        if match and method == "POST":
            # sounds on what comes on screen in the Razgon frames, read from their code (event_sounds.py)
            import event_sounds
            frames = body.get("frames")
            if frames is not None and (not isinstance(frames, list) or not all(type(n) is int for n in frames)):
                raise store.StudioError("frames: список номерів кадрів", 400)
            listed(match.group(1))
            return self.json_response({"started": event_sounds.start(match.group(1), set(frames) if frames else None)}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/frame-review", path)
        if match and method == "POST":
            import native_review
            return self.json_response(native_review.batch(store.load_project(match.group(1)), body.get("frames"), body.get("ticket")))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/capcut-preview", path)
        if match and method == "POST":
            global CAPCUT_DEMAND
            with CAPCUT_LOCK:
                CAPCUT_DEMAND += 1   # the seam the author looks at goes before the background pass
            try:
                answer = capcut_transition_preview(store.load_project(match.group(1)), str(body.get("join_id", "")))
            finally:
                with CAPCUT_LOCK:
                    CAPCUT_DEMAND -= 1
            warm_capcut(match.group(1))
            return self.json_response(answer)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/motion-check", path)
        if match and method == "POST":
            # the newest motion-code clip of a frame (or the one titled) run on four moments: PNG stills with alpha, and a warning when it fades before its end
            import motion_code
            project = store.load_project(match.group(1))
            clips = [c for t in project.get("tracks", []) for c in t.get("clips", []) if c.get("content_type") == "code"]
            frame, title = body.get("frame"), str(body.get("title") or "")
            prefix = f"K{int(frame):03d} моушн" if str(frame).isdigit() else ""
            chosen = [c for c in clips if str(c.get("title", "")).startswith(prefix) and (not title or c.get("title", "").endswith(title))]
            if not chosen:
                raise store.StudioError("Моушн-код кадру не знайдено", 404)
            clip = chosen[-1]
            length = float(clip["duration"])
            folder = store.cache_dir(project) / "motion-code" / ("check-" + clip["id"])
            return self.json_response(motion_code.stills(project, clip, [min(.3, length / 4), length / 2, length * .8, max(0, length - .1)], folder))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/still", path)
        if match and method == "POST":
            project = store.load_project(match.group(1))
            moment = float(body["time"])
            if not 0 <= moment <= float(project.get("duration", 0)) + 1:
                raise store.StudioError("Момент поза роликом")
            return self.json_response(export_still(project, moment, max(1, min(30, int(body.get("frames", 1)))), body.get("cpu") is True))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/actions", path)
        if match and method == "POST":
            project = store.apply_action(match.group(1), body["type"], body.get("payload", {}), body.get("expected_revision"))
            # a frame render that a newer one replaced is not kept (store.prune_razgon_renders)
            if store.prune_razgon_renders(match.group(1))["removed"]:
                project = store.load_project(match.group(1))
            if changes_joins(body):
                sync_transition_sounds(match.group(1))
            return self.json_response({"project": project})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/relocate", path)
        if match and method == "POST":
            if active_export(match.group(1)):
                raise store.StudioError("Дочекайтеся завершення експорту перед перенесенням матеріалів.",409)
            result=store.relocate_media(match.group(1),body.get("expected_revision"))
            if result.get("moved"):
                languages.language_mix.rebase_saved_after_move(match.group(1),store.read_json(Path(result["journal"])/"paths.json",{}))
            return self.json_response(result)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/pick", path)
        if match and method == "POST":
            project = store.load_project(match.group(1))
            selected = Path(body["path"]).expanduser().resolve() if body.get("path") else choose_local_file("Оберіть медіафайл")
            return self.json_response({"asset": store.import_asset_file(project, selected)}, 201)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/stock-sheet", path)
        if match and method == "POST":
            import stock_sheet
            return self.json_response(stock_sheet.sheet(store.load_project(match.group(1)), body.get("frame", 0), str(body.get("query") or ""),
                                                        str(body.get("kind") or "image"), body.get("count", 8)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/from-pixabay", path)
        if match and method == "POST":
            project = store.load_project(match.group(1))
            selected_id = body.get("pixabay_id", body.get("id"))
            return self.json_response({"asset": from_pixabay(project, body["kind"], int(selected_id), body.get("quality"))}, 201)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/export", path)
        if match and method == "POST":
            project = store.load_project(match.group(1))
            bitrate = body.get("video_bitrate")
            if body.get("channel_quality") is True and bitrate is None:
                # the card's «Експортувати»: the quality the channel chose, as «Автоекспорт» exports
                settings = store.read_channel_settings(store.get_channel_folder(project["channel_id"]), {}) or {}
                quality = "max" if settings.get("video_quality") == "max" else store.DEFAULT_VIDEO_QUALITY   # «Стандартна» is gone (26 November 2026)
                bitrate = store.video_bitrates(int(project.get("width") or 1920), int(project.get("height") or 1080),
                                               int(project.get("fps") or 25))[store.VIDEO_QUALITIES.index(quality)]
            return self.json_response({"job": start_export(project, body.get("confirm_export") is True,
                                                           int(bitrate) if isinstance(bitrate, (int, float)) else None)}, 202)
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{24})/cancel", path)
        if match and method == 'POST':
            return self.json_response({'job': cancel_export(match.group(1))}, 202)
        raise store.StudioError("Дію не знайдено", 404)

    def serve_static(self, raw_path):
        rel = raw_path.lstrip("/") or "index.html"
        if rel == "favicon.ico":   # browsers ask for it on their own; the studio's icon is the SVG
            rel = "favicon.svg"
        target = (FRONTEND_ROOT / rel).resolve()
        if not store.under(target, FRONTEND_ROOT) or not target.is_file():
            raise store.StudioError("Інтерфейс не знайдено", 404)
        body = target.read_bytes()
        if target == FRONTEND_ROOT / "index.html":
            body = versioned_index(body)
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") or mime == "application/javascript" else ""))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def serve_thumbnail(self, path: Path, cache=False, download: str | None = None):
        if not download:
            return self.serve_media(path, cache=cache)
        body = image_delivery.clean_png(path.read_bytes())
        self.send_response(200)
        self.send_header('Content-Type', 'image/png')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        plain = re.sub(r'[^A-Za-z0-9._ -]+', '_', download).strip('_ ') or 'preview.png'
        self.send_header('Content-Disposition', f'attachment; filename="{plain}"; filename*=UTF-8\'\'' + urllib.parse.quote(download))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def serve_media(self, path: Path, cache=False, download: str | None = None):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or not any(match.groups()):
                raise store.StudioError("Непідтримуваний діапазон", 416)
            if match.group(1):
                start = int(match.group(1))
                end = min(int(match.group(2)) if match.group(2) else size - 1, size - 1)
            else:
                suffix = int(match.group(2))
                if not suffix:
                    raise store.StudioError("Непідтримуваний діапазон", 416)
                start = max(0, size - suffix)
            if start >= size or end < start:
                raise store.StudioError("Діапазон поза файлом", 416)
            status = 206
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if cache:self.send_header('Cache-Control','private, max-age=31536000, immutable')
        if download:      # a file the author saves: its own name, Cyrillic kept (RFC 5987)
            plain = re.sub(r"[^A-Za-z0-9._ -]+", "_", download).strip("_ ") or "file"
            self.send_header("Content-Disposition", f'attachment; filename="{plain}"; filename*=UTF-8\'\'' + urllib.parse.quote(download))
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


class StudioHTTPServer(ThreadingHTTPServer):
    # A project can open several API requests and media thumbnails at once.
    # The standard-library default of five queued connections drops bursts.
    request_queue_size = 128


def warm_project_cache():
    try:
        projects = store.list_projects()
    except Exception as error:  # a broken project must not stop the server; the list request reports it
        print(f"Project cache warm-up failed: {error}", flush=True)
        return
    for item in projects:
        tidy_project(item["id"])


def tidy_project(pid: str) -> None:
    """Free disk space taken by Razgon renders nothing uses any more, in the Studio and in the Razgon project."""
    try:
        result = store.prune_razgon_renders(pid)
        if result["removed"]:
            print(f"Removed {result['removed']} replaced Razgon clips ({result['bytes'] / 1e9:.2f} GB) from {pid}", flush=True)
        razgon_live.clean_build(store.load_project(pid))
    except Exception as error:
        print(f"Cleanup of {pid} failed: {error}", flush=True)


TIDY_FIRST = 10 * 60      # the first tidy waits for the start-up work to settle
TIDY_EVERY = 6 * 3600     # then every six hours


def tidy_loop():
    """Clear what the studio piles up and never reads again (storage_tidy; user, 14 November 2026: «проблема з вагою
    видео кей студио… прибери»). A project with work running, an export among them, is left for the next round."""
    import storage_tidy
    time.sleep(TIDY_FIRST)
    while True:
        try:
            with JOBS_LOCK:
                skip = {entry['job']['project_id'] for entry in ACTIVE_EXPORTS.values()}
            skip |= busy_candidates()
            result = storage_tidy.tidy(store.DATA_ROOT, skip)
            if result["freed"]:
                print(f"Tidy freed {storage_tidy.gigabytes(result['freed'])} ({result['files']} items)", flush=True)
        except Exception:
            traceback.print_exc()
        time.sleep(TIDY_EVERY)


def production_edits_loop():
    import production_edits
    while True:
        time.sleep(2)
        try:
            with UPDATE_MUTEX:
                if UPDATE_RESTARTING or IN_FLIGHT:continue
                with JOBS_LOCK:blocked={entry['job']['project_id'] for entry in ACTIVE_EXPORTS.values()}
                production_edits.tick(blocked)
        except Exception:
            traceback.print_exc()


def migrate_at_start() -> None:
    for cid, result in technical_files.migrate_channels().items():
        if isinstance(result, dict) and result.get("error"):
            print(f"Channel configuration migration of {cid}: {result['error']}", flush=True)
    for pid, result in technical_files.migrate_all().items():
        if isinstance(result, dict) and result.get("error"):
            print(f"Technical file migration of {pid}: {result['error']}", flush=True)


def start_automation() -> None:
    import youtube_dates   # release dates of episodes marked published by Finder's blue tag, from the channels' feeds
    youtube_dates.start()
    # «Автоекспорт» and «Автопублікація» of the channels that switched them on, once the projects are migrated
    auto_pipeline.start(lambda project, confirmation, bitrate: start_export(project, confirmation, bitrate), active_export)


def start_edits_queue() -> None:
    # the author's queued frame edits start only on migrated projects, after an interrupted run was settled
    threading.Thread(target=production_edits_loop, daemon=True).start()


def keep_sounds() -> None:
    # every episode's sound gets a copy in the studio, so it still plays after the episode folder is deleted
    import keep
    keep.keep_all()


# in this order: the projects are migrated before anything else reads or changes them; a run cut by the restart is
# settled and hidden projects come back before the slower housekeeping
import music_sync  # noqa: E402


STARTUP_TASKS = (
    migrate_at_start,
    production.reset_interrupted,
    start_edits_queue,
    store.restore_hidden_projects,   # projects an earlier version hid when their episode folder was gone
    start_automation,
    director.resume_retimes,
    razgon_kit_at_start,
    music_sync.start,                # the channels' music library from its repository on every Mac (27 November 2026)
    topics.update_all,
    keep_sounds,
    spend_report.backfill_all,       # a run that ended while an older version ran still gets its spend report
    language_mix.refresh_all,        # language soundtracks saved before the music and effects are mixed again
    style_lab.warm,
    warm_project_cache,              # replaced Razgon renders are pruned, every project read once
)
STARTUP_STATE = {"done": False, "current": None}


def run_startup(tasks) -> None:
    """Each start-up task once, in order; one that fails is written to the log and the next one runs."""
    for task in tasks:
        STARTUP_STATE["current"] = getattr(task, "__name__", str(task))
        try:
            task()
        except Exception:
            traceback.print_exc()
    STARTUP_STATE.update(done=True, current=None)


def main():
    parser = argparse.ArgumentParser(description="VideoKey Studio local server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("Only local loopback is supported")
    # `kill -USR1 <pid>` writes where every thread stands, without stopping anything: a job hung for half an hour
    # (17 November 2026, a sentence revision) could not be read from outside, and only a forced restart ended it
    try:
        import faulthandler
        import signal
        threads_log = Path.home() / "Library" / "Logs" / "VideoKey Studio" / "threads.log"
        threads_log.parent.mkdir(parents=True, exist_ok=True)
        main.threads_file = open(threads_log, "a", encoding="utf-8")
        faulthandler.register(signal.SIGUSR1, file=main.threads_file, all_threads=True)
    except (OSError, AttributeError, ValueError):
        pass
    # every project read of this server is kept per version of its files (backend/project_reads.py)
    import project_reads
    project_reads.install()
    server = StudioHTTPServer((args.host, args.port), Handler)
    threading.Thread(target=update_loop, daemon=True).start()
    threading.Thread(target=tidy_loop, daemon=True).start()
    # the start-up work runs in the background, one task after another, so the server answers at once and the first
    # pages do not wait behind a dozen threads holding the interpreter (the migrations alone took 8-12 s before the
    # server answered its first request, 25 November 2026)
    threading.Thread(target=run_startup, args=(STARTUP_TASKS,), name="startup", daemon=True).start()
    print(f"VideoKey Studio ready at http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
