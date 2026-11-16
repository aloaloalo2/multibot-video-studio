"""One pause for the whole episode: everything that works on it stops, and «Продовжити» starts each again where it was.

User, 16 November 2026: «плей пауза теж надіюсь вміють працювати тепер і запамятовувати що зупиняється всі процеси і
відновлюються?» The narration, the director (with the early «Підготовка», backend/script_timing.py) and the frame agent
now run side by side, so a pause of the frames alone no longer holds the episode still.

pause() writes episode-pause.json with what it stopped: the narration (its phrases stay in the cache and are not bought
again), the director with the reason of his run, the frame agent (production.pause keeps its session). While the file
is there nothing new starts on the episode: a recognition that ends, a director's run that would hand on to the frames,
an automatic handoff. Each of those gates notes its step instead (note()), and resume() runs the stopped work and the
noted steps. The file lives beside the project, so a pause outlives a restart of the Studio.
"""
from __future__ import annotations

import threading
import time

import store

LOCK = threading.RLock()
STOP_WAIT = 5.0


def path(pid: str):
    return store.project_dir(pid) / "episode-pause.json"


def paused(pid: str) -> dict | None:
    data = store.read_json(path(pid), None)
    return data if isinstance(data, dict) else None


def stopped_narration(pid: str) -> dict | None:
    """A narration the author stopped half way (its «Стоп»): the card offers play for it too, and play goes on from the
    phrases already made (user, 16 November 2026: «озвучку зупинив, але плея нема… 30 фраз готово»)."""
    import project_narration
    if pid in project_narration.ACTIVE:
        return None
    job = store.read_json(project_narration.root(pid) / "job.json", {}) or {}
    # a record left «running» by a crash of the studio is a stopped narration too (no worker runs it any more)
    if job.get("status") in {"queued", "running", "cancelling"}:
        job = {**job, "status": "failed"}
    # stopped by the author, or by HeyGen's limit: either way play goes on from the phrases already made
    if job.get("status") not in {"cancelled", "failed"} or not job.get("script") or int(job.get("completed") or 0) >= int(job.get("total") or 0):
        return None
    try:
        project = store.load_project(pid)
    except store.StudioError:
        return None
    if (project.get("voice_script") or {}).get("text") != job["script"]:
        return None   # the script changed since: a new narration is the author's choice
    if project.get("narration_source") == "file" or float(project.get("restarted_at") or 0) > float(job.get("started_at") or 0):
        return None   # the author brought the voice another way, or started the episode over
    try:
        plan = store.load_project_plan(pid) or {}
    except (store.StudioError, OSError, ValueError):
        plan = {}
    if (plan.get("timing") or {}).get("status") == "audio_synced":
        return None   # the film already follows a finished voice: that narration is history
    return job


def resumable(pid: str) -> bool:
    return paused(pid) is not None or stopped_narration(pid) is not None


def label(pid: str) -> str | None:
    """What the card says while the episode waits for play: the stopped work itself, as it read while it ran
    (user, 16 November 2026: «не на паузі має бути, а озвучка там, як раніше писало»)."""
    import project_narration
    data = paused(pid)
    stopped = (data or {}).get("stopped") or ({"narration": {}} if stopped_narration(pid) else {})
    if not stopped:
        return None
    if "narration" in stopped:
        job = store.read_json(project_narration.root(pid) / "job.json", {}) or {}
        total = int(job.get("total") or 0)
        done = max(int(job.get("completed") or 0), int(job.get("cached") or 0))   # made phrases count from the start
        return f"Озвучка · {round(100 * done / total)}%" if total else "Озвучка"
    if "director" in stopped:
        return "Режисура"
    if "languages" in stopped:
        items = stopped["languages"]
        word = "Переклад" if all(i["kind"] == "translate" for i in items) else "Озвучка перекладу"
        return word + " · " + ", ".join(i["code"].upper() for i in items)
    return None   # the frames: the card shows their own stopped line


def started_by_hand(pid: str, part: str, kind: str | None = None, code: str | None = None) -> None:
    """The author started paused work again by hand (a language's «Озвучити» on a paused episode, 16 November 2026: the
    card kept «Озвучка перекладу · PL» with play while PL was voiced). That work leaves the pause; an empty pause ends."""
    with LOCK:
        data = paused(pid)
        if data is None:
            return
        stopped = data.get("stopped") or {}
        if part == "languages":
            left = [item for item in stopped.get("languages", []) if not (item.get("kind") == kind and item.get("code") == code)]
            if left:
                stopped["languages"] = left
            else:
                stopped.pop("languages", None)
        else:
            stopped.pop(part, None)
        data["stopped"] = stopped
        if not stopped and not data.get("pending"):
            path(pid).unlink(missing_ok=True)
        else:
            store.atomic_json(path(pid), data)


def note(pid: str, step: str, **details) -> bool:
    """A step that would start now on a paused episode waits for resume(). True when the episode is paused."""
    with LOCK:
        data = paused(pid)
        if data is None:
            return False
        pending = data.setdefault("pending", {})
        pending[step] = {**pending.get(step, {}), **details, "at": time.time()}
        store.atomic_json(path(pid), data)
        return True


def _wait(test, limit: float = STOP_WAIT) -> None:
    until = time.monotonic() + limit
    while test() and time.monotonic() < until:
        time.sleep(.05)


def running(pid: str) -> dict:
    """What works on the episode now and can be paused."""
    import director
    import production
    import project_narration
    project = store.load_project(pid)
    found = {}
    if pid in project_narration.ACTIVE:
        job = store.read_json(project_narration.root(pid) / "job.json", {}) or {}
        found["narration"] = {"script": job.get("script") or (project.get("voice_script") or {}).get("text")}
    if pid in director.ACTIVE:
        state = director.state(pid) or {}
        found["director"] = {"reason": state.get("reason") or "voice", "create_video": bool(state.get("create_video"))}
    if (project.get("production_request") or {}).get("status") in {"requested", "in_progress"}:
        found["production"] = {}
    import languages
    jobs = (languages.load_state(pid).get("jobs") or {})
    # translations and their voices (a thumbnail of a language is quick and left to finish)
    words = [{"kind": job["kind"], "code": job["code"]} for slot, job in jobs.items()
             if languages.job_key(pid, job.get("code", ""), "voice") in languages.ACTIVE and slot.endswith("|voice")
             and job.get("kind") in {"translate", "voice"} and job.get("status") == "running"]
    if words:
        found["languages"] = words
    return found


def pause(pid: str) -> dict:
    import director
    import production
    import project_narration
    with LOCK:
        work = running(pid)
        current = paused(pid)
        if not work:
            if current:
                return current
            raise store.StudioError("Над випуском зараз нічого не працює", 409)
        # a pause taken while one is on (work started by hand meanwhile) adds what runs now to it
        data = current or {"paused_at": time.time(), "stopped": {}, "pending": {}}
        data["stopped"] = {**data.get("stopped", {}), **work}
        store.atomic_json(path(pid), data)   # first: whatever ends while it stops finds the pause
    # the stops are sent at once and the answer goes back at once, like «Стоп» (user, 16 November 2026: «пауза не така
    # швидка, як стоп»); the phrase or part being made finishes in the background and is kept
    if "narration" in work:
        project_narration.cancel(pid)
    if "languages" in work:
        import languages
        for item in work["languages"]:
            languages.cancel(pid, f"{item['code']}|voice")
    if "director" in work:
        director.stop(pid, "director")
    if "production" in work:
        production.pause(pid)   # at most a couple of seconds; a play right after finds the request paused
    if "director" in work:
        threading.Thread(target=_settle_director, args=(pid, data), daemon=True).start()
    return data


def _settle_director(pid: str, data: dict) -> None:
    import director
    _wait(lambda: pid in director.ACTIVE, 30.0)
    import planner
    state = director.state(pid) or {}
    plan = store.load_project_plan(pid) or {}
    file = store.project_plan_file(store.load_project(pid))
    # stopped during the early «Підготовка»: his plan is written, only the kit is left, and production makes it
    directed = (plan.get("frame_source") == planner.DIRECTOR_FRAME_SOURCE and not plan.get("director_stale")
                and file is not None and file.stat().st_mtime >= float(state.get("started_at") or 0))
    with LOCK:
        current = paused(pid)
        if current is None or pid in director.ACTIVE:
            return   # already resumed, or a new run started: nothing to mark
        current["stopped"]["director"]["directed"] = directed
        store.atomic_json(path(pid), current)
        state.update(status="done" if directed else "paused", stage=None, finished_at=time.time())
        director.save(pid, state)


def resume(pid: str) -> dict:
    import director
    import production
    import project_narration
    with LOCK:
        data = paused(pid)
        if data is None:
            job = stopped_narration(pid)
            if job is None:
                raise store.StudioError("Випуск не на паузі", 409)
            data = {"stopped": {"narration": {"script": job["script"]}}, "pending": {}}
        import languages
        if pid in project_narration.ACTIVE or pid in director.ACTIVE or pid in production.ACTIVE or any(
                languages.job_key(pid, item["code"], "voice") in languages.ACTIVE for item in (data.get("stopped") or {}).get("languages", [])):
            raise store.StudioError("Ще зупиняємо попередню роботу. Спробуйте за кілька секунд", 409)
        path(pid).unlink(missing_ok=True)
    stopped, pending, errors = data.get("stopped") or {}, data.get("pending") or {}, []
    later = []   # steps that may run a long subprocess (a retime): after the answer, in the background

    def step(action):
        try:
            action()
        except (store.StudioError, OSError, RuntimeError) as error:
            errors.append(str(error))

    narration = stopped.get("narration")
    if narration and narration.get("script"):
        project = store.load_project(pid)
        job = store.read_json(project_narration.root(pid) / "job.json", {}) or {}
        if (project.get("voice_script") or {}).get("text") != narration["script"]:
            errors.append("Сценарій змінився під час паузи: запустіть озвучку нового тексту окремо")
        elif job.get("status") != "done" or job.get("script") != narration["script"]:
            step(lambda: project_narration.start(project, narration["script"], resume=True))
    run = stopped.get("director")
    if run and not run.get("directed"):
        # his plan may have been written after the pause (its last request was on the way): read the plan itself
        import planner
        plan = store.load_project_plan(pid) or {}
        if plan.get("frame_source") == planner.DIRECTOR_FRAME_SOURCE and not plan.get("director_stale"):
            run = {**run, "directed": True}
            state = director.state(pid) or {}
            if state.get("status") in {"paused", "running", "queued"}:
                director.save(pid, {**state, "status": "done"})
    if run and run.get("directed"):
        if run.get("create_video"):
            later.append(lambda: director.after_voice(pid, create_video=True))
    elif run:
        step(lambda: director.start(pid, "create_video" if run.get("create_video") else run.get("reason") or "voice"))
    if "after_voice" in pending:
        later.append(lambda: director.after_voice(pid, create_video=bool(pending["after_voice"].get("create_video"))))
    if "production" in stopped:
        request = store.load_project(pid).get("production_request") or {}
        if request.get("paused"):
            step(lambda: production.resume(pid))
    elif "production" in pending:
        step(lambda: production.start_from_plan(pid))
    for item in stopped.get("languages", []):
        # a translation goes on from its saved draft, a voice from its paid phrases
        step(lambda item=item: languages.start(pid, item["kind"], item["code"]))
    import episode_automation
    if "voice" in pending:
        step(lambda: episode_automation.after_script(pid, pending["voice"].get("draft") or {}))
    for key in pending:
        if key.startswith("translation_voice:"):
            code = key.split(":", 1)[1]
            step(lambda code=code: episode_automation.after_translation(pid, code, {"kind": "translate", "status": "done"}))
    if "translations" in pending:
        step(lambda: episode_automation.translate_all(pid))
    if "montage" in pending:
        later.append(lambda: episode_automation.after_voice(pid, pending["montage"].get("job") or {}))
    if later:
        def run_later():
            for action in later:
                try:
                    action()
                except Exception:
                    import traceback
                    traceback.print_exc()
        threading.Thread(target=run_later, daemon=True).start()
    return {"resumed": sorted(set(stopped) | set(pending)), "errors": errors}
