import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import heygen_voice as hg
import store


class HeyGenLimitTests(unittest.TestCase):
    """Every HeyGen narration shares one speech budget and waits out a 429 (user, 14 November 2026)."""

    def setUp(self):
        hg.SPEECH_SENT.clear()

    def test_speech_requests_stay_under_the_minute_budget(self):
        clock = [0.0]
        waited = []
        def sleep(seconds):
            waited.append(seconds)
            clock[0] += seconds
        for _ in range(hg.SPEECH_PER_MINUTE + 3):
            hg.speech_turn(now=lambda: clock[0], sleep=sleep)
        self.assertGreaterEqual(clock[0], 60)          # the extra three had to wait for the first minute to pass
        self.assertLessEqual(len(hg.SPEECH_SENT), hg.SPEECH_PER_MINUTE)

    def test_a_429_is_waited_out_and_the_request_repeats(self):
        replies = [hg.RateLimited(7), {"data": {"audio_url": "https://x"}}]
        def answer(*args, **kwargs):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        with patch.object(hg, "_call", side_effect=answer) as sent, patch.object(hg.time, "sleep") as slept:
            self.assertEqual(hg.call("/v3/models/audio/tts", {})["data"]["audio_url"], "https://x")
        self.assertEqual(sent.call_count, 2)
        # the 7 s are waited in steps of a second, so «Зупинити» is heard during the wait (15 November 2026)
        self.assertAlmostEqual(sum(call.args[0] for call in slept.call_args_list), 7)

    def test_a_stop_is_heard_while_a_limit_is_waited_out(self):
        class Stopped(Exception):
            pass
        calls = []
        def check():
            calls.append(1)
            if len(calls) > 2:
                raise Stopped()
        hg.STOP.check = check
        self.addCleanup(setattr, hg.STOP, 'check', None)
        with patch.object(hg, "_call", side_effect=hg.RateLimited(60)), patch.object(hg.time, "sleep") as slept:
            with self.assertRaises(Stopped):
                hg.call("/v3/models/audio/tts", {})
        self.assertLess(sum(call.args[0] for call in slept.call_args_list), 5)

    def test_a_limit_that_never_lets_go_stops_with_a_clear_note(self):
        with patch.object(hg, "_call", side_effect=hg.RateLimited(30)), patch.object(hg.time, "sleep"):
            with self.assertRaises(store.StudioError) as error:
                hg.call("/v3/models/audio/tts", {})
        self.assertIn("Ліміт запитів HeyGen", str(error.exception))

    def test_gateway_error_is_still_repeated_once(self):
        with patch.object(hg, "_call", side_effect=hg.Gateway(502)) as sent, patch.object(hg.time, "sleep"):
            with self.assertRaises(store.StudioError):
                hg.call("/v3/models/audio/tts", {})
        self.assertEqual(sent.call_count, 2)


if __name__ == "__main__":
    unittest.main()
