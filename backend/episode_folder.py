"""A renamed episode takes its folder's name along (user, 15 November 2026: «зміна імені проекта… змінить назву
папки? я думаю варто так зробити»).

The episode folder's path sits in the project (episode_path, asset paths, its history, plans, language files) and in
its Razgon project (story/studio_frames.json), so the folder is renamed and that one project's files get the new path
in the same step (path_rewrite). Nothing else moves: another project, the channel, the logs. The folder keeps its old
name when it is missing, when the new name is already taken in the channel, or when nothing would change.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

import path_rewrite
import store

MAX = 120


def folder_name(name: str) -> str:
    """The episode's name as a folder name: no «/» or «:», no leading dot, no trailing dot or space."""
    text = unicodedata.normalize("NFC", re.sub(r"[/:\x00-\x1f]+", " ", str(name or "")))
    text = re.sub(r"\s+", " ", text).strip().lstrip(".").rstrip(". ")
    return text[:MAX].rstrip(". ")


def follow(pid: str) -> dict:
    """Give the episode folder the project's current name. Returns {"moved": bool, "note": str, "path": str}."""
    with store.LOCK:
        project = store.load_project(pid)
        old = Path(project.get("episode_path") or "")
        if not project.get("episode_path") or not old.is_dir():
            return {"moved": False, "note": ""}
        name = folder_name(project.get("name"))
        if not name or unicodedata.normalize("NFC", old.name) == name:
            return {"moved": False, "note": "", "path": str(old)}
        new = old.with_name(name)
        if new.exists():
            return {"moved": False, "path": str(old),
                    "note": f"Папка «{name}» у каналі вже є, тому папка випуску лишилася «{old.name}»."}
        roots = [store.project_dir(pid)]
        link = store.razgon_link(project) or {}
        if link.get("project") and Path(link["project"]).is_dir():
            roots.append(Path(link["project"]))
        found = path_rewrite.changes(path_rewrite.text_files(roots), path_rewrite.pairs(old, new))
        os.rename(old, new)
        try:
            path_rewrite.write(found)
        except OSError:
            os.rename(new, old)   # the project still names the old folder: put it back
            raise
    try:
        import language_mix
        language_mix.refresh_later(pid, "episode folder renamed")   # the saved soundtracks name their new path
    except Exception:
        pass
    return {"moved": True, "note": "", "path": str(new)}
