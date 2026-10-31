"""tools/studio.py, the agent's entry point, and studio_restart.py asking the studio once what runs."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import studio  # noqa: E402
import studio_restart  # noqa: E402

CHANNELS = {"channels": [{"id": "c" * 16, "name": "Алексей Горбунов"}, {"id": "d" * 16, "name": "What If"}]}
PROJECTS = {"projects": [
    {"id": "a" * 24, "channel_id": "c" * 16, "name": "Печень заплывает ЖИРОМ?", "episode_path": "/Y/Алексей Горбунов/23 Овощи и печень", "revision": 7},
    {"id": "b" * 24, "channel_id": "c" * 16, "name": "Медленный кишечник", "episode_path": "/Y/Алексей Горбунов/22 Медленный кишечник после 45", "revision": 3},
    {"id": "e" * 24, "channel_id": "d" * 16, "name": "What if 23", "episode_path": "/Y/What If/23 Sun", "revision": 1},
]}


class FakeStudio:
    """Answers the calls studio.py makes, and keeps what it was sent."""

    def __init__(self):
        self.sent = []

    def __call__(self, method, path, body=None, raw=False, timeout=900):
        self.sent.append((method, path, body))
        if path == "/api/channels":
            return CHANNELS
        if path == "/api/projects":
            return PROJECTS
        if "/summary" in path:
            data = {"fps": 25, "frames": [{"n": 12, "start": 10.0, "end": 14.0, "line": "", "issues": []}], "head": ["h"], "issues": []}
            return "h\n" if raw and "format=text" in path else data
        if path.endswith("/ops"):
            return {"revision": 8, "report": ["кадр 12: text"], "applied": 3, "actions": []}
        if path.endswith("/still"):
            return {"outputs": ["/s.png"], "time": body["time"], "renderer": "gpu", "seconds": 1.2, "notes": []}
        raise AssertionError(path)


class StudioToolTest(unittest.TestCase):
    def run_tool(self, *argv):
        fake, out, err = FakeStudio(), io.StringIO(), io.StringIO()
        with patch.object(studio, "call", fake), redirect_stdout(out), redirect_stderr(err):
            code = studio.main(list(argv))
        return code, out.getvalue(), err.getvalue(), fake.sent

    def test_a_project_is_found_by_words_of_its_channel_folder_or_title(self):
        with patch.object(studio, "call", FakeStudio()):
            self.assertEqual(studio.find_project("горбунов 23")["id"], "a" * 24)
            self.assertEqual(studio.find_project("ЖИРОМ")["id"], "a" * 24)
            self.assertEqual(studio.find_project("b" * 24)["id"], "b" * 24)
            with self.assertRaises(studio.Failure) as many:
                studio.find_project("23")
            self.assertIn("Знайдено 2", str(many.exception))
            with self.assertRaises(studio.Failure):
                studio.find_project("Ветров")

    def test_moments_from_seconds_minutes_or_a_frame(self):
        with patch.object(studio, "call", FakeStudio()):
            project = {"id": "a" * 24}
            self.assertAlmostEqual(studio.moment(project, "83.4"), 83.4)
            self.assertAlmostEqual(studio.moment(project, "1:23.4"), 83.4)
            self.assertAlmostEqual(studio.moment(project, "f12"), 12.0)
            self.assertAlmostEqual(studio.moment(project, "f12:start"), 10.001)
            self.assertAlmostEqual(studio.moment(project, "f12:end"), 14.0 - 1 / 25)   # the frame's last video frame at 25 fps

    def test_accent_sends_one_checked_operation(self):
        code, out, _, sent = self.run_tool("accent", "горбунов 23", "12", "text", "--phrase", "строчку про жир", "--at", "1290,190", "--style", "card", "--font-size", "46")
        self.assertEqual(code, 0)
        method, path, body = sent[-1]
        self.assertEqual((method, path), ("POST", f"/api/projects/{'a' * 24}/ops"))
        self.assertEqual(body["expected_revision"], 7)
        self.assertEqual(body["ops"], [{"op": "accent", "frame": 12, "kind": "text", "space": "frame", "phrase": "строчку про жир", "at": [1290.0, 190.0],
                                        "font_size": 46, "style": "card"}])
        self.assertIn("застосовано дій: 3, версія 8", out)

    def test_still_prints_the_picture_and_the_preview_link_at_the_same_moment(self):
        code, out, _, sent = self.run_tool("still", "горбунов 23", "f12")
        self.assertEqual(code, 0)
        self.assertEqual(sent[-1][2], {"time": 12.0, "frames": 1, "cpu": False})
        self.assertIn("/s.png", out)
        self.assertIn(f"/channels/{'c' * 16}/projects/{'a' * 24}?t=12.000", out)

    def test_a_studio_that_is_down_gives_a_short_answer(self):
        with patch.object(studio, "STUDIO", "http://127.0.0.1:9"), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(studio.main(["status"]), 1)
        self.assertIn("studio_restart.py", err.getvalue())


class RestartCheckTest(unittest.TestCase):
    def test_busy_work_asks_the_studio_once(self):
        asked = []
        def get(path, timeout=5):
            asked.append(path)
            return {"busy": ["режисура: What If / 07"], "exports": []} if path == "/api/studio/status" else None
        with patch.object(studio_restart, "get", get):
            self.assertEqual(studio_restart.busy_work(), ["режисура: What If / 07"])
        self.assertEqual(asked, ["/api/studio/status"])

    def test_an_older_studio_is_still_walked_project_by_project(self):
        def get(path, timeout=5):
            if path == "/api/studio/status":
                return None
            if path == "/api/exports/active":
                return {"jobs": [{"project_id": "p", "status": "running", "progress": 40, "stage": "rendering"}]}
            if path == "/api/channels":
                return {"channels": []}
            return None
        with patch.object(studio_restart, "get", get):
            self.assertEqual(studio_restart.busy_work(), ["експорт p: 40%, rendering"])


if __name__ == "__main__":
    unittest.main()
