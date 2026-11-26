"""Local silence around completed original narration, before timing and planning: a lead-in, a closing pause and, for
narration the studio voiced, a short pause after some paragraphs, each a little different in every film (user, 26 November
2026: «динамічно… від до… і на початку також», «деколи… рандомні паузи… пів секунди… щоб аутентичність була»)."""
import hashlib
import json
import math
import random
import shutil
import subprocess
import threading
from pathlib import Path
import store
import job_timing

SECONDS = 1.5            # the fixed closing pause of version 1, kept for narration prepared before
VERSION = 2
LEAD = (0., .03)         # seconds of silence before the first word (user, 26 November 2026: «на початку… до 30 мілісекунд»)
ENDING = (1.0, 2.2)      # seconds after the last word
PAUSE = (.2, .6)         # an extra pause after a paragraph
PAUSE_SHARE = .35        # about one paragraph break in three gets one
BREATH = (.02, .05)      # between two requests inside a paragraph, always (user, 26 November 2026: «по 30 мілісекунд… плюс-мінус»)
LOCK = threading.RLock()
PROJECT_LOCKS = {}


def prepared(asset):
    """Narration already given its silence: version 1 (a fixed 1.5 s ending) stays as it is, so old films keep their times."""
    ending = asset.get('narration_ending') or {}
    path = Path(asset.get('path') or '')
    fixed = ending.get('version') == 1 and ending.get('seconds') == SECONDS
    return ((fixed or ending.get('version') == VERSION) and path.is_file()
            and ending.get('sha256') == store.audio_fingerprint(path))


def silence_plan(identity: str, breaks=()) -> dict:
    """The lead-in, ending and pauses of one recording, chosen from its own hash: the same recording always gets the same
    silence (an assembly again reuses its file), another recording other silence. `breaks` are the joins between the
    voiced parts as [share of the recording's length, 'paragraph' or 'group']: a paragraph's end sometimes gets a pause of
    a fifth to three fifths of a second, a join inside a paragraph always a breath of 20-50 ms."""
    rng = random.Random(int(identity[:16], 16))
    step = lambda span, grain=20: round(rng.uniform(*span) * grain) / grain
    lead, ending = step(LEAD, 1000), step(ENDING)
    pauses = []
    for item in sorted(breaks or (), key=lambda b: float(b[0])):
        share, kind = float(item[0]), item[1]
        if not 0 < share < 1:
            continue
        if kind == 'paragraph':
            if rng.random() < PAUSE_SHARE:
                pauses.append([round(share, 6), step(PAUSE)])
        else:
            pauses.append([round(share, 6), step(BREATH, 1000)])
    return {'lead': lead, 'ending': ending, 'pauses': pauses}


def breaks_of(takes, entries) -> list:
    """The joins between voiced parts as shares of their joined length, each a paragraph's end or a join inside one."""
    lengths = [store.media_duration(Path(path)) or 0 for path in takes]
    total = sum(lengths)
    if not total or len(lengths) < 2:
        return []
    out, at = [], 0.0
    for length, entry in zip(lengths[:-1], entries[:-1]):
        at += length
        out.append([at / total, 'paragraph' if entry.get('ends_paragraph') else 'group'])
    return out


def _audio_format(ffprobe, source):
    run = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=sample_rate,channels',
                          '-of', 'csv=p=0', str(source)], capture_output=True, text=True, timeout=60)
    rate, channels = (run.stdout.strip().split(',') + ['', ''])[:2]
    return int(rate or 44100), int(channels or 1)


def prepare_file(pid, source, breaks=()):
    source = Path(source)
    identity = store.audio_fingerprint(source)
    plan = silence_plan(identity, breaks)
    key = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:10]
    root = store.project_dir(pid) / 'narration-ending' / (identity + '-v' + str(VERSION) + '-' + key)
    root.mkdir(parents=True, exist_ok=True)
    output, receipt = root / 'Озвучка.flac', root / 'ending.json'
    saved = store.read_json(receipt, {}) or {}
    if output.is_file() and saved.get('sha256') == store.audio_fingerprint(output):
        return output, saved
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe: raise store.StudioError('Для пауз в озвучці потрібен FFmpeg')
    spoken = store.media_duration(source) or 0
    if not spoken or not math.isfinite(spoken):
        raise store.StudioError('Не вдалося виміряти озвучку')
    rate, channels = _audio_format(ffprobe, source)
    layout = 'mono' if channels == 1 else 'stereo'
    # the speech cut at the paragraph pauses, each piece followed by its silence; the lead-in before, the ending after
    cuts = [round(share * spoken, 4) for share, _ in plan['pauses']]
    edges = [0.0] + cuts + [None]
    parts, labels = [], []
    silence = lambda name, seconds: parts.append(f'anullsrc=r={rate}:cl={layout},atrim=0:{seconds:.3f}[{name}]') or labels.append(f'[{name}]')
    if plan['lead'] >= .001:
        silence('lead', plan['lead'])
    for index, (start, end) in enumerate(zip(edges, edges[1:])):
        trim = f'atrim=start={start:.4f}' + (f':end={end:.4f}' if end is not None else '')
        parts.append(f'[0:a]{trim},asetpts=PTS-STARTPTS,aformat=sample_rates={rate}:channel_layouts={layout}[s{index}]')
        labels.append(f'[s{index}]')
        if index < len(plan['pauses']):
            silence(f'p{index}', max(.001, plan['pauses'][index][1]))
    silence('end', plan['ending'])
    graph = ';'.join(parts) + ';' + ''.join(labels) + f'concat=n={len(labels)}:v=0:a=1[out]'
    pending = root / 'pending.flac'
    result = subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-y', '-i', str(source), '-filter_complex', graph,
                             '-map', '[out]', '-c:a', 'flac', str(pending)], capture_output=True, timeout=600)
    added = plan['lead'] + plan['ending'] + sum(p[1] for p in plan['pauses'])
    duration = store.media_duration(pending) if result.returncode == 0 else None
    if not duration or not math.isfinite(duration) or abs(duration - spoken - added) > .1:
        pending.unlink(missing_ok=True)
        raise store.StudioError('Не вдалося додати паузи до озвучки')
    pending.replace(output)
    saved = {'version': VERSION, 'seconds': plan['ending'], 'lead_seconds': plan['lead'], 'pauses': plan['pauses'],
             'source_sha256': identity, 'duration': duration, 'sha256': store.audio_fingerprint(output)}
    # the take-by-take timing proof (narration_sequence) holds only without silence inside: it gives way to Whisper
    if not plan['pauses'] and plan['lead'] < .001:
        saved['speech_duration'] = duration - plan['ending']
    store.atomic_json(receipt, saved)
    return output, saved


@job_timing.measure('saving')
def import_audio(project, source, source_name='narration', reverb=None, room_noise=None, breaks=()):
    """Preserve raw takes; reuse a matching prepared import instead of adding another pause."""
    with LOCK:
        project_lock = PROJECT_LOCKS.setdefault(project['id'], threading.RLock())
    with project_lock:
        import narration_effects
        effect_id = narration_effects.identity(reverb, room_noise)
        source = Path(source)
        identity = store.audio_fingerprint(source)
        current = store.load_project(project['id'])
        for asset in current.get('assets', []):
            if prepared(asset) and asset.get('narration_processing', '') == effect_id and (asset['narration_ending'].get('source_sha256') == identity
                                    or Path(asset['path']).resolve() == source.resolve()):
                return asset
        output, receipt = prepare_file(project['id'], source, breaks)
        if effect_id:
            target = output.parent / effect_id / 'Озвучка.flac'
            target.parent.mkdir(parents=True, exist_ok=True)
            effect_receipt = target.with_suffix('.json')
            saved = store.read_json(effect_receipt, {}) or {}
            if not target.is_file() or saved.get('sha256') != store.audio_fingerprint(target):
                pending = target.with_name('pending.flac')
                try:
                    narration_effects.render(output, reverb, pending, room_noise, closing_pause=receipt['seconds'])
                    duration = store.media_duration(pending) or 0
                    if abs(duration - receipt['duration']) > .06:
                        raise store.StudioError('Реверберація змінила тривалість озвучки')
                    pending.replace(target)
                finally:
                    pending.unlink(missing_ok=True)
                saved = {**receipt, 'sha256': store.audio_fingerprint(target)}
                store.atomic_json(effect_receipt, saved)
            output, receipt = target, saved
        asset = store.import_asset_file(current, output, source_name)
        asset['narration_ending'] = receipt
        asset['narration_processing'] = effect_id
        with store.LOCK:
            current = store.load_project(project['id'])
            for saved in current.get('assets', []):
                if saved['id'] == asset['id']:
                    saved['narration_ending'] = receipt
                    saved['narration_processing'] = effect_id
            store.save_project(current)
        return asset


def prepare_asset(project, asset):
    return asset if prepared(asset) else import_audio(project, asset['path'], 'speech-analysis')
