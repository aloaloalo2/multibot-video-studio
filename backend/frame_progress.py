"""Which frames of a Razgon episode the agent has already drawn as scenes, before they are rendered into the Studio.

The frame agent writes a scene for each shot first (every scene file under scenes/ registers its shots with
take('eNN', ...)), and only later renders a batch, checks it and pushes the pictures to the timeline. Until then the
timeline holds just the frame's code block, which reads as empty. A Studio frame counts as drawn once every shot it
shows has a scene; the answer is cached until a scene or the story changes.
"""
from __future__ import annotations

import re
from pathlib import Path

import store

# any take id: What If's e01, e51 and the per-frame f004s01 of a mixed episode (Alexey Gorbunov, 31 October 2026)
TAKE = re.compile(r"take\(\s*['\"]([\w-]+)['\"]")
# a take in several parts registers them in a loop: for (const id of ['e51', 'e52']) take(id, ...)
TAKE_LOOP = re.compile(r"for\s*\(\s*const\s+(\w+)\s+of\s+\[([^\]]*)\]\s*\)\s*take\(\s*\1\b")
SHOT_ID = re.compile(r"['\"]([\w-]+)['\"]")
_CACHE: dict[str, tuple[tuple, list[int]]] = {}


def taken(text: str) -> set[str]:
    """The shot ids a scene file registers, written out or in a loop."""
    ids = set(TAKE.findall(text))
    for _, items in TAKE_LOOP.findall(text):
        ids |= set(SHOT_ID.findall(items))
    return ids


def razgon_project(project: dict) -> Path | None:
    link = store.read_json(Path(project.get("episode_path") or "") / "razgon.json", None)
    path = Path(link["project"]) if isinstance(link, dict) and link.get("project") else None
    return path if path and path.is_dir() else None


def drawn(pid: str) -> list[int]:
    razgon = razgon_project(store.load_project(pid))
    if not razgon:
        return []
    story, frames = razgon / "story" / "shots.json", razgon / "story" / "studio_frames.json"
    scenes = sorted((razgon / "scenes").rglob("*.js")) if (razgon / "scenes").is_dir() else []
    if not story.is_file() or not frames.is_file():
        return []
    key = tuple((str(path), path.stat().st_mtime_ns) for path in [story, frames, *scenes])
    if _CACHE.get(pid, (None,))[0] == key:
        return _CACHE[pid][1]
    registered = set()
    for path in scenes:
        registered |= taken(path.read_text(encoding="utf-8", errors="replace"))
    shots = (store.read_json(story, {}) or {}).get("shots") or []
    result = []
    for frame in (store.read_json(frames, {}) or {}).get("frames") or []:
        ids = [shot["id"] for shot in shots if shot["start"] < frame["end"] - 1e-3 and shot["end"] > frame["start"] + 1e-3]
        if ids and all(item in registered for item in ids):
            result.append(int(frame["number"]))
    _CACHE[pid] = (key, result)
    return result
