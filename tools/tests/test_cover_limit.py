"""A thumbnail over YouTube's 2 MB goes up as a JPG copy under the limit; the original stays."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import youtube_publish  # noqa: E402


class CoverLimitTest(unittest.TestCase):
    def test_a_big_cover_is_squeezed_into_a_jpg_and_a_small_one_goes_as_it_is(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            big = root / "Превью.png"
            Image.frombytes("RGB", (1920, 1080), os.urandom(1920 * 1080 * 3)).save(big)
            self.assertGreater(big.stat().st_size, youtube_publish.COVER_LIMIT)
            with mock.patch.object(youtube_publish, "DATA", root / "data"):
                out = youtube_publish.upload_cover({"id": "p"}, big)
                self.assertEqual(out.suffix, ".jpg")
                self.assertLessEqual(out.stat().st_size, youtube_publish.COVER_LIMIT)
                self.assertTrue(big.is_file())
                small = root / "small.png"
                Image.new("RGB", (64, 36), "black").save(small)
                self.assertEqual(youtube_publish.upload_cover({"id": "p"}, small), small)


if __name__ == "__main__":
    unittest.main()
