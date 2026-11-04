"""Text-only recovery when a pacing draft ignores its measured length budget."""
import contextlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import languages


class PacingPreparationTest(unittest.TestCase):
    # The failed response preserved this entire 123-character line despite max_chars=108.
    original = (
        "Años después, en diciembre de dos mil diecisiete, Spurlock escribió que "
        "bebía alcohol con regularidad desde los trece años."
    )
    compact = (
        "En diciembre de dos mil diecisiete, Spurlock dijo que bebía habitualmente "
        "desde los trece años."
    )
    source = "Years later, in December 2017, Spurlock wrote that he had been drinking regularly since he was 13."

    def setUp(self):
        self.texts = ["An already paid phrase."] * 5 + [self.original]
        self.segments = [{"source": "Paid source."}] * 5 + [{"source": self.source}]
        self.targets = {5: 90}
        self.job = {}
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(languages, "translation_trace", return_value=contextlib.nullcontext()))
        self.stack.enter_context(patch.object(languages, "translator", return_value="Write Spanish."))
        self.stack.enter_context(patch.object(languages, "target_rule", return_value="Spanish only."))
        self.quality = self.stack.enter_context(patch.object(languages.language_quality, "require"))
        self.speak = self.stack.enter_context(patch.object(languages, "speak"))
        self.ask = self.stack.enter_context(patch.object(languages, "ask"))

    def draft(self, text):
        return json.dumps({"5": text}, ensure_ascii=False), .001

    def audit(self, ok=True):
        return json.dumps({"ok": ok, "ids": [5]}), .001

    def prepare(self):
        return languages.prepare_unvoiced("test-project", "es", self.texts,
                                          self.segments, self.targets, self.job)

    def test_repairs_123_character_response_with_108_character_budget_before_synthesis(self):
        self.assertEqual(len(self.original), 123)
        self.assertLessEqual(len(self.compact), 108)
        original_texts = list(self.texts)
        self.ask.side_effect = [self.draft(self.original), self.draft(self.compact), self.audit()]

        self.assertEqual(self.prepare(), {5: self.compact})

        self.assertEqual(self.ask.call_count, 3)  # draft, text repair, independent meaning audit
        repair_messages = json.dumps(self.ask.call_args_list[1].args[0], ensure_ascii=False)
        self.assertIn(str(languages.numeric_comparison.comparison_chars(self.original)), repair_messages)
        self.assertIn("90", repair_messages)
        self.assertEqual(self.texts, original_texts)
        self.speak.assert_not_called()

    def test_allows_second_bounded_text_repair(self):
        self.ask.side_effect = [self.draft(self.original), self.draft(self.original),
                                self.draft(self.compact), self.audit()]
        self.assertEqual(self.prepare(), {5: self.compact})
        self.assertEqual(self.ask.call_count, 4)  # three drafts at most, then audit
        self.speak.assert_not_called()

    def test_permanent_overlength_stops_after_three_drafts_without_speech(self):
        self.ask.return_value = self.draft(self.original)
        with self.assertRaises(RuntimeError):
            self.prepare()
        self.assertEqual(self.ask.call_count, 3)
        self.speak.assert_not_called()

    def test_missing_ids_can_be_repaired_before_meaning_audit(self):
        self.ask.side_effect = [("{}", .001), self.draft(self.compact), self.audit()]
        self.assertEqual(self.prepare(), {5: self.compact})
        self.assertEqual(self.ask.call_count, 3)
        self.speak.assert_not_called()

    def test_repaired_text_still_requires_correct_language(self):
        self.ask.side_effect = [self.draft(self.original), self.draft(self.compact)]
        self.quality.side_effect = RuntimeError("Wrong language")
        with self.assertRaisesRegex(RuntimeError, "Wrong language"):
            self.prepare()
        self.assertEqual(self.ask.call_count, 2)
        self.speak.assert_not_called()

    def test_length_compliant_text_still_requires_faithful_meaning(self):
        self.ask.side_effect = [self.draft(self.compact), self.audit(False)]
        with self.assertRaisesRegex(RuntimeError, "змісту"):
            self.prepare()
        self.assertEqual(self.ask.call_count, 2)
        self.speak.assert_not_called()

    def test_meaning_audit_id_order_is_irrelevant_but_every_id_is_required_once(self):
        self.texts.append(self.original)
        self.segments.append({"source": self.source})
        self.targets[6] = 90
        draft = json.dumps({"5": self.compact, "6": self.compact}), .001
        for ids, valid in [([6, 5], True), ([5, 5], False), ([5], False), ([5, "6"], False)]:
            with self.subTest(ids=ids):
                self.ask.side_effect = [draft, (json.dumps({"ok": True, "ids": ids}), .001)]
                if valid:
                    self.assertEqual(self.prepare(), {5: self.compact, 6: self.compact})
                else:
                    with self.assertRaisesRegex(RuntimeError, "змісту"):
                        self.prepare()
        self.speak.assert_not_called()

    def test_shortened_words_still_require_spoken_number_form(self):
        self.ask.side_effect = [self.draft(self.compact + " 13")]
        with self.assertRaisesRegex(RuntimeError, "числа"):
            self.prepare()
        self.assertEqual(self.ask.call_count, 1)
        self.speak.assert_not_called()


if __name__ == "__main__":
    unittest.main()
