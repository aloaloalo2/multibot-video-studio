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


def _wait(test) -> None:
    until = time.monotonic() + STOP_WAIT
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
    return found


def pause(pid: str) -> dict:
    import director
    import production
    import project_narration
    with LOCK:
        if paused(pid):
            return paused(pid)
        work = running(pid)
        if not work:
            raise store.StudioError("Над випуском зараз нічого не працює", 409)
        data = {"paused_at": time.time(), "stopped": work, "pending": {}}
        store.atomic_json(path(pid), data)   # first: whatever ends while it stops finds the pause
    if "narration" in work:
        project_narration.cancel(pid)
    if "director" in work:
        director.stop(pid, "director")
    if "production" in work:
        production.pause(pid)
    _wait(lambda: pid in project_narration.ACTIVE or pid in director.ACTIVE)
    if "director" in work:
        import planner
        state = director.state(pid) or {}
        plan = store.load_project_plan(pid) or {}
        file = store.project_plan_file(store.load_project(pid))
        # stopped during the early «Підготовка»: his plan is written, only the kit is left, and production makes it
        directed = (plan.get("frame_source") == planner.DIRECTOR_FRAME_SOURCE and not plan.get("director_stale")
                    and file is not None and file.stat().st_mtime >= float(state.get("started_at") or 0))
        with LOCK:
            current = paused(pid) or data
            current["stopped"]["director"]["directed"] = directed
            store.atomic_json(path(pid), current)
        state.update(status="done" if directed else "paused", stage=None, finished_at=time.time())
        director.save(pid, state)
    return paused(pid) or data


def resume(pid: str) -> dict:
    import director
    import production
    import project_narration
    with LOCK:
        data = paused(pid)
        if data is None:
            raise store.StudioError("Випуск не на паузі", 409)
        if pid in project_narration.ACTIVE or pid in director.ACTIVE:
            raise store.StudioError("Ще зупиняємо попередню роботу. Спробуйте за кілька секунд", 409)
        path(pid).unlink(missing_ok=True)
    stopped, pending, errors = data.get("stopped") or {}, data.get("pending") or {}, []

    def step(action):
        try:
            action()
        except (store.StudioError, OSError, RuntimeError) as error:
            errors.append(str(error))

    narration = stopped.get("narration")
    if narration and narration.get("script"):
        step(lambda: project_narration.start(store.load_project(pid), narration["script"], resume=True))
    run = stopped.get("director")
    if run and run.get("directed"):
        if run.get("create_video"):
            step(lambda: director.after_voice(pid, create_video=True))
    elif run:
        step(lambda: director.start(pid, "create_video" if run.get("create_video") else run.get("reason") or "voice"))
    if "after_voice" in pending:
        step(lambda: director.after_voice(pid, create_video=bool(pending["after_voice"].get("create_video"))))
    if "production" in stopped:
        request = store.load_project(pid).get("production_request") or {}
        if request.get("paused"):
            step(lambda: production.resume(pid))
    elif "production" in pending:
        step(lambda: production.start_from_plan(pid))
    if "montage" in pending:
        import episode_automation
        step(lambda: episode_automation.after_voice(pid, pending["montage"].get("job") or {}))
    return {"resumed": sorted(set(stopped) | set(pending)), "errors": errors}
