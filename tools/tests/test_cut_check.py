import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cut_check  # noqa: E402


def jumping_cells(frames):
    """Count the cells cut_check marks as jumping between frames[1] and frames[2], the way main() measures them."""
    p0, p2 = cut_check.pan(frames[0], frames[1]), cut_check.pan(frames[2], frames[3])
    expect = (round((p0[0] + p2[0]) / 2), round((p0[1] + p2[1]) / 2))
    excess = cut_check.moved(frames[1], frames[2], expect) - 2 * np.maximum(
        cut_check.moved(frames[0], frames[1], p0), cut_check.moved(frames[2], frames[3], p2))
    return int((excess > cut_check.JUMP).sum())


class CutCheckTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(6)
        # a wide set, blurred so that it looks like a picture and not like noise
        world = rng.integers(0, 255, (300, 2000)).astype(np.float32)
        for _ in range(3):
            world = (world + np.roll(world, 1, 0) + np.roll(world, 1, 1) + np.roll(world, -1, 0) + np.roll(world, -1, 1)) / 5
        self.world = (world - world.min()) / (world.max() - world.min()) * 255

    def view(self, x):
        return self.world[:, x:x + 480].copy()

    def test_a_fast_pan_across_a_join_is_not_a_jump(self):
        # episode 06: 15 px a frame, and the picture entering at the edge read as jumping cells
        frames = [self.view(400 + 15 * k) for k in range(4)]
        self.assertEqual(jumping_cells(frames), 0)

    def test_a_camera_that_jerks_at_the_junction_still_fails(self):
        frames = [self.view(400), self.view(415), self.view(470), self.view(485)]
        self.assertGreaterEqual(jumping_cells(frames), cut_check.CELLS_FAIL)

    def test_a_pose_that_snaps_during_a_pan_still_fails(self):
        frames = [self.view(400 + 15 * k) for k in range(4)]
        for f in frames[2:]:
            f[100:160, 200:260] = 255 - f[100:160, 200:260]
        self.assertGreaterEqual(jumping_cells(frames), cut_check.CELLS_FAIL)


if __name__ == "__main__":
    unittest.main()
