import base64
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_image
import agent_storage
import store


class Response(io.BytesIO):
    headers = {"X-Generation-Id": "generated-test"}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


class Vault:
    def read(self, service):
        return "mock-key"


class AgentImageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old = store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT
        store.YOUTUBE_ROOT, store.DATA_ROOT = root / "youtube", root / "data"
        store.PROJECTS_ROOT = store.DATA_ROOT / "projects"
        channel = store.YOUTUBE_ROOT / "Channel"
        channel.mkdir(parents=True)
        (channel / "video-plan.json").write_text("{}")
        self.project = store.create_project(store.channel_id(channel), "Episode")

    def tearDown(self):
        store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT = self.old
        self.temp.cleanup()

    def response(self, transparent):
        image = Image.new("RGBA", (8, 8), (20, 40, 60, 0 if transparent else 255))
        image.putpixel((4, 4), (200, 100, 10, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        result = {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}], "usage": {"cost": .01}}
        return Response(json.dumps(result).encode())

    def test_transparency_and_real_cost_survive_import(self):
        with patch.object(agent_image.credentials, "vault", return_value=Vault()), patch.object(agent_image.urllib.request, "urlopen", return_value=self.response(True)) as call:
            asset = agent_image.generate_transparent_asset(self.project["id"], "A small apple")
        sent = json.loads(call.call_args.args[0].data)
        self.assertEqual(sent["background"], "transparent")
        with Image.open(asset["path"]) as image:
            self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
        cost = agent_storage.get_conversation(self.project["id"])["costs"][0]
        self.assertEqual(cost["amount_usd"], .01)
        self.assertEqual(cost["request_id"], "generated-test")
        self.assertEqual(len(store.load_project(self.project["id"])["assets"]), 1)

    def test_opaque_result_is_rejected_but_cost_is_recorded(self):
        with patch.object(agent_image.credentials, "vault", return_value=Vault()), patch.object(agent_image.urllib.request, "urlopen", return_value=self.response(False)):
            with self.assertRaises(store.StudioError):
                agent_image.generate_transparent_asset(self.project["id"], "An apple")
        self.assertFalse(store.load_project(self.project["id"])["assets"])
        self.assertEqual(agent_storage.get_conversation(self.project["id"])["costs"][0]["amount_usd"], .01)

    def test_fully_transparent_and_broken_images_are_rejected(self):
        image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        for data in (buffer.getvalue(), b"not a png"):
            with self.assertRaises(store.StudioError):
                agent_image.validate_transparent_png(data)


if __name__ == "__main__":
    unittest.main()
