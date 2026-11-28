"""The date of the next video: the day after the last one, never before today, 13:00-18:00."""
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import youtube_publish as y


class SlotTest(unittest.TestCase):
    def test_the_day_after_the_last_never_before_today(self):
        now = datetime(2026, 11, 19, 10, 0)
        self.assertEqual(y.slot("2026-11-20", now), {"date": "2026-11-21", "time": "15:00"})
        self.assertEqual(y.slot("2026-11-18", now), {"date": "2026-11-19", "time": "13:00"})   # out yesterday: today
        self.assertEqual(y.slot("none", datetime(2026, 11, 19, 14, 5)), {"date": "2026-11-19", "time": "14:45"})
        # today is the day but the window is over: still today, the next quarter hour at least 30 minutes ahead
        self.assertEqual(y.slot("2026-11-18", datetime(2026, 11, 19, 19, 5)), {"date": "2026-11-19", "time": "19:45"})

    def test_the_channel_interval_counts_from_the_last(self):
        now = datetime(2026, 11, 19, 10, 0)
        self.assertEqual(y.slot("2026-11-20", now, days=2), {"date": "2026-11-22", "time": "15:00"})
        self.assertEqual(y.slot("2026-11-15", now, days=3), {"date": "2026-11-19", "time": "13:00"})   # never before today
        self.assertEqual(y.interval({"channel": {"settings": {}}}), 1)   # one day by default
        self.assertEqual(y.interval({"channel": {"settings": {"publish_interval_days": 4}}}), 4)


class CancelTest(unittest.TestCase):
    def test_a_cancelled_episode_is_refused_at_every_step(self):
        import json, tempfile
        from unittest.mock import patch
        folder, pid = Path(tempfile.mkdtemp()), "a" * 24
        (folder / "projects" / pid).mkdir(parents=True)
        (folder / "projects" / pid / "publishing.json").write_text(json.dumps({"cancelled": 1}))
        with patch.object(y, "DATA", folder), patch.object(y, "QUEUE", folder / "q.json"), \
                patch.object(y.studio, "find_project", lambda ref: {"id": pid}):
            self.assertEqual(y.main(["step", pid, "Розклад"]), 3)
            self.assertEqual(y.main(["endscreen", pid, "ok"]), 3)
            self.assertEqual(y.main(["done", pid, "abcdefghijk", "2026-11-21 15:00", "VK-abcdefghijk"]), 3)
            with self.assertRaises(y.studio.Failure):
                y.prepare(pid)


class MonetizationTest(unittest.TestCase):
    def test_done_asks_for_the_monetization_mark(self):
        import json, tempfile
        from unittest.mock import patch
        folder, pid = Path(tempfile.mkdtemp()), "a" * 24
        (folder / "projects" / pid).mkdir(parents=True)
        (folder / "projects" / pid / "publishing.json").write_text(json.dumps({"at": 1, "endscreen": "ok"}))
        with patch.object(y, "DATA", folder), patch.object(y.studio, "find_project", lambda ref: {"id": pid}):
            self.assertEqual(y.main(["done", pid, "abcdefghijk", "2026-11-22 15:00", "VK-abcdefghijk"]), 1)
            self.assertEqual(y.main(["monetization", pid, "ok"]), 0)
            state = json.loads((folder / "projects" / pid / "publishing.json").read_text())
            self.assertEqual(state["monetization"], "ok")


if __name__ == "__main__":
    unittest.main()


class MidnightSlotTest(unittest.TestCase):
    def test_late_evening_rolls_over_to_tomorrows_midnight(self):
        from datetime import datetime
        import youtube_publish
        self.assertEqual(youtube_publish.slot("2026-11-25", now=datetime(2026, 11, 26, 23, 26)), {"date": "2026-11-27", "time": "00:00"})
