"""A fractional audio end must not introduce an empty final video frame."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));import render

class TailFrameTest(unittest.TestCase):
    def test_cpu_and_gpu_keep_final_composition_through_fractional_audio_end(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=root/'image.png';Image.new('RGB',(320,180),(40,180,90)).save(image)
            voice=root/'voice.wav';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                'sine=frequency=440:duration=1.005','-y',str(voice)],check=True)
            project={'width':320,'height':180,'fps':25,'layer_mode':'item','timeline_layers':[
                {'clips':[{'type':'image','source':str(image),'start':0,'duration':1.005,
                           'x':.5,'y':.5,'width':1.,'height':1.}]},
                {'clips':[{'type':'audio','source':str(voice),'start':0,'duration':1.005,'volume':1}]}]}
            manifest=root/'project.json';manifest.write_text(json.dumps(project))
            visual,audio,total=render.timeline_plan(project,manifest,320,180,25)
            self.assertEqual(audio[0]['duration'],1.005)
            self.assertEqual(total,1.04)
            self.assertEqual(visual[0]['end'],total)
            for mode in ('0','1'):
                output=root/(mode+'.mp4')
                result=subprocess.run([sys.executable,str(ROOT/'render.py'),'--project',str(manifest),
                    '--output',str(output)],env={**os.environ,'MULTIBOT_GPU_EXPORT':mode,
                    'MULTIBOT_RENDER_CACHE':str(root/'cache')},capture_output=True,text=True,timeout=90)
                self.assertEqual(result.returncode,0,result.stdout[-1500:]+result.stderr[-1000:])
                raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-map','0:v',
                    '-fps_mode','passthrough','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
                frames=np.frombuffer(raw,dtype=np.uint8).reshape(-1,180,320,3)
                self.assertEqual(len(frames),26)
                self.assertLess(float(np.abs(frames[-1].astype(float)-(40,180,90)).mean()),4)
                self.assertLess(float(np.abs(frames[-1].astype(float)-frames[-2]).mean()),1)

    def test_explicit_long_tail_gap_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);voice=root/'voice.wav';subprocess.run(['ffmpeg','-v','error','-f','lavfi',
                '-i','sine=frequency=440:duration=1.5','-y',str(voice)],check=True)
            project={'layer_mode':'item','timeline_layers':[
                {'clips':[{'type':'animation','content_type':'shape','color':'#448855',
                           'start':0,'duration':1,'x':.5,'y':.5,'width':1.,'height':1.}]},
                {'clips':[{'type':'audio','source':str(voice),'start':0,'duration':1.5}]}]}
            visual,_,total=render.timeline_plan(project,root/'project.json',320,180,25)
            self.assertEqual(visual[0]['end'],1)
            self.assertEqual(total,1.52)

if __name__=='__main__':unittest.main()
