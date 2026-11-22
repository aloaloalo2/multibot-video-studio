"""A frame group fades in or out as one picture (user, 22 November 2026: «перехід використовує групи, а не кожен
слой»). Each layer faded alone shows the group's lower layers through its upper ones: at the middle of a crossfade a
green box on a blue photo read as a mix of green, blue and the outgoing red, where the group gives green over red."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import render


def fixture(root):
    paths = {}
    for name, size, colour in (('red', (320, 180), (255, 0, 0)), ('blue', (320, 180), (0, 0, 255)),
                               ('green', (80, 60), (0, 255, 0))):
        paths[name] = root / f'{name}.png'
        Image.new('RGB', size, colour).save(paths[name])
    join = {'type': 'crossfade', 'duration': .4, 'seam': 1.0}
    red = {'type': 'image', 'source': str(paths['red']), 'start': 0, 'duration': 1.4, 'x': .5, 'y': .5,
           'width': 1., 'height': 1., 'join_out': {**join, 'under': True, 'group': 'j:out'}}
    blue = {'type': 'image', 'source': str(paths['blue']), 'start': 1.0, 'duration': 1.0, 'x': .5, 'y': .5,
            'width': 1., 'height': 1., 'join_in': {**join, 'under': False, 'group': 'j:in'}}
    green = {'type': 'image', 'source': str(paths['green']), 'start': 1.0, 'duration': 1.0, 'x': .5, 'y': .5,
             'width': .25, 'height': 1 / 3, 'join_in': {**join, 'under': False, 'group': 'j:in'}}
    project = {'width': 320, 'height': 180, 'fps': 25, 'duration': 2.0, 'layer_mode': 'item',
               'timeline_layers': [{'clips': [red]}, {'clips': [blue]}, {'clips': [green]}]}
    manifest = root / 'project.json'
    manifest.write_text(json.dumps(project), encoding='utf-8')
    return manifest


def frame(video, number):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(video), '-map', '0:v', '-fps_mode', 'passthrough',
                                   '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'])
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, 180, 320, 3)[number].astype(int)


class GroupHelpersTest(unittest.TestCase):
    def test_only_fading_sides_on_top_belong_to_the_group(self):
        join = {'type': 'crossfade', 'duration': .4, 'seam': 1.0}
        self.assertEqual(render.group_key({'join_in': {**join, 'group': 'a:in'}}), 'a:in')
        self.assertIsNone(render.group_key({'join_in': {**join, 'group': 'a:in', 'under': True}}))
        self.assertIsNone(render.group_key({'join_in': {**join, 'type': 'slide_left', 'group': 'a:in'}}))
        self.assertIsNone(render.group_key({'join_in': join}))   # an older manifest fades each layer as before
        layer = {'global_offset': 1.0, 'join_in': {**join, 'group': 'a:in'}}
        self.assertAlmostEqual(render.group_alpha(layer, .2), .5)


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
class GroupFadeTest(unittest.TestCase):
    def check(self, gpu):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / 'out.mp4'
            result = subprocess.run([sys.executable, str(ROOT / 'render.py'), '--project', str(fixture(root)),
                                     '--output', str(output)], env={**os.environ, 'MULTIBOT_GPU_EXPORT': gpu},
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])
            middle = frame(output, 30)   # 1.2 s: half way through the crossfade
            box, photo = middle[90, 160], middle[20, 20]
            # the group's picture at half: green over red in the box, blue over red beside it
            self.assertLess(abs(box[0] - 128) + abs(box[1] - 128) + box[2], 30, box)
            self.assertLess(abs(photo[0] - 128) + photo[1] + abs(photo[2] - 128), 30, photo)

    def test_cpu_export_fades_the_group(self):
        self.check('0')

    @unittest.skipUnless(sys.platform == 'darwin' and os.uname().machine == 'arm64' and shutil.which('swiftc'),
                         'Apple Silicon GPU required')
    def test_gpu_export_fades_the_group(self):
        self.check('1')


if __name__ == '__main__':
    unittest.main()
