"""Reuse ElevenLabs clones by account, channel, language and exact reference audio."""
from __future__ import annotations
import fcntl
import hashlib
import math
from pathlib import Path
import subprocess
import threading
import time
import store

LOCK=threading.RLock()
# Stay below even the strictest reported per-file upload limit. Instant cloning
# uses one bounded sample; upload_files retains lossless transport for legacy callers.
UPLOAD_BYTES=900_000
UPLOAD_FILES=25
REFERENCE_SECONDS=70


def clone_files(source: Path, folder: Path) -> list[Path]:
    """Keep the full reference locally; send a compact sample for instant cloning."""
    duration = store.media_duration(source) or 0
    if source.suffix.lower() == '.mp3' and 0 < duration <= 120 and source.stat().st_size <= UPLOAD_BYTES:
        return [source]
    if duration <= 0:
        raise RuntimeError('Не вдалося прочитати звук прикладу голосу.')
    import numpy as np
    # Compare bounded windows by silence and clipping, favouring the earliest
    # equally usable window. This is not speaker separation or noise removal.
    scan = subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(source),'-t','300',
                           '-vn','-ac','1','-ar','8000','-f','s16le','pipe:1'],
                          capture_output=True,timeout=120)
    if scan.returncode or not scan.stdout:
        raise RuntimeError('Не вдалося підготувати приклад голосу. Оригінал збережено.')
    samples=np.frombuffer(scan.stdout,dtype='<i2').astype(np.float32)/32768
    window=min(len(samples),REFERENCE_SECONDS*8000)
    def quality(offset):
        segment=samples[offset:offset+window]
        frames=segment[:len(segment)//800*800].reshape(-1,800)
        active=float(np.mean(np.sqrt(np.mean(frames**2,axis=1)) > .006)) if len(frames) else 0
        return active-4*float(np.mean(np.abs(segment)>.99))
    start=max(range(0,max(1,len(samples)-window+1),5*8000),key=quality)/8000
    folder.mkdir(parents=True,exist_ok=True)
    prepared=folder/'clone-sample.mp3'
    result=subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(start),'-i',str(source),
                           '-t',str(min(REFERENCE_SECONDS,duration-start)),'-map','0:a:0','-vn',
                           '-af','loudnorm=I=-18:TP=-3:LRA=11','-ar','44100','-ac','1',
                           '-c:a','libmp3lame','-b:a','96k','-map_metadata','-1',str(prepared)],
                          capture_output=True,timeout=120)
    length=store.media_duration(prepared) if result.returncode==0 else None
    if not length or abs(length-min(REFERENCE_SECONDS,duration-start))>.15:
        raise RuntimeError('Не вдалося перевірити приклад голосу. Оригінал збережено.')
    store.atomic_json(folder/'preparation.json',{'source_duration':duration,'start':start,
        'sample_duration':length,'bytes':prepared.stat().st_size,'original_preserved':True})
    return upload_files(prepared,folder/'parts')


def upload_limit_error() -> RuntimeError:
    return RuntimeError(
        'Повний приклад голосу перевищує ліміт нового клону ElevenLabs: '
        'до 25 аудіофрагментів по 1 МБ. Запис збережено повністю. '
        'Використайте вже створений голос або завантажте коротший приклад.')


def upload_files(source: Path, folder: Path, max_bytes: int = UPLOAD_BYTES) -> list[Path]:
    """Split a prepared MP3 without re-encoding, retaining the entire recording."""
    if max_bytes <= 0:
        raise ValueError('max_bytes must be positive')
    if source.suffix.lower() != '.mp3':
        raise RuntimeError('Приклад голосу спершу потрібно перетворити на MP3.')
    size=source.stat().st_size
    duration=store.media_duration(source) or 0
    if not size or duration <= 0:
        raise RuntimeError('Не вдалося прочитати MP3 прикладу голосу.')
    if size <= max_bytes:
        return [source]
    # The provider limits both each file and the total sample count. A long
    # recording must never produce an invalid multipart request, lose its tail,
    # or silently be re-encoded at a lower quality to fit. resolve() checks the
    # shared clone registry before this transport preparation is even called.
    if size > max_bytes*UPLOAD_FILES:
        raise upload_limit_error()
    folder.mkdir(parents=True,exist_ok=True)
    count=min(UPLOAD_FILES,max(2,math.ceil(size/(max_bytes*.90))))
    for attempt in range(3):
        for path in folder.glob('reference-*.mp3'):
            path.unlink()
        result=subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(source),
                               '-map','0:a:0','-vn','-c:a','copy','-map_metadata','-1',
                               '-f','segment','-segment_times',','.join(f'{duration*n/count:.6f}' for n in range(1,count)),
                               '-reset_timestamps','1',str(folder/'reference-%04d.mp3')],
                              capture_output=True,timeout=120)
        if result.returncode:
            raise RuntimeError('Не вдалося підготувати MP3 для ElevenLabs. Оригінал збережено.')
        parts=sorted(folder.glob('reference-*.mp3'))
        if not parts:
            raise RuntimeError('Не вдалося підготувати частини прикладу голосу.')
        if len(parts) > UPLOAD_FILES:
            raise upload_limit_error()
        largest=max(path.stat().st_size for path in parts)
        if largest > max_bytes:
            if count >= UPLOAD_FILES:
                raise upload_limit_error()
            count=min(UPLOAD_FILES,math.ceil(count*largest/max_bytes*1.1))
            continue
        lengths=[store.media_duration(path) or 0 for path in parts]
        if any(length <= 0 for length in lengths) or abs(sum(lengths)-duration)>max(.1,len(parts)*.06):
            raise RuntimeError('Не вдалося зберегти повну тривалість прикладу голосу. Оригінал збережено.')
        return parts
    raise RuntimeError('Не вдалося вмістити частини MP3 у ліміт ElevenLabs. Оригінал збережено.')


def resolve(secret: str, channel: str, code: str, audio: bytes, known: str | None, create) -> str:
    # Only the fingerprint is stored; the credential remains in the vault.
    account=hashlib.sha256(secret.encode()).hexdigest()
    digest=hashlib.sha256(audio).hexdigest()
    identity=f'{account}:{channel}:{code}:{digest}'
    path=store.DATA_ROOT/'voice-clones'/'elevenlabs.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    with LOCK,path.with_suffix('.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        data=store.read_json(path,{}) or {}
        voices=data.setdefault('voices',{})
        found=(voices.get(identity) or {}).get('voice_id') or known
        if not found:
            previous=[*voices.values(),*data.get('legacy_voices',[])]
            ordinal=1+len({v['voice_id'] for v in previous if v.get('account')==account
                           and v.get('channel_id')==channel and v.get('language')==code})
            found=create(ordinal)
        if not found:raise RuntimeError('Сервіс не повернув клон голосу')
        voices[identity]={'voice_id':found,'account':account,'channel_id':channel,'language':code,
                          'audio_sha256':digest,'updated_at':time.time()}
        store.atomic_json(path,data)
        return found
