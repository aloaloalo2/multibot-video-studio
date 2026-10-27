"""Real PCM peak envelopes for the local timeline, cached by source fingerprint."""
import audioop
import hashlib
import json
import math
import subprocess
import tempfile
import wave
from pathlib import Path

def read_peaks(source, cache_dir, bins=8000):
    source=Path(source);stat=source.stat()
    key=hashlib.sha256((str(source)+str(stat.st_size)+str(stat.st_mtime_ns)+str(bins)).encode()).hexdigest()
    cache=Path(cache_dir)/('%s.json'%key)
    if cache.exists():return json.loads(cache.read_text())
    with tempfile.TemporaryDirectory(prefix='studio-waveform-') as work:
        path=source
        try:
            audio=wave.open(str(path),'rb')
            if audio.getsampwidth()!=2:audio.close();raise wave.Error('Convert sample format')
        except (wave.Error,EOFError):
            path=Path(work)/'decoded.wav'
            subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(source),'-vn','-ac','1','-ar','8000','-c:a','pcm_s16le',str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=90)
            audio=wave.open(str(path),'rb')
        with audio:
            count=audio.getnframes();rate=audio.getframerate();size=max(1,math.ceil(count/bins));peaks=[]
            while True:
                block=audio.readframes(size)
                if not block:break
                low,high=audioop.minmax(block,2);peaks.append([round(low/32768,4),round(high/32768,4)])
            result=dict(duration=count/rate,peaks=peaks,samples_per_bin=size,sample_rate=rate,source_size=stat.st_size,source_mtime_ns=stat.st_mtime_ns)
    cache.parent.mkdir(parents=True,exist_ok=True)
    # Concurrent requests may finish in either order; each replacement is complete.
    temp=cache.with_suffix('.tmp-'+str(__import__('uuid').uuid4().hex));temp.write_text(json.dumps(result));temp.replace(cache)
    return result
