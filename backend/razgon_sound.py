"""Music and sound effects of an animated film on the Studio timeline, with no video rendered.

Since the frames are rendered only by «Експорт MP4» (30 October 2026) nothing laid Razgon's music-and-effects clip on
the timeline: only `razgon_bridge.py push` did, and the agents may not push. So «Наживо» and the «Мови» tab's «Озвучка
зі звуком» files, which take the timeline's sound, had the voice alone (episode 07, 5 November 2026). Now the Studio
runs `razgon_bridge.py sound` itself when the director has written the shots of a film Razgon draws whole, and again
when the frame agent's run is done (it may have added cues): Razgon's own mix of music, SFX and ambience without the
voice, as M4A on its own layer «Razgon · музика й ефекти» under the channel plate. It renders no picture, so it runs
under the agents' MULTIBOT_RENDER_ON_EXPORT too. A bed equal to the one on the timeline stays; a new one makes the
saved language soundtracks read «outdated» through their sound signature (language_mix.snapshot). The run's state
lives in sound.json beside the project and the bridge's output in sound.log; studio_restart.py waits for it.
"""
from __future__ import annotations

import os, subprocess, sys, threading, time
from pathlib import Path

import store

BRIDGE = store.APP_ROOT / "tools" / "razgon_bridge.py"
# the bridge waits up to 30 minutes for Razgon renders to finish, the mix itself takes a few minutes for an hour of film
TIMEOUT = 3600
ACTIVE: set[str] = set()
AGAIN: set[str] = set()   # asked again while a run worked: one more run follows with the newest shots
LOCK = threading.Lock()


def state_path(pid: str) -> Path:
    return store.project_dir(pid) / "sound.json"


def state(pid: str) -> dict | None:
    data = store.read_json(state_path(pid), None)
    if isinstance(data, dict) and data.get("status") in {"queued", "running"} and pid not in ACTIVE:
        data.update(status="failed", error="Студію перезапустили, поки збиралися музика й ефекти")
    return data


def due(project: dict) -> dict | None:
    """The Razgon link of a film that gets its bed from Razgon: an animated channel's film with a Razgon project.
    A mixed episode (Razgon frames among photos) is told apart by the bridge, which refuses it."""
    if not project.get("episode_path") or store.project_plan_mode(project) == "direct" or not store.project_animated(project):
        return None
    link = store.razgon_link(project)
    return link if link and Path(link.get("project") or "").is_dir() else None


def start(pid: str, reason: str) -> bool:
    """Build and lay the bed in the background; True when a run was started or queued after the running one."""
    try:
        link = due(store.load_project(pid))
    except (store.StudioError, OSError):
        return False
    if not link:
        return False
    with LOCK:
        if pid in ACTIVE:
            AGAIN.add(pid)
            return True
        ACTIVE.add(pid)
    store.atomic_json(state_path(pid), {"status": "queued", "reason": reason, "queued_at": time.time()})
    threading.Thread(target=run, args=(pid, reason), daemon=True).start()
    return True


def run(pid: str, reason: str) -> None:
    try:
        while True:
            _run(pid, reason)
            with LOCK:
                if pid not in AGAIN:
                    ACTIVE.discard(pid)
                    return
                AGAIN.discard(pid)
            reason = "again"
    except BaseException:
        with LOCK:
            ACTIVE.discard(pid)
            AGAIN.discard(pid)
        raise


def command(link: dict) -> list[str]:
    # at a lower priority: the author keeps working while the mix runs
    return ["nice", "-n", "10", sys.executable, str(BRIDGE), "sound", "--razgon", str(link["project"])]


def _run(pid: str, reason: str) -> None:
    data = {"status": "running", "reason": reason, "started_at": time.time()}
    store.atomic_json(state_path(pid), data)
    try:
        link = due(store.load_project(pid))
        if not link:
            data.update(status="skipped", summary="Це не анімаційний ролик Razgon")
            return
        result = subprocess.run(command(link), cwd=store.APP_ROOT, capture_output=True, text=True, timeout=TIMEOUT,
                                env={**os.environ, "MULTIBOT_RENDER_ON_EXPORT": "1"})
        (store.project_dir(pid) / "sound.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if result.returncode:
            problem = [line for line in result.stderr.splitlines() if line.strip()]
            data.update(status="failed", error=(problem[-1] if problem else f"razgon_bridge.py sound завершився з кодом {result.returncode}")[-600:])
        else:
            data.update(status="done", summary=lines[-1] if lines else "")
            import language_mix   # the new bed belongs in every saved language soundtrack too
            language_mix.refresh(pid, "music and effects")
    except subprocess.TimeoutExpired:
        data.update(status="failed", error="Музика й ефекти не зібралися за годину")
    except (OSError, store.StudioError) as error:
        data.update(status="failed", error=str(error))
    finally:
        data["finished_at"] = time.time()
        try:
            store.atomic_json(state_path(pid), data)
        except OSError:
            pass
