"""The sound of an episode kept in the studio, so an old episode still plays after its folder is deleted (user,
2 November 2026: «після видалення папки… не можу передивитися старі проєкти… нема озвучки»).

The voice, music and effects on the timeline lie in the episode folder (or are picked from it). Each sound clip's file
gets a compressed copy in the studio's data, `projects/<id>/kept/<asset id>.m4a` (AAC 96 kbit/s: about 40 MB an hour of
voice), made once while the original is there: at every start and after a voice is recognised. store.resolve_asset
falls back to it when the original is gone, so the preview, the plan's voice player and the export keep the sound.
Pictures and videos are not kept: they are what deleting the folder is for.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import store


def kept_path(pid: str, aid: str) -> Path:
    return store.PROJECTS_ROOT / pid / "kept" / f"{aid}.m4a"


def keep_project(pid: str) -> int:
    """Make the missing copies of one project's sound clips; returns how many were made."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return 0
    try:
        project = store.load_project(pid)
    except (store.StudioError, OSError, ValueError):
        return 0
    used = {clip.get("asset_id") for track in project.get("tracks", []) for clip in track.get("clips", []) if clip.get("kind") == "audio"}
    try:   # the voice of the plan too: the plan page plays it before any frame is on the timeline
        used.add((((store.load_project_plan(pid) or {}).get("timing") or {}).get("audio") or {}).get("asset_id"))
    except (store.StudioError, OSError, ValueError):
        pass
    made = 0
    for asset in project.get("assets", []):
        if asset.get("id") not in used:
            continue
        source, target = Path(asset.get("path") or ""), kept_path(pid, asset["id"])
        if target.is_file():
            continue
        if not source.is_file():
            # gone from the episode folder: copied from where the studio still finds it (Razgon's voice, its bed)
            try:
                found = store.resolve_asset(project, asset["id"])
            except (store.StudioError, OSError):
                continue
            source = Path(found["path"])
            if not source.is_file() or source.suffix == ".m4a" and source.parent.name == "kept":
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.stem + ".tmp.m4a")
        try:
            run = subprocess.run(["nice", "-n", "10", ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                                  "-vn", "-c:a", "aac", "-b:a", "96k", str(temp)], capture_output=True, timeout=1800)
        except (OSError, subprocess.SubprocessError):
            temp.unlink(missing_ok=True)
            continue
        if run.returncode == 0 and temp.is_file() and temp.stat().st_size > 0:
            temp.replace(target)
            made += 1
        else:
            temp.unlink(missing_ok=True)
    return made


def keep_all() -> None:
    """At start: every project's sound gets its copy while its files are still there. Never stops the studio."""
    if not store.PROJECTS_ROOT.is_dir():
        return
    for folder in sorted(store.PROJECTS_ROOT.iterdir()):
        if (folder / "project.json").is_file():
            try:
                keep_project(folder.name)
            except Exception:   # one odd project must not stop the others
                continue
