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
# Stay below even the strictest reported per-file upload limit. All MP3 packets
# are sent in the same clone request; splitting is transport only, never a trim.
UPLOAD_BYTES=900_000


def upload_files(source: Path, folder: Path, max_bytes: int = UPLOAD_BYTES) -> list[Path]:
    """Split a prepared MP3 without re-encoding, retaining the entire recording."""
    if source.suffix.lower() != '.mp3':
        raise RuntimeError('Приклад голосу спершу потрібно перетворити на MP3.')
    size=source.stat().st_size
    duration=store.media_duration(source) or 0
    if not size or duration <= 0:
        raise RuntimeError('Не вдалося прочитати MP3 прикладу голосу.')
    if size <= max_bytes:
        return [source]
    folder.mkdir(parents=True,exist_ok=True)
    count=max(2,math.ceil(size/(max_bytes*.90)))
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
        largest=max(path.stat().st_size for path in parts)
        if largest > max_bytes:
            count=math.ceil(count*largest/max_bytes*1.1)
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
