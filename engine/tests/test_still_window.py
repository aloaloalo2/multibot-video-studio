"""gpu_prepare.py in a still's window (engine/still.py): the frame drawn is the export's frame at that moment."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StillWindowTest(unittest.TestCase):
    def test_a_still_draws_a_clip_as_the_export_does_not_cut_at_the_window(self):
        # a still at 5 s of a 10 s picture that fades out at its end: the export shows it whole at 5 s; cutting the
        # clip at the still's window made it fade out inside the window (alpha 0.1)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); picture = root/'red.png'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=320x180','-frames:v','1','-y',str(picture)],check=True)
            project = {'width':320,'height':180,'fps':25,'duration':10,'layer_mode':'item',
                       'timeline_layers':[{'clips':[{'type':'image','source':str(picture),'start':0,'duration':10,'x':.5,'y':.5,
                                                     'width':1.,'height':1.,'preset':'fade_out','preset_duration':.4}]}]}
            manifest=root/'project.json';manifest.write_text(json.dumps(project))
            result=subprocess.run([sys.executable,str(ROOT/'gpu_prepare.py'),str(manifest),str(root/'work'),'5.04'],
                                  env={**os.environ,'STUDIO_GPU_WINDOW_START':'5'},capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr[-1000:])
            prepared=json.loads((root/'work'/'gpu-project.json').read_text())
            self.assertEqual(len(prepared['scenes']),1)
            self.assertEqual(prepared['scenes'][0]['layers'][0]['frames'][0][3],1.0)



class VideoBitrateTest(unittest.TestCase):
    def test_the_export_window_quality_reaches_the_encoder(self):
        sys.path.insert(0, str(ROOT))
        import render
        self.assertEqual(render.video_bitrate({}), 2_000_000)                     # 2 Mbit/s unless the author picks
        self.assertEqual(render.video_bitrate({"video_bitrate": 8_000_000}), 8_000_000)
        self.assertEqual(render.video_bitrate({"video_bitrate": 999}), 2_000_000)  # only the window's choices
        render.EXPORT_BITRATE = 12_000_000
        try:
            options = render.video_encoder_options(True)
            self.assertEqual(options[options.index("-b:v") + 1], "12000000")
        finally:
            render.EXPORT_BITRATE = render.DEFAULT_VIDEO_BITRATE


if __name__ == "__main__":
    unittest.main()
