import sys
import json
import io
from datetime import datetime,timezone
from unittest.mock import patch
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

    def test_an_idle_codex_is_not_stale(self):
        self.log(self.home / ".codex/sessions/2026/rollout.jsonl", codex_event(25.0, int(time.time()) + 3600), age=22 * 60)
        result = self.read()["codex"]
        self.assertEqual((result["left"], result["stale"]), (75, False))

    def test_the_newest_window_counts_even_when_an_older_one_was_fuller(self):
        old, new = int(time.time()) - 60, int(time.time()) + 3600
        self.log(self.data / "projects/p/director.log", claude_event(0.95, old) + claude_event(0.05, new))
        self.assertEqual(self.read()["claude"]["left"], 95)

    def test_expired_receipt_does_not_invent_full_remaining_allowance(self):
        self.log(self.data / "projects/p/director.log", claude_event(0.97, int(time.time()) - 10))
        result = self.read()["claude"]
        self.assertTrue(result["reset"])
        self.assertFalse(result["known"])
        self.assertTrue(result["stale"])

    def test_logs_older_than_the_window_and_missing_data_say_unknown(self):
        self.log(self.data / "projects/p/director.log", claude_event(0.5, int(time.time()) + 60), age=6 * 3600)
        result = self.read()
        self.assertFalse(result["claude"]["known"])
        self.assertFalse(result["codex"]["known"])

    def account_response(self,used=100):
        folder=self.home/'.claude';folder.mkdir(exist_ok=True)
        (folder/'.credentials.json').write_text(json.dumps({'claudeAiOauth':{'accessToken':'test-only-token'}}))
        return json.dumps({'five_hour':{'utilization':used,'resets_at':datetime.fromtimestamp(time.time()+3600,timezone.utc).isoformat()}}).encode()

    def test_direct_account_exhaustion_overrides_last_95_percent_receipt(self):
        response=self.account_response()
        with patch.object(ai_limits.urllib.request,'urlopen',return_value=io.BytesIO(response)) as http:
            result=ai_limits.claude_usage(self.home)
        self.assertEqual(result['left'],0)
        self.assertEqual(result['source'],'account');self.assertFalse(result['stale'])
        request=http.call_args.args[0]
        self.assertEqual(request.get_method(),'GET')
        self.assertTrue(request.full_url.startswith('https://api.anthropic.com/api/oauth/usage'))
        self.assertNotIn('test-only-token',json.dumps(result))

    def test_account_failure_keeps_explicitly_dated_fallback(self):
        self.account_response()
        with patch.object(ai_limits.urllib.request,'urlopen',side_effect=OSError('offline')):
            self.assertIsNone(ai_limits.claude_usage(self.home))
        self.log(self.data/'projects/p/director.log',claude_event(.95,int(time.time())+3600),age=180)
        result=self.read()['claude']
        self.assertEqual(result['left'],5);self.assertTrue(result['stale']);self.assertEqual(result['source'],'logs')

    def fresh_state(self):
        ai_limits._CACHE.clear(); ai_limits._ACCOUNT.clear()
        self.addCleanup(ai_limits._CACHE.clear); self.addCleanup(ai_limits._ACCOUNT.clear)

    def test_the_account_is_asked_at_most_every_three_minutes(self):
        self.fresh_state()
        now=time.time();clock=[now];reset=now+3600
        account={'known':True,'left':40,'resets_at':reset,'seen_at':now,'source':'account','stale':False}
        with patch.object(ai_limits.time,'time',side_effect=lambda:clock[0]), \
             patch.object(ai_limits,'read',return_value={'claude':{'known':False},'codex':{}}), \
             patch.object(ai_limits,'claude_usage',return_value=account) as asked:
            self.assertEqual(ai_limits.cached(self.data)['claude']['left'],40)
            for step in (16,60,60):
                clock[0]+=step;ai_limits.cached(self.data)
            self.assertEqual(asked.call_count,1)
            clock[0]+=60;ai_limits.cached(self.data)
            self.assertEqual(asked.call_count,2)

    def test_a_429_waits_as_long_as_the_server_says(self):
        self.fresh_state()
        now=time.time();clock=[now]
        with patch.object(ai_limits.time,'time',side_effect=lambda:clock[0]), \
             patch.object(ai_limits,'read',return_value={'claude':{'known':False},'codex':{}}), \
             patch.object(ai_limits,'claude_usage',return_value={'retry_after':600}) as asked:
            ai_limits.cached(self.data)
            clock[0]+=500;ai_limits.cached(self.data)
            self.assertEqual(asked.call_count,1)
            clock[0]+=120;ai_limits.cached(self.data)
            self.assertEqual(asked.call_count,2)

    def test_429_from_the_server_becomes_a_wait(self):
        self.account_response()
        error=ai_limits.urllib.error.HTTPError('u',429,'Rate limited',{'Retry-After':'900'},None)
        with patch.object(ai_limits.urllib.request,'urlopen',side_effect=error):
            self.assertEqual(ai_limits.claude_usage(self.home),{'retry_after':900.0})

    def test_a_newer_studio_receipt_of_the_same_window_wins(self):
        now=time.time();reset=now+3600
        account={'known':True,'left':40,'resets_at':reset,'seen_at':now-600,'source':'account'}
        logs={'known':True,'left':35,'resets_at':reset+1,'seen_at':now-20,'source':'logs','stale':False}
        self.assertEqual(ai_limits._merge(account,logs,now)['left'],35)
        older={**logs,'seen_at':now-900,'left':70}
        merged=ai_limits._merge(account,older,now)
        self.assertEqual((merged['left'],merged['source'],merged['stale']),(40,'account',True))

if __name__ == "__main__":
    unittest.main()
