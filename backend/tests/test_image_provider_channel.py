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

    def test_the_avatar_goes_along_as_an_input_reference(self):
        # a paid test on 17 November 2026 drew Karl from his avatar this way, recognisably
        import base64, io
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            avatar = Path(tmp, "avatar.png")
            Image.new("RGB", (8, 8), "red").save(avatar)
            sent = {}
            png = io.BytesIO(); Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(png, "PNG")
            reply = {"data": [{"b64_json": base64.b64encode(png.getvalue()).decode()}], "usage": {"cost": 0.016}}
            class Answer:
                def __enter__(self): return io.BytesIO(json.dumps(reply).encode())
                def __exit__(self, *a): return False
            def urlopen(request, timeout):
                sent.update(json.loads(request.data)); return Answer()
            vault = mock.Mock(); vault.read.return_value = "k"
            with mock.patch.object(openrouter_images, "setting", return_value={"provider": "openrouter"}), \
                 mock.patch.object(openrouter_images.credentials, "vault", return_value=vault), \
                 mock.patch.object(openrouter_images.urllib.request, "urlopen", side_effect=urlopen), \
                 mock.patch.object(openrouter_images.project_costs, "record_at"), \
                 mock.patch.object(store, "project_dir", return_value=Path(tmp)):
                openrouter_images.draw("p", "the host", refs=[str(avatar)])
            ref = sent["input_references"][0]
            self.assertEqual(ref["type"], "image_url")
            self.assertTrue(ref["image_url"]["url"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
