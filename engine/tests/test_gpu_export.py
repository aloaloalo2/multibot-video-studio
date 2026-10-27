"""End-to-end checks for GPU export, fallback and cancellation."""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gpu_export
import render


@unittest.skipUnless(sys.platform == 'darwin' and os.uname().machine == 'arm64'
                     and shutil.which('swiftc') and shutil.which('ffmpeg'), 'Apple Silicon GPU required')
class GPUExportTest(unittest.TestCase):
    def test_finished_preparer_cleanup_cannot_trigger_slow_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'still.png';Image.new('RGB',(320,180),(50,90,120)).save(source)
            project={'width':320,'height':180,'fps':25,'duration':1,'layer_mode':'item',
                     'timeline_layers':[{'clips':[{'type':'image','source':str(source),'start':0,
                                                  'duration':1,'x':.5,'y':.5,'width':1.,'height':1.}]}]}
            manifest=root/'p.json';manifest.write_text(json.dumps(project));output=root/'result.mp4'
            # macOS may reject signalling an already-exited process group.
            # Successful encoding must survive that best-effort cleanup.
            original_stream=gpu_export._stream;attempts=[];events=[]
            def transient_failure(command,stage,*args,**kwargs):
                if stage=='render':
                    attempts.append(stage)
                    if len(attempts)==1:raise gpu_export.GPUExportError('temporary encoder failure')
                return original_stream(command,stage,*args,**kwargs)
            with patch.dict(os.environ,{'MULTIBOT_RENDER_CACHE':str(root/'cache')}), \
                 patch.object(gpu_export.os,'killpg',side_effect=PermissionError(1,'Operation not permitted')), \
                 patch.object(gpu_export,'_stream',side_effect=transient_failure), \
                 patch.object(render,'emit',side_effect=lambda stage,**fields:events.append(stage)):
                summary=gpu_export.render_gpu(render,manifest,output,project,320,180,25,1)
            self.assertEqual(summary['duration'],1)
            self.assertTrue(output.is_file())
            self.assertEqual(len(attempts),2)
            self.assertIn('gpu_chunk_retry',events)

    def test_chunk_cache_reuses_visuals_and_invalidates_only_changed_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);clips=[]
            colors=[(220,30,30),(30,220,30),(30,30,220)]
            for n,color in enumerate(colors):
                path=root/f'{n}.png';Image.new('RGB',(320,180),color).save(path)
                clips.append({'type':'image','source':str(path),'start':n+.001 if n else 0,
                              'duration':1-.001 if n else 1,'x':.5,'y':.5,'width':1.,'height':1.})
            voice=root/'voice.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=3',
                            '-y',str(voice)],check=True)
            audio={'type':'audio','source':str(voice),'start':0,'duration':3,'volume':.2}
            project={'width':320,'height':180,'fps':25,'duration':3,'layer_mode':'item',
                     'timeline_layers':[{'clips':clips},{'clips':[audio]}]}
            manifest=root/'p.json';env={**os.environ,'MULTIBOT_GPU_EXPORT':'1','MULTIBOT_GPU_PIPELINE':'1',
                'MULTIBOT_RENDER_CACHE':str(root/'cache'),'STUDIO_GPU_CHUNK_SECONDS':'.5'}
            outputs=[]
            for mode in ('cold','audio','edit'):
                if mode=='audio':audio['volume']=.8
                if mode=='edit':Image.new('RGB',(320,180),(30,220,220)).save(root/'1.png')
                manifest.write_text(json.dumps(project));output=root/(mode+'.mp4')
                result=subprocess.run([sys.executable,str(ROOT/'render.py'),'--project',str(manifest),
                    '--output',str(output)],env=env,capture_output=True,text=True,timeout=90)
                self.assertEqual(result.returncode,0,result.stdout[-2000:]+result.stderr[-1000:])
                self.assertNotIn('gpu_fallback',result.stdout)
                events=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
                if mode=='audio':self.assertTrue(any(e.get('stage')=='cache_video' and e['reused'] for e in events))
                if mode=='edit':
                    chunks=[e for e in events if e.get('stage')=='cache_chunk']
                    self.assertTrue(any(e['reused'] for e in chunks),chunks)
                    self.assertTrue(any(not e['reused'] for e in chunks),chunks)
                raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-map','0:v',
                    '-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
                frames=np.frombuffer(raw,dtype=np.uint8).reshape(-1,180,320,3)
                self.assertEqual(len(frames),75)
                for index,color in enumerate(colors):
                    expected=(30,220,220) if mode=='edit' and index==1 else color
                    self.assertLess(float(np.abs(frames[index*25:(index+1)*25].astype(float)-expected).mean()),4)
                sound=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-map','0:a',
                    '-ac','1','-f','f32le','pipe:1'])
                outputs.append(np.frombuffer(sound,dtype=np.float32))
            rms=[float(np.sqrt(np.mean(a*a))) for a in outputs]
            self.assertAlmostEqual(rms[1]/rms[0],4,delta=.1)
            self.assertAlmostEqual(rms[1],rms[2],delta=.0001)

    def fixture(self, root):
        source = root / 'variable.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=s=320x180:r=30:d=4', '-vf', 'select=not(eq(mod(n\\,7)\\,0))',
                        '-fps_mode', 'vfr', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-y', str(source)], check=True)
        config = {'colors': ['#284a39', '#8b6440', '#303a70', '#823d37'],
                  'points': [[.1,.1],[.9,.1],[.8,.9],[.2,.9]], 'speed': .15,
                  'amplitude': .2, 'softness': .1}
        join = {'type': 'cin_champagne', 'duration': .4, 'seam': 1.2}
        gradient = {'type':'animation', 'content_type':'gradient', 'gradient':config,
                    'start':0, 'duration':1.6, 'x':.5, 'y':.5, 'width':1., 'height':1.,
                    'join_out':join}
        video = {'type':'video', 'source':str(source), 'start':1.2, 'duration':1.6,
                 'trim_start':.413, 'x':.5, 'y':.5, 'width':1., 'height':1., 'volume':0,
                 'join_in':join}
        graphic = {'type':'animation', 'content_type':'graphic_transition',
                   'graphic_style':'cin_champagne', 'start':1.2, 'duration':.4,
                   'x':.5, 'y':.5, 'width':1., 'height':1.}
        project = {'width':320, 'height':180, 'fps':25, 'duration':2.8, 'layer_mode':'item',
                   'timeline_layers':[{'clips':[gradient]}, {'clips':[video]}, {'clips':[graphic]}]}
        manifest = root / 'project.json'
        manifest.write_text(json.dumps(project), encoding='utf-8')
        return manifest

    def test_gpu_cli_keeps_timing_with_vfr_and_gradient_transition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = self.fixture(root)
            videos = []
            for mode in ('0', '1'):
                output = root / (mode+'.mp4')
                result = subprocess.run([sys.executable, str(ROOT/'render.py'), '--project', str(manifest),
                                         '--output', str(output)], env={**os.environ, 'MULTIBOT_GPU_EXPORT':mode},
                                        capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout[-2000:]+result.stderr[-2000:])
                if mode == '1':
                    self.assertIn('"stage": "gpu_start"', result.stdout)
                    self.assertNotIn('"stage": "gpu_fallback"', result.stdout)
                raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(output), '-map', '0:v',
                                               '-fps_mode', 'passthrough', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'])
                videos.append(np.frombuffer(raw, dtype=np.uint8).reshape(-1,180,320,3).astype(np.int16))
            self.assertEqual(len(videos[0]), 70)
            self.assertEqual(len(videos[0]), len(videos[1]))
            difference = np.abs(videos[0]-videos[1]).mean(axis=(1,2,3))
            self.assertLess(float(difference.mean()), 4)
            self.assertLess(float(difference.max()), 8)

    def test_gpu_error_falls_back_to_verified_renderer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = self.fixture(root); output = root/'fallback.mp4'; events = []
            with patch.dict(os.environ, {'MULTIBOT_GPU_EXPORT':'1'}), \
                 patch.object(gpu_export, 'available', return_value=True), \
                 patch.object(gpu_export, 'render_gpu', side_effect=gpu_export.GPUExportError('test failure')), \
                 patch.object(render, 'emit', side_effect=lambda stage, **data: events.append(stage)):
                render.render(manifest, output)
            self.assertIn('gpu_fallback', events)
            self.assertIn('complete', events)
            self.assertGreater(output.stat().st_size, 1024)

    def test_rotated_video_uses_the_established_renderer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root/'source.mp4'; rotated = root/'rotated.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=25:d=2',
                            '-c:v','libx264','-pix_fmt','yuv420p','-y',str(source)],check=True)
            subprocess.run(['ffmpeg','-v','error','-display_rotation','90','-i',str(source),'-c','copy',
                            '-y',str(rotated)],check=True)
            project = {'width':320,'height':180,'fps':25,'duration':1,'layer_mode':'item',
                       'timeline_layers':[{'clips':[{'type':'video','source':str(rotated),'start':0,
                                                     'duration':1,'trim_start':0,'x':.5,'y':.5,
                                                     'width':1.,'height':1.,'volume':0}]}]}
            manifest=root/'project.json';manifest.write_text(json.dumps(project))
            result=subprocess.run([sys.executable,str(ROOT/'gpu_prepare.py'),str(manifest),str(root/'work'),'1'],
                                  env={**os.environ,'STUDIO_GPU_CPU_FALLBACK':'1'},capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout[-1000:]+result.stderr[-1000:])
            self.assertIn('CPU fallback',result.stdout)

    def test_cancel_gpu_export_removes_temporary_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = self.fixture(root); output = root/'cancelled.mp4'
            log = root/'cancel.log'
            with log.open('w') as stream:
                process = subprocess.Popen([sys.executable, str(ROOT/'render.py'), '--project', str(manifest),
                                            '--output', str(output)], env={**os.environ, 'MULTIBOT_GPU_EXPORT':'1',
                                                                         'MULTIBOT_RENDER_CACHE_ENABLED':'0'},
                                           stdout=stream, stderr=subprocess.STDOUT, text=True, start_new_session=True)
                try:
                    deadline=time.monotonic()+15
                    while time.monotonic()<deadline and process.poll() is None:
                        if '"stage": "gpu_start"' in log.read_text():break
                        time.sleep(.02)
                    self.assertIn('"stage": "gpu_start"', log.read_text())
                    time.sleep(.2)
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=15)
                    self.assertNotEqual(process.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertFalse(list(root.glob('.mbvs-gpu-*')))
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()


if __name__ == '__main__':
    unittest.main()
