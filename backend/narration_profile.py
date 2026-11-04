"""Reusable measured pace for one voice, language, model and synthesis settings.

No synthesis is performed here. These observations guide explicit translation
jobs; they never alter saved wording during playback or narration.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
from numeric_comparison import comparison_chars as letter_count
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
        if letter_count(text) < 20 or not math.isfinite(length) or length <= 0:
            continue
        # Reusing one cached phrase is one observation, however often it is played.
        key = hashlib.sha256((audio['fingerprint'] + text).encode()).hexdigest()
        updates[key] = {'chars': letter_count(text), 'seconds': length, 'at': time.time()}
    if not updates:
        return
    root.mkdir(parents=True, exist_ok=True)
    path = location(root, identity)
    with LOCK, path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            saved = json.loads(path.read_text())
            previous = saved.get('observations', {}) if saved.get('version')==2 else {}
        except (OSError, ValueError, AttributeError):
            previous = {}
        for key, value in updates.items():
            previous.setdefault(key, value)
        values = dict(sorted(previous.items(), key=lambda x: x[1]['at'])[-512:])
        temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}')
        try:
            temporary.write_text(json.dumps({'version': 2, 'observations': values}))
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def read(root: Path, identity: dict) -> dict | None:
    try:
        data = json.loads(location(root, identity).read_text())
        points = list(data['observations'].values())
        if data['version'] != 2 or any(type(p['chars']) is not int or not 20 <= p['chars'] <= 20000
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
    if not profile or not texts or total <= 0 or len(texts) != len(segments):
        return {'ids': []}
    rate = profile['seconds_per_character']
    if not math.isfinite(rate) or rate <= 0:
        return {'ids': []}
    available = max(0., total - .05*max(0, len(texts)-1) - max(1., total*.003))
    limit = math.floor(available * narration_pacing.MAX_SPEED / rate)
    targets = {i: letter_count(text) for i, text in enumerate(texts)}

    def reduce(indexes, excess):
        order = sorted(indexes, key=lambda i: (
            -(targets[i]*rate - max(0., segments[i]['end']-segments[i]['start'])), -targets[i]))
        for i in order:
            if excess <= 0:
                break
            # At most twelve percent per pass, even if both a block and the
            # film need room. Re-audit all wording before any further pass.
            capacity = min(letter_count(texts[i])-1, max(1, math.floor(letter_count(texts[i])*.12)))
            used = letter_count(texts[i])-targets[i]
            reduction = min(excess, max(0, capacity-used))
            targets[i] -= reduction
            excess -= reduction

    reduce(range(len(texts)), sum(targets.values())-limit)
    windows = []
    for start in range(0, len(texts), 10):
        end = min(len(texts), start+10)
        # Adjacent blocks can borrow two seconds on each side. The whole-film
        # constraint above still applies, so this cannot extend the final audio.
        left = max(0., float(segments[start]['start'])-2) if start else 0.
        right = min(total, float(segments[end]['start'])+2) if end<len(texts) else total
        seconds = max(0., right-left-.05*(end-start))
        block_limit = math.floor(seconds*narration_pacing.MAX_SPEED/rate)
        excess = sum(targets[i] for i in range(start,end))-block_limit
        if excess > 0:
            windows.append({'start_index':start,'end_index':end-1,'max_chars':block_limit})
            reduce(range(start,end),excess)
    # Fixed-size blocks can each borrow a little and still accumulate a long
    # delay. Check the complete chain against every original sentence boundary.
    for _ in range(len(texts)):
        alignment = narration_pacing.alignment_check(segments,
            {i:targets[i]*rate/narration_pacing.MAX_SPEED for i in targets},total)
        if alignment['within_limit']:
            break
        issue = max(alignment['issues'],key=lambda value:value['excess'])
        previous = sum(targets.values())
        reduce(range(issue['first_index'],issue['index']+1),
               math.ceil((issue['excess']+.1)*narration_pacing.MAX_SPEED/rate))
        if sum(targets.values()) == previous:
            break
    changed = {i:value for i,value in targets.items() if value<letter_count(texts[i])}
    return {'ids': sorted(changed), 'targets': changed, 'max_chars': limit,'windows':windows,
            'over_by': max(0, sum(map(letter_count, texts))-limit), 'observations': profile['observations'],
            'alignment':alignment}
