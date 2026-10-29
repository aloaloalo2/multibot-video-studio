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
        self.assertIn(formats[0], {"generated_photo", "stock_photo"})
        self.assertLessEqual(max(len(list(items)) for _, items in groupby(formats)), 5)
        self.assertTrue(set(formats[1:]) <= {"generated_photo", "stock_photo"})

    def test_impossible_single_format_run_is_explained(self):
        with self.assertRaisesRegex(ValueError, "ще одного формату"):
            planner.assign_formats([(i, i + 1) for i in range(8)], {"weights": {"generated_photo": 100}})

    def test_razgon_channel_may_use_one_format_for_the_whole_video(self):
        formats = planner.assign_formats([(i, i + 1) for i in range(40)], {"weights": {"razgon_2d": 100}})
        self.assertEqual(set(formats), {"razgon_2d"})
        plan = planner.build_plan("What if the Moon vanished? " * 30, {"weights": {"razgon_2d": 100}}, "What If")
        self.assertEqual({frame["format"] for frame in plan["frames"]}, {"razgon_2d"})

    def test_automatic_first_prefers_enabled_video_and_respects_first_hint(self):
        times = [(0, 1), (1, 2)]
        self.assertEqual(planner.assign_formats(times, {"weights": {"stock_video": 13, "generated_video": 0, "generated_photo": 87}})[0], "stock_video")
        self.assertEqual(planner.assign_formats(times, {"weights": {"generated_video": 30, "generated_photo": 70}})[0], "generated_video")
        self.assertEqual(planner.assign_formats(times, {"weights": {"generated_photo": 100}})[0], "generated_photo")
        self.assertEqual(planner.assign_formats(times, {"weights": {"stock_video": 50, "stock_photo": 50}}, {1: "stock_photo"}, [["First."], ["Second."]])[0], "stock_photo")

    def test_explicit_first_format_and_count_override_automatic_preference(self):
        times = [(i, i + 1) for i in range(10)]
        weights = {"stock_video": 20, "generated_photo": 80}
        result = planner.assign_formats(times, {"weights": weights, "first_clip_format": "generated_video", "first_clip_count": 8})
        self.assertEqual(result[:8], ["generated_video"] * 8)
        self.assertEqual(result[8], "generated_photo")
        self.assertEqual(planner.assign_formats(times, {"weights": weights, "first_clip_format": "generated_photo"})[0], "generated_photo")
        self.assertEqual(planner.assign_formats(times, {"weights": weights, "first_clip_format": "video"})[0], "stock_video")

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

    def test_zero_first_clip_uses_weights_and_ignores_retired_opening_settings(self):
        config = {"first_clip_seconds": 0, "opening_clip_types": ["generated_video"] * 6,
                  "opening_seconds": 90, "opening_clip_count": 6, "weights": {"text": 100}}
        plan = planner.build_plan("One long complete sentence about cinnamon. Another complete sentence follows here.", config, "Channel")
        self.assertEqual(plan["frames"][0]["format"], "text")
        self.assertTrue(all(frame["format"] == "text" for frame in plan["frames"][1:]))
        self.assertNotIn("opening_clip_types", plan["settings_snapshot"])

    def test_positive_first_clip_and_sentence_coverage(self):
        script = "Small. One complete longer sentence about cinnamon powder. Another complete sentence follows right here today."
        plan = planner.build_plan(script, {"first_clip_seconds": 8, "first_clip_format": "generated_video", "weights": {"text": 100}}, "Channel", duration=30)
        self.assertEqual(plan["frames"][0]["format"], "generated_video")
        self.assertEqual(plan["frames"][0]["end"], 8)
        self.assertEqual(plan["frames"][-1]["end"], 30)
        self.assertEqual([s for frame in plan["frames"] for s in frame["sentences"]], planner.split_sentences(script))
        self.assertEqual(plan["frames"][0]["sentences"][0], "Small.")

    def test_long_single_sentence_draft_has_an_eight_second_opening(self):
        script = "A single long introductory sentence for the entire video."
        plan = planner.build_plan(script, {"first_clip_seconds": 8, "weights": {"text": 100}}, "Channel", duration=30)
        self.assertEqual([(f["start"], f["end"]) for f in plan["frames"]], [(0, 8), (8, 30)])
        self.assertEqual(plan["frames"][1]["continuation"]["text"], script)
        self.assertTrue(plan["frames"][1]["continuation"]["approximate"])
        self.assertEqual([s for f in plan["frames"] for s in f["sentences"]], [script])

    def test_synced_opening_preserves_crossing_sentence_and_exact_clip(self):
        script = "One hundred men took part in a careful hair study. Fifty people used lotion on their scalp."
        sentences = planner.split_sentences(script)
        timings = [{"text": sentences[0], "start": .08, "end": 8.72},
                   {"text": sentences[1], "start": 9.26, "end": 14.06}]
        plan = planner.build_plan(script, {"first_clip_seconds": 8, "first_clip_format": "generated_video", "weights": {"stock_video": 40, "text": 60}}, "Channel", duration=15, alignment=timings)
        self.assertEqual([(x["start"], x["end"]) for x in plan["frames"]], [(0, 8), (8, 15)])
        self.assertEqual(plan["frames"][0]["format"], "generated_video")
        self.assertEqual(plan["frames"][1]["sentences"], [sentences[1]])
        self.assertEqual(plan["frames"][1]["continuation"], {"number": 1, **timings[0]})
        self.assertEqual([s for frame in plan["frames"] for s in frame["sentences"]], sentences)
        plan = planner.digitize_synced_plan(plan)
        planner.validate_synced_plan(plan, 15)
        self.assertEqual(plan["frames"][1]["continuation"]["text"], plan["frames"][0]["sentences"][0])
        broken = __import__('copy').deepcopy(plan)
        broken["frames"][1]["continuation"]["end"] = 8
        with self.assertRaises(ValueError):
            planner.validate_synced_plan(broken, 15)

    def test_opening_at_sentence_boundary_needs_no_empty_continuation(self):
        script = "A first complete sentence here. A second complete sentence follows."
        sentences = planner.split_sentences(script)
        timings = [{"text": sentences[0], "start": .1, "end": 7.5}, {"text": sentences[1], "start": 8, "end": 10}]
        plan = planner.build_plan(script, {"first_clip_seconds": 8, "weights": {"text": 100}}, "Channel", duration=12, alignment=timings)
        self.assertEqual([(f["start"], f["end"]) for f in plan["frames"]], [(0, 8), (8, 12)])
        self.assertNotIn("continuation", plan["frames"][1])
        planner.validate_synced_plan(plan, 12)

    def test_continuation_is_visual_when_next_text_starts_later(self):
        script = "A first complete sentence here. A second complete sentence follows."
        sentences = planner.split_sentences(script)
        timings = [{"text": sentences[0], "start": .1, "end": 8.7}, {"text": sentences[1], "start": 9.3, "end": 11}]
        settings = {"first_clip_seconds": 8, "weights": {"text": 100}}
        plan = planner.build_plan(script, settings, "Channel", duration=12, alignment=timings)
        self.assertEqual(plan["frames"][1]["format"], "animation")
        self.assertEqual(plan["frames"][1]["start"], 8)
        planner.validate_synced_plan(plan, 12)
        with self.assertRaisesRegex(ValueError, "Текстова підказка"):
            planner.build_plan(script, settings, "Channel", duration=12, alignment=timings, hints={"2": "text"})

    def test_opening_can_cover_multiple_sentences_without_duplication(self):
        script = "First short sentence here. Second sentence starts shortly afterwards. Third sentence crosses the opening boundary. Fourth starts after the boundary ends."
        sentences = planner.split_sentences(script)
        intervals = [(.1, 1.5), (2, 4), (6, 8.7), (9.5, 11.5)]
        timings = [{"text": s, "start": a, "end": b} for s, (a, b) in zip(sentences, intervals)]
        plan = planner.build_plan(script, {"first_clip_seconds": 8, "weights": {"text": 100}}, "Channel", duration=12, alignment=timings)
        self.assertEqual(plan["frames"][0]["sentences"], sentences[:3])
        self.assertEqual(plan["frames"][1]["continuation"]["text"], sentences[2])
        self.assertEqual([s for f in plan["frames"] for s in f["sentences"]], sentences)
        planner.validate_synced_plan(plan, 12)

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
