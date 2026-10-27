"""Guarded Apple Silicon GPU export using the existing timeline contract."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import queue
import threading
import signal
import time
from pathlib import Path
from render_cache import RenderCache, key_for, renderer_version, visual_key, prepared_key


class GPUExportError(RuntimeError):
    pass


def _build(root, binary, cache, version):
    key=key_for(['swift-build',version,os.uname().machine,os.uname().release,shutil.which('swiftc')])
    if cache.restore('build',key,binary) is not None:
        binary.chmod(0o700)
        return
    compilation=subprocess.run([shutil.which('swiftc'),'-O',str(root/'gpu_render.swift'),'-o',str(binary)],
                               capture_output=True,text=True,timeout=120)
    if compilation.returncode:
        raise GPUExportError('Could not build GPU renderer: '+compilation.stderr[-1000:])
    cache.publish('build',key,binary)


def _validate_video(renderer,path,width,height,fps,frames):
    stream=next((s for s in renderer.probe(path).get('streams',[]) if s.get('codec_type')=='video'),{})
    if (int(stream.get('width',0))!=width or int(stream.get('height',0))!=height
        or int(stream.get('nb_frames',0))!=frames or stream.get('codec_name')!='hevc'):
        raise GPUExportError('GPU video chunk differs from validated timeline')
    if abs(float(stream.get('duration',0))-frames/fps)>1/fps+.001:
        raise GPUExportError('GPU video chunk has incorrect duration')


def _pipelined(renderer,root,binary,project_file,work,env,width,height,fps,total,cache,version):
    """Prepare the next scenes while a single GPU worker encodes ready chunks."""
    events=queue.Queue();tail=[];prepared_until=0.;rendered_until=0.;segments=[]
    process=subprocess.Popen([sys.executable,str(root/'gpu_prepare.py'),str(project_file),str(work),str(total)],
                             stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,
                             env={**env,'STUDIO_GPU_CHUNKS':'1'},start_new_session=True)
    def read_events():
        try:
            for line in process.stdout:
                events.put(line)
        finally:events.put(None)
    reader=threading.Thread(target=read_events,daemon=True);reader.start()
    def progress():
        renderer.emit('scene_done',rendered_duration=min(.999,(.4*prepared_until+.6*rendered_until)/total),total_duration=1)
    try:
        while True:
            line=events.get()
            if line is None:break
            tail.append(line.strip());tail=tail[-12:]
            match=re.search(r'timeline_end=([0-9.]+)',line)
            if match:
                prepared_until=max(prepared_until,float(match.group(1)));progress()
            if not line.startswith('{'):continue
            event=json.loads(line)
            if event.get('stage')!='chunk_ready':continue
            manifest=Path(event['path']);chunk=json.loads(manifest.read_text())
            prepared_until=max(prepared_until,float(event['end']))
            frames=sum(renderer.frame_index(s['end']-s['start'],fps) for s in chunk['scenes'])
            key=prepared_key(chunk['scenes'],width,height,fps,cache,version)
            target=work/f'chunk-{event["index"]:06d}.mp4'
            hit=cache.restore('chunk',key,target)
            if hit is not None:
                try:_validate_video(renderer,target,width,height,fps,frames)
                except (GPUExportError,ValueError,TypeError):
                    target.unlink();cache.discard('chunk',key);hit=None
            if hit is None:
                def chunk_progress(stage,**fields):
                    nonlocal rendered_until
                    if stage=='scene_done':
                        rendered_until=max(rendered_until,float(event['start'])+float(fields['rendered_duration'])*chunk['duration'])
                        progress()
                for attempt in range(2):
                    try:
                        _stream([str(binary),str(manifest),str(target)],'render',chunk_progress,env,frames,preparation_weight=0)
                        _validate_video(renderer,target,width,height,fps,frames)
                        break
                    except GPUExportError as error:
                        target.unlink(missing_ok=True)
                        if attempt:raise
                        renderer.emit('gpu_chunk_retry',index=event['index'],message=str(error)[-1000:])
                        time.sleep(.25)
                cache.publish('chunk',key,target)
            renderer.emit('cache_chunk',index=event['index'],reused=hit is not None)
            segments.append(target);rendered_until=float(event['end']);progress()
            acknowledgement=work/'chunks'/'consumed.tmp'
            acknowledgement.write_text(str(event['index']+1));os.replace(acknowledgement,work/'chunks'/'consumed')
        code=process.wait()
        if code:raise GPUExportError('\n'.join(tail)[-2000:] or f'Preparation failed ({code})')
        if not segments or abs(rendered_until-total)>.001:raise GPUExportError('Incomplete GPU chunk sequence')
        metadata=json.loads((work/'gpu-metadata.json').read_text())
        return segments,metadata
    finally:
        # Also stop a source conversion still running after a preparation
        # error. This group is separate so ordinary fallback cannot leave a
        # background FFmpeg process competing with the replacement renderer.
        try:os.killpg(process.pid,signal.SIGTERM)
        except OSError:pass
        if process.poll() is None:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except OSError:pass
                process.wait()
        reader.join(timeout=5)
        if process.stdout:process.stdout.close()


def available(project: dict, width: int, height: int, fps: int) -> bool:
    """Keep the established renderer for unsupported machines or formats."""
    if os.environ.get('MULTIBOT_GPU_EXPORT', '1') == '0' or os.environ.get('MULTIBOT_EXPORT_ENCODER') == 'software':
        return False
    if sys.platform != 'darwin' or not shutil.which('swiftc'):
        return False
    if os.uname().machine != 'arm64' or 'timeline_layers' not in project:
        return False
    if width * height > 1920 * 1080 or fps > 30:
        return False
    root = Path(__file__).resolve().parent
    return (root / 'gpu_prepare.py').is_file() and (root / 'gpu_render.swift').is_file()


def _stream(command, stage, emit, env, total_frames=1, preparation_weight=.45):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, env=env, bufsize=1)
    lines = []
    try:
        for line in process.stdout:
            lines.append(line.strip())
            if len(lines) > 12:
                lines.pop(0)
            if stage == 'prepare':
                match = re.match(r'prepared scene\s+(\d+)\s*/\s*(\d+)', line)
                if match:
                    timeline = re.search(r'timeline_end=([0-9.]+)\s+timeline_total=([0-9.]+)', line)
                    completed = (float(timeline.group(1))/max(.001,float(timeline.group(2))) if timeline
                                 else int(match.group(1))/max(1,int(match.group(2))))
                    fraction = preparation_weight * min(1,completed)
                    emit('scene_done', rendered_duration=fraction, total_duration=1)
            else:
                match = re.search(r'frames=(\d+)', line)
                if match:
                    fraction = preparation_weight + (1-preparation_weight) * min(1, int(match.group(1)) / total_frames)
                    emit('scene_done', rendered_duration=fraction, total_duration=1)
        result = process.wait()
    finally:
        if process.stdout:
            process.stdout.close()
        if process.poll() is None:
            process.terminate()
            process.wait()
    if result:
        raise GPUExportError('\n'.join(lines)[-2000:] or f'GPU process failed ({result})')


def render_gpu(renderer, project_file: Path, output: Path, project: dict,
               width: int, height: int, fps: int, total: float) -> dict:
    """Render into temporary files and publish only after a complete decode."""
    root = Path(__file__).resolve().parent
    output = output.expanduser().resolve()
    if output.suffix.lower() != '.mp4' or output == project_file:
        raise GPUExportError('Invalid export destination')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise GPUExportError('Output already exists')
    with tempfile.TemporaryDirectory(prefix='.mbvs-gpu-', dir=output.parent) as temp:
        work = Path(temp)
        binary = work / 'gpu-render'
        pipeline=os.environ.get('MULTIBOT_GPU_PIPELINE','1')!='0'
        cache=RenderCache(max_bytes=None if pipeline else 0)
        version=renderer_version(root)
        env = {**os.environ, 'STUDIO_GPU_CPU_FALLBACK': '1',
               'STUDIO_GPU_PROCEDURAL_GRADIENT': '1', 'STUDIO_GPU_VIDEO_BLUR': '0',
               'STUDIO_GPU_PERSISTENT_CACHE':'1' if pipeline else '0',
               'GPU_CODEC': 'hevc', 'GPU_BITRATE': '2000000'}
        video = work / 'video.mp4'
        visual,audio,_=renderer.timeline_plan(project,project_file,width,height,fps)
        scene_count=len(renderer.timeline_segments(visual,total,fps))
        full_key=visual_key(project,project_file,width,height,fps,total,renderer,cache,version) if pipeline else None
        reused=cache.restore('visual',full_key,video) if full_key else None
        if reused is not None:
            try:_validate_video(renderer,video,width,height,fps,renderer.frame_index(total,fps))
            except (GPUExportError,ValueError,TypeError):
                video.unlink();cache.discard('visual',full_key);reused=None
        if reused is not None:
            segments=[video];metadata={'audio':audio,'duration':total}
            renderer.emit('cache_video',reused=True)
            renderer.emit('scene_done',rendered_duration=1,total_duration=1)
        else:
            _build(root,binary,cache,version)
            if pipeline:
                segments,metadata=_pipelined(renderer,root,binary,project_file,work,env,width,height,fps,total,cache,version)
            else:
                preparation_weight = .6 if total > 600 else .45
                _stream([sys.executable, str(root/'gpu_prepare.py'), str(project_file), str(work), str(total)],
                        'prepare', renderer.emit, env, preparation_weight=preparation_weight)
                prepared = json.loads((work/'gpu-project.json').read_text(encoding='utf-8'))
                metadata=prepared
                _stream([str(binary), str(work/'gpu-project.json'), str(video)], 'render', renderer.emit,
                        env, renderer.frame_index(total, fps), preparation_weight)
                segments=[video]
        if abs(float(metadata['duration']) - total) > .001:
            raise GPUExportError('GPU timeline duration differs from validated project')
        temporary = work / 'complete.mp4'
        renderer.compose_timeline(segments, metadata['audio'], temporary, work, total)
        renderer.verify_output_streams(renderer.probe(temporary), total, fps)
        renderer.emit('verify', progress=0)
        renderer.run_ffmpeg([renderer.FFMPEG, '-nostdin', '-v', 'error', '-xerror', '-i', str(temporary),
                             '-progress', 'pipe:1', '-nostats', '-f', 'null', '-'], 'verify', duration=total)
        if full_key and reused is None:
            if visual_key(project,project_file,width,height,fps,total,renderer,cache,version)!=full_key:
                raise GPUExportError('Visual source changed during export')
            cache.publish('visual',full_key,work/'joined.mp4',{'scenes':scene_count})
        renderer.emit('cache_summary',hits=cache.hits,misses=cache.misses)
        os.link(temporary, output)
    summary = {'duration': round(total, 3), 'width': width, 'height': height, 'fps': fps,
               'scenes': scene_count,
               'clips': sum(len(layer['clips']) for layer in project['timeline_layers'])}
    renderer.emit('complete', output=str(output), **summary)
    return summary
