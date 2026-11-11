"""Local tempo previews. Never synthesize speech or change the source recording."""
import hashlib
import math
from pathlib import Path
import threading
import time

import languages
import store

LOCK = threading.Lock()


def speed(value, minimum=.87, maximum=1.05):
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float('nan')
    if isinstance(value, bool) or not math.isfinite(result) or not minimum <= result <= maximum:
        raise store.StudioError('Швидкість має бути від 87 до 105%')
    return result


def preview(source, ratio):
    ratio = speed(ratio, .5, 2.)
    source = Path(source)
    if abs(ratio - 1.) < 1e-7:
        return source
    stamp = source.stat()
    identity = hashlib.sha256(f'{source.resolve()}:{stamp.st_size}:{stamp.st_mtime_ns}'.encode()).hexdigest()
    folder = store.DATA_ROOT / 'audio-effects' / 'tempo-v1' / identity
    target = folder / f'{ratio:.6f}.flac'
    # One render per exact source and speed. Keep just three recent auditions.
    with LOCK:
        if target.is_file():
            target.touch()
            return target
        folder.mkdir(parents=True, exist_ok=True)
        pending = target.with_suffix('.pending.flac')
        try:
            languages.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(source), '-vn',
                           '-af', f'atempo={ratio:.6f}', '-c:a', 'flac', str(pending)],
                          'підготувати темп зразка без зміни тону')
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)
        others = sorted((p for p in folder.glob('*.flac') if p != target), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in others[2:]:
            if time.time() - old.stat().st_mtime > 60:
                old.unlink(missing_ok=True)
    return target
