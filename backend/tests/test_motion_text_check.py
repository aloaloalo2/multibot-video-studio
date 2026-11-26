"""The motion-code text check's own arithmetic (backend/motion_text_check.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import motion_text_check as M


class MotionTextCheckTest(unittest.TestCase):
    def test_colours_as_the_canvas_gives_them(self):
        self.assertEqual(M.parse_colour('#f555c5'), ((245, 85, 197), 1.0))
        self.assertEqual(M.parse_colour('rgba(243, 232, 240, 0.6)'), ((243, 232, 240), 0.6))
        self.assertIsNone(M.parse_colour('[object CanvasGradient]'))

    def test_contrast_is_wcag(self):
        self.assertAlmostEqual(M.ratio(M.luminance((255, 255, 255)), M.luminance((0, 0, 0))), 21, places=3)

    def test_moments_cover_every_line_fullest_first(self):
        moments = [{'t': 1, 'texts': [{'text': 'a', 'alpha': 1}]},
                   {'t': 2, 'texts': [{'text': 'a', 'alpha': 1}, {'text': 'b', 'alpha': 1}]},
                   {'t': 3, 'texts': [{'text': 'c', 'alpha': .2}]},
                   {'t': 4, 'texts': [{'text': 'c', 'alpha': 1}]}]
        self.assertEqual(M.pick_moments(moments), [2, 4])

    def test_clip_place_follows_its_keyframes(self):
        clip = {'x': .5, 'y': .5, 'scale': 1, 'keyframes': [{'time': 0, 'x': .4, 'scale': 1.0}, {'time': 2, 'x': .6, 'scale': 1.2}]}
        scale, cx, cy = M.place(clip, 1, 1920, 1080)
        self.assertAlmostEqual(scale, 1.1)
        self.assertAlmostEqual(cx, 960)
        self.assertAlmostEqual(cy, 540)


if __name__ == '__main__':
    unittest.main()
