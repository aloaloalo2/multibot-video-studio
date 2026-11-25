"""Sounds on what really happens in the Razgon frames of a regular film (user, 25 November 2026: «появляється щось,
звук появляється відповідний… щось пише, появляється звук… якщо довго пише, то довго звук»).

The frame agent used to guess the times of its sound cues after writing a scene; nothing compared them with the
picture. Here the scenes themselves are read: Razgon's `render.mjs --events` draws the frames without a picture and
notes when a line of text comes in, when a picture comes in and how long a text is written letter by letter; the
montage operation `appear_sounds` (soundtrack.appear) lays the channel's sounds on those moments. Free and local: no
model, no render, about three minutes for a 24-minute film.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

import store

RUNNING: set[str] = set()
LOCK = threading.Lock()
TIMEOUT = 1800


def frames_span(project: dict, frames=None) -> tuple[float, float] | None:
    """(from, to) of the Razgon blocks on the timeline, or of the requested frames among them."""
    spans = []
    for track in project.get("tracks", []):
        for clip in track.get("clips", []):
            title = str(clip.get("title", ""))
            if not title.startswith("Razgon · кадр"):
                continue
            try:
                number = int(title.rsplit(" ", 1)[-1])
            except ValueError:
                number = None
            if frames is not None and number not in frames:
                continue
            spans.append((float(clip["start"]), float(clip["start"]) + float(clip["duration"])))
    if not spans:
        return None
    return min(a for a, _ in spans), max(b for _, b in spans)


def scan(project: dict, frames=None) -> dict | None:
    """The events of the Razgon frames ({'events': [...]}) read from their code, or None without Razgon frames."""
    link = store.razgon_link(project) or {}
    root, razgon = link.get("razgon_root"), link.get("project")
    span = frames_span(project, frames)
    if not (root and razgon and span and Path(razgon, "config.json").is_file()):
        return None
    out = store.cache_dir(project) / "razgon-events.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    command = ["nice", "-n", "10", "node", "render.mjs", "--project", str(razgon), "--events", "--scale", "0.5",
               "--from", f"{max(0.0, span[0] - 0.2):.3f}", "--to", f"{span[1] + 0.2:.3f}", "--out", str(out)]
    done = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=TIMEOUT,
                          env={**os.environ, "MULTIBOT_RENDER_ON_EXPORT": "1"})
    if done.returncode != 0 or not out.is_file():
        raise RuntimeError(((done.stdout or "") + (done.stderr or "")).strip()[-600:] or "the scan gave no events")
    return json.loads(out.read_text(encoding="utf-8"))


def run(pid: str, frames=None) -> str:
    """Scan the Razgon frames (all, or `frames`) and lay their sounds; a short report."""
    import montage_ops
    project = store.load_project(pid)
    if store.project_animated(project):
        return "анімаційний фільм: звук кладе сам Razgon"
    found = scan(project, frames)
    if found is None:
        return "у ролику немає кадрів Razgon"
    op = {"op": "appear_sounds", "events": found.get("events", []), "prune_guessed": True}
    if frames is not None:
        op["frames"] = sorted(frames)
    result = montage_ops.run(pid, [op])
    return "; ".join(result.get("report", [])) if isinstance(result, dict) else str(result)


def start(pid: str, frames=None) -> bool:
    """run() in the background, one at a time a project; never breaks what called it."""
    with LOCK:
        if pid in RUNNING:
            return False
        RUNNING.add(pid)

    def work():
        try:
            print(f"[event sounds] {pid}: {run(pid, frames)}", flush=True)
        except Exception as error:   # the film is fine without them; the author can run them again
            print(f"[event sounds] {pid}: {error}", flush=True)
        finally:
            with LOCK:
                RUNNING.discard(pid)
    threading.Thread(target=work, daemon=True).start()
    return True
