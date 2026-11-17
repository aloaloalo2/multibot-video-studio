import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sound_settings


class MusicStyleTest(unittest.TestCase):
    """A channel chooses the style of its generated music (user, 17 November 2026)."""

    def test_the_original_score_is_the_default_and_unknown_styles_are_refused(self):
        self.assertEqual(sound_settings.normalize({})['music']['style'], 'whatif')
        self.assertEqual(sound_settings.normalize({'music': {'style': 'space'}})['music']['style'], 'space')
        with self.assertRaises(ValueError):
            sound_settings.normalize({'music': {'style': 'disco'}})

    def test_every_style_renders_and_sounds_different_from_the_original(self):
        import numpy as np
        music = sound_settings.audio_module('music')
        plan = [{'start': 0, 'end': 4, 'mood': 'wonder', 'intensity': .6}]
        base = music.render_score(plan, 4, seed=7)
        for style in sound_settings.MUSIC_STYLES:
            out = music.render_score(plan, 4, seed=7, style=style)
            self.assertTrue(np.isfinite(out).all())
            if style == 'whatif':
                self.assertTrue(np.allclose(out, base))   # What If keeps the very same score
            else:   # above the shared bass line the instruments and the tune differ
                n = min(len(out), len(base))
                self.assertLess(abs(np.corrcoef(music.hp(out[:n, 0], 300), music.hp(base[:n, 0], 300))[0, 1]), .6)
        self.assertEqual(set(sound_settings.MUSIC_STYLES), set(music.STYLES))

    def test_every_synthesizer_keeps_the_music_changing_with_the_mood(self):
        # The author likes that the score changes with the story (17 November 2026): a synthesizer swaps instruments only.
        import numpy as np
        music = sound_settings.audio_module('music')
        for style in sound_settings.MUSIC_STYLES:
            one, two = (music.hp(music.render_score([{'start': 0, 'end': 4, 'mood': mood, 'intensity': .6}], 4, seed=7, style=style)[:, 0], 300)
                        for mood in ('mystery', 'wonder'))
            n = min(len(one), len(two))
            self.assertLess(abs(np.corrcoef(one[:n], two[:n])[0, 1]), .6, style)
            self.assertNotEqual(music.styled('mystery', style)['bpm'], music.styled('tension', style)['bpm'])


if __name__ == '__main__':
    unittest.main()
