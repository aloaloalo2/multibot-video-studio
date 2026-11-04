"""Conservative local fitting of narration; preserve pitch, phrase anchors and raw takes."""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import narration_audio

MIN_SPEED = 0.93
MAX_SPEED = 1.07
LONG_GAP = 1.5


def quiet_edges(samples, rate: int, speed: float = 1.) -> dict:
    """Measure existing boundary silence without removing any audio samples."""
    import numpy as np
    active = np.flatnonzero(np.abs(samples) >= 10 ** (-50 / 20))
    # A wholly silent/invalid take is not evidence of a safe speech boundary.
    if not len(active) or not np.isfinite(samples).all():
        return {'leading': 0., 'trailing': 0., 'speed': speed}
    return {'leading': int(active[0]) / rate,
            'trailing': (len(samples) - int(active[-1]) - 1) / rate, 'speed': speed}


def measure_edges(path: Path, speed: float = 1.) -> dict:
    import numpy as np
    import wave
    if path.suffix.lower() == '.wav':
        try:
            with wave.open(str(path), 'rb') as audio:
                if audio.getsampwidth() == 2 and audio.getcomptype() == 'NONE':
                    samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2')
                    samples = np.max(np.abs(samples.astype(np.float32).reshape(-1, audio.getnchannels())), axis=1) / 32768
                    return quiet_edges(samples, audio.getframerate(), speed)
        except wave.Error:
            pass  # Decode float/other WAV formats with ffmpeg below.
    raw = command(['-i', path, '-vn', '-ac', 1, '-ar', 48000, '-f', 'f32le', 'pipe:1'])
    return quiet_edges(np.frombuffer(raw, dtype='<f4'), 48000, speed)


def join_gaps(items: list[dict], gap: float = .05) -> list[float]:
    """Top up a breath only when the recordings do not already contain it.

    Reserve 10 ms at each measured edge and allow for the fastest permitted tempo.
    Missing measurements keep the original full gap. Never trim or overlap takes.
    """
    def quiet(item, side):
        edge = item.get('edge_silence') or {}
        value, speed = edge.get(side), edge.get('speed')
        if (not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
                or not isinstance(speed, (int, float)) or not math.isfinite(speed)
                or not MIN_SPEED <= speed <= MAX_SPEED):
            return 0.
        return max(0., value * speed / MAX_SPEED - .01)
    return [max(0., gap - quiet(a, 'trailing') - quiet(b, 'leading'))
            for a, b in zip(items, items[1:])]


def centered_schedule(items: list[dict], total: float, gap: float = .05) -> list[dict]:
    """Balance spare time around phrases, borrowing neighbouring silence without overlap.

    Isotonic projection keeps starts nearest their source-window centres while preserving order.
    Durations must already be measured after local fitting. No word is cut to meet the deadline.
    """
    lengths=[float(x['fitted_length']) for x in items]
    gaps=join_gaps(items,gap)+[0.]
    occupied=sum(lengths)+sum(gaps)
    slack=total-occupied
    if slack<-.001:
        raise RuntimeError(f'Озвучка довша за ролик на {-slack:.1f} с навіть після локальної підгонки. '
                           'Усі аудіофрагменти збережені. Автоматичної платної перегенерації не буде.')
    prefix=0.;blocks=[];targets=[]
    for n,item in enumerate(items):
        left=float(item.get('original_start',item['start']))
        right=float(items[n+1].get('original_start',items[n+1]['start'])) if n+1<len(items) else total
        target=left+max(0,right-left-gaps[n]-lengths[n])/2
        targets.append(target)
        blocks.append([target-prefix,1,n,n+1])
        while len(blocks)>1 and blocks[-2][0]>blocks[-1][0]:
            b=blocks.pop();a=blocks.pop();weight=a[1]+b[1]
            blocks.append([(a[0]*a[1]+b[0]*b[1])/weight,weight,a[2],b[3]])
        prefix+=lengths[n]+gaps[n]
    shifts=[0.]*len(items)
    for value,_,a,b in blocks:
        shifts[a:b]=[max(0.,min(max(0.,slack),value))]*(b-a)
    result=[];prefix=0.
    for n,item in enumerate(items):
        start=prefix+shifts[n]
        result.append({**item,'start':start,'end':start+lengths[n],'center_target':targets[n]})
        prefix+=lengths[n]+gaps[n]
    return result


def review_items(manifest: list[dict]) -> list[dict]:
    """Small, seekable markers for every audible tempo adjustment or timing shift."""
    result=[]
    for n,item in enumerate(manifest):
        speed=float(item.get('speed') or 1)
        start=float(item.get('start') or 0)
        shift=start-float(item.get('original_start',start))
        if abs(speed-1)<.01 and abs(shift)<.3:continue
        result.append({'index':int(item.get('index',n)), 'start':round(start,3),
                       'end':round(float(item.get('end',start+float(item.get('length') or 0)/speed)),3),
                       'speed':round(speed,4),'shift':round(shift,3),'text':str(item.get('text') or '')[:200]})
    return result


def fit_speed(length: float, place: float, speech_span: float) -> float:
    if length <= 0 or place <= 0:
        return MAX_SPEED if place <= 0 else 1.0
    if length > place:
        return min(MAX_SPEED, length / place)
    # Fill only excess silence, leaving the original's breath after the spoken span.
    target = min(place, max(length, speech_span))
    if target - length < 0.5:
        return 1.0
    return max(MIN_SPEED, length / target)


def fitting_speeds(items: list[dict], total: float) -> list[float]:
    """Use spare time across the whole film before declaring a bounded fit impossible."""
    speeds=[]
    gaps=join_gaps(items)+[0.]
    for n,item in enumerate(items):
        start=float(item.get('original_start',item['start']))
        end=float(items[n+1].get('original_start',items[n+1]['start'])) if n+1<len(items) else total
        speeds.append(fit_speed(item['length'],end-start-gaps[n],float(item['original_end'])-start))
    available=total-sum(gaps)
    minimum=sum(x['length']/MAX_SPEED for x in items)
    budget=max(minimum,available-.1)
    def occupied(delta):return sum(x['length']/min(MAX_SPEED,s+delta) for x,s in zip(items,speeds))
    if minimum>available:
        excess=minimum-available
        raise RuntimeError(f'Озвучка довша за ролик щонайменше на {excess:.1f} с при межі 7%. '
                           'Усі аудіофрагменти збережені. Автоматичної платної перегенерації не буде.')
    if occupied(0)<=budget:return speeds
    lo,hi=0.,MAX_SPEED-MIN_SPEED
    for _ in range(40):
        mid=(lo+hi)/2
        if occupied(mid)>budget:lo=mid
        else:hi=mid
    return [min(MAX_SPEED,s+hi) for s in speeds]


def fit_measured(items: list[dict], total: float, render, *, gap: float = .05,
                 max_passes: int = 3) -> list[dict]:
    """Correct local tempo against measured output, retaining every original take.

    ``render(item, speed)`` must render from the preserved source (never from an
    already stretched output) and return its actual duration in seconds. It may
    replace the copied item's edge_silence with measured output boundaries. Only
    changed speeds are rendered. The caller owns any output files; input manifest
    dictionaries are copied. No text changes, synthesis or audio cuts occur here.
    """
    if not math.isfinite(total) or total <= 0 or not math.isfinite(gap) or gap < 0:
        raise ValueError('Invalid narration duration or gap')
    if not isinstance(max_passes, int) or not 1 <= max_passes <= 3:
        raise ValueError('Measured fitting allows one to three local passes')
    result = [dict(item) for item in items]
    for item in result:
        speed, length = item.get('speed'), item.get('fitted_length')
        if (not isinstance(speed, (int, float)) or not math.isfinite(speed)
                or not MIN_SPEED <= speed <= MAX_SPEED
                or not isinstance(length, (int, float)) or not math.isfinite(length) or length <= 0):
            raise RuntimeError('Не вдалося перевірити тривалість локальних аудіофрагментів. '
                               'Усі записи фраз збережені.')
    def budget():
        return total - sum(join_gaps(result, gap))

    def occupied():
        return sum(item['fitted_length'] for item in result)

    for _ in range(max_passes):
        if occupied() <= budget() + 1e-6:
            return result
        movable = [item for item in result if item['speed'] < MAX_SPEED - 1e-7]
        if not movable:
            break
        # Inverse duration is an estimate only. Leave a small margin, then measure
        # again: atempo's windowing/padding need not equal raw_length / speed.
        target = max(0., budget() - .1)
        def predicted(delta):
            return sum(item['fitted_length'] * item['speed'] /
                       min(MAX_SPEED, item['speed'] + delta) for item in result)
        lo, hi = 0., MAX_SPEED - MIN_SPEED
        if predicted(hi) <= target:
            for _ in range(40):
                mid = (lo + hi) / 2
                if predicted(mid) > target:
                    lo = mid
                else:
                    hi = mid
        # Round upwards to the same precision as ffmpeg's atempo argument.
        for item in movable:
            speed = min(MAX_SPEED, math.ceil((item['speed'] + hi) * 1e6) / 1e6)
            if speed <= item['speed']:
                continue
            rendered = dict(item)
            length = render(rendered, speed)
            if (not isinstance(length, (int, float)) or not math.isfinite(length) or length <= 0):
                raise RuntimeError('Не вдалося перевірити тривалість після локальної підгонки. '
                                   'Усі записи фраз збережені.')
            item.update(speed=speed, fitted_length=float(length))
            if 'edge_silence' in rendered:
                item['edge_silence'] = rendered['edge_silence']
    if occupied() <= budget() + 1e-6:
        return result
    excess = max(0., occupied() - budget())
    raise RuntimeError(f'Озвучка довша за ролик на {excess:.1f} с після перевірки фактичної тривалості '
                       'при межі 7%. Усі аудіофрагменти збережені. '
                       'Автоматичної платної перегенерації не буде.')


def command(args):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', *map(str, args)],
                            capture_output=True, timeout=600)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-600:])
    return result.stdout


def recover(source: Path, segments: list[dict], folder: Path) -> list[dict]:
    """Split a legacy joined voice only at verified quiet boundaries, retaining every voiced sample."""
    import numpy as np
    import wave
    rate = 48000
    raw = command(['-i', source, '-vn', '-ac', '1', '-ar', rate, '-f', 'f32le', 'pipe:1'])
    samples = np.frombuffer(raw, dtype='<f4')
    hop = 480  # 10 ms; use peak level so quiet consonants are kept.
    peaks = np.max(np.abs(np.pad(samples, (0, (-len(samples)) % hop)).reshape(-1, hop)), axis=1)
    quiet = peaks < 10 ** (-50 / 20)
    boundaries = [0]
    for item in segments[1:]:
        nominal = round(float(item['start']) * 100)
        candidates = [i for i in range(max(2, nominal - 60), min(len(quiet)-2, nominal + 61))
                      if quiet[i-2:i+2].all() and i*hop > boundaries[-1]]
        if not candidates:
            raise RuntimeError(f"No safe silence at phrase {len(boundaries)+1}; keep the original voice")
        boundaries.append(min(candidates, key=lambda i: abs(i-nominal)) * hop)
    boundaries.append(len(samples))
    folder.mkdir(parents=True, exist_ok=False)
    manifest = []
    for n, (a, b) in enumerate(zip(boundaries, boundaries[1:])):
        piece = samples[a:b]
        active = np.flatnonzero(np.abs(piece) >= 10 ** (-50 / 20))
        if not len(active):
            raise RuntimeError(f"Phrase {n+1} contains no speech; keep the original voice")
        # Remove trailing silence only, with a 120 ms guard. Never remove pauses inside speech.
        end = min(len(piece), int(active[-1]) + int(.12 * rate))
        piece = piece[:end]
        path = folder / f'{n:05d}.wav'
        with wave.open(str(path), 'wb') as out:
            out.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            out.writeframes((np.clip(piece, -1, 1) * 32767).astype('<i2').tobytes())
        manifest.append({'index': n, 'file': path.name, 'start': a/rate, 'source_end': b/rate,
                         'length': len(piece)/rate, 'original_start': segments[n]['start'],
                         'original_end': segments[n]['end']})
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return manifest


def rebuild(parts: Path, manifest: list[dict], target: Path, total: float, progress=None) -> dict:
    """Fit retained takes locally, then balance surrounding silence without cutting speech."""
    import numpy as np
    rate = 48000
    mix = np.zeros(round(total*rate), dtype='<f4')
    report = []
    fitted=[None]*len(manifest)
    # Read the preserved sources so legacy manifests also account for native pauses.
    prepared=[]
    for n,item in enumerate(manifest):
        if progress:progress(n,len(manifest))
        trim=narration_audio.inspect(parts/item['file'],parts.parent/'audio-measurements')
        prepared.append({**item,'trim':trim,'length':trim['length'],'raw_length':trim['raw_length'],
                         'edge_silence':trim['edge_silence']})
    manifest=prepared
    speeds=fitting_speeds(manifest,total)
    def render(item, speed):
        pcm = command(['-i', parts/item['file'], '-af', narration_audio.filters(item,speed), '-ar', rate,
                       '-ac', '1', '-f', 'f32le', 'pipe:1'])
        audio = np.frombuffer(pcm, dtype='<f4')
        fitted[item['_rebuild_position']] = audio
        item['edge_silence'] = quiet_edges(audio,rate,speed)
        return len(audio)/rate
    for n, item in enumerate(manifest):
        if progress:progress(n,len(manifest))
        speed = speeds[n]
        measured={**item,'_rebuild_position':n,'speed':speed}
        measured['fitted_length']=render(measured,speed)
        report.append(measured)
    report=fit_measured(report,total,render)
    report=centered_schedule(report,total)
    for n,item in enumerate(report):
        audio=fitted[item.pop('_rebuild_position')]
        a=round(item['start']*rate)
        mix[a:a+len(audio)]=audio
        next_start=report[n+1]['start'] if n+1<len(report) else total
        item['gap_after']=max(0,next_start-item['end'])
    raw = target.with_suffix('.f32')
    try:
        mix.tofile(raw)
        command(['-f', 'f32le', '-ar', rate, '-ac', '1', '-i', raw,
                 '-af', 'alimiter=limit=0.841395:level=false', '-c:a', 'libmp3lame', '-b:a', '192k', target])
    finally:
        raw.unlink(missing_ok=True)
    return {'min_speed': MIN_SPEED, 'phrases': report,
            'changed': sum(x['speed'] < .999 for x in report),
            'long_gaps': [x for x in report if x['gap_after'] > LONG_GAP]}


def pause_report(path: Path) -> list[dict]:
    """Report actual silence in the encoded file, including silence returned by the provider."""
    import re
    result = subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-i', str(path), '-af',
                             f'silencedetect=noise=-40dB:d={LONG_GAP}', '-f', 'null', '-'],
                            capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise RuntimeError('Could not check the finished voice for pauses')
    return [{'start': round(float(end)-float(length), 3), 'end': round(float(end), 3),
             'seconds': round(float(length), 3)}
            for end, length in re.findall(r'silence_end: ([\d.]+) \| silence_duration: ([\d.]+)', result.stderr)]
