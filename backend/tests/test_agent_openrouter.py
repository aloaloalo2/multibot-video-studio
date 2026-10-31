import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_openrouter
import agent_storage
import store


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Vault:
    def read(self, service):
        return "test-secret"


class AgentOpenRouterTest(unittest.TestCase):
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

    def test_records_actual_cost_and_never_persists_key(self):
        body = {"id": "gen-test", "choices": [{"message": {"role": "assistant", "content": "Hello"}}], "usage": {"cost": .004}}
        with patch.object(agent_openrouter.credentials, "vault", return_value=Vault()), patch.object(agent_openrouter.urllib.request, "urlopen", return_value=Response(json.dumps(body).encode())):
            result = agent_openrouter.chat(self.project["id"], [{"role": "user", "content": "Hello"}])
        self.assertEqual(result["content"], "Hello")
        saved = agent_storage.get_conversation(self.project["id"])
        self.assertEqual(saved["costs"][0]["amount_usd"], .004)
        self.assertEqual(saved["costs"][0]["request_id"], "gen-test")
        self.assertNotIn("test-secret", agent_storage.conversation_path(self.project["id"]).read_text())

    def test_failed_request_is_not_reported_as_free(self):
        with patch.object(agent_openrouter.credentials, "vault", return_value=Vault()), patch.object(agent_openrouter.urllib.request, "urlopen", side_effect=TimeoutError("secret error details")):
            with self.assertRaises(store.StudioError) as error:
                agent_openrouter.chat(self.project["id"], [])
        self.assertNotIn("secret", str(error.exception))
        summary = agent_storage.cost_summary(agent_storage.get_conversation(self.project["id"])["costs"])
        self.assertEqual(summary["unknown_count"], 1)

    def test_estimate_uses_current_model_pricing(self):
        payload = {"data": [{"id": agent_openrouter.MODEL, "pricing": {"prompt": "0.000001", "completion": "0.000002"}}]}
        with patch.object(agent_openrouter.urllib.request, "urlopen", return_value=Response(json.dumps(payload).encode())):
            prices = agent_openrouter.model_prices()
        estimated = agent_openrouter.estimate([{"role": "user", "content": "тест"}], prices, max_output_tokens=100)
        self.assertGreater(estimated["estimated_input_tokens"], 0)
        self.assertAlmostEqual(estimated["estimated_usd"], estimated["estimated_input_tokens"] * .000001 + .0002)

    def test_effort_is_sent_and_auto_preserves_provider_default(self):
        body = {"choices": [{"message": {"role": "assistant", "content": "OK"}}]}
        for effort in ("auto", "low", "high", "max"):
            with self.subTest(effort=effort), patch.object(agent_openrouter.credentials, "vault", return_value=Vault()), patch.object(agent_openrouter.urllib.request, "urlopen", return_value=Response(json.dumps(body).encode())) as open_url:
                agent_openrouter.chat(self.project["id"], [], reasoning_effort=effort)
                payload = json.loads(open_url.call_args.args[0].data)
                if effort == "auto":
                    self.assertNotIn("reasoning", payload)
                else:
                    self.assertEqual(payload["reasoning"], {"effort": effort})
                    self.assertTrue(payload["provider"]["require_parameters"])
        with self.assertRaises(store.StudioError):
            agent_openrouter.chat(self.project["id"], [], reasoning_effort="medium")


if __name__ == "__main__":
    unittest.main()
