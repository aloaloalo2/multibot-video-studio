import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tests import test_backend as support

store = support.store
import audio_level  # noqa: E402


class AudioLevelTest(unittest.TestCase):
    def test_gain_brings_the_voice_to_the_standard_level_under_the_peak_ceiling(self):
        # a loud HeyGen voice (GORBUNOV-23): its peaks at 0 dBFS decide, −1.5 dB
        self.assertAlmostEqual(audio_level.gain({"lufs": -15.1, "peak": 0.0}), 10 ** (-1.5 / 20), places=3)
        # a quiet voice is brought up to −16 LUFS while its peaks stay clear
        self.assertAlmostEqual(audio_level.gain({"lufs": -22.0, "peak": -9.0}), 10 ** (6 / 20), places=3)
        self.assertAlmostEqual(audio_level.gain({"lufs": -22.0, "peak": -4.0}), 10 ** (2.5 / 20), places=3)

    def test_measure_reads_loudness_once_per_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(audio_level, "CACHE", Path(tmp) / "levels.json"):
            path = Path(tmp) / "tone.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4:sample_rate=48000", "-af", "volume=-12dB", str(path)], check=True)
            level = audio_level.measure(path)
            # ffmpeg's sine peaks at −18 dBFS, 12 dB down gives −30: a sine reads about 4 LU under its peak
            self.assertLess(abs(level["peak"] + 30), 0.6, level)
            self.assertLess(abs(level["lufs"] + 34), 1.5, level)
            with patch.object(audio_level.subprocess, "run", side_effect=AssertionError("measured twice")):
                self.assertEqual(audio_level.measure(path), level)


if __name__ == "__main__":
    unittest.main()
