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

    def test_unicode_ellipsis_does_not_shift_later_sentence_times(self):
        script = 'Сосиски выручают, когда готовить некогда. На такой случай держите котлеты.'
        words = self.heard(script.replace('выручают,', 'выручают…'))
        report = speech.compare_script(script, words, 5)
        self.assertEqual(report['status'], 'matched')
        self.assertEqual(report['timings']['sentences'][0]['end'], words[4]['end'])
        self.assertEqual(report['timings']['sentences'][1]['start'], words[5]['start'])
        self.assertAlmostEqual(report['timings']['sentences'][1]['end'], words[-1]['end'])
        for aligned, heard in zip(report['aligned_words'], words):
            self.assertAlmostEqual(aligned['start'], heard['start'])
            self.assertAlmostEqual(aligned['end'], heard['end'])

    def test_verified_take_order_does_not_stop_on_whisper_spelling_slips(self):
        script='Ещё в моём меню прибавилось калия.'
        words=[{'text': text, 'start': i*.3, 'end': i*.3+.2, 'probability':.95}
               for i,text in enumerate('Еще в моем меню прибавилась каллия.'.split())]
        self.assertEqual(speech.compare_script(script,words,3)['status'],'needs_review')
        report=speech.compare_script(script,words,3,sequence_verified=True)
        self.assertEqual(report['status'],'matched')
        self.assertEqual(report['word_match_percent'],66.7)
        self.assertEqual(report['timings']['sentences'][0]['text'],script)
        self.assertIn('low_phrase_match',report['phrases'][0]['issues'])

    def test_verified_assembly_still_requires_speech_and_real_sentence_boundaries(self):
        for words in [self.words()[:-1],self.words()[3:]]:
            report=speech.compare_script(self.script,words,2,sequence_verified=True)
            self.assertEqual(report['status'],'needs_review')
            self.assertIsNone(report['timings'])

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

    def test_each_sentence_must_match_even_when_the_whole_script_exceeds_95_percent(self):
        script = ('The patient sits quietly near the open window. ' * 8 + 'Both hands remain completely relaxed.').strip()
        heard = script.replace('hands remain', 'feet become')
        report = speech.compare_script(script, self.heard(heard), 30)
        self.assertGreater(report['word_match_percent'], 95)
        self.assertEqual(report['phrases'][-1]['word_match_percent'], 60)
        self.assertIn('low_phrase_match', report['phrases'][-1]['issues'])
        self.assertEqual(report['status'], 'needs_review')
        self.assertIsNone(report['timings'])
        boundary = speech.compare_script(script, self.heard(script.replace('hands', 'arms')), 30)
        self.assertEqual(boundary['phrases'][-1]['word_match_percent'], 80)
        self.assertEqual(boundary['status'], 'matched')

    def test_90_percent_is_inclusive_and_every_sentence_still_needs_confirmation(self):
        script = ('Today the patient sits quietly near the large open window. '
                  'Then the doctor explains each movement slowly before practice begins.')
        heard = script.replace('quietly', 'calmly').replace('slowly', 'clearly')
        report = speech.compare_script(script, self.heard(heard), 10)
        self.assertEqual(report['word_match_percent'], 90)
        self.assertEqual(report['matched_phrases'], report['phrase_count'])
        self.assertEqual(report['status'], 'matched')
        self.assertIsNotNone(report['timings'])
        below = speech.compare_script(script, self.heard(heard.replace('large', 'wide')), 10)
        self.assertEqual(below['word_match_percent'], 85)
        self.assertTrue(all(p['word_match_percent'] >= 80 for p in below['phrases']))
        self.assertEqual(below['status'], 'needs_review')
        self.assertIsNone(below['timings'])

    def test_number_words_and_digits_are_equal_in_both_directions(self):
        pairs = [
            ('Повторите это движение 15 раз.', 'Повторите это движение пятнадцать раз.'),
            ('Повторите это движение 21 раз.', 'Повторите это движение двадцать один раз.'),
            ('Підніміть руку 15 разів.', 'Підніміть руку п’ятнадцять разів.'),
            ('Use 21 grams of this ingredient.', 'Use twenty one grams of this ingredient.'),
            ('Wiederholen Sie diese Bewegung 25 Mal.', 'Wiederholen Sie diese Bewegung fünfundzwanzig Mal.'),
        ]
        for digits, written in pairs:
            for script, heard in [(digits, written), (written, digits)]:
                with self.subTest(script=script, heard=heard):
                    words = self.heard(heard)
                    report = speech.compare_script(script, words, len(words) * .3 + 1)
                    self.assertEqual(report['status'], 'matched')
                    self.assertEqual(report['word_match_percent'], 100)
                    self.assertEqual(report['matched_phrases'], report['phrase_count'])

    def test_wrong_numbers_block_even_with_a_high_overall_and_sentence_match(self):
        script = 'The patient sits quietly near the open window. ' * 8 + 'Repeat these movements 15 times every single morning.'
        report = speech.compare_script(script, self.heard(script.replace('15', '50')), 30)
        self.assertGreater(report['word_match_percent'], 95)
        self.assertGreater(report['phrases'][-1]['word_match_percent'], 80)
        self.assertIn('number_difference', report['phrases'][-1]['issues'])
        self.assertEqual(report['status'], 'needs_review')
        numeric = speech.compare_script(script, self.heard(script.replace('15', 'fifteen')), 30)
        self.assertEqual(numeric['status'], 'matched')

    def test_original_narration_checks_sentence_presence_without_blocking_asr_spelling_or_numbers(self):
        cases = [
            ('Viele Fachleute raten, Winterreifen nach etwa sechs bis acht Jahren zu ersetzen.',
             'Viele Fachleute raten, Winterreifen nach etwa 6 -8 Jahren zu ersetzen.'),
            ('Gesetzlich verlangt sind in Deutschland 1,6 Millimeter im Winter.',
             'Gesetzlich verlangt sind in Deutschland 1 ,6 Millimeter im Winter.'),
            ('Du fährst vielleicht zehntausend Kilometer im Jahr und sparst zwei Wechsel.',
             'Du fährst vielleicht 10 .000 Kilometer im Jahr und sparst 2 Wechsel.'),
            ('Das klingt für viele falsch herum.', 'Das klingt für viele Falscher rum.'),
            ('Repeat these movements 15 times every single morning.',
             'Repeat these movements 50 times every single morning.'),
        ]
        for script, heard in cases:
            with self.subTest(script=script):
                words = self.heard(heard)
                saved = [dict(word) for word in words]
                duration = len(words) * .3 + 1
                self.assertEqual(speech.compare_script(script, words, duration)['status'], 'needs_review')
                report = speech.compare_script(script, words, duration, order_only=True)
                self.assertEqual(report['status'], 'matched')
                self.assertEqual(report['recognition_policy'], 'sentence_order')
                self.assertEqual(report['matched_phrases'], report['phrase_count'])
                self.assertTrue(report['phrases'][0]['issues'])
                self.assertIsNotNone(report['timings'])
                self.assertNotIn('sequence_verification', report)
                self.assertEqual(words, saved)

    def test_order_policy_still_rejects_unrelated_or_missing_speech_and_overlapping_boundaries(self):
        candidates = [self.heard('Different unrelated text. Nothing matches here.'),
                      self.words()[:-3], self.words()[3:]]
        overlap = self.words(); overlap[3]['start'] = .4
        candidates.append(overlap)
        for words in candidates:
            with self.subTest(words=words):
                report = speech.compare_script(self.script, words, 6, order_only=True)
                self.assertEqual(report['status'], 'needs_review')
                self.assertIsNone(report['timings'])

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
