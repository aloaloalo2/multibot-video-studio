"""Measure narration from decoded samples and remove only quiet outer padding.

Paid recordings remain immutable. The small content-addressed cache contains
measurements only; every render decodes the original and applies the same trim.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path

RATE = 48000
VERSION = 1
GUARD = .03
THRESHOLD = 10 ** (-50 / 20)
FORMAT = f'aformat=sample_rates={RATE}:channel_layouts=mono'


def inspect(path: Path, cache: Path) -> dict:
    import numpy as np

    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    fingerprint = digest.hexdigest()
    record = cache / f'{fingerprint}-v{VERSION}.json'
    try:
        result = json.loads(record.read_text())
        if (result.get('fingerprint') == fingerprint and result.get('version') == VERSION
                and 0 <= result['start_sample'] < result['end_sample'] <= result['samples']
                and result['rate'] == RATE):
            return result
    except (OSError, ValueError, KeyError, TypeError):
        pass
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path),
                              '-vn', '-af', FORMAT, '-f', 'f32le', 'pipe:1'],
                             capture_output=True, timeout=180)
    if decoded.returncode:
        raise RuntimeError('Не вдалося прочитати збережений запис фрази. Оригінал збережено.')
    samples = np.frombuffer(decoded.stdout, dtype='<f4')
    active = np.flatnonzero(np.abs(samples) >= THRESHOLD)
    if not len(active) or not np.isfinite(samples).all():
        raise RuntimeError('У записі фрази немає придатного звуку. Оригінал збережено, повторну оплату не запущено.')
    guard = round(GUARD * RATE)
    start = max(0, int(active[0]) - guard)
    end = min(len(samples), int(active[-1]) + 1 + guard)
    result = {'version': VERSION, 'fingerprint': fingerprint, 'rate': RATE,
              'samples': len(samples), 'start_sample': start, 'end_sample': end,
              'raw_length': len(samples) / RATE, 'length': (end - start) / RATE,
              'removed_leading': start / RATE, 'removed_trailing': (len(samples) - end) / RATE,
              'edge_silence': {'leading': (int(active[0]) - start) / RATE,
                               'trailing': (end - int(active[-1]) - 1) / RATE, 'speed': 1.}}
    cache.mkdir(parents=True, exist_ok=True)
    temporary = record.with_name(f'.{record.name}.{uuid.uuid4().hex}.tmp')
    try:
        temporary.write_text(json.dumps(result))
        os.replace(temporary, record)
    finally:
        temporary.unlink(missing_ok=True)
    return result


def filters(item: dict, speed: float) -> str:
    """Use exactly the decoded sample coordinates measured by inspect()."""
    trim = item.get('trim')
    parts = [FORMAT]
    if trim:
        if (trim.get('version') != VERSION or trim.get('rate') != RATE
                or not 0 <= trim['start_sample'] < trim['end_sample'] <= trim['samples']):
            raise ValueError('Invalid narration trim')
        parts += [f"atrim=start_sample={trim['start_sample']}:end_sample={trim['end_sample']}",
                  'asetpts=PTS-STARTPTS']
    if abs(speed - 1) > 1e-7:
        parts.append(f'atempo={speed:.6f}')
    return ','.join(parts)
