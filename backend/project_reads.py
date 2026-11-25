"""store.load_project once per version of what it reads, for the running server only.

A project read parses project.json, binds the channel's current logo (logo_layer.bind) and marks every transition with
its lead (joins.anchor, which measures the videos at each seam). On a long episode that took 0.25 s, and one poll of
«Статус студії» read the same project three times, so the UI waited seconds while an agent worked (25 November 2026:
1.2-4.5 s a status poll, 2-11 s the project list). The result is kept as a pickle together with the files it was made
from: project.json, the channel's settings and logo, the channel folder listing and every video and logo file of the
project. A read whose files are all unchanged gets a fresh copy of the kept result (a pickle load, about 4 ms for the
longest episode), so callers may change what they get as before. Anything changed reads the project again.

`install()` is called by app.main(); tests and tools keep the plain store.load_project unless they install it.
"""
from __future__ import annotations

import os
import pickle
import threading

import store

LIMIT = 96          # projects kept; the least recently read go first
_CACHE: dict[str, tuple] = {}   # pid -> (key, dependency paths, pickled project)
_LOCK = threading.Lock()
_ORIGINAL = None
STATS = {"hits": 0, "misses": 0}


def _stat(path) -> tuple | None:
    try:
        value = os.stat(path)
    except (OSError, TypeError, ValueError):
        return None
    return value.st_mtime_ns, value.st_size


def _paths(pid: str, project: dict) -> tuple:
    """The files a project read depends on, besides the channel folder listing."""
    paths = [str(store.project_path(pid))]
    cid = project.get("channel_id")
    if cid:
        channel = store.DATA_ROOT / "channels" / str(cid)
        paths += [str(channel / "settings.json"), str(channel / "logo.png")]
        try:   # an old installation may still read its settings from the channel folder
            paths.append(str(store.channel_settings_source(store.get_channel_folder(cid, include_disabled=True))))
        except (store.StudioError, OSError):
            pass
    for asset in project.get("assets", []) or []:
        path = asset.get("path") if isinstance(asset, dict) else None
        # videos are measured at the seams; the logo overlay must still be there
        if path and (asset.get("kind") == "video" or asset.get("source") == "channel-logo"
                     or os.path.splitext(str(path))[1].lower() in {".mp4", ".mov", ".webm", ".mkv", ".m4v"}):
            paths.append(str(path))
    return tuple(dict.fromkeys(paths))


def _key(paths: tuple) -> tuple:
    return (store._folders_key(), tuple(_stat(path) for path in paths))


def load_project(pid: str) -> dict:
    with _LOCK:
        hit = _CACHE.get(pid)
    if hit is not None:
        key, paths, blob = hit
        try:
            fresh = _key(paths) == key
        except store.StudioError:
            fresh = False
        if fresh:
            with _LOCK:
                STATS["hits"] += 1
                if pid in _CACHE:   # most recently read last
                    _CACHE[pid] = _CACHE.pop(pid)
            return pickle.loads(blob)
    before = _stat(store.project_path(pid))
    project = _ORIGINAL(pid)
    with _LOCK:
        STATS["misses"] += 1
    try:
        paths = _paths(pid, project)
        key = _key(paths)
        # a project saved while it was read is read again next time
        if key[1][0] == before and before is not None:
            blob = pickle.dumps(project, protocol=pickle.HIGHEST_PROTOCOL)
            with _LOCK:
                _CACHE.pop(pid, None)
                _CACHE[pid] = (key, paths, blob)
                while len(_CACHE) > LIMIT:
                    _CACHE.pop(next(iter(_CACHE)))
    except (store.StudioError, OSError, pickle.PicklingError, TypeError):
        pass
    return project


def forget(pid: str | None = None) -> None:
    with _LOCK:
        if pid is None:
            _CACHE.clear()
        else:
            _CACHE.pop(pid, None)


def install() -> None:
    """Route every store.load_project of this process through the cache (store's own calls included)."""
    global _ORIGINAL
    if _ORIGINAL is None:
        _ORIGINAL = store.load_project
        store.load_project = load_project


def uninstall() -> None:
    global _ORIGINAL
    if _ORIGINAL is not None:
        store.load_project = _ORIGINAL
        _ORIGINAL = None
    forget()
