import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import speech  # noqa: E402
import speech_order  # noqa: E402

SENTENCES = ["Your body has one more heater inside it.", "Scientists only confirmed it in adults in 2009.",
             "It is called brown fat and it burns energy.", "Newborn babies have plenty of it between the shoulders.",
             "They cannot shiver well yet so they need it.", "Adults keep a little of it near the neck."]


def voice(order, sentences=SENTENCES):
    words, t = [], 0.0
    for index in order:
        for word in sentences[index].split():
            words.append({"text": word, "start": t, "end": t + .3, "probability": .95})
            t += .35
        t += .4
    return words, t


class SpeechOrderTest(unittest.TestCase):
    def compare(self, order, sentences=SENTENCES):
        words, duration = voice(order, sentences)
        return speech.compare_script(" ".join(sentences), words, duration)

    def test_a_voice_in_order_passes(self):
        report = self.compare([0, 1, 2, 3, 4, 5])
        self.assertEqual(report["status"], "matched")
        self.assertFalse([d for d in report["differences"] if d.get("note")])

    def test_a_piece_said_twice_is_caught_with_both_times(self):
        report = self.compare([0, 1, 2, 1, 2, 3, 4, 5])
        self.assertEqual((report["status"], report["timings"]), ("needs_review", None))
        notes = [d["note"] for d in report["differences"] if d.get("kind") == "repeated"]
        self.assertEqual(notes[0], "Фраза 2 прозвучала двічі: о 0:03, о 0:09.")
        self.assertIn("repeated_speech", report["phrases"][1]["issues"])

    def test_the_end_said_before_the_opening_is_caught_as_out_of_place(self):
        report = self.compare([3, 4, 5, 0, 1, 2])
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual([d["sentences"] for d in report["differences"] if d.get("kind") == "moved"], [[4], [5], [6]])
        self.assertIn("out_of_order", report["phrases"][3]["issues"])

    def test_words_the_script_itself_says_again_are_no_repeat(self):
        sentences = ["Nobody is dead until they are warm and dead.", "Doctors kept working on her for nine long hours.",
                     "If they seem dead, keep doing it, because nobody is dead until they are warm and dead."]
        self.assertEqual(speech_order.check(" ".join(sentences), voice([0, 1, 2], sentences)[0]), {})


if __name__ == "__main__":
    unittest.main()
