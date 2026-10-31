"""Frame-aligned slices remain valid after floating-point subtraction."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import render

class SingleFrameDurationTest(unittest.TestCase):
    def test_one_frame_at_large_absolute_time_decodes_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for fps in (25,30,60):
                start=780.88
                duration=(start+1/fps)-start
                output=root/f'frame-{fps}.mp4';work=root/f'work-{fps}';work.mkdir()
                with patch.object(render,'hardware_export',return_value=False):
                    render.render_scene({'type':'color','color':'#17322f','duration':duration},root/'project.json',output,work,320,180,fps,239)
                info=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_entries','stream=nb_read_frames','-of','json',str(output)]))
                self.assertEqual(int(info['streams'][0]['nb_read_frames']),1)

    def test_real_half_frame_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for fps in (25,30,60):
                with self.assertRaisesRegex(ValueError,'duration must be at least'):
                    render.render_scene({'type':'color','duration':.5/fps},root/'p.json',root/'out.mp4',root,320,180,fps,239)

if __name__=='__main__':unittest.main()
