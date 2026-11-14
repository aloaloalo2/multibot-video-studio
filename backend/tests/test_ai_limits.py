import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_limits  # noqa: E402

NOW = 1_800_000_000


def claude_event(used, resets):
    return ('{"type":"rate_limit_event","rate_limit_info":{"status":"allowed","resetsAt":%d,"rateLimitType":"five_hour",'
            '"unifiedWindows":{"five_hour":{"utilization":%s,"resetsAt":%d,"status":"allowed"},'
            '"seven_day":{"utilization":0.5,"resetsAt":%d,"status":"allowed"}}}}\n' % (resets, used, resets, resets + 9e5))


def codex_event(used, resets):
    return ('{"type":"event_msg","payload":{"type":"token_count","rate_limits":{"limit_id":"codex","primary":'
            '{"used_percent":%s,"window_minutes":300,"resets_at":%d},"secondary":{"used_percent":40.0,'
            '"window_minutes":10080,"resets_at":%d}}}}\n' % (used, resets, resets + 9e5))


class AiLimitsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data, self.home = Path(self.tmp.name) / "data", Path(self.tmp.name) / "home"
        (self.data / "projects" / "p").mkdir(parents=True)
        (self.home / ".codex" / "sessions" / "2026").mkdir(parents=True)

    def log(self, path, text, age=60):
        path.write_text(text)
        stamp = time.time() - age
        import os
        os.utime(path, (stamp, stamp))

    def read(self):
        return ai_limits.read(self.data, self.home, now=time.time())

    def test_reads_the_five_hour_windows_and_ignores_the_weekly_ones(self):
        resets = int(time.time()) + 3600
        self.log(self.data / "projects/p/production-a.log", claude_event(0.10, resets) + claude_event(0.12, resets))
        self.log(self.home / ".codex/sessions/2026/rollout.jsonl", codex_event(19.0, resets) + codex_event(21.0, resets))
        result = self.read()
        self.assertEqual((result["claude"]["left"], result["claude"]["resets_at"]), (88, resets))
        self.assertEqual((result["codex"]["left"], result["codex"]["resets_at"]), (79, resets))

    def test_the_newest_window_counts_even_when_an_older_one_was_fuller(self):
        old, new = int(time.time()) - 60, int(time.time()) + 3600
        self.log(self.data / "projects/p/director.log", claude_event(0.95, old) + claude_event(0.05, new))
        self.assertEqual(self.read()["claude"]["left"], 95)

    def test_a_window_past_its_reset_reads_as_renewed(self):
        self.log(self.data / "projects/p/director.log", claude_event(0.97, int(time.time()) - 10))
        result = self.read()["claude"]
        self.assertTrue(result["reset"])
        self.assertEqual(result["left"], 100)

    def test_logs_older_than_the_window_and_missing_data_say_unknown(self):
        self.log(self.data / "projects/p/director.log", claude_event(0.5, int(time.time()) + 60), age=6 * 3600)
        result = self.read()
        self.assertFalse(result["claude"]["known"])
        self.assertFalse(result["codex"]["known"])


if __name__ == "__main__":
    unittest.main()
