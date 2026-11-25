"""The gallery's cards load a small JPEG of each version, not the 2 MB original (25 November 2026)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store  # noqa: E402
import thumbnail_gen  # noqa: E402


class SmallVersionTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        patch.object(thumbnail_gen, "keep_dir", return_value=self.root).start()
        self.addCleanup(patch.stopall)
        Image.new("RGB", (1920, 1080), (200, 40, 40)).save(self.root / "Превью v2.png")

    def test_small_name_gives_a_cached_480_px_jpeg(self):
        small = thumbnail_gen.version_file("p", "Превью v2.small.png")
        self.assertEqual(small.suffix, ".jpg")
        with Image.open(small) as image:
            self.assertEqual(image.size, (480, 270))
        self.assertEqual(thumbnail_gen.version_file("p", "Превью v2.small.png"), small)   # made once
        self.assertEqual(thumbnail_gen.version_file("p", "Превью v2.png"), self.root / "Превью v2.png")
        self.assertEqual([p.name for p in self.root.glob("Превью*.png")], ["Превью v2.png"])

    def test_a_changed_original_replaces_its_small_copy(self):
        first = thumbnail_gen.version_file("p", "Превью v2.small.png")
        Image.new("RGB", (1280, 720), (0, 0, 200)).save(self.root / "Превью v2.png")
        second = thumbnail_gen.version_file("p", "Превью v2.small.png")
        self.assertNotEqual(first, second)
        self.assertFalse(first.exists())

    def test_unknown_names_are_refused(self):
        for name in ("Превью v9.small.png", "other.small.png", "../x.small.png"):
            with self.assertRaises(store.StudioError):
                thumbnail_gen.version_file("p", name)


if __name__ == "__main__":
    unittest.main()
