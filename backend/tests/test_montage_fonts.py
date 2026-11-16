import unittest
from unittest.mock import patch

import montage_ops


class ChannelFontsTest(unittest.TestCase):
    def context(self, typography, project_font=None):
        project = {"id": "p", "channel_id": "c", "tracks": [], "width": 1920, "height": 1080, "settings": {}}
        if project_font:
            project["font_family"] = project_font
        with patch.object(montage_ops.store, "get_channel_folder", return_value="folder"), \
             patch.object(montage_ops.store, "read_channel_settings", return_value={"typography": typography}):
            return montage_ops.Context(project)

    def test_text_frames_and_captions_take_the_channels_fonts(self):
        ctx = self.context({"font_family": "Mulish", "accent_font_family": "Play"})
        self.assertEqual((ctx.text_font, ctx.accent_font), ("Mulish", "Play"))

    def test_captions_fall_back_to_the_main_font_and_a_project_font_wins(self):
        self.assertEqual(self.context({"font_family": "Exo 2"}).accent_font, "Exo 2")
        ctx = self.context({"font_family": "Mulish", "accent_font_family": "Play"}, project_font="Rubik")
        self.assertEqual((ctx.text_font, ctx.accent_font), ("Rubik", "Rubik"))


if __name__ == "__main__":
    unittest.main()
