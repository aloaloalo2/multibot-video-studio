import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production

KIT = Path(__file__).resolve().parents[2] / "razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/tools/codex_image.py"


class CodexLimitTest(unittest.TestCase):
    """Codex out of its limit puts the frame job on pause instead of frames without pictures (user, 14 November 2026)."""

    def tool(self):
        namespace = {}
        exec(KIT.read_text(encoding="utf-8").split("ap = argparse")[0], namespace)
        return namespace

    def test_the_tool_recognises_the_limit_and_its_reset(self):
        tool = self.tool()
        text = "ERROR: You've hit your usage limit. Upgrade to Pro, or try again at 5:12 PM."
        self.assertTrue(tool["LIMIT"].search(text))
        self.assertEqual(tool["reset_time"](text), "о 17:12")
        self.assertFalse(tool["LIMIT"].search("stream disconnected before completion"))

    def test_the_note_names_codex_and_the_reset(self):
        note = production.codex_limit_note("о 17:12")
        self.assertIn("ліміт Codex", note)
        self.assertIn("о 17:12", note)
        self.assertIn("Продовжити", note)
        self.assertNotIn("<", production.codex_limit_note("<script>"))

    def test_pause_keeps_the_codex_note(self):
        saved = {}
        project = {"production_request": {"id": "r", "status": "in_progress"}}
        with mock.patch.object(production.store, "load_project", return_value=project), \
             mock.patch.object(production, "run_log", return_value=Path("/nowhere/log")), \
             mock.patch.object(production.store, "project_dir", return_value=Path("/nowhere")), \
             mock.patch.object(production.director, "stop"), \
             mock.patch("razgon_sound.stop"), \
             mock.patch.object(production, "set_request", side_effect=lambda pid, **f: saved.update(f)):
            production.pause("p", production.codex_limit_note("о 17:12"))
        self.assertTrue(saved["paused"])
        self.assertIn("ліміт Codex", saved["error"])


class CodexBackgroundTest(unittest.TestCase):
    """Codex draws in the background while the agent writes other frames (user, 14 November 2026)."""

    FAKE = """#!/bin/bash
dir=""; while [ $# -gt 0 ]; do [ "$1" = "-C" ] && dir="$2"; shift; done
p=$(cat); name=$(echo "$p" | grep -o '"[^"]*\\.png"' | tail -1 | tr -d '"')
sleep 2
python3 -c "open('$dir/$name','wb').write(b'png')"
"""

    def test_two_sheets_draw_at_once_and_wait_collects_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp, "codex.sh")
            fake.write_text(self.FAKE)
            fake.chmod(0o755)
            Path(tmp, "p.txt").write_text("a sheet")
            env = {**os.environ, "CODEX_IMAGE_BIN": str(fake)}
            started = time.monotonic()
            for name in ("a.png", "b.png"):
                run = subprocess.run([sys.executable, str(KIT), "--prompt", "p.txt", "--out", name, "--background"],
                                     cwd=tmp, env=env, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
            self.assertLess(time.monotonic() - started, 2)
            done = subprocess.run([sys.executable, str(KIT), "--wait", "a.png", "b.png"], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(Path(tmp, "a.png").is_file() and Path(tmp, "b.png").is_file())
            self.assertLess(time.monotonic() - started, 9)


if __name__ == "__main__":
    unittest.main()
