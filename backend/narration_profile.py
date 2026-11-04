"""Reusable measured pace for one voice, language, model and synthesis settings.

No synthesis is performed here. These observations guide explicit translation
jobs; they never alter saved wording during playback or narration.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import threading
import time
import uuid
from pathlib import Path

import narration_pacing

LOCK = threading.Lock()


def location(root: Path, identity: dict) -> Path:
    key = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return root / f'{key}.json'


def remember(root: Path, identity: dict, observations: list[tuple[str, dict]]) -> None:
    updates = {}
    for text, audio in observations:
        length = audio['length']
        if len(text) < 20 or not math.isfinite(length) or length <= 0:
            continue
        # Reusing one cached phrase is one observation, however often it is played.
        key = hashlib.sha256((audio['fingerprint'] + text).encode()).hexdigest()
        updates[key] = {'chars': len(text), 'seconds': length, 'at': time.time()}
    if not updates:
        return
    root.mkdir(parents=True, exist_ok=True)
    path = location(root, identity)
    with LOCK, path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            previous = json.loads(path.read_text()).get('observations', {})
        except (OSError, ValueError, AttributeError):
            previous = {}
        for key, value in updates.items():
            previous.setdefault(key, value)
        values = dict(sorted(previous.items(), key=lambda x: x[1]['at'])[-512:])
        temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}')
        try:
            temporary.write_text(json.dumps({'version': 1, 'observations': values}))
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def read(root: Path, identity: dict) -> dict | None:
    try:
        data = json.loads(location(root, identity).read_text())
        points = list(data['observations'].values())
        if data['version'] != 1 or any(type(p['chars']) is not int or not 20 <= p['chars'] <= 20000
                                      or not math.isfinite(p['seconds']) or p['seconds'] <= 0 for p in points):
            return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    rate = narration_pacing.seconds_per_character(['x'*p['chars'] for p in points],
                                                 {i: p['seconds'] for i, p in enumerate(points)})
    return {'seconds_per_character': rate, 'observations': len(points)} if rate else None


def refinement(texts: list[str], segments: list[dict], total: float, profile: dict | None) -> dict:
    """Choose the largest overruns before paying for a newly translated script.

    The rate already includes uncertainty. Leave modest room for measured DSP
    duration and breaths. Dense sentences may borrow from their neighbours.
    """
    if not profile or total <= 0 or len(texts) != len(segments):
        return {'ids': []}
    rate = profile['seconds_per_character']
    if not math.isfinite(rate) or rate <= 0:
        return {'ids': []}
    available = max(0., total - .05*max(0, len(texts)-1) - max(1., total*.003))
    limit = math.floor(available * narration_pacing.MAX_SPEED / rate)
    excess = sum(map(len, texts)) - limit
    if excess <= 0:
        return {'ids': [], 'max_chars': limit, 'observations': profile['observations']}
    order = sorted(range(len(texts)), key=lambda i: (
        -(len(texts[i])*rate - max(0., segments[i]['end']-segments[i]['start'])), -len(texts[i])))
    targets = {}
    for i in order:
        reduction = min(excess, max(1, math.floor(len(texts[i])*.12)))
        targets[i] = len(texts[i]) - reduction
        excess -= reduction
        if excess <= 0:
            break
    return {'ids': sorted(targets), 'targets': targets, 'max_chars': limit,
            'over_by': max(0, sum(map(len, texts))-limit), 'observations': profile['observations']}
