import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tests import test_backend as support

store = support.store
import audio_level  # noqa: E402


class AudioLevelTest(unittest.TestCase):
    def test_visual_media_never_loads_narration_or_measures_audio(self):
        project={'tracks':[{'clips':[{'kind':'image','asset_id':'picture'},
                                    {'kind':'audio','asset_id':'voice'}]}]}
        with patch.object(audio_level, '_voice_paths', side_effect=AssertionError('visual request read narration')):
            self.assertEqual(audio_level.voice_file(project,'picture',Path('scene.png')),Path('scene.png'))
        with patch.object(audio_level,'_voice_paths',return_value={'voice':Path('voice.mp4')}), \
             patch.object(audio_level,'leveled',return_value=Path('leveled.flac')) as level:
            self.assertEqual(audio_level.voice_file(project,'voice',Path('voice.mp4')),Path('leveled.flac'))
            level.assert_called_once_with(Path('voice.mp4'),wait=False)

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

    def test_leveled_copy_reaches_the_standard_with_peaks_held(self):
        # a quiet voice with high peaks (HeyGen 08: −26.6 LUFS, peaks −5.1 dB): the capped gain stops far below −16,
        # the leveled copy reaches it, its peaks held under the ceiling, every sample in place
        with tempfile.TemporaryDirectory() as tmp, patch.object(audio_level, "CACHE", Path(tmp) / "levels.json"), \
                patch.object(audio_level, "LEVELED", Path(tmp) / "leveled"):
            path = Path(tmp) / "voice.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=6:sample_rate=48000",
                            "-f", "lavfi", "-i", "sine=frequency=2000:duration=6:sample_rate=48000", "-filter_complex",
                            "[0]volume=-4dB[a];[1]volume=0.4,volume='if(lt(mod(t,1),0.03),15,0.05)':eval=frame[b];[a][b]amix=normalize=0",
                            str(path)], check=True)
            level = audio_level.measure(path)
            self.assertLess(audio_level.gain(level), 10 ** ((audio_level.TARGET_LUFS - level["lufs"]) / 20) * 0.9, level)
            out = audio_level.leveled(path)
            self.assertNotEqual(out, path)
            got = audio_level.measure(out)
            # this test voice has peaks 20 dB over its body, far spikier than speech (08 came to −16.6): within 1.5 LU
            self.assertLess(abs(got["lufs"] - audio_level.TARGET_LUFS), 1.5, got)
            self.assertLessEqual(got["peak"], audio_level.PEAK_DBTP + 0.3, got)
            dur = lambda p: float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                                 capture_output=True, text=True).stdout)
            self.assertAlmostEqual(dur(out), dur(path), places=2)
            self.assertEqual(audio_level.leveled(path, wait=False), out)   # made once


if __name__ == "__main__":
    unittest.main()
