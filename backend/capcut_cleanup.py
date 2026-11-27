"""A published film's CapCut renders leave the shared cache at once (user, 27 November 2026: «якщо опублікований ролик,
варто думаю очистити одразу переходи»).

The shared `capcut-cache` keeps every drawn transition, its two sides and the CapCut effects on clips, named by a hash
of what they show; storage_tidy drops them only after three unused days or past 2 GB. Each episode now lists the files
it drew or used (`projects/<id>/capcut/used.txt`, written by engine/capcut_fx.py) and the seams its editor played
(`projects/<id>/capcut/ready.json`). Once the film is published those files go, unless another unpublished film lists
the same file. A later re-export simply draws them again.
"""
from __future__ import annotations

import threading
from pathlib import Path

import store

LOCK = threading.Lock()
SUFFIXES = ('.mov', '.mp4', '.none', '.raw')


def names(pid: str) -> set[str]:
    folder = store.DATA_ROOT / 'projects' / pid / 'capcut'
    found = set()
    try:
        found |= {line.strip() for line in (folder / 'used.txt').read_text(encoding='utf-8').splitlines() if line.strip()}
    except OSError:
        pass
    for item in (store.read_json(folder / 'ready.json', {}) or {}).values():
        if isinstance(item, dict) and item.get('url'):
            found.add(str(item['url']).rsplit('/', 1)[-1])
    return {name for name in found if '/' not in name and name.startswith(('side-', 'transition-direct-capcut-'))}


def kept_by_others(pid: str) -> set[str]:
    """Files another film still needs: listed by a project that is not published."""
    kept = set()
    for folder in (store.DATA_ROOT / 'projects').glob('*'):
        other = folder.name
        if other == pid or not (folder / 'capcut').is_dir():
            continue
        if (store.read_json(folder / 'published.json', {}) or {}).get('at'):
            continue
        kept |= names(other)
    return kept


def clear(pid: str) -> int:
    """Drop the published film's CapCut files from the shared cache; returns the bytes freed."""
    with LOCK:
        cache = store.DATA_ROOT / 'capcut-cache'
        mine = names(pid) - kept_by_others(pid)
        freed = 0
        for name in mine:
            stem = Path(name).stem
            for suffix in SUFFIXES:
                target = cache / (stem + suffix)
                try:
                    size = target.stat().st_size
                    target.unlink()
                    freed += size
                except OSError:
                    continue
        folder = store.DATA_ROOT / 'projects' / pid / 'capcut'
        for leftover in ('used.txt', 'ready.json'):
            try:
                (folder / leftover).unlink()
            except OSError:
                pass
        return freed


def after_publish(pid: str) -> None:
    """Once per published film, in the background: the project list must not wait for the files."""
    mark = store.DATA_ROOT / 'projects' / pid / 'published.json'

    def work():
        try:
            freed = clear(pid)
            saved = store.read_json(mark, {}) or {}
            if saved.get('at'):
                store.atomic_json(mark, {**saved, 'capcut_cleared': True})
            if freed:
                print(f"[capcut] {pid} published: {freed / 1024 ** 2:.0f} MB of transitions cleared", flush=True)
        except Exception as error:   # the shared cache's own tidy takes them later
            print(f"[capcut] {pid}: {error}", flush=True)
    threading.Thread(target=work, daemon=True).start()
