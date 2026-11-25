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


class HandWritingTest(unittest.TestCase):
    """A written text is a keyboard; a pencil only where a hand or a pen writes it (user, 25 November 2026)."""

    def test_write_events_in_a_shot_with_a_hand_are_marked(self):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        import event_sounds, store
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "story").mkdir()
            (root / "scenes" / "shots").mkdir(parents=True)
            (root / "story" / "shots.json").write_text(json.dumps({"shots": [{"id": "f001s01", "start": 0, "end": 5}, {"id": "f002s01", "start": 5, "end": 9}]}))
            (root / "scenes" / "shots" / "f001s01.js").write_text("kText(g, 'Title', 1, 1)")
            (root / "scenes" / "shots" / "f002s01.js").write_text("drawHand(g, pencil.x, pencil.y); kText(g, 'Note', 1, 1)")
            events = [{"t": 1, "kind": "write", "dur": 1}, {"t": 6, "kind": "write", "dur": 1}, {"t": 7, "kind": "text"}]
            with patch.object(store, "razgon_link", return_value={"project": str(root)}):
                marked = event_sounds.mark_hands({}, events)
        self.assertEqual([e.get("hand") for e in marked], [None, True, None])

    def test_typing_pass_takes_keys_for_texts_and_a_pencil_only_for_a_hand(self):
        import soundtrack
        self.assertTrue(soundtrack.HAND.search("const hand = drawHand()"))
        self.assertTrue(soundtrack.HAND.search("chalk.write"))
        self.assertFalse(soundtrack.HAND.search("handler(); kText('Андромеда')"))
