import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import director
import production


class ParallelSessionStopTest(unittest.TestCase):
    """A stop of the frame job reaches both sessions of an episode (user, 14 November 2026)."""

    def test_stop_kills_every_session_of_the_feed(self):
        patcher = patch.object(director, "activity_path", return_value=Path("/nowhere/production-activity.json"))
        patcher.start(); self.addCleanup(patcher.stop)
        feed = str(director.activity_path("p" * 24, "production"))
        first, second = Mock(), Mock()
        director.RUNNING[feed] = first
        director.RUNNING_MORE[feed] = [second]
        self.addCleanup(director.RUNNING.pop, feed, None)
        self.addCleanup(director.RUNNING_MORE.pop, feed, None)
        self.addCleanup(director.CANCELLED.discard, feed)
        with patch.object(director, "kill") as kill:
            director.stop("p" * 24, "production")
        self.assertEqual([call.args[0] for call in kill.call_args_list], [first, second])


if __name__ == "__main__":
    unittest.main()
