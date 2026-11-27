"""The music library on every Mac (user, 27 November 2026: «на інш пк нема музики»).

The tracks the channels tick in «Звук ролика» live in `<data>/music-library` (backend/music_library.py), which is not in
git, so a second Mac had none and its films got no library music. The library is published in its own public repository,
https://github.com/aloaloalo2/videokey-music-library (YouTube Audio Library tracks, each with its licence in the README),
apart from the studio's repository so the studio never carries 300 MB of audio. At every start the studio fetches that
repository's catalog and downloads the tracks and analyses this Mac lacks, in the background; tracks already here and rows
this Mac knows better (its own vocals marks, its own imports) stay as they are. `push` publishes this Mac's new tracks.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path

import music_library
import store

REPO = 'aloaloalo2/videokey-music-library'
RAW = f'https://raw.githubusercontent.com/{REPO}/main/'
TIMEOUT = 60
LOCK = threading.Lock()
STATE: dict = {'running': False, 'added': 0, 'error': None}


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': 'VideoKey-Studio'})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        return answer.read()


def _save(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + '.part')
    part.write_bytes(data)
    part.replace(path)


def valid(row) -> bool:
    name = str(row.get('file') or '') if isinstance(row, dict) else ''
    return bool(isinstance(row, dict) and row.get('id') and name.startswith('files/') and '..' not in name)


def merge(local: list, remote: list) -> list:
    """This Mac's rows first and unchanged, then the valid remote rows it does not have."""
    known = {row.get('id') for row in local if isinstance(row, dict)}
    return list(local) + [row for row in remote if valid(row) and row['id'] not in known]


def sync(get=None) -> int:
    """Download what this Mac lacks; returns how many tracks were added."""
    get = get or _get
    root = music_library.root()
    remote = json.loads(get(RAW + 'catalog.json').decode('utf-8'))
    added = 0
    for row in remote:
        if not valid(row):
            continue
        name = row['file']
        target = root / name
        if not target.is_file():
            _save(target, get(RAW + name))
            added += 1
        analysis = root / 'analysis' / f"{row['id']}.json"
        if not analysis.is_file():
            try:
                _save(analysis, get(RAW + f"analysis/{row['id']}.json"))
            except Exception:   # a track without an analysis falls back to whole tracks by category
                pass
    local = store.read_json(root / 'catalog.json', []) or []
    merged = merge(local, remote)
    if merged != local:
        store.atomic_json(root / 'catalog.json', merged)
    return added


def run() -> None:
    if not LOCK.acquire(blocking=False):
        return
    STATE.update(running=True, error=None)
    try:
        STATE['added'] = sync()
        if STATE['added']:
            print(f"[music] library: {STATE['added']} tracks downloaded from {REPO}", flush=True)
    except Exception as error:   # offline or GitHub down: the tracks already here still play, the next start tries again
        STATE['error'] = str(error)
        print(f"[music] library sync skipped: {error}", flush=True)
    finally:
        STATE['running'] = False
        LOCK.release()


def start() -> None:
    """A start-up task: the download runs beside the studio and never holds the other start-up tasks."""
    threading.Thread(target=run, name='music-sync', daemon=True).start()


def push() -> str:
    """Publish this Mac's library to the repository (needs `gh` signed in with write access)."""
    root = music_library.root()
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder) / 'library'
        subprocess.run(['gh', 'repo', 'clone', REPO, str(work), '--', '--depth', '1'], check=True, capture_output=True)
        remote = json.loads((work / 'catalog.json').read_text('utf-8'))
        local = store.read_json(root / 'catalog.json', []) or []
        new = [row for row in local if row.get('id') not in {r.get('id') for r in remote} and (root / row.get('file', '')).is_file()]
        if not new:
            return 'нових треків немає'
        for row in new:
            shutil.copy2(root / row['file'], work / row['file'])
            analysis = root / 'analysis' / f"{row['id']}.json"
            if analysis.is_file():
                (work / 'analysis').mkdir(exist_ok=True)
                shutil.copy2(analysis, work / 'analysis' / analysis.name)
        rows = remote + new
        (work / 'catalog.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', 'utf-8')
        readme = work / 'README.md'
        readme.write_text(readme.read_text('utf-8') + ''.join(
            f"| {r['title']} | {r['artist']} | {r['category']} | {r['license']} |\n" for r in new), 'utf-8')
        git = ['git', '-C', str(work)]
        subprocess.run(git + ['add', '-A'], check=True, capture_output=True)
        subprocess.run(git + ['commit', '-m', f'{len(new)} more tracks from the YouTube Audio Library'], check=True, capture_output=True)
        subprocess.run(git + ['push'], check=True, capture_output=True)
        return f'опубліковано треків: {len(new)}'
