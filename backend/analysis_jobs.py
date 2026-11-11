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
import job_timing
import narration_ending
import number_text
import narration_sequence
import status_views

RUN_LOCK = threading.Lock()
ACTIVE_JOBS = set()
ACTIVE_PROJECTS: dict[str, str] = {}   # job id → project id of the recognitions this server runs


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


def latest(pid, load_job, *, compact=False, include_report=True):
    store.load_project(pid)
    pointer = store.read_json(store.project_dir(pid) / "analysis-state.json", {})
    if not pointer.get("job_id"):
        return {"job": None, "report": None}
    job = load_job(pointer["job_id"])
    if job.get("project_id") != pid or job.get("type") != "speech":
        raise store.StudioError("Звіт не належить цьому випуску", 404)
    if job["status"] in {"queued", "running"} and not owner_alive(job):
        job = {**job, "status": "failed", "stage": "failed", "error": "Обробку перервано перезапуском студії. Запустіть її ще раз"}
    report_path = store.project_dir(pid) / "analysis" / job["id"] / "result.json"
    report = (status_views.analysis_report(report_path) if compact else store.read_json(report_path)) if include_report else None
    return {"job": status_views.job(job) if compact else job, "report": report, **({'compact':True} if compact else {})}


def create_video(project, asset_id, save_job, load_job, script=None):
    """One explicit author action: recognise once, direct, then create the complete film's frames."""
    with store.LOCK:
        current = latest(project['id'], load_job)
        job, report = current.get('job') or {}, current.get('report') or {}
        source = store.resolve_asset(project, asset_id)
        script_hashes = {report.get('script_sha256'), report.get('studio_script_sha256')}
        same_script = not isinstance(script, str) or not script.strip() or hashlib.sha256(script.strip().encode()).hexdigest() in script_hashes
        same_audio = report.get('source', {}).get('asset_id') == asset_id and report.get('source', {}).get('sha256') == store.audio_fingerprint(Path(source['path']))
        narration = store.load_project_narration(project['id']) or {}
        current_script = narration.get('script_sha256') in script_hashes
        if job.get('status') == 'complete' and report.get('applied') and same_audio and same_script and current_script:
            store.atomic_json(store.project_dir(project['id']) / 'analysis-state.json', {'job_id': job['id'], 'create_video': True})
            try:
                director.after_voice(project['id'], create_video=True)
            except Exception as error:
                job['handoff_error'] = str(error)
                save_job(job)
                raise
            if job.pop('handoff_error', None):
                save_job(job)
            return {**job, 'create_video': True}
        reuse={'reuse_report_id':job['id']} if job.get('status')=='complete' and same_audio and same_script and report.get('words') else {}
        return start(project, asset_id, save_job, load_job, script, create_video=True, **reuse)


def creation_status(project, load_job):
    pointer = store.read_json(store.project_dir(project['id']) / 'analysis-state.json', {})
    if not pointer.get('create_video'):
        handoff=(store.read_json(store.project_dir(project['id']) / 'automation.json', {}) or {}).get('montage') or {}
        if handoff.get('status') == 'failed':
            return {'status':'failed','stage':'recognizing','error':handoff.get('error')}
        return {'status': 'idle', 'stage': None}
    analysis = latest(project['id'], load_job, compact=True)
    job = analysis.get('job') or {}
    if job.get('status') in {'queued', 'running'}:
        return {'status': job['status'], 'stage': 'recognizing', 'progress': job.get('progress', 0), 'job': job}
    if job.get('status') == 'failed' or not (analysis.get('report') or {}).get('applied'):
        report=analysis.get('report') or {}
        blocking=speech.blocking_issues(bool(report.get('sequence_verification'))) | {'repeated_speech','out_of_order'}
        blocked=[str(row['number']) for row in report.get('phrases',[]) if blocking.intersection(row.get('issues',[]))]
        reason='Потрібно уточнити розпізнавання фраз: '+', '.join(blocked[:8]) if blocked else 'Текст не збігся з озвучкою'
        return {'status': 'failed', 'stage': 'recognizing', 'error': job.get('error') or reason}
    direction = director.state(project['id']) or {}
    if direction.get('status') in {'queued', 'running'}:
        return {'status': direction['status'], 'stage': 'planning'}
    request = project.get('production_request') or {}
    if job.get('handoff_error') and request.get('status') not in {'requested', 'in_progress'}:
        return {'status': 'failed', 'stage': 'planning', 'error': job['handoff_error']}
    if request:
        status = {'requested':'queued', 'in_progress':'running'}.get(request.get('status'), request.get('status'))
        return {'status': status, 'stage': 'creating', 'frames': request.get('frames'), 'error': request.get('error')}
    if direction.get('creation_error'):
        return {'status': 'failed', 'stage': 'creating', 'error': direction['creation_error']}
    if direction.get('status') == 'failed':
        return {'status': 'failed', 'stage': 'planning', 'error': direction.get('error')}
    plan = store.load_project_plan(project['id']) or {}
    count = len(plan.get('frames') or [])
    if count and set(range(1, count + 1)) <= set(store.made_frames(project, plan)):
        return {'status':'done', 'stage':'creating', 'frames':count}
    return {'status': 'queued', 'stage': 'creating'}


def start(project, asset_id, save_job, load_job, script=None, create_video=False, reuse_report_id=None):
    """Recognise a voice. The text comes from the author's script when there is one, else from the voice itself."""
    import director, production
    if project["id"] in director.ACTIVE or project["id"] in production.ACTIVE:
        # a new voice rebuilds the plan: not under the director or the frame agent at work
        raise store.StudioError("Над випуском зараз працює режисер або агент кадрів. Дочекайтеся, поки він закінчить", 409)
    source_data = store.load_project_source(project["id"]) if store.project_plan_mode(project) == "direct" else None
    plan = store.load_project_narration(project["id"])
    if isinstance(script, str) and script.strip():
        script, script_from = script.strip(), "request"
    elif plan and isinstance(plan.get("script"), str) and plan["script"].strip():
        script, script_from = plan["script"], "source" if source_data else "plan"
    elif isinstance(project.get("voice_script"), dict) and str(project["voice_script"].get("text") or "").strip():
        # An episode waits for its voice with the author's script saved on the project.
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
                if create_video:
                    store.atomic_json(store.project_dir(project['id']) / 'analysis-state.json', {'job_id': active['id'], 'create_video': True})
                    return {**active, 'create_video': True}
                return active
            raise store.StudioError("У цьому випуску вже обробляється інший файл", 409)
        job = {"id": uuid.uuid4().hex[:24], "type": "speech", "project_id": project["id"],
               "source_asset_id": asset_id, "source_name": asset["name"], "status": "queued",
               "progress": 0, "stage": "queued", "error": None, "created_at": time.time(), "owner_pid": os.getpid(),
               "script_from": script_from, "create_video": bool(create_video)}
        author_script=(store.load_project(project['id']).get('voice_script') or {}).get('text','')
        job['author_script_sha256']=hashlib.sha256(author_script.encode()).hexdigest()
        if reuse_report_id:job['reuse_report_id']=reuse_report_id
        save_job(job)
        ACTIVE_JOBS.add(job["id"])
        ACTIVE_PROJECTS[job["id"]] = project["id"]
        try:
            store.atomic_json(store.project_dir(project["id"]) / "analysis-state.json", {"job_id": job["id"], "create_video": bool(create_video)})
        except Exception:
            ACTIVE_JOBS.discard(job['id'])
            ACTIVE_PROJECTS.pop(job['id'], None)
            raise
    try:
        threading.Thread(target=worker, args=(job, script, save_job), daemon=True).start()
    except Exception:
        job.update(status='failed', stage='failed', error='Не вдалося запустити розпізнавання', finished_at=time.time())
        try:
            save_job(job)
        finally:
            ACTIVE_JOBS.discard(job['id'])
            ACTIVE_PROJECTS.pop(job['id'], None)
        raise
    return job


@job_timing.track('analysis', project='job', job='job')
def worker(job, script, save_job):
    def progress(value, stage="recognizing"):
        job_timing.advance({'loading_model':'recognition', 'recognizing':'recognition', 'comparing':'verification'}.get(stage, 'preparation'))
        job.update(status="running", progress=value, stage=stage)
        save_job(job)
    try:
        work = store.project_dir(job["project_id"]) / "analysis" / job["id"]
        work.mkdir(parents=True, exist_ok=True)
        with job_timing.queued_lock(RUN_LOCK):
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
                audio = narration_ending.import_audio(project, extracted, "speech-analysis")
                extracted.unlink(missing_ok=True)
                cache[original_hash] = {"asset_id": audio["id"], "sha256": store.audio_fingerprint(Path(audio["path"]))}
                store.atomic_json(cache_path, cache)
            audio = narration_ending.prepare_asset(project, audio)
            path = Path(audio["path"])
            duration = store.media_duration(path)
            if not duration or duration > 36000:
                raise RuntimeError("Не вдалося визначити тривалість аудіо або воно довше 10 годин")
            sequence = narration_sequence.verify(project, audio, script)
            audio_hash = store.audio_fingerprint(path)
            progress(15, "loading_model")
            previous=store.read_json(store.project_dir(project['id'])/'analysis'/job.get('reuse_report_id','unused')/'result.json',{}) or {}
            reusable=(previous.get('source',{}).get('sha256')==original_hash and previous.get('audio',{}).get('sha256')==audio_hash
                      and isinstance(script,str) and hashlib.sha256(script.encode()).hexdigest() in {previous.get('script_sha256'),previous.get('studio_script_sha256')} and previous.get('words'))
            if reusable:
                words,engine=list(previous['words']),dict(previous.get('engine') or {})
            else:
                try:
                    words, engine = speech.transcribe(path, duration, progress)
                except RuntimeError as error:
                    if not sequence or sequence.get('version') != 2 or not sequence.get('sentence_timings'):
                        raise
                    words, engine = [], {'engine': 'generated-takes', 'local': True, 'recognition_error': str(error)}
            # Generated takes supply measured sentence boundaries. ASR refines words
            # within those boundaries without rejecting the proven assembly.
            report = narration_sequence.align(script, words, duration, sequence) if sequence else None
            if report:
                engine.update(repaired_holes=0, repaired_script_phrases=0)
            else:
                words, engine["repaired_holes"] = speech_repair.repair(path, words, engine.get("language"))
                if script:
                    words,engine['repaired_script_phrases']=speech_repair.repair_script(path,script,words,engine.get('language'),duration=duration,sequence_verified=bool(sequence))
            if script is None:
                # No script from the author: the recognised voice becomes the script of the episode.
                script = speech.transcript_script(words)
            progress(90, "comparing")
            if report is None:
                report = speech.compare_script(script, words, duration, sequence_verified=True) if sequence else speech.compare_script(script, words, duration)
            if sequence:
                report['sequence_verification'] = sequence
            report.update(engine=engine, source={"asset_id": source["id"], "name": source["name"], "kind": source["kind"], "sha256": original_hash},
                          audio={"asset_id": audio["id"], "name": audio["name"], "duration": duration, "sha256": audio_hash},
                          script_sha256=hashlib.sha256(script.encode()).hexdigest(), words=words,
                          recognized_text=number_text.to_digits(" ".join(word["text"] for word in words)),
                          recognized_text_original=" ".join(word["text"] for word in words), applied=False, created_at=time.time(),
                          script_from=job.get("script_from", "plan"))
            if store.audio_fingerprint(original) != original_hash or store.audio_fingerprint(path) != audio_hash:
                report["status"] = "source_changed"
            with job_timing.span('saving'), store.LOCK:
                current = store.load_project_narration(project["id"])
                snapshot = store.load_project_source(project["id"]) if job.get("script_from") == "source" else current
                if job.get("script_from", "plan") in {"plan", "source"} and (not snapshot or snapshot.get("script") != script):
                    report["status"] = "script_changed"
                if job.get("script_from") == "project":
                    current_script = (store.load_project(project["id"]).get("voice_script") or {}).get("text")
                    if current_script != script:
                        report["status"] = "script_changed"
                if 'author_script_sha256' in job:
                    author_script=(store.load_project(project['id']).get('voice_script') or {}).get('text','')
                    if hashlib.sha256(author_script.encode()).hexdigest()!=job['author_script_sha256'] and author_script!=script:
                        report['status']='script_changed'
                if report["status"] == "matched":
                    timings = {**report["timings"], "audio_sha256": audio_hash, "asset_id": audio["id"]}
                    project = store.load_project(project["id"])
                    generated = store.generate_project_plan(project["channel_id"], project["name"], project["episode_path"],
                        script=script, hints=(current or {}).get("hints") if job.get("script_from", "plan") == "plan" else None,
                        project_id=project["id"], timings=timings)
                    report["studio_script_sha256"] = (generated.get("source") or generated["plan"])["script_sha256"]
                    report["applied"] = True
            store.atomic_json(work / "result.json", report)
            job.update(status="complete", progress=100, stage="complete", analysis_status=report["status"], applied=report["applied"])
        if report["applied"]:
            try:
                import keep
                threading.Thread(target=keep.keep_project, args=(project["id"],), daemon=True).start()
            except Exception:
                import traceback
                traceback.print_exc()
            try:
                # Publish completion and hand off under the same gate as a joining click.
                with store.LOCK:
                    pointer = store.read_json(store.project_dir(project['id']) / 'analysis-state.json', {})
                    if pointer.get('job_id') == job['id'] and pointer.get('create_video'):
                        director.after_voice(project['id'], create_video=True)
                    else:
                        director.after_voice(project["id"])
                    job.pop('handoff_error', None)
                    save_job(job)
            except Exception as error:   # keep applied recognition and expose a recoverable handoff failure
                job['handoff_error'] = str(error)
                import traceback
                traceback.print_exc()
    except (store.StudioError, RuntimeError) as error:
        job.update(status="failed", stage="failed", error=str(error))
    except Exception:
        import traceback
        traceback.print_exc()
        job.update(status="failed", stage="failed", error="Не вдалося обробити файл. Перевірте медіа та локальний Whisper")
    finally:
        job["finished_at"] = time.time()
        try:
            save_job(job)
        finally:
            ACTIVE_JOBS.discard(job["id"])
            ACTIVE_PROJECTS.pop(job["id"], None)
