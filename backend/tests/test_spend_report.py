import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spend_report  # noqa: E402


def turn(mid, read, write, calls=(), parent=None, text=""):
    content = [{"type": "text", "text": text}] if text else []
    content += [{"type": "tool_use", "id": cid, "name": name, "input": data} for cid, name, data in calls]
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"id": mid, "content": content,
                        "usage": {"input_tokens": 1, "cache_read_input_tokens": read, "output_tokens": 1,
                                  "cache_creation": {"ephemeral_1h_input_tokens": write, "ephemeral_5m_input_tokens": 0}}}}


def result(cid, text="", images=0):
    content = [{"type": "text", "text": text}] + [{"type": "image", "source": {}}] * images
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": cid, "content": content}]}}


class SpendReportTest(unittest.TestCase):
    def write_log(self, events):
        folder = Path(tempfile.mkdtemp()) / "0123456789abcdef01234567"
        folder.mkdir()
        log = folder / "production-abc.log"
        log.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        return log

    def test_groups_carried_context_repeats_and_helpers(self):
        events = [
            turn("m1", 0, 60_000, [("r1", "Read", {"file_path": "/x/scenes/e01.js"})]),
            result("r1", "code"),
            turn("m2", 60_000, 5_000, [("i1", "Read", {"file_path": "/x/build/review/review_01.png"})]),
            result("i1", images=1),
            turn("m3", 65_000, 40_000, [("w1", "Write", {"file_path": "/x/scenes/e02.js", "content": "x" * 3200})]),
            result("w1", "ok"),
            turn("m4", 105_000, 1_000, [("r2", "Read", {"file_path": "/x/scenes/e01.js"})]),
            result("r2", "code"),
            turn("m5", 106_000, 8_000, [("t1", "Task", {"description": "кадри 1-5", "prompt": "..."})]),
            # a helper that starts with a copy of the whole conversation
            turn("s1", 200_000, 1_000, [("b1", "Bash", {"command": "python3 tools/frame_review.py --project p sheets"})], parent="t1"),
            result("b1", "sheets"),
            turn("s2", 201_000, 1_000, [], parent="t1", text="готово"),
            turn("m6", 114_000, 500, [], text="Кадри готові"),
            {"type": "result", "num_turns": 6, "total_cost_usd": 1.0,
             "modelUsage": {"claude-opus-5-5": {"inputTokens": 8, "outputTokens": 2000, "thinkingTokens": 1200,
                                                "cacheReadInputTokens": 751_000, "cacheCreationInputTokens": 116_500, "costUSD": 1.0}}},
        ]
        report = spend_report.analyse(self.write_log(events))
        self.assertEqual(report["cost_usd"], 1.0)
        self.assertTrue(report["cost_measured"])
        self.assertAlmostEqual(sum(g["usd"] for g in report["groups"]), 1.0, places=1)
        names = {g["name"] for g in report["groups"]}
        self.assertIn("Код сцен", names)
        self.assertIn("Перевірки й стоп-кадри", names)
        self.assertEqual(report["images"], 1)
        self.assertEqual(len(report["helpers"]), 1)
        self.assertTrue(report["helpers"][0]["forked"])
        self.assertEqual(report["repeated_reads"][0]["times"], 2)
        self.assertTrue(report["repeated_reads"][0]["path"].endswith("e01.js"))
        # the write's 40k tokens of new context are carried by the later turns of the main agent
        carried = {c["what"]: c for c in report["most_carried"]}
        self.assertGreaterEqual(carried["Write scenes/e02.js"]["turns"], 2)
        self.assertTrue(any("помічник" in note for note in report["advice"]))
        self.assertIn("На що пішло", spend_report.text(report))

    def test_resumed_session_is_named(self):
        events = [turn("m1", 400_000, 2_000, [("b", "Bash", {"command": "ls"})]), result("b", "a"),
                  turn("m2", 402_000, 100, [], text="ok")]
        report = spend_report.analyse(self.write_log(events))
        self.assertTrue(report["resumed"])
        self.assertFalse(report["cost_measured"])
        self.assertTrue(any("стару сесію" in note for note in report["advice"]))

    def test_resumed_run_counts_only_its_own_spending(self):
        usage = lambda cost, out: {"claude-opus-5-5": {"inputTokens": 1, "outputTokens": out, "thinkingTokens": 0,
                                                       "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "costUSD": cost}}
        events = [{"type": "result", "num_turns": 0, "modelUsage": usage(100.0, 9000)},
                  turn("m1", 300_000, 2_000, [("b", "Bash", {"command": "ls"})]), result("b", "a"),
                  turn("m2", 302_000, 100, [], text="ok"),
                  {"type": "result", "num_turns": 2, "modelUsage": usage(104.5, 9500)}]
        report = spend_report.analyse(self.write_log(events))
        self.assertEqual(report["cost_usd"], 4.5)
        self.assertEqual(report["tokens"]["output"], 500)

    def test_record_saves_beside_project_and_never_raises(self):
        log = self.write_log([turn("m1", 0, 50_000, []), {"type": "result", "num_turns": 1, "modelUsage": {}}])
        with mock.patch.object(spend_report.store, "project_dir", return_value=log.parent), \
                mock.patch.object(spend_report.store, "load_project", return_value={}):
            self.assertIsNotNone(spend_report.record(log))
            self.assertEqual(len(list((log.parent / "spend").glob("*.json"))), 1)
            self.assertEqual(spend_report.backfill(log.parent.name), [])   # the same log is not reported twice
            self.assertEqual(len(spend_report.reports(log.parent.name)["reports"]), 1)
        self.assertIsNone(spend_report.record(log.parent / "missing.log"))
        broken = log.parent / "director.log"
        broken.write_text("not json\n", encoding="utf-8")
        self.assertIsNone(spend_report.record(broken))

    def test_stopped_run_uses_native_total_including_helpers_and_refreshes_once(self):
        import project_costs
        sid = "11111111-1111-1111-1111-111111111111"
        log = self.write_log([{"type": "system", "session_id": sid}, turn("first", 160_000, 10_000, text="Done")])
        native = log.parent / "native.jsonl"
        def receipt(cost):
            native.write_text(json.dumps(turn("first", 0, 1)) + "\n" + json.dumps({
                "type": "cost-state", "sessionId": sid, "modelUsage": {"claude-opus-5-5": {
                    "costUSD": cost, "outputTokens": 1000, "thinkingTokens": 800}}}) + "\n")
        receipt(45.22)
        with mock.patch.object(spend_report, "session_file", return_value=native), \
                mock.patch.object(spend_report.store, "project_dir", return_value=log.parent):
            report = spend_report.record(log)
            self.assertEqual(report['cost_usd'], 45.22)
            self.assertTrue(report['cost_measured'])
            self.assertEqual(report['cost_source'], 'claude-session')
            receipt(46.5)
            self.assertEqual(len(spend_report.backfill(log.parent.name)), 1)
            self.assertEqual(spend_report.backfill(log.parent.name), [])
            data = project_costs.collect(log.parent, spend_report.store.read_json(log.parent / 'project-costs.json'))
            events = [e for e in data['events'].values() if e['provider'] == 'claude_code']
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['amount'], 46.5)

    def test_native_cumulative_total_is_rejected_when_stream_starts_mid_session(self):
        sid = "11111111-1111-1111-1111-111111111111"
        log = self.write_log([{"type": "system", "session_id": sid}, turn("later", 200_000, 10, text="Done")])
        native = log.parent / 'native.jsonl'
        native.write_text(json.dumps(turn('earlier', 0, 10)) + '\n' + json.dumps({
            'type': 'cost-state', 'sessionId': sid, 'modelUsage': {'model': {'costUSD': 999}}}))
        with mock.patch.object(spend_report, 'session_file', return_value=native):
            report = spend_report.analyse(log)
        self.assertFalse(report['cost_measured'])
        self.assertLess(report['cost_usd'], 999)


if __name__ == "__main__":
    unittest.main()
