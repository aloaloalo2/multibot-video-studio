"""gpu_prepare.py draws a picture that several slices or clips share only once (25 November 2026)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class PreparedPictureReuseTest(unittest.TestCase):
    def test_a_text_a_blurred_photo_and_same_coloured_shapes_are_drawn_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); photo = root/'photo.png'
            Image.new('RGB', (320, 180), (40, 120, 200)).save(photo)
            shape = {'type': 'animation', 'content_type': 'shape', 'color': '#ff0000', 'x': .25, 'y': .5, 'width': .3, 'height': .4}
            project = {'width': 320, 'height': 180, 'fps': 25, 'duration': 3, 'layer_mode': 'item', 'timeline_layers': [
                {'clips': [{'type': 'image', 'source': str(photo), 'start': 0, 'duration': 3, 'x': .5, 'y': .5,
                            'width': 1., 'height': 1., 'blur': 4}]},
                {'clips': [{**shape, 'start': 0, 'duration': 1}, {**shape, 'start': 2, 'duration': 1}]},
                {'clips': [{'type': 'text', 'text': 'Один напис', 'start': 0, 'duration': 3, 'x': .5, 'y': .8,
                            'width': .8, 'height': .3, 'font_size': 24, 'color': '#ffffff'}]}]}
            manifest = root/'project.json'; manifest.write_text(json.dumps(project))
            result = subprocess.run([sys.executable, str(ROOT/'gpu_prepare.py'), str(manifest), str(root/'work'), '3'],
                                    env={**os.environ, 'MULTIBOT_RENDER_CACHE': str(root/'cache')},
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout[-1000:] + result.stderr[-1000:])
            scenes = json.loads((root/'work'/'gpu-project.json').read_text())['scenes']
            self.assertEqual(len(scenes), 3)   # the shapes cut the film at 1 s and 2 s
            sources = [{Path(layer['source']).name for layer in scene['layers']} for scene in scenes]
            for name in ('graphic-', 'scene-'):   # the blurred photo and the text: one file in every slice
                used = {item for names in sources for item in names if item.startswith(name)}
                self.assertEqual(len(used), 1, (name, sources))
            sized = {item for names in sources for item in names if item.startswith('shape-')}
            self.assertEqual(len(sized), 1, sources)   # two clips of one colour and size share their picture


if __name__ == '__main__':
    unittest.main()
