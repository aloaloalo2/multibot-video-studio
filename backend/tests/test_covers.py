import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import covers  # noqa: E402
import store  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is needed for video fixtures")
class CoverTest(unittest.TestCase):
    def test_cover_skips_a_dark_opening_for_a_detailed_frame_and_is_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dark, busy = tmp / "dark.mp4", tmp / "busy.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=2", "-r", "25", str(dark)], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x180:d=2", "-r", "25", str(busy)], check=True)
            assets = [{"id": "a1", "kind": "video", "path": str(dark)}, {"id": "a2", "kind": "video", "path": str(busy)}]
            project = {"id": "p" * 24, "duration": 4, "scene_groups": [],
                       "tracks": [{"clips": [{"id": "c1", "asset_id": "a1", "start": 0, "duration": 2},
                                             {"id": "c2", "asset_id": "a2", "start": 2, "duration": 2}]}]}
            with patch.object(store, "discover_assets", return_value=assets), patch.object(store, "project_dir", return_value=tmp / "project"):
                cover = covers.get(project)
                self.assertEqual(cover.suffix, ".webp")
                with covers.Image.open(cover) as image:
                    self.assertEqual(image.size, covers.SIZE)
                    self.assertGreater(covers.score(image.convert("RGB")), 20)
                with patch.object(covers, "frame", side_effect=AssertionError("cached cover was rebuilt")):
                    self.assertEqual(covers.get(project), cover)

    def test_project_without_scene_media_has_no_cover(self):
        project = {"id": "q" * 24, "duration": 4, "scene_groups": [], "tracks": [{"clips": [{"id": "t", "kind": "text", "start": 0, "duration": 1}]}]}
        with patch.object(store, "discover_assets", return_value=[]):
            self.assertIsNone(covers.get(project))


if __name__ == "__main__":
    unittest.main()
