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


class ScriptPhraseRepairTest(unittest.TestCase):
    script = ('The patient sits quietly near the open window. '
              'Glasses for reading are removed before these exercises. '
              'Both hands remain relaxed on the kitchen table.')

    def setUp(self):
        self.full = [w(text, round(2 + n * 8 + i * .4, 3), round(2 + n * 8 + i * .4 + .3, 3))
                     for n, sentence in enumerate(speech_repair.speech.planner.split_sentences(self.script))
                     for i, text in enumerate(sentence.split())]
        self.broken = [word for word in self.full if not 10.8 <= word['start'] < 14]

    def rehear(self, words):
        bounds = []
        def cut(audio, start, end, target):
            bounds[:] = [start, end]
            return True
        def transcribe(*args):
            start, end = bounds
            return ([{**word, 'start': word['start'] - start, 'end': word['end'] - start}
                     for word in self.full if word['start'] >= start and word['end'] <= end], {})
        with patch.object(speech_repair, 'cut', side_effect=cut), \
             patch.object(speech_repair.speech, 'transcribe', side_effect=transcribe) as recognize:
            result, fixed = speech_repair.repair_script(Path('voice.wav'), self.script, words, 'en', duration=24)
        return result, fixed, bounds, recognize.call_count

    def test_swallowed_sentence_is_reheard_once_with_real_times_and_unchanged_neighbours(self):
        result, fixed, bounds, calls = self.rehear(self.broken)
        self.assertEqual((fixed, calls), (1, 1))
        self.assertGreater(bounds[0], 5)
        self.assertLess(bounds[1], 24)
        self.assertEqual(result, self.full)
        self.assertEqual(speech_repair.speech.compare_script(self.script, result, 24)['status'], 'matched')

    def test_completely_missing_ending_uses_measured_audio_duration(self):
        result, fixed, bounds, calls = self.rehear([word for word in self.full if word['start'] < 18])
        self.assertEqual((fixed, calls), (1, 1))
        self.assertEqual(bounds[1], 24)
        self.assertEqual(result, self.full)

    def test_correct_recognition_never_runs_a_second_pass(self):
        with patch.object(speech_repair.speech, 'transcribe') as recognize:
            self.assertEqual(speech_repair.repair_script(Path('voice.wav'), self.script, self.full, duration=24), (self.full, 0))
        recognize.assert_not_called()

    def test_bad_or_failed_second_pass_keeps_original_evidence_and_no_retry_loop(self):
        for response in [([w('Unrelated.', 0, .3)], {}), RuntimeError('recognition unavailable')]:
            with self.subTest(response=response), patch.object(speech_repair, 'cut', return_value=True), \
                 patch.object(speech_repair.speech, 'transcribe', **({'side_effect': response} if isinstance(response, Exception) else {'return_value': response})) as recognize:
                self.assertEqual(speech_repair.repair_script(Path('voice.wav'), self.script, self.broken, duration=24), (self.broken, 0))
                recognize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
