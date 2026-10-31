import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import video_plan

class StudioClientTest(unittest.TestCase):
    def test_command_only_submits_script_to_studio(self):
        channel = {"id": "abc", "name": "Channel", "path": "/tmp/Channel"}
        result = {"plan_url": "/channels/abc/projects/123/plan",
                  "plan": {"report": {"json": "/tmp/Channel/Episode/plan.json", "project_id": "123"},
                           "generator": "multibot-video-studio", "settings_signature": "saved-signature"}}
        with patch.object(video_plan, "studio_request", side_effect=[{"channels": [channel]}, result]) as request, \
             patch.object(sys, "argv", ["video_plan", "--channel", "Channel", "--script", "/tmp/Channel/Episode/script.txt"]), \
             contextlib.redirect_stdout(io.StringIO()):
            video_plan.main()
        self.assertEqual(request.call_args_list[1].args[1], "/api/projects/generate-plan")
        payload = request.call_args_list[1].args[2]
        self.assertEqual(payload["script_path"], str(Path("/tmp/Channel/Episode/script.txt").resolve()))
        self.assertNotIn("settings", payload)
        self.assertNotIn("plan", payload)

    def test_animated_channel_reports_waiting_for_voice(self):
        channel = {"id": "abc", "name": "Channel", "path": "/tmp/Channel"}
        result = {"awaiting_voice": True, "plan": None, "plan_url": "/channels/abc/projects/123/plan",
                  "project": {"id": "123"}, "script_sha256": "f" * 64}
        out = io.StringIO()
        with patch.object(video_plan, "studio_request", side_effect=[{"channels": [channel]}, result]), \
             patch.object(sys, "argv", ["video_plan", "--channel", "Channel", "--script", "/tmp/Channel/Episode/script.txt"]), \
             contextlib.redirect_stdout(out):
            video_plan.main()
        report = __import__("json").loads(out.getvalue())
        self.assertTrue(report["awaiting_voice"])
        self.assertEqual(report["plan_url"], "http://127.0.0.1:8770/channels/abc/projects/123/plan")
        self.assertNotIn("frames", report)

    def test_offline_studio_fails_without_local_generation(self):
        with patch.object(video_plan, "studio_request", side_effect=OSError("offline")), \
             patch.object(sys, "argv", ["video_plan", "--channel", "Channel", "--script", "/tmp/script.txt"]), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            video_plan.main()
        self.assertEqual(error.exception.code, 1)

if __name__ == "__main__":
    unittest.main()
