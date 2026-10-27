"""Exercise compact hardware output across mixed color ranges and cuts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from PIL import Image

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))
import render


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg is required')
class HardwareExport(unittest.TestCase):
    def test_unavailable_hardware_uses_software_encoder(self):
        with mock.patch.dict(os.environ, {'MULTIBOT_EXPORT_ENCODER': 'auto'}):
            with mock.patch.object(render, 'hardware_hevc_available', return_value=False):
                self.assertFalse(render.hardware_export(320, 180, 25))
                self.assertIn('libx264', render.video_encoder_options(False))
        with mock.patch.dict(os.environ, {'MULTIBOT_EXPORT_ENCODER': 'software'}):
            with mock.patch.object(render, 'hardware_hevc_available') as probe:
                self.assertFalse(render.hardware_export(320, 180, 25))
                probe.assert_not_called()

    def test_mixed_sources_keep_color_frames_and_audio_across_fractional_cuts(self):
        if not render.hardware_export(320, 180, 25):
            self.skipTest('Hardware HEVC is not available')
        with tempfile.TemporaryDirectory(prefix='mbvs-hardware-test-') as tmp:
            root = Path(tmp)
            Image.new('RGB', (320, 180), (43, 173, 84)).save(root / 'photo.png')
            for name, color in [('red', '0xc83d22'), ('blue', '0x2354bf')]:
                subprocess.run([render.FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                                f'color=c={color}:s=320x180:r=25:d=2', '-c:v', 'libx264',
                                '-pix_fmt', 'yuv420p', str(root / f'{name}.mp4')], check=True)
            subprocess.run([render.FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=48000:duration=2', '-c:a', 'pcm_s16le',
                            str(root / 'voice.wav')], check=True)
            project = {'width': 320, 'height': 180, 'fps': 25, 'timeline_layers': [
                {'id': 'picture', 'clips': [
                    {'id': 'red', 'type': 'video', 'source': 'red.mp4', 'start': 0, 'duration': .51},
                    {'id': 'photo', 'type': 'image', 'source': 'photo.png', 'start': .51, 'duration': .75},
                    {'id': 'blue', 'type': 'video', 'source': 'blue.mp4', 'start': 1.26, 'duration': .74}]},
                {'id': 'sound', 'clips': [{'id': 'voice', 'type': 'audio', 'source': 'voice.wav',
                                            'start': .13, 'duration': 1.7, 'trim_start': .1, 'volume': .8}]}]}
            manifest = root / 'project.json'
            manifest.write_text(json.dumps(project), encoding='utf-8')
            outputs = []
            for encoder in ('software', 'auto'):
                out = root / (encoder + '.mp4')
                env = dict(os.environ, MULTIBOT_EXPORT_ENCODER=encoder)
                result = subprocess.run([sys.executable, str(ENGINE_DIR / 'render.py'), '--project',
                                         str(manifest), '--output', str(out)], capture_output=True,
                                        text=True, timeout=90, env=env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                outputs.append(out)
            info = json.loads(subprocess.check_output([render.FFPROBE, '-v', 'error', '-show_streams',
                                                        '-of', 'json', str(outputs[1])]))
            video = next(stream for stream in info['streams'] if stream['codec_type'] == 'video')
            self.assertEqual((video['codec_name'], video['codec_tag_string'], video['color_range']),
                             ('hevc', 'hvc1', 'tv'))
            def decode(path):
                return subprocess.check_output([render.FFMPEG, '-v', 'error', '-i', str(path),
                    '-map', '0:v:0', '-vf', 'crop=2:2:160:90', '-pix_fmt', 'rgb24',
                    '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'])
            reference, fast = map(decode, outputs)
            self.assertEqual(len(reference), 50 * 12)
            self.assertEqual(len(fast), len(reference))
            for index in range(50):
                a = reference[index * 12:index * 12 + 3]
                b = fast[index * 12:index * 12 + 3]
                self.assertLess(max(abs(x-y) for x,y in zip(a,b)), 12, f'Frame {index}')
                dominant = 0 if index < 13 else 1 if index < 32 else 2
                self.assertEqual(max(range(3), key=lambda i: b[i]), dominant, f'Cut at frame {index}')
            def sound(path):
                return subprocess.check_output([render.FFMPEG, '-v', 'error', '-i', str(path),
                    '-map', '0:a:0', '-f', 's16le', '-ac', '1', '-ar', '48000', '-'])
            self.assertEqual(sound(outputs[0]), sound(outputs[1]))
