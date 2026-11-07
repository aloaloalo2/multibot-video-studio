"""Local full-band speech enhancement. Official pinned DeepFilterNet binaries, no uploaded audio."""
import hashlib
from pathlib import Path
import platform
import subprocess
import tempfile
import threading
import urllib.request
import numpy as np
import store

LOCK = threading.Lock()
VERSION = 'deepfilternet3-v0.5.6'
ASSETS = {
    'arm64': ('deep-filter-0.5.6-aarch64-apple-darwin', '4601e7f4e4c03e59a4c5b5000216ef3add3e808799cfccd95e14e83ea4611081'),
    'x86_64': ('deep-filter-0.5.6-x86_64-apple-darwin', 'd3be84003acb7c23e738ad7f70a158ec779a8d233a82e7fa3e717d112eb5b50f'),
}
MODEL_URL = 'https://raw.githubusercontent.com/Rikorose/DeepFilterNet/main/models/DeepFilterNet3_onnx.tar.gz'
MODEL_SHA = 'c94d91f70911001c946e0fabb4aa9adc37045f45a03b56008cb0c8244cb63616'


def tools():
    if platform.system() != 'Darwin' or platform.machine() not in ASSETS:
        raise store.StudioError('Локальне очищення DeepFilterNet поки не встановлене для цієї системи. Початковий запис доступний.')
    name, digest = ASSETS[platform.machine()]
    root = store.DATA_ROOT/'tools'/'deepfilter';root.mkdir(parents=True,exist_ok=True)
    with LOCK:
        for file, url, expected in [(root/'deep-filter', 'https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/'+name, digest),
                                    (root/'DeepFilterNet3.tar.gz', MODEL_URL, MODEL_SHA)]:
            if file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == expected: continue
            with urllib.request.urlopen(url, timeout=90) as response: data=response.read(50*1024*1024)
            if hashlib.sha256(data).hexdigest() != expected:
                raise store.StudioError('Не вдалося перевірити модель очищення. Початковий запис збережено.')
            pending=file.with_suffix('.download');pending.write_bytes(data);pending.replace(file)
        (root/'deep-filter').chmod(0o755)
    return root/'deep-filter',root/'DeepFilterNet3.tar.gz'


def command(args, timeout=600):
    result=subprocess.run([str(x) for x in args],capture_output=True,timeout=timeout)
    if result.returncode:
        raise store.StudioError('Не вдалося виконати локальне очищення. Початковий запис збережено.')
    return result.stdout


def enhance(source, target):
    binary, model = tools()
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        root=Path(tmp);input=root/'input.wav';out=root/'out'
        command(['ffmpeg','-v','error','-nostdin','-y','-i',source,'-ac','1','-ar','48000',input])
        command([binary,'-D','-m',model,'-o',out,input])
        results=list(out.glob('*.wav'))
        if len(results)!=1: raise store.StudioError('Модель не повернула очищений звук')
        # No positive gain. Limit peaks to those of the input and preserve exact duration.
        def decode(path):
            raw=command(['ffmpeg','-v','error','-i',path,'-ac','1','-ar','48000','-f','f32le','pipe:1'])
            return np.frombuffer(raw,dtype='<f4')
        before, after=decode(input),decode(results[0])
        if not len(after) or not np.isfinite(after).all(): raise store.StudioError('Очищений звук пошкоджено')
        peak_before=float(np.max(np.abs(before)));peak_after=float(np.max(np.abs(after)))
        gain=min(1.,peak_before/max(peak_after,1e-9),.94/max(peak_after,1e-9))
        duration=len(before)/48000
        command(['ffmpeg','-v','error','-nostdin','-y','-i',results[0],'-af',f'volume={gain:.9f},apad',
                 '-t',f'{duration:.9f}','-ac','1','-ar','48000','-b:a','160k','-map_metadata','-1',target])
