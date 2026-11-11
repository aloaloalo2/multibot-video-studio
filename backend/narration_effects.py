"""Local room reverb shared by browser audition and saved narration."""
from array import array
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import shutil
import threading
import wave

import store

VERSION = 4
RATE = 48000
DEFAULT = {'enabled': False, 'preset': 'office', 'amount': 15}
NOISE_DEFAULT = {'enabled': False, 'preset': 'office', 'amount': 35}
NOISE_PRESETS = {'office':'Тихий кабінет','room':'Тиха кімната','soft':'М’який фон','city':'Місто вдалині'}
RESOURCES = Path(__file__).parent / 'resources'
PRESETS = {'office': ('Кабінет лікаря', .24, .0081), 'studio': ('Студія', .18, .008),
           'room': ('Кімната', .62, .022), 'hall': ('Зала', 1.2, .035)}
LOCK = threading.RLock()


def normalize(value=None):
    if value is not None and not isinstance(value, dict):
        raise store.StudioError('Невірні налаштування реверберації')
    result = {**DEFAULT, **(value or {})}
    if set(result) != set(DEFAULT) or type(result['enabled']) is not bool or not isinstance(result['preset'], str) or result['preset'] not in PRESETS:
        raise store.StudioError('Оберіть простір для реверберації')
    amount = result['amount']
    if type(amount) not in (int, float) or not math.isfinite(amount) or not 0 <= amount <= 100:
        raise store.StudioError('Сила реверберації має бути від 0 до 100%')
    return result


def active(value):
    value = normalize(value)
    return value['enabled'] and value['amount'] > 0


def noise_options(value=None):
    if value is not None and not isinstance(value, dict):
        raise store.StudioError('Невірні налаштування фонового шуму')
    value = {**NOISE_DEFAULT, **(value or {})}
    if set(value) != set(NOISE_DEFAULT) or type(value['enabled']) is not bool or not isinstance(value['preset'], str) or value['preset'] not in NOISE_PRESETS or type(value['amount']) not in (int, float) or not math.isfinite(value['amount']) or not 0 <= value['amount'] <= 100:
        raise store.StudioError('Гучність фонового шуму має бути від 0 до 100%')
    return value


def noise_active(value=None):
    value = noise_options(value)
    return value['enabled'] and value['amount'] > 0


def noise_gain(value):
    amount = noise_options(value)['amount']
    return 10 ** ((-60 + amount * .3) / 20) / .1 if amount > 0 else 0.


def identity(value, room_noise=None):
    value = normalize(value)
    noise = noise_options(room_noise)
    if not active(value) and not noise_active(noise):
        return ''
    return hashlib.sha256(json.dumps([VERSION, value if active(value) else None, noise if noise_active(noise) else None], sort_keys=True).encode()).hexdigest()[:20]


def gains(value):
    value=normalize(value)
    if value['preset']=='office':
        wet=.10*(value['amount']/100)**.8
        return 1-wet*.25,wet
    wet = value['amount'] / 100 * .22
    return 1 - wet, wet


@lru_cache(maxsize=1)
def impulse_gain_options():
    # FFmpeg renamed its IR normalization control; both variants must remain unnormalized.
    help_text = subprocess.run(['ffmpeg','-hide_banner','-h','filter=afir'],capture_output=True,text=True,timeout=10,check=True)
    return 'gtype=-1:irnorm=-1:irgain=1' if 'irnorm' in help_text.stdout + help_text.stderr else 'gtype=-1:irgain=1'


def impulse(preset):
    if preset not in PRESETS:
        raise store.StudioError('Невідомий простір', 404)
    target = store.DATA_ROOT / 'audio-effects' / f'v{VERSION}' / (preset + '.wav')
    with LOCK:
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            pending = target.with_suffix('.pending.wav')
            try:
                shutil.copyfile(RESOURCES / 'voice-rooms' / (preset + '.wav'), pending)
                pending.replace(target)
            finally:pending.unlink(missing_ok=True)
    return target


def microphone_noise(preset='office'):
    """Quiet CC0 room recordings, prepared once and kept entirely offline."""
    if preset not in NOISE_PRESETS:
        raise store.StudioError('Невідомий кімнатний фон', 404)
    target = store.DATA_ROOT / 'audio-effects' / f'v{VERSION}' / ('noise-' + preset + '.wav')
    with LOCK:
        if target.is_file():return target
        raw = subprocess.check_output(['ffmpeg','-v','error','-i',str(RESOURCES/'voice-roomtones'/(preset+'.flac')),
                                       '-ac','1','-ar',str(RATE),'-f','s16le','-'],timeout=20)
        pcm=array('h');pcm.frombytes(raw)
        if sys.byteorder != 'little':pcm.byteswap()
        values=[float(x) for x in pcm]
        fade=round(RATE*.4)
        for i in range(fade):
            t=i/fade;values[i]=values[-fade+i]*(1-t)+values[i]*t
        values=values[:-fade]
        scale=.1*32767/math.sqrt(sum(x*x for x in values)/len(values))
        pcm=array('h',(max(-32767,min(32767,round(x*scale))) for x in values))
        if sys.byteorder != 'little':pcm.byteswap()
        target.parent.mkdir(parents=True,exist_ok=True)
        pending=target.with_suffix('.pending.wav')
        try:
            with wave.open(str(pending),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(RATE);out.writeframes(pcm.tobytes())
            pending.replace(target)
        finally:pending.unlink(missing_ok=True)
    return target


def render(source, value, destination, room_noise=None, closing_pause=0.):
    """Source already includes the closing pause; keep that exact duration."""
    import languages
    value = normalize(value)
    noise = noise_options(room_noise)
    dry, wet = gains(value)
    # Use the same unnormalized impulse as Web Audio's ConvolverNode.
    inputs = ['-i', str(source)]
    probe = subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=channels','-of','csv=p=0',str(source)],capture_output=True,text=True,timeout=10,check=True)
    layout = 'pan=stereo|c0=c0|c1=c0,' if probe.stdout.strip() == '1' else ''
    graph = f'[0:a]{layout}aformat=sample_rates={RATE}:channel_layouts=stereo'
    if active(value):
        inputs += ['-i', str(impulse(value['preset']))]
        graph += (f',asplit=2[d][s];[s][1:a]afir=dry=1:wet=1:{impulse_gain_options()}:minp=512[w];'
                  f'[d][w]amix=inputs=2:weights={dry:.6f} {wet:.6f}:normalize=0:duration=first')
    if noise_active(noise):
        slot = 2 if active(value) else 1
        inputs += ['-stream_loop', '-1', '-i', str(microphone_noise(noise['preset']))]
        duration = store.media_duration(Path(source))
        fade_at = max(0., duration - max(.25, closing_pause))
        graph += (f'[voice];[{slot}:a]pan=stereo|c0=c0|c1=c0,volume={noise_gain(noise):.8f},afade=t=in:d=0.08,'
                  f'afade=t=out:st={fade_at:.6f}:d=0.25[n];'
                  '[voice][n]amix=inputs=2:normalize=0:duration=first')
    graph += ',alimiter=limit=.98:level=0:latency=1[out]'
    codec = ['-c:a', 'flac'] if Path(destination).suffix == '.flac' else ['-c:a', 'libmp3lame', '-b:a', '128k']
    languages.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', *inputs, '-filter_complex', graph,
                   '-map', '[out]', *codec, str(destination)], 'застосувати налаштування голосу')
