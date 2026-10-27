# -*- coding: utf-8 -*-
import sys
import copy
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import number_text
import planner
import speech
import legacy_number_text


class NumberTextTest(unittest.TestCase):
    def test_current_channel_quantities_and_exact_fractions(self):
        cases={
            "Восемь граммов.":"8 граммов.",
            "шестьдесят килограммов":"60 килограммов",
            "двадцать один день":"21 день",
            "одной десятой миллиграмма":"0,1 миллиграмма",
            "две трети грамма":"2/3 грамма",
            "полминуты и полграмма":"0,5 минуты и 0,5 грамма",
            "втрое меньше":"в 3 раза меньше",
            "Первый шаг и вторую неделю":"1-й шаг и 2-ю неделю",
            "двадцать третьего числа":"23-го числа",
            "двенадцать булочек, пять граммов":"12 булочек, 5 граммов",
        }
        for source,expected in cases.items():
            with self.subTest(source=source):self.assertEqual(number_text.to_digits(source),expected)

    def test_languages_used_by_other_channels(self):
        cases={
            "eight grams":"8 grams",
            "twenty-one dollars":"21 dollars",
            "two thousand five hundred dollars":"2500 dollars",
            "one point five grams":"1.5 grams",
            "one and a half hours":"1.5 hours",
            "two thirds of a cup":"2/3 of a cup",
            "neunzehnhundertachtundachtzig":"1988",
            "acht Gramm und ein Liter":"8 Gramm und 1 Liter",
            "dreiundzwanzig Euro":"23 Euro",
            "вісім грамів і двадцять один день":"8 грамів і 21 день",
            "п'ять грамів":"5 грамів",
        }
        for source,expected in cases.items():
            with self.subTest(source=source):self.assertEqual(number_text.to_digits(source),expected)

    def test_existing_digits_and_non_numeric_words_remain(self):
        for value in ["8 граммов, 0,1 мг, 2/3 грамма", "однажды он посмотрел", "someone noticed", "ein guter Mechaniker"]:
            self.assertEqual(number_text.to_digits(value),value)

    def test_russian_years_and_ambiguous_words_preserve_meaning(self):
        cases = {
            "В две тысячи пятнадцатом году": "В 2015-м году",
            "Испытание две тысячи пятнадцатого года": "Испытание 2015-го года",
            "В две тысячи двадцать пятом году": "В 2025-м году",
            "Средства влияют друг на друга по другим причинам": "Средства влияют друг на друга по другим причинам",
            "Семью пригласили, а семь человек ушли": "Семью пригласили, а 7 человек ушли",
            "С семью людьми": "С 7 людьми",
            "Зустрілися з другим учасником": "Зустрілися з 2-м учасником",
            "За полгода и до полугода": "За 0,5 года и до 0,5 года",
            "до сотни волос, сотни людей": "до 100 волос, сотни людей",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(number_text.to_digits(source), expected)

    def test_exact_values_not_ambiguous_ranges(self):
        self.assertEqual(planner.speech_text("одной десятой"),planner.speech_text("0.1"))
        self.assertEqual(planner.speech_text("две четверти"),planner.speech_text("0,5"))
        self.assertNotEqual(planner.speech_text("две трети"),planner.speech_text("2-3"))
        self.assertNotEqual(planner.speech_text("восемь"),planner.speech_text("9"))

    def test_word_spans_preserve_multiword_number_audio_boundaries(self):
        words=[{"text":text,"start":i*.2,"end":i*.2+.15,"probability":.99}
               for i,text in enumerate(["Use","twenty","one","grams."])]
        report=speech.compare_script("Use 21 grams.",words,1)
        self.assertEqual(report["status"],"matched")
        self.assertAlmostEqual(report["timings"]["sentences"][0]["end"],.75)
        self.assertEqual(report["phrases"][0]["recognized"],"Use 21 grams.")

    def test_speech_number_formatting_does_not_hide_wrong_fraction(self):
        words=[{"text":text,"start":i*.3,"end":i*.3+.2,"probability":.99}
               for i,text in enumerate(["2-3","грамма."])]
        self.assertEqual(speech.compare_script("Две трети грамма.",words,1)["status"],"needs_review")

    def test_ukrainian_locale_persists_in_sentences_without_unique_letters(self):
        script = "Ці учасники слухали. Другого дня учасники прийшли."
        sentences = planner.split_sentences(script)
        timing = [{"text": sentences[0], "start": 0, "end": 1},
                  {"text": sentences[1], "start": 1.2, "end": 2.4}]
        plan = planner.build_plan(script, {"weights": {"text": 100}}, "Channel", duration=2.4, alignment=timing)
        plan["timing"]["audio"] = {"duration": 2.4}
        formatted = planner.digitize_synced_plan(plan)
        self.assertIn("2-го дня", formatted["script"])
        self.assertIn("2-го дня", formatted["timing"]["sentences"][1]["text"])
        planner.validate_synced_plan(formatted, 2.4)

    def test_post_asr_plan_contains_digit_script_and_preserves_spoken_source(self):
        script="Насыпьте восемь граммов. Потом двадцать один грамм."
        phrases=[{"text":"Насыпьте 8 граммов.","start":0,"end":1}, {"text":"Потом 21 грамм.","start":1.2,"end":2}]
        plan=planner.build_plan(script,{"weights":{"text":100}},"Channel",duration=2,alignment=phrases)
        plan["timing"]["audio"]={"duration":2}
        plan=planner.digitize_synced_plan(plan)
        self.assertEqual(plan["script"],"Насыпьте 8 граммов. Потом 21 грамм.")
        self.assertEqual(plan["spoken_script"],script)
        self.assertEqual(plan["timing"]["sentences"][0]["text"],"Насыпьте 8 граммов.")
        planner.validate_synced_plan(plan,2)

    def test_draft_does_not_rewrite_spoken_script_before_whisper(self):
        plan=planner.build_plan("Насыпьте восемь граммов.",{"weights":{"text":100}},"Channel")
        self.assertEqual(planner.digitize_synced_plan(plan)["script"],"Насыпьте восемь граммов.")

    def test_legacy_number_format_is_read_without_changing_frame_times(self):
        script = "Мы помогаем друг другу. Он позвал всю семью."
        phrases = [{"text": text, "start": start, "end": end} for text, start, end in
                   zip(planner.split_sentences(script), [0, 1.1], [1, 2])]
        plan = planner.build_plan(script, {"weights": {"stock_video": 50, "text": 50}}, "Channel", duration=2, alignment=phrases)
        plan['timing']['audio'] = {'duration': 2}
        with patch.object(planner, 'number_text', legacy_number_text):
            legacy = planner.digitize_synced_plan(plan)
        saved = copy.deepcopy(legacy)
        self.assertNotEqual(legacy['script'], number_text.to_digits(script))
        fixed = planner.upgrade_legacy_number_format(legacy)
        self.assertEqual(legacy, saved)
        self.assertEqual(fixed['script'], number_text.to_digits(script))
        self.assertEqual([(f['start'], f['end'], f['format']) for f in fixed['frames']],
                         [(f['start'], f['end'], f['format']) for f in saved['frames']])
        planner.validate_synced_plan(fixed, 2)
        damaged = copy.deepcopy(saved)
        damaged['frames'][0]['sentence_timings'][0]['end'] += .1
        self.assertIs(planner.upgrade_legacy_number_format(damaged), damaged)

    def test_german_numeric_ordinals_keep_original_phrase_grid(self):
        script="Beim dritten Versuch klappt es. Dann warten wir acht Sekunden."
        phrases=[{"text":"Beim 3. Versuch klappt es.","start":0,"end":1}, {"text":"Dann warten wir 8 Sekunden.","start":1.2,"end":2}]
        plan=planner.build_plan(script,{"weights":{"text":100}},"Karl",duration=2,alignment=phrases)
        plan["timing"]["audio"]={"duration":2}
        plan=planner.digitize_synced_plan(plan)
        self.assertEqual(len(plan["timing"]["sentences"]),2)
        self.assertIn("3. Versuch",plan["script"])
        planner.validate_synced_plan(plan,2)


if __name__=="__main__":unittest.main()
