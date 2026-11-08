"""A fixed, local closing pause on completed original narration, before timing and planning."""
import math
import shutil
import subprocess
import threading
from pathlib import Path
import store

SECONDS = 1.5
VERSION = 1
LOCK = threading.RLock()
PROJECT_LOCKS = {}


def prepared(asset):
    ending = asset.get('narration_ending') or {}
    path = Path(asset.get('path') or '')
    return (ending.get('version') == VERSION and ending.get('seconds') == SECONDS and path.is_file()
            and ending.get('sha256') == store.audio_fingerprint(path))


def prepare_file(pid, source):
    source = Path(source)
    identity = store.audio_fingerprint(source)
    root = store.project_dir(pid) / 'narration-ending' / (identity + '-v' + str(VERSION))
    root.mkdir(parents=True, exist_ok=True)
    output, receipt = root / 'Озвучка.flac', root / 'ending.json'
    saved = store.read_json(receipt, {}) or {}
    if output.is_file() and saved.get('sha256') == store.audio_fingerprint(output):
        return output, saved
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg: raise store.StudioError('Для завершальної паузи потрібен FFmpeg')
    pending = root / 'pending.flac'
    result = subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-y', '-i', str(source), '-map', '0:a:0',
        '-af', f'apad=pad_dur={SECONDS}', '-c:a', 'flac', str(pending)], capture_output=True, timeout=600)
    duration = store.media_duration(pending) if result.returncode == 0 else None
    if not duration or not math.isfinite(duration) or duration <= SECONDS:
        pending.unlink(missing_ok=True)
        raise store.StudioError('Не вдалося додати завершальну паузу до озвучки')
    pending.replace(output)
    saved = {'version': VERSION, 'seconds': SECONDS, 'source_sha256': identity,
             'speech_duration': duration - SECONDS, 'duration': duration, 'sha256': store.audio_fingerprint(output)}
    store.atomic_json(receipt, saved)
    return output, saved


def import_audio(project, source, source_name='narration'):
    """Preserve raw takes; reuse a matching prepared import instead of adding another pause."""
    with LOCK:
        project_lock = PROJECT_LOCKS.setdefault(project['id'], threading.RLock())
    with project_lock:
        source = Path(source)
        identity = store.audio_fingerprint(source)
        current = store.load_project(project['id'])
        for asset in current.get('assets', []):
            if prepared(asset) and (asset['narration_ending'].get('source_sha256') == identity
                                    or Path(asset['path']).resolve() == source.resolve()):
                return asset
        output, receipt = prepare_file(project['id'], source)
        asset = store.import_asset_file(current, output, source_name)
        asset['narration_ending'] = receipt
        with store.LOCK:
            current = store.load_project(project['id'])
            for saved in current.get('assets', []):
                if saved['id'] == asset['id']: saved['narration_ending'] = receipt
            store.save_project(current)
        return asset


def prepare_asset(project, asset):
    return asset if prepared(asset) else import_audio(project, asset['path'], 'speech-analysis')
