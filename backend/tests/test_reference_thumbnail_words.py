import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import idea_reference


class DescribeTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "thumbnail.jpg").write_bytes(b"jpg")
        (self.root / "reference.json").write_text(json.dumps({"id": "abcdefghijk", "title": "Невероятное растение"}))
        p = patch.object(idea_reference, "folder", return_value=self.root); p.start(); self.addCleanup(p.stop)

    def test_the_thumbnail_is_read_once_and_kept(self):
        answer = {"result": '{"text": "", "shows": "a hand holding an aloe leaf", "subject": "aloe for joints"}'}
        run = SimpleNamespace(stdout=json.dumps(answer))
        with patch.object(idea_reference.subprocess, "run", return_value=run) as call:
            first = idea_reference.describe("c", "abcdefghijk")
            again = idea_reference.describe("c", "abcdefghijk")
        call.assert_called_once()   # kept in reference.json, never asked twice
        self.assertEqual(first["subject"], "aloe for joints")
        self.assertEqual(first, again)

    def test_an_unreadable_answer_gives_nothing(self):
        with patch.object(idea_reference.subprocess, "run", return_value=SimpleNamespace(stdout="not json")):
            self.assertIsNone(idea_reference.describe("c", "abcdefghijk"))


if __name__ == "__main__":
    unittest.main()
