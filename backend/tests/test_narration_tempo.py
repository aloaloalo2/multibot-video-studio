from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import narration_tempo as tempo
import store


class TempoPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(store, 'DATA_ROOT', self.root / 'studio')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.source = self.root / 'take.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'lavfi',
                        '-i', 'sine=frequency=440:sample_rate=48000:duration=3', str(self.source)], check=True)

    def test_slow_preview_is_lossless_pitch_preserved_and_never_changes_the_original(self):
        before = hashlib.sha256(self.source.read_bytes()).digest()
        target = tempo.preview(self.source, .9)
        self.assertTrue(target.is_relative_to(store.DATA_ROOT))
        self.assertEqual(target.suffix, '.flac')
        self.assertAlmostEqual(store.media_duration(target), 3/.9, delta=.07)
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(target), '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'])
        samples = np.frombuffer(raw, dtype='<f4')
        for part in (samples[24000:72000], samples[72000:120000]):
            frequencies = np.fft.rfftfreq(len(part), 1/48000)
            self.assertAlmostEqual(frequencies[np.argmax(abs(np.fft.rfft(part)))], 440, delta=1)
            self.assertLess(np.max(abs(part)), .14)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(), before)
        with patch.object(tempo.languages, 'run', side_effect=AssertionError('must reuse preview')):
            self.assertEqual(tempo.preview(self.source, .9), target)
            self.assertEqual(tempo.preview(self.source, 1), self.source)

    def test_changed_source_has_a_separate_cache_and_invalid_speed_never_starts_render(self):
        first = tempo.preview(self.source, 1.05)
        self.source.write_bytes(self.source.read_bytes() + b'\0\0')
        self.assertNotEqual(tempo.preview(self.source, 1.05), first)
        with patch.object(tempo.languages, 'run') as render:
            for value in [None, True, 'nan', 'inf', {}, .86, 1.06]:
                with self.assertRaises(store.StudioError):
                    tempo.speed(value)
            render.assert_not_called()

    def test_failed_local_render_keeps_source_and_does_not_publish_partial_preview(self):
        before = self.source.read_bytes()
        with patch.object(tempo.languages, 'run', side_effect=RuntimeError('local encoder stopped')):
            with self.assertRaises(RuntimeError):
                tempo.preview(self.source, .9)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(list(store.DATA_ROOT.rglob('*.flac')), [])
