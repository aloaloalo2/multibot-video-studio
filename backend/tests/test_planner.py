import sys
import unittest
from itertools import groupby
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import planner


class PlannerTest(unittest.TestCase):
    def test_no_more_than_five_consecutive_frames_even_with_very_uneven_durations(self):
        durations = [50] + [.2] * 48 + [50] + [.2] * 48
        times, elapsed = [], 0
        for duration in durations:
            times.append((elapsed, elapsed + duration)); elapsed += duration
        formats = planner.assign_formats(times, {"weights": {"generated_photo": 90, "stock_photo": 10}, "first_clip_seconds": 0})
        self.assertIn(formats[0], {"stock_video", "generated_video"})
        self.assertLessEqual(max(len(list(items)) for _, items in groupby(formats)), 5)
        self.assertTrue(set(formats[1:]) <= {"generated_photo", "stock_photo"})

    def test_impossible_single_format_run_is_explained(self):
        with self.assertRaisesRegex(ValueError, "ще одного формату"):
            planner.assign_formats([(i, i + 1) for i in range(8)], {"weights": {"generated_photo": 100}})

    def test_opening_is_video_even_when_first_hint_requests_a_photo(self):
        for weights in [{"stock_photo": 100}, {"stock_video": 100}, {"generated_video": 100}]:
            formats = planner.assign_formats([(0, 1), (1, 2)], {"weights": weights}, {1: "stock_photo"}, [["First."], ["Second."]])
            self.assertIn(formats[0], {"stock_video", "generated_video"})

    def test_duration_alone_is_always_a_draft(self):
        plan = planner.build_plan("One complete sentence about a simple subject.", {"weights": {"text": 100}}, "Channel", duration=30)
        self.assertEqual(plan["timing"]["status"], "draft")
        self.assertEqual(plan["report"]["timing_basis"], "duration_estimate")
        with self.assertRaises(ValueError):
            planner.validate_synced_plan(plan, 30)

    def test_real_phrase_boundaries_override_estimated_first_clip(self):
        script = "First complete sentence about a simple subject. Second complete sentence about another simple subject."
        timings = [{"text": sentence, "start": start, "end": end} for sentence, start, end in zip(planner.split_sentences(script), [.3, 2.7], [1.4, 3.6])]
        plan = planner.build_plan(script, {"weights": {"text": 100}, "first_clip_seconds": 8}, "Channel", duration=4, alignment=timings)
        self.assertEqual(plan["timing"]["status"], "audio_synced")
        self.assertEqual([(frame["start"], frame["end"]) for frame in plan["frames"]], [(0, 2.7), (2.7, 4)])
        self.assertEqual(plan["frames"][0]["sentence_timings"][0]["start"], .3)
        planner.validate_synced_plan(plan, 4)
        plan["frames"][0]["end"] = 2
        with self.assertRaises(ValueError):
            planner.validate_synced_plan(plan, 4)

    def test_alignment_requires_complete_text_and_ordered_real_intervals(self):
        script = "First complete sentence. Second complete sentence."
        good = [{"text": "First complete sentence.", "start": .1, "end": .5}, {"text": "Second complete sentence.", "start": .7, "end": 1.2}]
        invalid = [good[:1], [dict(good[0], text="Different sentence."), good[1]], [good[0], dict(good[1], start=.4)], [good[0], dict(good[1], end=3)], [dict(good[0], start=True), good[1]]]
        for timings in invalid:
            with self.subTest(timings=timings), self.assertRaises(ValueError):
                planner.validate_sentence_timings(script, timings, 2)

    def test_zero_first_clip_keeps_video_first_and_ignores_retired_opening_settings(self):
        config = {"first_clip_seconds": 0, "opening_clip_types": ["generated_video"] * 6,
                  "opening_seconds": 90, "opening_clip_count": 6, "weights": {"text": 100}}
        plan = planner.build_plan("One long complete sentence about cinnamon. Another complete sentence follows here.", config, "Channel")
        self.assertEqual(plan["frames"][0]["format"], "generated_video")
        self.assertTrue(all(frame["format"] == "text" for frame in plan["frames"][1:]))
        self.assertNotIn("opening_clip_types", plan["settings_snapshot"])

    def test_positive_first_clip_and_sentence_coverage(self):
        script = "Small. One complete longer sentence about cinnamon powder. Another complete sentence follows right here today."
        plan = planner.build_plan(script, {"first_clip_seconds": 8, "weights": {"text": 100}}, "Channel", duration=30)
        self.assertEqual(plan["frames"][0]["format"], "generated_video")
        self.assertEqual(plan["frames"][0]["end"], 8)
        self.assertEqual(plan["frames"][-1]["end"], 30)
        self.assertEqual([s for frame in plan["frames"] for s in frame["sentences"]], planner.split_sentences(script))
        self.assertEqual(plan["frames"][0]["sentences"][0], "Small.")

    def test_duration_weights_and_hints(self):
        times = [(i * 5.0, (i + 1) * 5.0) for i in range(200)]
        weights = {"stock_video": 8, "stock_photo": 20, "generated_photo": 40, "animation": 16, "text": 16}
        formats = planner.assign_formats(times, {"weights": weights, "first_clip_seconds": 0})
        for kind, target in weights.items():
            self.assertEqual(formats.count(kind) / len(formats) * 100, target)
        plan = planner.build_plan("First complete longer sentence about cinnamon powder. Second complete longer sentence about daily food.",
                                  {"weights": {"text": 100}}, "Channel", hints={"2": "animation"})
        self.assertEqual(plan["frames"][1]["format"], "animation")

    def test_invalid_duration_and_hints(self):
        for duration in [0, -1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                planner.build_plan("A sentence.", {"weights": {"text": 100}}, "Channel", duration=duration)
        with self.assertRaises(ValueError):
            planner.build_plan("A sentence.", {"weights": {"text": 100}}, "Channel", hints={"3": "text"})

    def test_settings_signature_ignores_removed_fields_but_tracks_active_fields(self):
        settings = {"weights": {"text": 100}, "first_clip_seconds": 0}
        self.assertEqual(planner.settings_signature(settings), planner.settings_signature({**settings, "opening_seconds": 90}))
        self.assertNotEqual(planner.settings_signature(settings), planner.settings_signature({**settings, "short_sentence_words": 7}))


if __name__ == "__main__":
    unittest.main()
