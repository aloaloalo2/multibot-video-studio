import unittest
from pathlib import Path
from unittest.mock import patch

import director

LOST = {"is_error": True, "terminal_reason": "api_error", "api_error": "connection_failed", "session_id": "s1",
        "result": "API Error: Connection lost mid-response.", "total_cost_usd": 1.0}


class LostConnectionTest(unittest.TestCase):
    def test_a_dropped_connection_resumes_the_same_session_and_counts_both_costs(self):
        calls = []
        answers = [(1, LOST), (0, {"is_error": False, "session_id": "s1", "result": "готово", "total_cost_usd": 0.5})]
        def once(cli, prompt, log, activity, timeout, resume, *rest):
            calls.append((prompt, log.name, resume))
            return answers.pop(0)
        with patch.object(director, "_claude_once", side_effect=once), patch.object(director.time, "sleep"):
            code, answer = director.claude(Path("claude"), "бриф", Path("/tmp/run.log"), Path("/tmp/feed.json"), 3600)
        self.assertEqual(code, 0)
        self.assertEqual(answer["result"], "готово")
        self.assertAlmostEqual(answer["total_cost_usd"], 1.5)
        self.assertEqual(calls[1][1:], ("run-resend1.log", "s1"))

    def test_gives_up_after_four_drops_in_a_row(self):
        with patch.object(director, "_claude_once", return_value=(1, LOST)) as once, patch.object(director.time, "sleep"):
            code, answer = director.claude(Path("claude"), "бриф", Path("/tmp/run.log"), Path("/tmp/feed.json"), 36000)
        self.assertEqual(once.call_count, 1 + director.LOST_RETRIES)
        self.assertTrue(director.lost(answer))

    def test_other_errors_are_not_retried(self):
        with patch.object(director, "_claude_once", return_value=(1, {"is_error": True, "result": "інша помилка"})) as once:
            director.claude(Path("claude"), "бриф", Path("/tmp/run.log"), Path("/tmp/feed.json"), 3600)
        self.assertEqual(once.call_count, 1)

    def test_a_one_answer_run_asks_again_after_a_drop_and_keeps_each_answer(self):
        import json, subprocess
        outs = [json.dumps(LOST), json.dumps({"is_error": False, "result": "промпт", "total_cost_usd": 0.2})]
        kept = []
        def run(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0 if len(outs) == 1 else 1, outs.pop(0), "")
        with patch.object(director.subprocess, "run", side_effect=run), patch.object(director.time, "sleep"):
            done, answer = director.run_json(["claude"], "бриф", "/tmp", 60, lambda out, a: kept.append(a.get("total_cost_usd")))
        self.assertEqual(answer["result"], "промпт")
        self.assertEqual(kept, [1.0, 0.2])


if __name__ == "__main__":
    unittest.main()


class LongerDescriptionTest(unittest.TestCase):
    def test_three_wordy_sentences_of_about_ninety_words_pass(self):
        import episode_metadata
        sentence = " ".join(["mot"] * 29) + "."
        value = {"titles": ["Titre un", "Titre deux", "Titre trois"], "description": f"{sentence} {sentence} {sentence}\n\n#espace #trounoir",
                 "tags": ["espace", "univers", "astronomie", "quasar"]}
        self.assertEqual(len(episode_metadata.validate(value, "Titre un")["tags"]), 4)


class WritingFreshSessionTest(unittest.TestCase):
    def test_two_drops_move_to_a_fresh_session_and_two_more_stop(self):
        import episode_ideas
        calls = []
        def run(cmd, prompt, root, identity, **options):
            calls.append((cmd[cmd.index('--resume') if '--resume' in cmd else cmd.index('--session-id'):][:2], prompt[:40], identity))
            return 1, {**LOST, "session_id": cmd[-1]}
        session = {"session_id": "old", "model": director.MODEL, "effort": "medium", "api_cost_usd": 1.0}
        with patch.object(episode_ideas.writing_jobs, "run", side_effect=run), patch.object(episode_ideas.writing_jobs, "check"), \
             patch.object(episode_ideas.time, "sleep"), patch.object(director, "executable", return_value=Path("claude")):
            with self.assertRaises(RuntimeError):
                episode_ideas.opus("ЗАВДАННЯ", Path("/tmp"), "editing-x", "c", session=session, resume=True)
        self.assertEqual([c[0][0] for c in calls], ["--resume", "--resume", "--session-id", "--resume"])
        self.assertEqual(calls[1][0][1], "old")
        self.assertNotEqual(calls[2][0][1], "old")
        self.assertTrue(calls[2][1].startswith(episode_ideas.FRESH[:40]))
        self.assertEqual(session["session_id"], calls[2][0][1])   # later phases go on in the fresh session

    def test_a_production_run_that_dropped_twice_stops_with_continue(self):
        self.assertEqual(director.limit_stop(LOST), director.LOST_NOTE)
