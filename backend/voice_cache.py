"""Project-local paid takes, reused only for matching words, language and voice settings."""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from functools import lru_cache
from pathlib import Path

import store


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@lru_cache(maxsize=2048)
def _file_hash(path: str, size: int, stamp: int) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_hash(path: Path) -> str:
    stat = path.stat()
    return _file_hash(str(path), stat.st_size, stat.st_mtime_ns)


def take_key(identity: dict, text: str) -> str:
    # Neighbouring phrases and timeline positions are deliberately not part of the key.
    # Keep paid speech when only a neighbour or local timing changes.
    return digest({'voice': identity, 'text': text.strip()})


def candidates(work: Path, identity: dict, aliases: set[str]) -> dict[str, Path]:
    found = {}
    cache = work / 'voice-cache'
    index = store.read_json(cache / 'index.json', {}) or {}
    for key, item in index.items():
        if item.get('identity') != identity:
            continue
        path = cache / f'{key}.mp3'
        if path.is_file() and path.stat().st_size > 1000 and file_hash(path) == item.get('sha256'):
            found[item['text']] = path
    # Legacy paid takes remain eligible only when their recorded voice configuration is known.
    # Read exact requested words for first takes, and manifest words for selected shorter takes.
    roots = [work / 'parts', *sorted((work / 'voice-history').glob('*/parts'), reverse=True)]
    for parts in roots:
        request = store.read_json(parts / 'request.json', {}) or {}
        same = request.get('identity') == identity if request.get('identity') else request.get('voice_key') in aliases
        if not same or request.get('provider') != identity['provider']:
            continue
        entries = list(store.read_json(parts / 'manifest.json', []) or [])
        ledger = store.read_json(parts / 'requests.json', None)
        if ledger is not None:
            entries += [item for item in ledger if item.get('status') == 'complete' and item.get('kind') == 'original']
        else:
            entries += [{'text': text, 'file': f'{n:05d}.mp3'}
                        for n, text in enumerate(request.get('translations') or [])]
        for item in entries:
            name, text = item.get('file'), str(item.get('text') or '').strip()
            if not name or Path(name).name != name or not text or text in found:
                continue
            path = parts / name
            if path.is_file() and path.stat().st_size > 1000:
                found[text] = path
    return found


def remember(work: Path, identity: dict, text: str, source: Path) -> Path:
    """Commit a successfully decoded raw take before fitting or archiving a generation."""
    length = store.media_duration(source)
    if not length or length <= 0:
        raise store.StudioError('Збережена фраза пошкоджена. Потрібна перевірка перед повторною оплатою.', 409)
    cache = work / 'voice-cache'
    cache.mkdir(parents=True, exist_ok=True)
    key = take_key(identity, text)
    target = cache / f'{key}.mp3'
    if source != target:
        staged = cache / f'{key}.tmp'
        shutil.copy2(source, staged)
        staged.replace(target)
    index = store.read_json(cache / 'index.json', {}) or {}
    index[key] = {'text': text.strip(), 'identity': identity, 'sha256': file_hash(target),
                  'duration': length, 'saved_at': time.time()}
    store.atomic_json(cache / 'index.json', index)
    return target
