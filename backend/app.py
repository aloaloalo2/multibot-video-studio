#!/usr/bin/env python3
"""Local HTTP API and static shell for VideoKey Studio."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import store
import covers
import channel_branding
import style_lab
import style_copy
import director
import episode_restart
import frame_progress
import space
import production
import thumbnail_gen
import agent_estimate
import agent_runtime
import agent_storage
import credentials
import analysis_jobs
import razgon_live
import razgon_export
import audio_level
import waveforms
import joins
import agent_view
import montage_ops
import thumbnails
import updater


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(APP_ROOT / "engine"))
FRONTEND_ROOT = APP_ROOT / "frontend"
ENGINE_SCRIPT = APP_ROOT / "engine" / "render.py"
JOBS_ROOT = store.DATA_ROOT / "jobs"
JOBS_LOCK = threading.RLock()
ACTIVE_EXPORTS = {}
UPDATE_MUTEX = threading.RLock()
UPDATE_MANAGER = updater.Updater(APP_ROOT)
UPDATE_BOOT = uuid.uuid4().hex
UPDATE_RESTARTING = False


def restart_after_update():
    global UPDATE_RESTARTING
    try:
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except OSError:
        traceback.print_exc()
        UPDATE_MANAGER.state = {'status': 'restart_failed'}
        UPDATE_RESTARTING = False


def begin_update():
    global UPDATE_RESTARTING
    with UPDATE_MUTEX:
        if UPDATE_RESTARTING:
            raise store.StudioError('Студія вже оновлюється.', 409)
        with JOBS_LOCK:
            if ACTIVE_EXPORTS or analysis_jobs.ACTIVE_JOBS:
                raise store.StudioError('Дочекайтеся завершення експорту або обробки озвучки.', 409)
        try:
            UPDATE_MANAGER.apply()
        except updater.UpdateError as error:
            raise store.StudioError(str(error), 409) from error
        UPDATE_RESTARTING = True
        timer = threading.Timer(1.0, restart_after_update)
        timer.daemon = True
        timer.start()
        return True


def update_loop():
    while True:
        UPDATE_MANAGER.refresh()
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


def pixabay_module():
    sys.path.insert(0, str(store.APP_ROOT / "tools"))
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
    dest = store.project_dir(project["id"]) / "media"
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


def valid_local_source(path: Path, project: dict) -> bool:
    return path.is_file() and (store.under(path, store.project_dir(project["id"]) / "media") or store.under(path, Path(project["episode_path"])))


def normalize_for_engine(project: dict) -> dict:
    """Convert UI manifest to deterministic scene/track render manifest."""
    if project.get("schema_version") == 2:
        layers = []
        assets = {asset["id"]: asset for asset in store.discover_assets(project)}
        voice = audio_level.voice_gains(project)   # the voice at 100% is the Studio's standard level (audio_level.py)
        visual_count = 0
        for z, layer in enumerate(project.get("tracks", [])):
            rendered_clips = []
            for clip in layer.get("clips", []):
                kind = clip.get("kind")
                if kind not in {"video", "image", "text", "animation", "audio"}:
                    raise store.StudioError("Невідомий тип кліпу")
                source = None
                needs_asset = kind in {"video", "image", "audio"} or kind == "animation" and clip.get("content_type") == "image"
                if needs_asset:
                    asset = assets.get(clip.get("asset_id"))
                    if asset is None:
                        raise store.StudioError("Для кліпу «%s» ще не вибрано матеріал" % clip.get("title", ""))
                    source = Path(asset["path"]).resolve()
                    if not valid_local_source(source, project):
                        raise store.StudioError("Матеріал кліпу недоступний")
                if kind != "audio":
                    visual_count += 1
                rendered_clips.append({"id": clip["id"], "type": kind, "source": str(source) if source else None, "text": clip.get("text", ""), "content_type": clip.get("content_type"), "color": clip.get("color", "#101114"), "start": float(clip["start"]), "duration": float(clip["duration"]), "trim_start": float(clip.get("trim_start", 0)), "volume": 0.0 if layer.get("muted") else float(clip.get("volume", 1)) * (voice.get(clip.get("asset_id"), 1.0) if kind == "audio" else 1.0), "transition": copy.deepcopy(clip.get("transition", {"type": "cut", "duration": 0})), "x": clip.get("x", .5), "y": clip.get("y", .5), "width": clip.get("width", 1), "height": clip.get("height", 1), "scale": clip.get("scale", 1), "opacity": clip.get("opacity", 1), "preset": clip.get("preset"), "preset_duration": clip.get("preset_duration", 0), "keyframes": copy.deepcopy(clip.get("keyframes", [])), "audio_role": clip.get("audio_role"), "easing": clip.get("easing", "linear")})
                for field in ("font_size", "text_words", "mask", "corner_radius", "shadow", "font_family", "font_weight", "text_align", "line_height", "word_entrance", "gradient", "blur", "motion_blur", "visual_effect"):
                    if field in clip:
                        rendered_clips[-1][field] = copy.deepcopy(clip[field])
                if not clip.get("preset"):
                    rendered_clips[-1].pop("preset")
                    rendered_clips[-1].pop("preset_duration")
            layers.append({"id": layer["id"], "z": z, "clips": rendered_clips})
        joins.transport(project,layers)
        if not visual_count:
            raise store.StudioError("Додайте хоча б один візуальний кліп перед експортом")
        return {"width": int(project.get("width", 1920)), "height": int(project.get("height", 1080)), "fps": int(project.get("fps", 30)), "duration": float(project.get("duration", 0)), "layer_mode": "item", "timeline_layers": layers}
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
    return store.read_json(path)


def save_job(job: dict) -> None:
    with JOBS_LOCK:
        store.atomic_json(job_path(job["id"]), job)


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
    started_at, clips, error = time.monotonic(), None, None
    with JOBS_LOCK:
        if entry['cancel']:
            return
        process = subprocess.Popen(razgon_export.frames_command(mixed), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
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
            elif event.get('stage') == 'razgon':
                with JOBS_LOCK:
                    if entry['cancel']:
                        break
                    share = max(0.0, min(1.0, float(event.get('progress', 0))))
                    job.update(stage='razgon_frames', progress=min(99, round(99 * share)), razgon_completed=int(event.get('completed', 0)), razgon_total=int(event.get('total', 0)))
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
    razgon_export.point_blocks_at_clips(manifest, mixed, clips)
    store.atomic_json(render_manifest, manifest)
    with JOBS_LOCK:
        # the engine's own progress starts over from 0 for the whole timeline
        job.update(stage='preparing', progress=0, remaining_seconds=None)
        save_job(job)


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
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
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
        try:
            progress_from = None
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
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
                with JOBS_LOCK:
                    if not entry['cancel']:
                        job['progress'] = progress if event.get('stage') == 'gpu_fallback' else max(job['progress'],progress)
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
            process.stdout.close()
        if entry['cancel']:
            return
        if returncode:
            prefix = f'Сцена {current_scene}: ' if current_scene and not (render_error or '').startswith('Сцена ') else ''
            fallback = f'процес зупинено сигналом {-returncode}' if returncode < 0 else f'код {returncode}'
            raise RuntimeError(prefix + (render_error or fallback))
        _check_render(staging)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise RuntimeError("Файл з такою назвою вже існує")
        with JOBS_LOCK:
            if entry['cancel']:
                return
            os.replace(str(staging), str(destination))
            job["status"] = "complete"
            job["output_path"] = str(destination)
            job["progress"] = 100
    except Exception as exc:
        with JOBS_LOCK:
            if not entry['cancel']:
                job["status"] = "failed"
                job["error"] = str(exc)
    finally:
        if staging.exists():
            staging.unlink()
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


def start_export(project: dict, confirmation: bool) -> dict:
    if confirmation is not True:
        raise store.StudioError("Підтвердіть фінальний експорт після перегляду проєкту")
    readiness = store.plan_readiness(project)
    if not readiness["export_ready"]:
        raise store.StudioError(readiness["reason"], 409)
    razgon = razgon_export.export_job(project)
    # a mixed episode: the bridge renders its Razgon code blocks first, then the engine exports the timeline
    mixed = razgon if razgon and razgon.get("mixed") else None
    razgon = None if mixed else razgon
    manifest = razgon or normalize_for_engine(project)
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
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = output_folder / ("Video Studio " + timestamp + "-" + jid[:6] + ".mp4")
    render_dir = store.project_dir(project["id"]) / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
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
        guard = agent_runtime.acquire_project_guard(project['id'], 'export')
        if guard is None:
            manifest_path.unlink(missing_ok=True)
            raise store.StudioError("Дочекайтеся завершення роботи агента або експорту.", 409)
        try:
            if store.load_project(project['id']).get('revision', 0) != project.get('revision', 0):
                raise store.StudioError("Проєкт змінився перед експортом. Спробуйте ще раз.", 409)
            save_job(job)
            ACTIVE_EXPORTS[jid] = {'job': job, 'process': None, 'cancel': False, 'project_guard': guard}
            command = razgon_export.command(manifest_path, staging) if razgon else None
            threading.Thread(target=_render_worker, args=(job, manifest_path, staging, destination, command, mixed), daemon=True).start()
        except Exception:
            ACTIVE_EXPORTS.pop(jid, None)
            guard.close()
            manifest_path.unlink(missing_ok=True)
            raise
    return job


STILL_SCRIPT = APP_ROOT / "engine" / "still.py"
STILL_LOCK = threading.Lock()


def project_jobs(pid: str) -> dict:
    """{what: status} of the work that runs for one project besides its export."""
    request = store.load_project(pid).get("production_request")
    def status(read):
        try:
            return (read() or {}).get("status")
        except (store.StudioError, OSError, ValueError, KeyError):
            return None
    return {"розпізнавання озвучки": status(lambda: analysis_jobs.latest(pid, load_job).get("job")),
            "режисура": status(lambda: director.state(pid)),
            "створення кадрів": request.get("status") if isinstance(request, dict) else None,
            "прев'ю": status(lambda: thumbnail_gen.state(pid)),
            "агент студії": status(lambda: agent_runtime.snapshot(pid))}


def recent_exports(pid: str, limit: int = 5) -> list[dict]:
    """The project's latest export jobs, newest first (running, finished, failed or cancelled)."""
    found = []
    for path in sorted(JOBS_ROOT.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:400]:
        try:
            job = store.read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(job, dict) and job.get("project_id") == pid and "output_path" in job:
            found.append({key: job.get(key) for key in ("id", "status", "progress", "stage", "remaining_seconds", "output_path", "error",
                                                         "razgon_completed", "razgon_total", "render_mode")})
            found[-1]["updated_at"] = round(path.stat().st_mtime)
            if len(found) >= limit:
                break
    return found


def export_still(project: dict, moment: float, frames: int = 1, cpu: bool = False) -> dict:
    """A still of the export at `moment` (the first of `frames` frames), drawn by the export's own renderer on a
    window of the render manifest (engine/still.py), to hold against the preview at the same moment. Razgon code
    frames are not rendered here: they stay code until «Експорт MP4» (user, 30 October 2026)."""
    manifest = normalize_for_engine(project)
    from render_cache import renderer_version
    key = hashlib.sha256(json.dumps([manifest, round(float(moment), 4), int(frames), bool(cpu), renderer_version(APP_ROOT / "engine")],
                                    sort_keys=True, default=str).encode()).hexdigest()[:20]
    folder = store.project_dir(project["id"]) / "stills"
    folder.mkdir(exist_ok=True)
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
                                    capture_output=True, text=True, timeout=900)
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
        stills = sorted(folder.glob("still-*"), key=lambda item: item.stat().st_mtime, reverse=True)
        for old in stills[120:]:
            old.unlink(missing_ok=True)
    return {**info, "cached": False, "notes": notes}


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
    return (project.get("revision"), project.get("duration"), project.get("fps"), project.get("episode_path"), plan_key, tuple(audio))


def derived_state(project: dict) -> tuple[dict, dict]:
    """(production readiness, voice gains) of a project, computed once per version of what they read: every project
    response carries both, and measuring them again took most of a request on a long episode."""
    key = _derived_key(project)
    with _DERIVED_LOCK:
        hit = _DERIVED.get(project["id"])
        if hit and hit[0] == key:
            return copy.deepcopy(hit[1]), dict(hit[2])
    readiness, gains = store.plan_readiness(project), audio_level.voice_gains(project)
    with _DERIVED_LOCK:
        _DERIVED[project["id"]] = (key, readiness, gains)
    return copy.deepcopy(readiness), dict(gains)


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


class Handler(BaseHTTPRequestHandler):
    server_version = "MultiBotVideoStudio/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[video-studio] " + fmt % args + "\n")

    def json_response(self, value, status=200):
        if isinstance(value, dict) and isinstance(value.get("project"), dict):
            project = dict(value["project"])
            project.update(store.history_state(project["id"]))
            # the preview plays the voice at the export's level (audio_gain)
            project["production"], project["audio_gain"] = derived_state(project)
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
            return json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            raise store.StudioError("Невірний JSON") from None

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
            with UPDATE_MUTEX:
                if UPDATE_RESTARTING:
                    raise store.StudioError('Студія перезапускається після оновлення.', 503)
                project_match = re.match(r'^/api/projects/([0-9a-f]{24})(?:/|$)', path)
                # the live preview only starts a viewer of the Razgon code and changes nothing in the project
                # a still only reads the project, as the live preview does
                if project_match and not path.endswith(('/export', '/razgon-live', '/still')) and active_export(project_match.group(1)):
                    raise store.StudioError('Проєкт заблоковано під час експорту. Дочекайтеся завершення або скасуйте експорт.', 423)
                if project_match and not path.endswith(('/agent/cancel', '/still')) and agent_runtime.active(project_match.group(1)):
                    raise store.StudioError('Дочекайтеся завершення агента або зупиніть його перед зміною проєкту.', 423)
                upload = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/upload", path)
                if method == "POST" and upload:
                    return self.route_upload(upload.group(1))
                body = self.read_json_body() if method in {"POST", "PATCH"} else None
                return self.route_mutation(method, path, body or {})
        except store.StudioError as exc:
            return self.json_response({"error": str(exc)}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            # A video element drops a range request it no longer needs while seeking; there is nobody left to answer.
            self.close_connection = True
            return None
        except (KeyError, TypeError, ValueError) as exc:
            return self.json_response({"error": "Невірні параметри запиту"}, 400)
        except Exception:
            traceback.print_exc()
            return self.json_response({"error": "Внутрішня помилка студії"}, 500)

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def do_PATCH(self):
        self.handle_request("PATCH")

    def do_DELETE(self):
        self.handle_request("DELETE")

    def route_upload(self, pid):
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
            raise store.StudioError("Очікується медіафайл", 415)
        size = int(self.headers.get("Content-Length", "0"))
        filename = urllib.parse.unquote(self.headers.get("X-File-Name", ""))
        project = store.load_project(pid)
        asset = store.import_asset_stream(project, self.rfile, size, filename)
        return self.json_response({"asset": asset}, 201)

    def route_get(self, path, query):
        if path == '/api/update':
            return self.json_response({**UPDATE_MANAGER.public_state(), 'boot': UPDATE_BOOT, 'restarting': UPDATE_RESTARTING})
        if path in {"/api/health", "/health"}:
            return self.json_response({"service": "multibot-video-studio", "status": "ok", "api_version": 2, "project_schema": 2, "layer_mode": "item", "plan_workflow": "audio_required"})
        if path == "/api/channels":
            return self.json_response({"channels": store.list_channels()})
        if path == "/api/settings":
            return self.json_response({"settings": store.global_settings()})
        if path == "/api/service-keys":
            return self.json_response({"providers": credentials.providers()})
        if path == "/api/projects":
            return self.json_response({"projects": store.list_projects((query.get("channel") or [None])[0])})
        if path == "/api/exports/active":
            with JOBS_LOCK:
                jobs=[dict(entry['job']) for entry in ACTIVE_EXPORTS.values()
                      if entry['job'].get('status') in {'queued','running','cancelling'}]
            return self.json_response({'jobs':jobs})
        if path == "/api/studio/status":
            with JOBS_LOCK:
                jobs = [dict(entry['job']) for entry in ACTIVE_EXPORTS.values()]
            return self.json_response(agent_view.studio_status(jobs, project_jobs))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/export/active", path)
        if match:
            return self.json_response({'job': active_export(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/exports", path)
        if match:
            store.load_project(match.group(1))
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
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/stills/(still-[0-9a-f]{20}(?:-\d{2})?\.png)", path)
        if match:
            target = store.project_dir(match.group(1)) / "stills" / match.group(2)
            if not target.is_file():
                raise store.StudioError("Стоп-кадр не знайдено", 404)
            return self.serve_media(target)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/analysis", path)
        if match:
            return self.json_response(analysis_jobs.latest(match.group(1), load_job))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/razgon-live", path)
        if match:
            return self.json_response(razgon_live.status(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/agent", path)
        if match:
            project_id = match.group(1)
            conversation = agent_storage.get_conversation(project_id)
            return self.json_response({"messages": conversation["messages"], "costs": agent_storage.cost_summary(conversation["costs"]), "job": agent_runtime.snapshot(project_id), "settings": agent_storage.get_settings(project_id)})
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/agent-memory", path)
        if match:
            return self.json_response({"memory": agent_storage.get_memory(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/plan/cost-estimate", path)
        if match:
            return self.json_response({"estimate": agent_estimate.estimate(match.group(1))})
        if path == "/api/pixabay/search":
            q = (query.get("q") or [""])[0].strip()
            kind = (query.get("kind") or ["video"])[0]
            limit = int((query.get("limit") or ["12"])[0])
            return self.json_response({"results": search_pixabay(q, kind, limit)})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})", path)
        if match:
            return self.json_response({"project": store.load_project(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/plan", path)
        if match:
            plan = store.load_project_plan(match.group(1))
            return self.json_response({"plan": plan, "settings_match": store.plan_settings_match(match.group(1), plan)})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets", path)
        if match:
            project = store.load_project(match.group(1))
            return self.json_response({"assets": store.discover_assets(project)})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/([0-9a-f]{20})/waveform", path)
        if match:
            project=store.load_project(match.group(1));asset=store.resolve_asset(project,match.group(2))
            if asset.get('kind') not in {'audio','video'}:raise store.StudioError('Waveform requires audio')
            return self.json_response(waveforms.read_peaks(asset['path'],store.project_dir(project['id'])/'waveforms'))
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/style-previews/([0-9a-f]{20})/([a-z0-9_-]+-\d\.jpg)", path)
        if match:
            store.get_channel_folder(match.group(1))
            try:
                return self.serve_media(style_lab.preview_file(*match.groups()), cache=True)
            except style_lab.StyleLabError as error:
                raise store.StudioError(str(error), 404) from None
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/custom-styles", path)
        if match:
            return self.json_response({"styles": style_copy.load(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/thumbnail", path)
        if match:
            return self.json_response(thumbnail_gen.defaults(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/activity/(director|production)", path)
        if match:
            store.load_project(match.group(1))
            return self.json_response({"activity": store.read_json(director.activity_path(*match.groups()), [])})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/director", path)
        if match:
            store.load_project(match.group(1))
            return self.json_response({"director": director.state(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/frames-drawn", path)
        if match:
            return self.json_response({"drawn": frame_progress.drawn(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/space", path)
        if match:
            return self.json_response({**space.usage(match.group(1)), "exporting": bool(active_export(match.group(1)))})
        match = re.fullmatch(r"/api/style-cards/([0-9a-f]{20})/([a-z0-9_-]+-0\.jpg)", path)
        if match:
            try:
                return self.serve_media(style_lab.card_file(*match.groups()), cache=True)
            except style_lab.StyleLabError as error:
                raise store.StudioError(str(error), 404) from None
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/logo-overlay\.png", path)
        if match:
            folder = store.get_channel_folder(match.group(1))
            try:
                frame = (int((query.get("w") or ["1920"])[0]), int((query.get("h") or ["1080"])[0]))
            except ValueError:
                raise store.StudioError("Невірний розмір кадру") from None
            if not (16 <= frame[0] <= 7680 and 16 <= frame[1] <= 7680):
                raise store.StudioError("Невірний розмір кадру")
            settings = store.read_json(folder / store.PLAN_CONFIG, {})
            target = store.DATA_ROOT / "channels" / match.group(1) / f"logo-overlay-{frame[0]}x{frame[1]}.png"
            if not channel_branding.overlay_png(match.group(1), settings.get("logo"), frame, target):
                raise store.StudioError("Логотип не додано або вимкнено", 404)
            return self.serve_media(target)
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/logo", path)
        if match:
            store.get_channel_folder(match.group(1))
            logo = channel_branding.logo_path(match.group(1))
            if not logo.is_file():
                raise store.StudioError("Логотип не додано", 404)
            return self.serve_media(logo, cache=True)
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
            project = store.load_project(match.group(1))
            asset = store.resolve_asset(project, match.group(2))
            return self.serve_media(Path(asset["path"]))
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{24})", path)
        if match:
            return self.json_response({"job": load_job(match.group(1))})
        if path.startswith("/api/"):
            raise store.StudioError("Сторінку не знайдено", 404)
        if re.fullmatch(r"/channels/[0-9a-f]{16}(?:/projects/[0-9a-f]{24}(?:/(?:plan|agent|preview))?)?/?", path):
            return self.serve_static("/")
        return self.serve_static(path)

    def route_mutation(self, method, path, body):
        if method == 'POST' and path == '/api/update/apply':
            begin_update()
            return self.json_response({'status': 'restarting'}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/tidy", path)
        if match and method == "POST":
            store.load_project(match.group(1))
            threading.Thread(target=tidy_project, args=(match.group(1),), daemon=True).start()
            return self.json_response({"started": True}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/razgon-live", path)
        if match and method == "POST":
            return self.json_response(razgon_live.start(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/production-request", path)
        if match and method == "POST":
            project = store.request_production(match.group(1), body.get("frames"))
            production.start(project["id"])   # Claude Opus starts on the frames at once
            return self.json_response({"project": store.load_project(project["id"])})
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
            return self.json_response(result)
        if method == "POST" and path == "/api/service-keys":
            return self.json_response({"provider": credentials.save_provider(body.get("provider_id"), body.get("name"), body.get("key"))})
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/agent-memory", path)
        if match and method == "POST":
            return self.json_response({"memory": agent_storage.set_memory(match.group(1), body.get("memory"))})
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
        if method == "PATCH" and path == "/api/settings":
            return self.json_response({"settings": store.update_global_settings(body.get("settings", {}))})
        if method == "POST" and path == "/api/channels/pick":
            selected = Path(body["path"]).expanduser().resolve() if body.get("path") else choose_local_folder("Оберіть папку каналу в YOUTUBE")
            return self.json_response({"channel": store.add_channel(selected, body.get("copy_from"))})
        if method == "POST" and path == "/api/channels/create":
            return self.json_response({"channel": store.create_channel(body["name"], body.get("copy_from"))}, 201)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/thumbnail", path)
        if match and method == "POST":
            return self.json_response({"job": thumbnail_gen.start(match.group(1), body.get("title"), body.get("script"), body.get("wishes"))}, 202)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/production-fix", path)
        if match and method == "POST":
            return self.json_response({"project": production.fix(match.group(1), body.get("notes"))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/production-resume", path)
        if match and method == "POST":
            return self.json_response({"project": production.resume(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/space", path)
        if match and method == "POST":
            if active_export(match.group(1)):
                raise store.StudioError("Зачекайте, доки закінчиться експорт, і звільніть місце потім", 409)
            return self.json_response(space.free(match.group(1)))
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/restart", path)
        if match and method == "POST":
            if active_export(match.group(1)):
                raise store.StudioError("Зачекайте, доки закінчиться експорт, і почніть заново", 409)
            return self.json_response({"project": episode_restart.restart(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/director", path)
        if match and method == "POST":
            return self.json_response({"director": director.start(match.group(1), "manual")})
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/custom-styles", path)
        if match and method == "POST":
            try:
                style = style_copy.create(match.group(1), body.get("image"), body.get("note") or "")
            except style_copy.StyleCopyError as error:
                raise store.StudioError(str(error), 409) from None
            return self.json_response({"style": style}, 201)
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/custom-styles/(custom-[0-9a-f]{10})", path)
        if match and method == "DELETE":
            try:
                style_copy.remove(*match.groups())
            except style_copy.StyleCopyError as error:
                raise store.StudioError(str(error), 404) from None
            return self.json_response({"ok": True})
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/style-cards", path)
        if match and method == "POST":
            try:
                return self.json_response(style_lab.showcase(match.group(1)))
            except style_lab.StyleLabError as error:
                raise store.StudioError(str(error), 409) from None
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/style-previews", path)
        if match and method == "POST":
            try:
                return self.json_response(style_lab.previews(match.group(1), bool(body.get("assets", True)), body.get("animation"), body.get("style")))
            except style_lab.StyleLabError as error:
                raise store.StudioError(str(error), 409) from None
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/logo", path)
        if match and method in {"POST", "DELETE"}:
            try:
                if method == "POST":
                    return self.json_response({"logo": channel_branding.save_logo(match.group(1), body.get("data"))}, 201)
                channel_branding.remove_logo(match.group(1))
                return self.json_response({"logo": None})
            except channel_branding.BrandingError as error:
                raise store.StudioError(str(error)) from None
        match = re.fullmatch(r"/api/channels/([0-9a-f]{16})", path)
        if match and method == "PATCH":
            return self.json_response({"channel": store.update_channel_settings(match.group(1), body.get("settings", {}))})
        if match and method == "DELETE":
            store.disable_channel(match.group(1))
            return self.json_response({"ok": True})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})", path)
        if match and method == "PATCH":
            project = store.apply_action(match.group(1), "rename_project", {"name": body.get("name")}, body.get("expected_revision"))
            return self.json_response({"project": project})
        if match and method == "DELETE":
            store.delete_project(match.group(1))
            return self.json_response({"ok": True})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/restore", path)
        if match and method == "POST":
            return self.json_response({"project": store.restore_project(match.group(1))})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/plan", path)
        if match and method == "POST":
            return self.json_response({"project": store.attach_plan(match.group(1), body["plan"])})
        if method == "POST" and path == "/api/projects/from-plan":
            project = store.project_from_plan(body["channel_id"], body["name"], body["episode_path"], body["plan"])
            return self.json_response({"project": project, "plan_url": f"/channels/{project['channel_id']}/projects/{project['id']}/plan"})
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
            return self.json_response(result)
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
            return self.json_response({"project": project})
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/pick", path)
        if match and method == "POST":
            project = store.load_project(match.group(1))
            selected = Path(body["path"]).expanduser().resolve() if body.get("path") else choose_local_file("Оберіть медіафайл")
            return self.json_response({"asset": store.import_asset_file(project, selected)}, 201)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/assets/from-pixabay", path)
        if match and method == "POST":
            project = store.load_project(match.group(1))
            selected_id = body.get("pixabay_id", body.get("id"))
            return self.json_response({"asset": from_pixabay(project, body["kind"], int(selected_id), body.get("quality"))}, 201)
        match = re.fullmatch(r"/api/projects/([0-9a-f]{24})/export", path)
        if match and method == "POST":
            project = store.load_project(match.group(1))
            return self.json_response({"job": start_export(project, body.get("confirm_export") is True)}, 202)
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{24})/cancel", path)
        if match and method == 'POST':
            return self.json_response({'job': cancel_export(match.group(1))}, 202)
        raise store.StudioError("Дію не знайдено", 404)

    def serve_static(self, raw_path):
        rel = raw_path.lstrip("/") or "index.html"
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

    def serve_media(self, path: Path, cache=False):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header.strip())
            if not match:
                raise store.StudioError("Непідтримуваний діапазон", 416)
            start = int(match.group(1))
            end = min(int(match.group(2)) if match.group(2) else size - 1, size - 1)
            if start >= size or end < start:
                raise store.StudioError("Діапазон поза файлом", 416)
            status = 206
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if cache:self.send_header('Cache-Control','private, max-age=31536000, immutable')
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


def main():
    parser = argparse.ArgumentParser(description="VideoKey Studio local server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("Only local loopback is supported")
    server = StudioHTTPServer((args.host, args.port), Handler)
    threading.Thread(target=update_loop, daemon=True).start()
    # Checking every plan takes seconds on long episodes; do it before the first page asks for the project list.
    threading.Thread(target=warm_project_cache, daemon=True).start()
    threading.Thread(target=style_lab.warm, daemon=True).start()
    threading.Thread(target=production.reset_interrupted, daemon=True).start()
    print(f"VideoKey Studio ready at http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
