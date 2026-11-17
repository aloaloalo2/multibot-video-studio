import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openrouter_images
import store


class ChannelImageProviderTest(unittest.TestCase):
    """«Малює» in the channel's settings picks Codex or OpenRouter; an episode's own choice wins (17 November 2026)."""

    def check(self, channel, episode):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            if episode:
                (folder / "image-provider.json").write_text(json.dumps({"provider": episode}))
            with mock.patch.object(store, "project_dir", return_value=folder), \
                 mock.patch.object(store, "load_project", return_value={"channel_id": "c"}), \
                 mock.patch.object(store, "get_channel_folder", return_value=folder), \
                 mock.patch.object(store, "read_channel_settings", return_value={"animation": {"image_provider": channel}}):
                return openrouter_images.setting("p").get("provider")

    def test_channel_choice_and_episode_override(self):
        self.assertEqual(self.check("openrouter", None), "openrouter")
        self.assertIsNone(self.check("codex", None))
        self.assertIsNone(self.check("openrouter", "codex"))
        self.assertEqual(self.check("codex", "openrouter"), "openrouter")


if __name__ == "__main__":
    unittest.main()
