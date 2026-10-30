"""«Звільнити місце» on a project card: the extra copies of an episode's frames, with their size before anything goes.

Two kinds are safe to remove. The Razgon project's build folder is the render workshop: every frame rendered as its own
clip, the film without sound, uncompressed music and mix, seam strips and review stills. All of it is made again from the
scenes, and the studio plays from its own copies, never from there. The studio's own copies of frames that a later render
replaced stay only for «Скасувати»: they go together with the undo steps that still show them. The frames on the
timeline, the voice, the scenes and the finished film in the episode folder are not touched.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import director
import frame_progress
import production
import store

# the live view writes its log here while it runs; it is a few bytes
KEEP_IN_BUILD = {"live.log"}


def size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.is_dir() else 0


def build_items(project: dict) -> list[Path]:
    """What the Razgon build folder holds that may go: everything but the live log and files the studio still points at."""
    razgon = frame_progress.razgon_project(project)
    build = razgon / "build" if razgon else None
    if not build or not build.is_dir():
        return []
    held = [Path(asset.get("path") or "").resolve() for asset in project.get("assets", [])]
    return [item for item in build.iterdir() if item.name not in KEEP_IN_BUILD
            and not any(path == item.resolve() or item.resolve() in path.parents for path in held)]


def old_renders(pid: str, project: dict) -> list[dict]:
    """Studio copies of frame renders the timeline no longer shows (the bridge's names in the project's media)."""
    media = (store.project_dir(pid) / "media").resolve()
    used = {clip.get("asset_id") for track in project.get("tracks", []) for clip in track.get("clips", [])}
    return [asset for asset in project.get("assets", []) if asset.get("id") not in used
            and Path(asset.get("path") or "").parent.resolve() == media
            and store.RAZGON_RENDER.fullmatch(Path(asset.get("path") or "").name) and Path(asset["path"]).is_file()]


def busy(pid: str) -> str | None:
    if pid in director.ACTIVE:
        return "Зараз іде режисура"
    if pid in production.ACTIVE:
        return "Зараз агент малює кадри"
    return None


def usage(pid: str) -> dict:
    project = store.load_project(pid)
    build = sum(size(item) for item in build_items(project))
    old = old_renders(pid, project)
    renders = sum(Path(asset["path"]).stat().st_size for asset in old)
    return {"build": build, "old_renders": renders, "old_count": len(old), "total": build + renders, "busy": busy(pid)}


def clip_assets(snapshot: dict) -> set:
    return {clip.get("asset_id") for track in snapshot.get("tracks", []) for clip in track.get("clips", [])}


def free(pid: str) -> dict:
    reason = busy(pid)
    if reason:
        raise store.StudioError(f"{reason}. Звільнити місце можна, коли робота закінчиться", 409)
    freed = 0
    # the workshop goes first and outside the studio's lock: removing gigabytes takes a moment
    for item in build_items(store.load_project(pid)):
        freed += size(item)
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)
    with store.LOCK:
        store.migrate_history(pid)
        project = store.load_project(pid)
        old = old_renders(pid, project)
        if old:
            ids = {asset["id"] for asset in old}
            # undo steps that still show those frames go with them: the oldest steps up to the last one that holds any,
            # so the steps left form one unbroken chain
            past = store.history_entries(pid, "past")
            holding = [index for index, entry in enumerate(past) if ids & clip_assets(store.read_json(entry, {}) or {})]
            for entry in past[:holding[-1] + 1] if holding else []:
                entry.unlink()
            if any(ids & clip_assets(store.read_json(entry, {}) or {}) for entry in store.history_entries(pid, "future")):
                store.clear_history(pid, "future")
            for asset in old:
                freed += Path(asset["path"]).stat().st_size
                Path(asset["path"]).unlink()
            # the media list is not part of an edit, so the revision stays and an open editor is not interrupted
            project["assets"] = [asset for asset in project.get("assets", []) if asset.get("id") not in ids]
            store.save_project(project)
    return {"freed": freed}
