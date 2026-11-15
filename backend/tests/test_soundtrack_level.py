import sys
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audio_level
import soundtrack


class MusicLevelTest(unittest.TestCase):
    def test_music_sits_a_measured_distance_under_the_voice(self):
        with mock.patch.object(audio_level, 'measure', return_value={'lufs': -19.9, 'peak': -3.0}):
            volume = soundtrack.music_volume('music.wav')
        # −16 LUFS voice, 30 dB under it: −46 LUFS from a −19.9 LUFS file
        self.assertAlmostEqual(volume, 10 ** ((-46 + 19.9) / 20), places=3)
        self.assertLess(volume, .35)

    def test_unmeasured_music_is_quiet(self):
        with mock.patch.object(audio_level, 'measure', return_value=None):
            self.assertEqual(soundtrack.music_volume('music.wav'), soundtrack.MUSIC_FALLBACK_VOLUME)


if __name__ == '__main__':
    unittest.main()
