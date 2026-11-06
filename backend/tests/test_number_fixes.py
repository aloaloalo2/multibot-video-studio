import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import number_text
import planner


def synced(script, duration=30.0):
    sentences = planner.split_sentences(script)
    step = duration / len(sentences)
    timings = [{"text": s, "start": round(i * step + .1, 3), "end": round((i + 1) * step - .1, 3)} for i, s in enumerate(sentences)]
    plan = planner.build_plan(script, {"weights": {"text": 100}}, "Channel", duration=duration, alignment=timings)
    plan["timing"]["audio"] = {"duration": duration}
    return planner.digitize_synced_plan(plan), sentences


class NumberFixesTest(unittest.TestCase):
    """The formatter finds numbers; the agent decides how a sentence reads (user, 5 November 2026)."""

    script = "Каждый мазал ногти полгода. Это решает половину дела. Потом пришли сто семнадцать человек."

    def test_manual_writing_replaces_the_formatter_in_script_timings_and_frames(self):
        plan, sentences = synced(self.script)
        self.assertIn("0,5", plan["script"])
        fixed = planner.apply_number_fixes(plan, {sentences[0]: sentences[0], sentences[1]: sentences[1]})
        planner.validate_synced_plan(fixed, 30.0)
        self.assertIn("полгода", fixed["script"])
        self.assertIn("половину дела", fixed["script"])
        self.assertIn("117", fixed["script"])
        texts = [t for frame in fixed["frames"] for t in frame["sentences"]]
        self.assertEqual(texts[:2], sentences[:2])
        self.assertEqual([i["text"] for i in fixed["timing"]["sentences"]], texts)
        self.assertEqual(fixed["spoken_script"], plan["spoken_script"])

    def test_a_fix_may_only_change_how_numbers_are_written(self):
        plan, sentences = synced(self.script)
        with self.assertRaises(ValueError):
            planner.apply_number_fixes(plan, {sentences[2]: "Потом пришли сто семнадцать врачей."})
        with self.assertRaises(ValueError):
            planner.apply_number_fixes(plan, {"Такой фразы нет.": "Такой фразы нет."})
        tampered = planner.apply_number_fixes(plan, {sentences[0]: sentences[0]})
        tampered["number_fixes"][sentences[0]] = "Каждый мазал ногти год."
        with self.assertRaises(ValueError):
            planner.validate_synced_plan(tampered, 30.0)

    def test_a_fix_equal_to_the_formatter_is_dropped_and_german_works(self):
        plan, sentences = synced(self.script)
        same = planner.apply_number_fixes(plan, {sentences[2]: number_text.to_digits(sentences[2])})
        self.assertNotIn("number_fixes", same)
        german = "Damit die Türen gar nicht erst festfrieren, hilft Pflege. Schaltest du als Erstes die Wischer ein, reißt das Gummi."
        plan, sentences = synced(german)
        fixed = planner.apply_number_fixes(plan, {s: s for s in sentences})
        planner.validate_synced_plan(fixed, 30.0)
        self.assertIn("gar nicht erst", fixed["script"])
        self.assertIn("als Erstes", fixed["script"])

    def test_legacy_upgrade_leaves_a_fixed_plan_alone(self):
        plan, sentences = synced(self.script)
        fixed = planner.apply_number_fixes(plan, {sentences[0]: sentences[0]})
        self.assertEqual(planner.upgrade_legacy_number_format(copy.deepcopy(fixed)), fixed)


if __name__ == "__main__":
    unittest.main()
