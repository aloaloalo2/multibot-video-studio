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
        self.assertEqual(y.slot("2026-11-18", datetime(2026, 11, 19, 19, 0)), {"date": "2026-11-20", "time": "15:00"})

    def test_the_channel_interval_counts_from_the_last(self):
        now = datetime(2026, 11, 19, 10, 0)
        self.assertEqual(y.slot("2026-11-20", now, days=2), {"date": "2026-11-22", "time": "15:00"})
        self.assertEqual(y.slot("2026-11-15", now, days=3), {"date": "2026-11-19", "time": "13:00"})   # never before today
        self.assertEqual(y.interval({"channel": {"settings": {}}}), 1)   # one day by default
        self.assertEqual(y.interval({"channel": {"settings": {"publish_interval_days": 4}}}), 4)


if __name__ == "__main__":
    unittest.main()
