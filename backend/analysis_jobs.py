"""Background local media analysis, with recoverable reports and unchanged source media."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid

import speech
import speech_repair
import director
import store
import number_text

RUN_LOCK = threading.Lock()
ACTIVE_JOBS = set()


def owner_alive(job):
    pid = job.get("owner_pid")
    if type(pid) is not int or pid <= 0:
        return False
    if pid == os.getpid():
        return job["id"] in ACTIVE_JOBS
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def latest(pid, load_job):
    store.load_project(pid)
    pointer = store.read_json(store.project_dir(pid) / "analysis-state.json", {})
    if not pointer.get("job_id"):
        return {"job": None, "report": None}
    job = load_job(pointer["job_id"])
    if job.get("project_id") != pid or job.get("type") != "speech":
        raise store.StudioError("Звіт не належить цьому випуску", 404)
    if job["status"] in {"queued", "running"} and not owner_alive(job):
        job = {**job, "status": "failed", "stage": "failed", "error": "Обробку перервано перезапуском студії. Запустіть її ще раз"}
    report = store.read_json(store.project_dir(pid) / "analysis" / job["id"] / "result.json")
    return {"job": job, "report": report}


def start(project, asset_id, save_job, load_job, script=None):
    """Recognise a voice. The text comes from the author's script when there is one, else from the voice itself."""
    plan = store.load_project_plan(project["id"])
    if isinstance(script, str) and script.strip():
        script, script_from = script.strip(), "request"
    elif plan and isinstance(plan.get("script"), str) and plan["script"].strip():
        script, script_from = plan["script"], "plan"
    elif isinstance(project.get("voice_script"), dict) and str(project["voice_script"].get("text") or "").strip():
        # An animated episode waits for its voice with the author's script saved on the project.
        script, script_from = project["voice_script"]["text"], "project"
    else:
        script, script_from = None, "audio"
    asset = store.resolve_asset(project, asset_id)
    if asset.get("kind") not in {"audio", "video"}:
        raise store.StudioError("Для розпізнавання виберіть аудіо або відео")
    with store.LOCK:
        active = latest(project["id"], load_job)["job"]
        if active and active["status"] in {"queued", "running"}:
            if active.get("source_asset_id") == asset_id:
                return active
            raise store.StudioError("У цьому випуску вже обробляється інший файл", 409)
        job = {"id": uuid.uuid4().hex[:24], "type": "speech", "project_id": project["id"],
               "source_asset_id": asset_id, "source_name": asset["name"], "status": "queued",
               "progress": 0, "stage": "queued", "error": None, "created_at": time.time(), "owner_pid": os.getpid(),
               "script_from": script_from}
        save_job(job)
        ACTIVE_JOBS.add(job["id"])
        store.atomic_json(store.project_dir(project["id"]) / "analysis-state.json", {"job_id": job["id"]})
    threading.Thread(target=worker, args=(job, script, save_job), daemon=True).start()
    return job


def worker(job, script, save_job):
    work = store.project_dir(job["project_id"]) / "analysis" / job["id"]
    work.mkdir(parents=True, exist_ok=True)
    def progress(value, stage="recognizing"):
        job.update(status="running", progress=value, stage=stage)
        save_job(job)
    try:
        with RUN_LOCK:
            progress(5, "preparing")
            project = store.load_project(job["project_id"])
            source = store.resolve_asset(project, job["source_asset_id"])
            original = Path(source["path"])
            original_hash = store.audio_fingerprint(original)
            audio = source
            if source["kind"] == "video":
                cache_path = store.project_dir(project["id"]) / "analysis" / "audio-cache.json"
                cache = store.read_json(cache_path, {})
                cached = cache.get(original_hash)
                if cached:
                    try:
                        candidate = store.resolve_asset(project, cached["asset_id"])
                        if store.audio_fingerprint(Path(candidate["path"])) == cached["sha256"]:
                            audio = candidate
                    except (store.StudioError, OSError, KeyError):
                        pass
            if source["kind"] == "video" and audio is source:
                ffmpeg = shutil.which("ffmpeg")
                if not ffmpeg:
                    raise RuntimeError("Для вилучення звуку з відео потрібен FFmpeg")
                extracted = work / ("Озвучка з відео " + job["id"][:8] + ".wav")
                command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(original),
                           "-map", "0:a:0", "-vn", "-c:a", "pcm_s24le", "-y", str(extracted)]
                run = subprocess.run(command, capture_output=True, timeout=600)
                if run.returncode or not extracted.is_file():
                    raise RuntimeError("Не вдалося отримати звук із відео. Перевірте, чи воно містить звукову доріжку")
                audio = store.import_asset_file(project, extracted, "speech-analysis")
                extracted.unlink(missing_ok=True)
                cache[original_hash] = {"asset_id": audio["id"], "sha256": store.audio_fingerprint(Path(audio["path"]))}
                store.atomic_json(cache_path, cache)
            path = Path(audio["path"])
            duration = store.media_duration(path)
            if not duration or duration > 36000:
                raise RuntimeError("Не вдалося визначити тривалість аудіо або воно довше 10 годин")
            audio_hash = store.audio_fingerprint(path)
            progress(15, "loading_model")
            words, engine = speech.transcribe(path, duration, progress)
            # Whisper sometimes swallows a sentence on a long voice: those holes are recognised again on their own.
            words, engine["repaired_holes"] = speech_repair.repair(path, words, engine.get("language"))
            if script is None:
                # No script from the author: the recognised voice becomes the script of the episode.
                script = speech.transcript_script(words)
            progress(90, "comparing")
            report = speech.compare_script(script, words, duration)
            report.update(engine=engine, source={"asset_id": source["id"], "name": source["name"], "kind": source["kind"], "sha256": original_hash},
                          audio={"asset_id": audio["id"], "name": audio["name"], "duration": duration, "sha256": audio_hash},
                          script_sha256=hashlib.sha256(script.encode()).hexdigest(), words=words,
                          recognized_text=number_text.to_digits(" ".join(word["text"] for word in words)),
                          recognized_text_original=" ".join(word["text"] for word in words), applied=False, created_at=time.time(),
                          script_from=job.get("script_from", "plan"))
            if store.audio_fingerprint(original) != original_hash or store.audio_fingerprint(path) != audio_hash:
                report["status"] = "source_changed"
            with store.LOCK:
                current = store.load_project_plan(project["id"])
                if job.get("script_from", "plan") == "plan" and (not current or current.get("script") != script):
                    report["status"] = "script_changed"
                if report["status"] == "matched":
                    timings = {**report["timings"], "audio_sha256": audio_hash}
                    project = store.load_project(project["id"])
                    generated = store.generate_project_plan(project["channel_id"], project["name"], project["episode_path"],
                        script=script, hints=(current or {}).get("hints") if job.get("script_from", "plan") == "plan" else None,
                        project_id=project["id"], timings=timings)
                    report["studio_script_sha256"] = generated["plan"]["script_sha256"]
                    report["applied"] = True
            store.atomic_json(work / "result.json", report)
            job.update(status="complete", progress=100, stage="complete", analysis_status=report["status"], applied=report["applied"])
        if report["applied"]:
            director.after_voice(project["id"])
    except (store.StudioError, RuntimeError) as error:
        job.update(status="failed", stage="failed", error=str(error))
    except Exception:
        import traceback
        traceback.print_exc()
        job.update(status="failed", stage="failed", error="Не вдалося обробити файл. Перевірте медіа та локальний Whisper")
    finally:
        job["finished_at"] = time.time()
        save_job(job)
        ACTIVE_JOBS.discard(job["id"])
