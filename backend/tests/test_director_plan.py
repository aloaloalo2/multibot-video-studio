import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import director_plan  # noqa: E402
import planner  # noqa: E402
import store  # noqa: E402

SCRIPT = " ".join(f"Sentence number {word} talks about one simple thing here." for word in
                  ("one", "two", "three", "four", "five", "six", "seven", "eight"))
CHANNEL = {"id": "c" * 16, "settings": {"weights": {"stock_photo": 50, "text": 50}, "max_sentences_per_scene": 3}}
PROJECT = {"id": "a" * 24, "channel_id": "c" * 16}


def frames(*spec):
    return [{"sentences": numbers, "format": kind, "idea": "a picture"} for numbers, kind in spec]


class DirectorPlanTest(unittest.TestCase):
    def setUp(self):
        alignment = [{"text": text, "start": i * 2 + .1, "end": i * 2 + 1.9} for i, text in enumerate(planner.split_sentences(SCRIPT))]
        self.plan = planner.build_plan(SCRIPT, planner.effective_settings(CHANNEL["settings"]), "Test", duration=16.5, alignment=alignment)
        self.plan["timing"]["audio"] = {"duration": 16.5}   # the Studio adds the voice it measured
        self.saved = []
        for item in (patch.object(store, "load_project", return_value=PROJECT),
                     patch.object(store, "load_project_plan", side_effect=lambda pid: self.plan),
                     patch.object(store, "list_channels", return_value=[CHANNEL]),
                     patch.object(store, "attach_plan", side_effect=lambda pid, plan: self.saved.append(plan))):
            item.start()
            self.addCleanup(item.stop)

    def test_the_director_reads_numbered_sentences_and_the_channel_shares(self):
        data = director_plan.sentences(PROJECT["id"])
        self.assertEqual([item["number"] for item in data["sentences"]], list(range(1, 9)))
        self.assertEqual(data["shares"], {"stock_photo": 50.0, "text": 50.0})
        self.assertEqual(data["max_sentences"], 3)

    def test_a_plan_needs_the_voice(self):
        self.plan = None
        with self.assertRaises(store.StudioError):
            director_plan.sentences(PROJECT["id"])

    def test_frames_are_checked_before_they_are_saved(self):
        def problems(*spec):
            result = director_plan.apply(PROJECT["id"], frames(*spec), dry_run=True)
            self.assertFalse(result["ok"])
            return " ".join(result["problems"])
        self.assertIn("до 3", problems(([1, 2, 3, 4], "text"), ([5, 6, 7, 8], "stock_photo")))
        self.assertIn("підряд від 3", problems(([1, 2], "text"), ([4, 5, 6], "stock_photo"), ([7, 8], "text")))
        self.assertIn("не використовує", problems(([1, 2], "host"), ([3, 4, 5], "text"), ([6, 7, 8], "stock_photo")))
        self.assertIn("1–6", problems(([1, 2, 3], "text"), ([4, 5, 6], "stock_photo")))
        self.assertIn("Текстова сцена", problems(([1, 2, 3], "text"), ([4, 5, 6], "text"), ([7, 8], "stock_photo")))
        self.assertIn("поспіль", problems(*[([n], "text") for n in range(1, 7)], ([7], "stock_photo"), ([8], "stock_photo")))
        self.assertEqual(self.saved, [])

    def test_good_frames_become_the_plan_with_times_from_the_voice(self):
        good = frames(([1, 2], "text"), ([3, 4], "stock_photo"), ([5, 6], "text"), ([7, 8], "stock_photo"))
        self.assertTrue(director_plan.apply(PROJECT["id"], good, dry_run=True)["ok"])
        self.assertEqual(self.saved, [])
        self.assertTrue(director_plan.apply(PROJECT["id"], good)["ok"])
        plan = self.saved[-1]
        self.assertEqual(plan["frame_source"], planner.DIRECTOR_FRAME_SOURCE)
        self.assertEqual([frame["format"] for frame in plan["frames"]], ["text", "stock_photo", "text", "stock_photo"])
        self.assertEqual(plan["frames"][0]["visual"], "a picture")
        self.assertEqual(plan["frames"][1]["start"], plan["frames"][1]["sentence_timings"][0]["start"])
        self.assertEqual(plan["frames"][-1]["end"], 16.5)
        # a later recognition of the same sentences keeps the director's frames and their ideas
        kept = planner.keep_director_frames(self.plan, plan)
        self.assertEqual([frame.get("visual") for frame in kept["frames"]], ["a picture"] * 4)


if __name__ == "__main__":
    unittest.main()
