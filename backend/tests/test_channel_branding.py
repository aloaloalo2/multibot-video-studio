import base64
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import channel_branding  # noqa: E402
import store  # noqa: E402


def png(size=(200, 100), color=(255, 0, 0, 255)):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


class BrandingTest(unittest.TestCase):
    def test_settings_validation(self):
        channel_branding.validate({"channel_kind": "animated", "logo": {"position": "bottom-left", "size": 20, "margin": 2, "opacity": 80, "enabled": True}})
        for bad in ({"channel_kind": "cartoon"}, {"logo": {"position": "center"}}, {"logo": {"size": 90}}, {"logo": {"opacity": 0}}, {"logo": "x"}):
            with self.assertRaises(channel_branding.BrandingError):
                channel_branding.validate(bad)

    def test_box_uses_width_percent_for_size_and_margin(self):
        frame = (1920, 1080)
        self.assertEqual(channel_branding.box({"position": "top-right", "size": 10, "margin": 2}, (400, 200), frame), (1920 - 192 - 38, 38, 192, 96))
        self.assertEqual(channel_branding.box({"position": "bottom-center", "size": 10, "margin": 2}, (400, 200), frame), ((1920 - 192) // 2, 1080 - 96 - 38, 192, 96))
        self.assertEqual(channel_branding.box({"position": "middle-left", "size": 10, "margin": 0}, (100, 100), frame), (0, (1080 - 192) // 2, 192, 192))

    def test_save_draw_and_remove_logo(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, "DATA_ROOT", Path(tmp)), patch.object(store, "get_channel_folder", return_value=Path(tmp)):
            info = channel_branding.save_logo("a" * 16, png((3000, 1500)))
            self.assertEqual((info["width"], info["height"]), (1200, 600))
            frame = Image.new("RGB", (1920, 1080), (0, 0, 0))
            drawn = channel_branding.draw(frame, "a" * 16, {"position": "top-left", "size": 10, "margin": 0, "opacity": 100})
            self.assertEqual(drawn.getpixel((5, 5))[:3], (255, 0, 0))
            self.assertEqual(drawn.getpixel((1900, 1000))[:3], (0, 0, 0))
            self.assertIs(channel_branding.draw(frame, "a" * 16, {"enabled": False}), frame)
            overlay = channel_branding.overlay_png("a" * 16, {"position": "bottom-right"}, (1920, 1080), Path(tmp) / "overlay.png")
            with Image.open(overlay) as image:
                self.assertEqual(image.size, (1920, 1080))
                self.assertEqual(image.getpixel((5, 5))[3], 0)
            channel_branding.remove_logo("a" * 16)
            self.assertIsNone(channel_branding.logo_info("a" * 16))

    def test_rejects_files_that_are_not_images(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, "DATA_ROOT", Path(tmp)), patch.object(store, "get_channel_folder", return_value=Path(tmp)):
            with self.assertRaises(channel_branding.BrandingError):
                channel_branding.save_logo("a" * 16, base64.b64encode(b"not an image").decode())

    def test_display_name_keeps_the_folder_and_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "What If"; folder.mkdir()
            plain = store.channel_record(folder)
            self.assertEqual((plain["name"], plain["folder_name"]), ("What If", "What If"))
            (folder / store.PLAN_CONFIG).write_text('{"display_name": "  Що як  "}')
            named = store.channel_record(folder)
            self.assertEqual((named["name"], named["folder_name"], named["id"]), ("Що як", "What If", plain["id"]))
            (folder / store.PLAN_CONFIG).write_text('{"display_name": null}')
            self.assertEqual(store.channel_record(folder)["name"], "What If")
        base = {"weights": {"stock_photo": 100}}
        store.validate_settings({**base, "display_name": None})
        for bad in ("", "   ", 5, "x" * 81):
            with self.assertRaisesRegex(store.StudioError, "Назва каналу"):
                store.validate_settings({**base, "display_name": bad})


if __name__ == "__main__":
    unittest.main()
