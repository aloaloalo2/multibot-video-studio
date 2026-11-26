"""A transparent HEVC written by FFmpeg's hevc_videotoolbox (the studio's motion-code renders) holds straight colour but
is labelled premultiplied; the GPU export must draw its soft edges as the CPU export does (26 November 2026: letters of
a motion-code clip got a ring of light dots, «що з якістю тексту?»)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gpu_export
import render


@unittest.skipUnless(sys.platform == 'darwin' and os.uname().machine == 'arm64'
                     and shutil.which('swiftc') and shutil.which('ffmpeg'), 'Apple Silicon GPU required')
class StraightAlphaHevcTest(unittest.TestCase):
    def test_soft_edges_of_a_transparent_hevc_keep_their_colour(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # white rings with soft edges on a transparent picture, as Chromium's screenshot gives them: straight RGBA,
            # the colour of every edge pixel white whatever its alpha
            mask = Image.new('L', (320, 180), 0)
            draw = ImageDraw.Draw(mask)
            for x in (60, 160, 260):
                draw.ellipse((x - 40, 50, x + 40, 130), fill=255)
                draw.ellipse((x - 22, 68, x + 22, 112), fill=0)
            mask = mask.filter(ImageFilter.GaussianBlur(1.6))
            picture = Image.merge('RGBA', (*[Image.new('L', (320, 180), 240)] * 3, mask))
            still = root / 'rings.png'
            picture.save(still)
            video = root / 'rings.mov'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-framerate', '25', '-i', str(still), '-t', '1',
                            '-c:v', 'hevc_videotoolbox', '-alpha_quality', '0.9', '-q:v', '70', '-tag:v', 'hvc1',
                            '-pix_fmt', 'bgra', str(video)], check=True)
            project = {'width': 320, 'height': 180, 'fps': 25, 'duration': 1, 'layer_mode': 'item', 'background': '#000000',
                       'timeline_layers': [{'clips': [{'type': 'video', 'source': str(video), 'start': 0, 'duration': 1,
                                                       'x': .5, 'y': .5, 'width': 1., 'height': 1., 'volume': 0}]}]}
            manifest = root / 'p.json'
            manifest.write_text(json.dumps(project))
            output = root / 'out.mp4'
            with patch.dict(os.environ, {'MULTIBOT_RENDER_CACHE': str(root / 'cache')}), \
                 patch.object(render, 'emit', side_effect=lambda stage, **fields: None):
                gpu_export.render_gpu(render, manifest, output, project, 320, 180, 25, 1)
            frame = root / 'frame.png'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '0.5', '-i', str(output), '-frames:v', '1', str(frame)], check=True)
            drawn = np.asarray(Image.open(frame).convert('L'), dtype=float)
            alpha = np.asarray(mask, dtype=float) / 255
            expected = 240 * alpha   # straight white over black
            edge = (alpha > .03) & (alpha < .5)
            self.assertGreater(edge.sum(), 200)
            # read as premultiplied, a faint edge pixel came out near white (240 instead of a few tens)
            self.assertLess(np.abs(drawn[edge] - expected[edge]).mean(), 20)


if __name__ == '__main__':
    unittest.main()
