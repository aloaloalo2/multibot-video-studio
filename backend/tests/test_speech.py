import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import speech
import analysis_jobs


class SpeechTest(unittest.TestCase):
    script = "First complete sentence. Second complete sentence."

    def words(self):
        return [{"text": text, "start": index * .2, "end": index * .2 + .15, "probability": .99}
                for index, text in enumerate(["First", "complete", "sentence.", "Second", "complete", "sentence."])]

    def test_complete_match_uses_actual_boundary_words(self):
        report = speech.compare_script(self.script, self.words(), 2)
        self.assertEqual(report["status"], "matched")
        self.assertEqual(report["word_match_percent"], 100)
        self.assertEqual(report["timings"]["sentences"][0]["end"], .55)
        self.assertAlmostEqual(report["timings"]["sentences"][1]["start"], .6)

    def test_missing_last_word_never_gets_an_invented_boundary(self):
        report = speech.compare_script(self.script, self.words()[:-1], 2)
        self.assertEqual(report["status"], "needs_review")
        self.assertIsNone(report["timings"])
        self.assertIsNone(report["phrases"][1]["end"])
        self.assertIn("missing_boundary", report["phrases"][1]["issues"])

    def test_extra_and_replaced_words_are_reported(self):
        words = self.words(); words[1]["text"] = "different"
        report = speech.compare_script(self.script, words, 2)
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["differences"][0]["expected"], "complete")
        self.assertEqual(report["differences"][0]["recognized"], "different")
        self.assertLess(report["word_match_percent"], 100)

    def test_low_recognition_confidence_is_reported_without_blocking(self):
        words = self.words(); words[0]["probability"] = .2
        report = speech.compare_script(self.script, words, 2)
        self.assertEqual(report["status"], "matched")
        self.assertIn("low_recognition_confidence", report["phrases"][0]["issues"])

    def long_script(self):
        return ("The soles of your feet go soft in orbit. " * 3 + "Folds appear in the choroid layer. " * 3).strip()

    def heard(self, text):
        return [{"text": word, "start": index * .3, "end": index * .3 + .25, "probability": .95}
                for index, word in enumerate(text.split())]

    def test_recognition_slips_take_the_script_words_and_the_heard_time(self):
        script = self.long_script()
        words = self.heard(script.replace("soles", "souls", 1).replace("choroid", "coroid", 1))
        report = speech.compare_script(script, words, 20)
        self.assertEqual(report["status"], "matched")
        self.assertEqual(report["corrected_words"], 2)
        aligned = report["aligned_words"]
        self.assertEqual([word["text"] for word in aligned], script.split())
        self.assertEqual(aligned[1]["text"], "soles")
        self.assertEqual((aligned[1]["start"], aligned[1]["end"]), (words[1]["start"], words[1]["end"]))
        self.assertEqual(report["timings"]["sentences"][0]["text"], "The soles of your feet go soft in orbit.")

    def test_a_real_gap_in_the_voice_still_needs_review(self):
        script = self.long_script()
        spoken = script.split()
        words = self.heard(" ".join(spoken[:10] + spoken[16:]))
        report = speech.compare_script(script, words, 20)
        self.assertEqual(report["status"], "needs_review")
        self.assertIn("missing_speech", report["phrases"][1]["issues"])
        self.assertIsNone(report["timings"])

    def test_overlapping_sentences_require_review(self):
        words = self.words(); words[3]["start"] = .4
        report = speech.compare_script(self.script, words, 2)
        self.assertIn("uncertain_boundary", report["phrases"][1]["issues"])
        self.assertIsNone(report["timings"])

    def test_case_punctuation_and_yo_do_not_create_false_text_differences(self):
        words = [{"text": "Ещё", "start": 0.0, "end": .2, "probability": 1.0}, {"text": "раз!", "start": .3, "end": .5, "probability": 1.0}]
        report = speech.compare_script("ЕЩЕ раз.", words, 1)
        self.assertEqual(report["status"], "matched")

    def test_repeated_script_phrase_with_missing_audio_is_not_filled_in(self):
        report = speech.compare_script(self.script + " Second complete sentence.", self.words(), 2)
        self.assertEqual(report["status"], "needs_review")
        self.assertIsNone(report["timings"])

    def test_analysis_owned_by_another_live_server_is_not_interrupted(self):
        with patch.object(analysis_jobs.os, "kill") as check:
            self.assertTrue(analysis_jobs.owner_alive({"id": "test", "owner_pid": analysis_jobs.os.getpid() + 100000}))
            check.assert_called_once()

    def test_interrupted_owner_is_detected(self):
        with patch.object(analysis_jobs.os, "kill", side_effect=ProcessLookupError):
            self.assertFalse(analysis_jobs.owner_alive({"id": "test", "owner_pid": analysis_jobs.os.getpid() + 100000}))


    def test_gpu_engine_is_used_when_a_local_mlx_model_exists(self):
        words = [{"text": "First", "start": 0.0, "end": .2, "probability": .9}]
        with patch.object(speech, "mlx_model_path", return_value="/models/small"), \
             patch.object(speech, "transcribe_mlx", return_value=(words, {"engine": "mlx-whisper"})) as gpu:
            self.assertEqual(speech.transcribe("voice.wav", 1, lambda value: None), (words, {"engine": "mlx-whisper"}))
        gpu.assert_called_once()

    def test_mlx_is_skipped_off_apple_silicon(self):
        with patch.object(speech.sys, "platform", "linux"):
            self.assertIsNone(speech.mlx_model_path())

    def test_cpu_engine_uses_every_core(self):
        self.assertEqual(speech.CPU_THREADS, speech.os.cpu_count() or 4)
