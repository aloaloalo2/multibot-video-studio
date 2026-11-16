"""An episode published on YouTube, read from the blue Finder tag on its folder and kept by the studio.

The user's ChatGPT marks an episode folder with Finder's blue tag once the video is on YouTube (user, 16 November 2026:
«синій кружочок біля папки… відмічає ролики, які опубліковані… відмітити другою галочкою… навіть якщо я видалю ту
папку… щоб та друга галочка нікуди не зникла»). The studio notices the tag and writes published.json in the project,
so the mark stays when the folder is gone or the tag is removed.
"""
from __future__ import annotations

import plistlib
import subprocess
import time
from pathlib import Path

import store

BLUE = 4                       # Finder's colour number of the blue tag, whatever its name in the system language
_SEEN: dict[str, tuple] = {}   # folder -> (its change time, blue?) so the list does not ask Finder every few seconds


def path(pid: str) -> Path:
    return store.project_dir(pid) / 'published.json'


def blue(folder: Path) -> bool:
    try:
        stamp = folder.stat().st_ctime_ns   # setting a tag changes the folder's change time
    except OSError:
        return False
    cached = _SEEN.get(str(folder))
    if cached and cached[0] == stamp:
        return cached[1]
    found = False
    try:
        raw = subprocess.run(['xattr', '-px', 'com.apple.metadata:_kMDItemUserTags', str(folder)],
                             capture_output=True, text=True, timeout=5)
        if raw.returncode == 0:
            tags = plistlib.loads(bytes.fromhex(''.join(raw.stdout.split())))
            found = isinstance(tags, list) and any(str(tag).rsplit('\n', 1)[-1] == str(BLUE) for tag in tags if '\n' in str(tag))
    except Exception:   # an odd tag from another app never breaks the project list
        found = False
    if not found:
        # Finder also keeps a folder's colour in its FinderInfo flags (bits 1-3 of byte 9): the blue dot the user saw
        # was written that way, with no tag at all (16 November 2026)
        try:
            info = subprocess.run(['xattr', '-px', 'com.apple.FinderInfo', str(folder)], capture_output=True, text=True, timeout=5)
            raw = bytes.fromhex(''.join(info.stdout.split())) if info.returncode == 0 else b''
            found = len(raw) > 9 and (raw[9] >> 1) & 7 == BLUE
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    _SEEN[str(folder)] = (stamp, found)
    return found


def check(item: dict) -> dict | None:
    """The saved mark of a listed project, written once when its folder first shows the blue tag."""
    saved = store.read_json(path(item['id']), None)
    if isinstance(saved, dict) and saved.get('at'):
        return saved
    folder = item.get('episode_path')
    if folder and blue(Path(folder)):
        saved = {'at': time.time(), 'source': 'finder-blue-tag'}
        try:
            store.atomic_json(path(item['id']), saved)
        except OSError:
            pass
        return saved
    return None
