"""An episode in the publishing queue goes to one session only (26 November 2026: three waiting sessions each uploaded
Andromeda: «чому 3 сесії публікують роліки?… це баг публікації»)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import youtube_publish as y


class ClaimTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        for pid in ("a" * 24, "b" * 24):
            (data / "projects" / pid).mkdir(parents=True)
            (data / "projects" / pid / "project.json").write_text("{}")
        self.patches = [patch.object(y, "DATA", data), patch.object(y, "QUEUE", data / "youtube-queue.json"),
                        patch.object(y, "LISTENER", data / "youtube-listener.json"), patch.object(y, "LOCK", data / "youtube-queue.lock")]
        for p in self.patches:
            p.start()
        y.QUEUE.write_text(json.dumps([{"project": "a" * 24}, {"project": "b" * 24}]))

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_each_episode_is_taken_once(self):
        self.assertEqual(y.claim(), "a" * 24)
        self.assertEqual(y.claim(), "b" * 24)   # a second session gets the next one, never the same
        self.assertIsNone(y.claim())
        rows = json.loads(y.QUEUE.read_text())
        self.assertTrue(all(row["claimed"]["pid"] == os.getpid() for row in rows))

    def test_a_claim_left_by_a_session_that_never_prepared_expires(self):
        rows = [{"project": "a" * 24, "claimed": {"pid": 1, "at": 0}}]
        y.QUEUE.write_text(json.dumps(rows))
        self.assertEqual(y.claim(), "a" * 24)

    def test_a_second_waiting_session_is_told_to_finish(self):
        y.LISTENER.write_text(json.dumps({"pid": 4242}))
        with patch.object(y, "waiting", return_value=True):
            with self.assertRaises(y.studio.Failure) as caught:
                y.wait(poll=0.01)
        self.assertIn("Інша сесія", str(caught.exception))
        with patch.object(y, "waiting", return_value=False):
            self.assertEqual(y.wait(poll=0.01), "a" * 24)
        self.assertEqual(json.loads(y.LISTENER.read_text())["pid"], os.getpid())

    def test_prepare_takes_the_episode_off_the_queue(self):
        y.take("a" * 24)
        self.assertEqual([row["project"] for row in json.loads(y.QUEUE.read_text())], ["b" * 24])


if __name__ == "__main__":
    unittest.main()
