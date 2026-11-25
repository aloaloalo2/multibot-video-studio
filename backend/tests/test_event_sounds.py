"""event_sounds: the scan of the Razgon frames hands its events to the appearance-sound operation."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.tests import test_backend as support

store = support.store
import event_sounds  # noqa: E402
import montage_ops  # noqa: E402


class EventSoundsTest(unittest.TestCase):
    def test_the_scan_of_the_razgon_blocks_reaches_the_sound_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            razgon = Path(tmp) / "film"
            razgon.mkdir()
            (razgon / "config.json").write_text("{}")
            project = {"id": "a" * 24, "tracks": [{"clips": [
                {"title": "Razgon · кадр 004", "start": 10.0, "duration": 5.0},
                {"title": "Razgon · кадр 009", "start": 40.0, "duration": 6.0},
                {"title": "K005 кадр", "start": 15.0, "duration": 5.0}]}]}
            seen = {}

            def node(command, **kwargs):
                seen["command"] = command
                out = Path(command[command.index("--out") + 1])
                out.write_text(json.dumps({"events": [{"t": 11.0, "kind": "text"}]}))
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch.object(store, "load_project", return_value=project), patch.object(store, "project_animated", return_value=False), \
                    patch.object(store, "razgon_link", return_value={"razgon_root": tmp, "project": str(razgon)}), \
                    patch.object(store, "cache_dir", side_effect=lambda p: Path(tmp) / p["id"]), \
                    patch.object(event_sounds.subprocess, "run", side_effect=node), \
                    patch.object(montage_ops, "run", return_value={"report": ["звуки появи: 1 з 1 подій"]}) as ops:
                report = event_sounds.run("a" * 24, {4})
            self.assertIn("звуки появи", report)
            command = seen["command"]
            self.assertEqual(float(command[command.index("--from") + 1]), 9.8)    # only frame 4, with a little margin
            self.assertEqual(float(command[command.index("--to") + 1]), 15.2)
            op = ops.call_args[0][1][0]
            self.assertEqual((op["op"], op["frames"], op["prune_guessed"]), ("appear_sounds", [4], True))
            self.assertEqual(op["events"], [{"t": 11.0, "kind": "text"}])


if __name__ == "__main__":
    unittest.main()
