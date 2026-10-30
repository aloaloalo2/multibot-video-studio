import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import speech_repair  # noqa: E402


def w(text, start, end):
    return {"text": text, "start": start, "end": end, "probability": 0.9}


# "These are the lucky stories. Studies of adults ... report that only" came back as "These are the that only".
SWALLOWED = [w("healthy", 10.0, 10.3), w("brain.", 10.3, 10.7), w("These", 11.7, 12.1), w("are", 12.1, 15.6), w("the", 15.6, 17.7),
             w("that", 17.7, 17.9), w("only", 17.9, 18.2), w("somewhere", 18.2, 18.7)]


class SpeechRepairTest(unittest.TestCase):
    def test_stretched_words_mark_one_merged_hole(self):
        self.assertEqual(speech_repair.holes(SWALLOWED), [(1, 6)])
        self.assertEqual(speech_repair.holes([w("fine", 0, 0.4), w("words", 0.4, 0.9)]), [])

    def test_the_hole_is_heard_again_and_stays_between_its_neighbours(self):
        again = [w(t, i * 0.4, i * 0.4 + 0.3) for i, t in enumerate(
            "brain. These are the lucky stories. Studies of adults report that".split())]
        with patch.object(speech_repair, "cut", return_value=True), \
                patch.object(speech_repair.speech, "transcribe", return_value=(again, {})):
            words, fixed = speech_repair.repair(Path("voice.wav"), SWALLOWED, "en")
        self.assertEqual(fixed, 1)
        self.assertEqual([x["text"] for x in words][:3], ["healthy", "brain.", "These"])
        self.assertIn("lucky", [x["text"] for x in words])
        self.assertEqual(words[-1]["text"], "somewhere")
        starts = [x["start"] for x in words]
        self.assertEqual(starts, sorted(starts))
        self.assertGreaterEqual(words[1]["start"], SWALLOWED[0]["end"])        # never before the word ahead of the hole
        self.assertLessEqual(words[-2]["end"], SWALLOWED[-1]["start"])         # never after the word behind it

    def test_a_second_pass_that_hears_less_keeps_the_first(self):
        with patch.object(speech_repair, "cut", return_value=True), \
                patch.object(speech_repair.speech, "transcribe", return_value=([w("x", 0, 0.2)], {})):
            words, fixed = speech_repair.repair(Path("voice.wav"), SWALLOWED, "en")
        self.assertEqual((words, fixed), (SWALLOWED, 0))
        with patch.object(speech_repair, "cut", return_value=False):
            self.assertEqual(speech_repair.repair(Path("voice.wav"), SWALLOWED)[1], 0)


if __name__ == "__main__":
    unittest.main()
