"""A full-frame photo that misses the frame by a few pixels is flagged even over the studio's black ground (26 November 2026)."""
import unittest

from backend.tests import test_backend as support  # noqa: F401  (sys.path)
import agent_view


class Picture:
    """A 1.85 picture contained in a 1920×1080 frame: 1920×1040 at scale 1, held at `scale`."""
    W, H, cw, ch, duration, portrait = 1920, 1080, 1920, 1040, 3.0, False

    def __init__(self, scale):
        self.scale = scale

    def state(self, moment):
        return .5, .5, self.scale


CLIP = {"kind": "image", "width": 1, "height": 1}


class UncoveredOverFieldTest(unittest.TestCase):
    def test_a_thin_strip_over_the_black_ground_is_a_defect(self):
        self.assertEqual(agent_view._uncovered({}, CLIP, Picture(1.03), field=True), "відкритий край 4px на 0.0с")

    def test_a_wide_margin_over_a_field_is_the_frames_design(self):
        self.assertIsNone(agent_view._uncovered({}, CLIP, Picture(.8), field=True))
        self.assertIsNotNone(agent_view._uncovered({}, CLIP, Picture(.8), field=False))

    def test_a_photo_that_covers_the_frame_passes(self):
        self.assertIsNone(agent_view._uncovered({}, CLIP, Picture(1.04), field=True))


if __name__ == "__main__":
    unittest.main()
