"""«Логотип» in the thumbnail gallery: the channel's logo laid by hand becomes a new cover version (17 November 2026)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import store
import thumbnail_gen
import thumbnail_logo


class PlaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.work = self.tmp / "preview"
        self.work.mkdir()
        Image.new("RGB", (1280, 720), "black").save(self.work / "Превью v2.png")
        self.logo = self.tmp / "logo.png"
        Image.new("RGBA", (200, 100), (255, 0, 0, 255)).save(self.logo)
        self.patches = [patch.object(store, "load_project", return_value={"id": "p", "channel_id": "c", "episode_path": ""}),
                        patch.object(thumbnail_gen, "keep_dir", return_value=self.work),
                        patch.object(thumbnail_logo.channel_branding, "logo_path", return_value=self.logo)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_the_logo_lands_where_it_was_put_on_a_new_cover_version(self):
        result = thumbnail_logo.place("p", "Превью v2.png", 0.5, 0.5, 0.25)
        self.assertEqual(result["name"], "Превью v3.png")
        with Image.open(self.work / "Превью v3.png") as made:
            self.assertEqual(made.getpixel((640 + 10, 360 + 10))[:3], (255, 0, 0))   # inside the 320×160 logo
            self.assertEqual(made.getpixel((600, 340))[:3], (0, 0, 0))               # outside it
        with Image.open(self.work / "Превью v2.png") as kept:
            self.assertEqual(kept.getpixel((650, 370))[:3], (0, 0, 0))               # the source version stays
        self.assertTrue(next(v for v in result["versions"] if v["name"] == "Превью v3.png")["current"])

    def test_a_logo_past_the_edge_stays_whole_on_the_picture(self):
        thumbnail_logo.place("p", "Превью v2.png", 0.99, 0.99, 0.2)
        with Image.open(self.work / "Превью v3.png") as made:
            self.assertEqual(made.getpixel((1279, 719))[:3], (255, 0, 0))

    def test_bad_values_and_a_channel_without_logo_are_refused(self):
        with self.assertRaises(store.StudioError):
            thumbnail_logo.place("p", "Превью v2.png", 0.1, 0.1, 5)
        self.logo.unlink()
        with self.assertRaisesRegex(store.StudioError, "логотипа"):
            thumbnail_logo.place("p", "Превью v2.png", 0.1, 0.1, 0.2)


if __name__ == "__main__":
    unittest.main()
