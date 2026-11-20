"""Recognition takes only the time from the voice; the script's text, digits and number forms are never compared
(user, 20 November 2026, after «ein zweites Mal» failed a whole German recognition)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import number_text
import planner
import speech_repair

SCRIPT = ("Die Linien laufen nach außen. Im Schweif liegen sie so dicht, dass sie sich ein zweites Mal neu verbinden. "
          "Danach bleibt der Schweif ruhig.")


class RecognitionTextFreeTest(unittest.TestCase):
    def test_german_article_before_digits_is_not_the_number_one(self):
        self.assertEqual(number_text.comparison_tokens("sich ein 2. Mal neu", "de"), ["sich", "ein", "2", "mal", "neu"])
        self.assertEqual(number_text.comparison_tokens("eine 3-stündige Fahrt", "de")[0], "eine")
        self.assertEqual(number_text.comparison_tokens("ein Mal", "de"), ["1", "mal"])   # a real «once» stays a number

    def test_sentence_timings_never_compare_words_or_numbers(self):
        heard = [{"text": "völlig anders gehört", "start": 0.0, "end": 1.0},
                 {"text": "ein 2. Mal, zwei Mal, 2x", "start": 1.2, "end": 4.0},
                 {"text": "", "start": 4.1, "end": 5.0}]
        result = planner.validate_sentence_timings(SCRIPT, heard, 5.5)
        self.assertEqual([row["text"] for row in result], planner.split_sentences(SCRIPT))   # the script's own text

    def test_sentence_timings_still_check_time(self):
        for bad in ([{"text": "", "start": 0, "end": 1}],
                    [{"text": "", "start": 0, "end": 2}, {"text": "", "start": 1, "end": 3}, {"text": "", "start": 3, "end": 4}],
                    [{"text": "", "start": 0, "end": 1}, {"text": "", "start": 1, "end": 2}, {"text": "", "start": 2, "end": 9}]):
            with self.assertRaises(ValueError):
                planner.validate_sentence_timings(SCRIPT, bad, 5)

    def test_optional_rehearing_never_fails_the_recognition(self):
        words = [{"text": "x", "start": 0.0, "end": 1.0}]
        with patch.object(speech_repair.speech, "compare_script", side_effect=ValueError("check failed")):
            self.assertEqual(speech_repair.repair_script(Path("missing.wav"), SCRIPT, words, "de", duration=2), (words, 0))


if __name__ == "__main__":
    unittest.main()
