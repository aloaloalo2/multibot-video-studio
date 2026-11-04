import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numeric_comparison as numbers
import translation_budget


class NumericComparisonTest(unittest.TestCase):
    def test_spelled_out_numbers_compare_identically_to_digits_in_supported_languages(self):
        cases=[('es','dos mil cuatro, veinticinco, treinta y dos','2004, 25, 32'),
               ('uk','дві тисячі сімнадцятого року, двадцять п’ять','2017 року, 25'),
               ('ru','две тысячи семнадцатого года, двадцать пять','2017 года, 25'),
               ('pl','dwa tysiące siedemnastego roku, dwudziestu pięciu','2017 roku, 25'),
               ('en','two thousand and seventeen, twenty-five','2017, 25'),
               ('de','zweitausendsiebzehn, fünfundzwanzig','2017, 25'),
               ('fr','deux mille dix-sept, vingt-cinq','2017, 25'),
               ('it','duemiladiciassette, venticinque','2017, 25'),
               ('pt','dois mil e dezassete, vinte e cinco','2017, 25')]
        for code,spoken,digits in cases:
            with self.subTest(code=code):
                self.assertEqual(numbers.normalized(spoken,code)[0],digits)
                result=numbers.comparison(digits,spoken,code,code)
                self.assertEqual(result['source_chars'],result['translated_chars'])
                self.assertEqual(result['difference_percent'],0. if result['source_chars'] else None)
                self.assertEqual(result['source_numbers'],result['translated_numbers'])

    def test_numbers_are_not_deleted_and_a_changed_value_stays_visible(self):
        original='25 days';translated='dos mil quinientos días'
        result=numbers.comparison(original,translated,'en','es')
        self.assertEqual(numbers.normalized(translated,'es')[0],'2500 días')
        self.assertEqual(result['source_chars'],4)
        self.assertEqual(result['translated_chars'],sum(c.isalpha() for c in translated))
        self.assertEqual(result['translated_numbers'],0)
        self.assertEqual(original,'25 days');self.assertEqual(translated,'dos mil quinientos días')

    def test_decimal_grouping_mixed_scales_ordinals_and_polish_decimal(self):
        for text,code,expected in [
            ('1,500 and 1.5 million','en','1500 and 1500000'),
            ('1.500 y mil quinientos','es','1500 y 1500'),
            ('trzy przecinek pięć','pl','3.5'),
            ('dos coma cinco','es','2.5'),
            ('25th and twenty-fifth','en','25 and 25'),
            ('дві тисячі двадцять третього року','uk','2023 року'),
            ('30\u202f000','uk','30000'),
        ]:
            with self.subTest(text=text):self.assertEqual(numbers.normalized(text,code)[0],expected)

    def test_articles_pronouns_and_units_are_kept(self):
        for text,code in [('Una persona, un problema y uno de ellos.','es'),
                          ('unos minutos y unas horas','es'),('miles de millones de personas','es'),
                          ('tres cuartos de hora','es'),
                          ('the one who stayed','en'),('First aid is useful.','en')]:
            with self.subTest(text=text):self.assertEqual(numbers.normalized(text,code)[0],text)
        self.assertEqual(numbers.normalized('veinticinco por ciento','es')[0],'25 por ciento')

    def test_spanish_half_scales_keep_the_complete_quantity(self):
        for text,expected in [('ocho millones y medio','8500000'),
                              ('un millón y medio','1500000'),('dos y medio millones','2500000')]:
            with self.subTest(text=text):
                self.assertEqual(numbers.normalized(text,'es')[0],expected)

    def test_indefinite_favour_requests_keep_their_words_and_explicit_counts_remain_numbers(self):
        for code,text in [('ru','Пока вы ещё спите, прошу об одном маленьком одолжении.'),
                          ('uk','Прошу вас про одну маленьку послугу.'),
                          ('pl','Proszę o jedną małą przysługę.')]:
            with self.subTest(code=code):
                result=numbers.comparison('A quick favour.',text,'en',code)
                self.assertEqual(result['translated_chars'],sum(c.isalpha() for c in text))
                self.assertEqual(result['translated_numbers'],0)
        result=numbers.comparison("While you're still asleep, here's a quick favor.",
            'Пока вы ещё спите, прошу об одном маленьком одолжении.','en','ru')
        self.assertEqual(result['translated_chars'],44)
        self.assertEqual(result['difference_percent'],18.92)
        self.assertEqual(numbers.normalized('Прошу ровно одно одолжение.','ru')[0],'Прошу ровно 1 одолжение.')

    def test_only_original_digits_and_their_exact_word_counterparts_are_discounted(self):
        for source,translated,expected in [
            ('25 days','veinticinco días','25 días'),
            ('twenty-five days','veinticinco días','veinticinco días'),
            ('A small favour.','Прошу об одном одолжении.','Прошу об одном одолжении.'),
            ('25 days','veintiséis días','veintiséis días'),
            ('25 days','25 días','25 días'),
            ('25 days','veinticinco y veinticinco días','25 y veinticinco días'),
        ]:
            code='ru' if 'Прошу' in translated else 'es'
            with self.subTest(source=source,translated=translated):
                left,right=numbers.paired_forms(source,translated,'en',code)
                self.assertEqual(left[0],source)
                self.assertEqual(right[0],expected)
                self.assertEqual(len(left[1]),len(right[1]))

    def test_a_digit_in_another_phrase_cannot_discount_an_unrelated_word(self):
        sources=['1 hour','A favour.'];targets=['час','одна просьба']
        result=numbers.comparison('\n'.join(sources),'\n'.join(targets),'en','ru',
            source_units=sources,translated_units=targets)
        self.assertEqual(result['translated_chars'],sum(c.isalpha() for c in ''.join(targets)))
        self.assertEqual(result['source_numbers'],0)
        plan=translation_budget.number_refinement_plan('\n'.join(sources),targets,sources,'en','ru')
        self.assertEqual(plan['phrases'][1]['translated_chars'],sum(c.isalpha() for c in targets[1]))

    def test_expansion_is_local_and_does_not_turn_comparison_into_price_or_acceptance(self):
        result=translation_budget.assessment('In 2004 he gained 25 pounds.',
            'En dos mil cuatro ganó veinticinco libras.','en','es')
        self.assertTrue(result['number_comparison']['available'])
        self.assertGreater(result['translated_chars'],result['number_comparison']['translated_chars'])
        self.assertTrue(result['advisory_only'])
        self.assertFalse(result['duration_estimate'])
        self.assertNotIn('within_budget',result)

    def test_unsupported_language_has_no_false_normalized_percentage(self):
        result=numbers.comparison('25','二十五','en','zh')
        self.assertFalse(result['available']);self.assertIsNone(result['difference_percent'])

    def test_empty_input_and_newline_boundaries(self):
        self.assertIsNone(numbers.comparison('','','en','es')['difference_percent'])
        self.assertEqual(numbers.normalized('veinte\ncinco','es')[0],'20\n5')
        self.assertEqual(numbers.normalized('dwadzieścia\npięć','pl')[0],'20\n5')
        # The saved text's spacing is preserved for comparable display counts.
        self.assertEqual(numbers.normalized('  veinticinco  \n','es')[0],'  25  \n')

    def test_punctuation_is_ignored_in_both_comparison_counts_without_changing_text(self):
        source='Hello, world!';target='Hello: world...'
        result=numbers.comparison(source,target,'en','en')
        self.assertEqual((result['source_chars'],result['translated_chars']),(10,10))
        self.assertEqual(result['difference_percent'],0)
        self.assertTrue(result['punctuation_excluded'])
        self.assertEqual(numbers.comparison_chars('«пʼять», п’ять; п\'ять!'),12)
        self.assertEqual(source,'Hello, world!');self.assertEqual(target,'Hello: world...')

    def test_number_values_are_matched_before_punctuation_is_discounted(self):
        result=numbers.comparison('2.5 days!','dos coma cinco días.','en','es')
        self.assertEqual((result['source_numbers'],result['translated_numbers']),(1,1))
        self.assertEqual(result['source_chars'],4)
        self.assertEqual(result['translated_chars'],4)
        mismatch=numbers.comparison('2.5 days!','veinticinco días.','en','es')
        self.assertEqual(mismatch['translated_numbers'],0)

    def test_whole_and_phrase_budgets_share_punctuation_free_counts_but_billing_stays_raw(self):
        sources=['Hello, world!','25 days.'];targets=['Hello: world...','veinticinco días!']
        source='\n'.join(sources);target='\n'.join(targets)
        whole=numbers.comparison(source,target,'en','es',source_units=sources,translated_units=targets)
        self.assertEqual((whole['source_chars'],whole['translated_chars']),(14,14))
        plan=translation_budget.number_refinement_plan(source,targets,sources,'en','es')
        self.assertEqual([x['difference_percent'] for x in plan['phrases']],[0,0])
        self.assertTrue(plan['within_budget'])
        raw=translation_budget.assessment(source,target,'en','es')
        self.assertEqual(raw['translated_chars'],sum(c.isalpha() for c in target))
        self.assertEqual(raw['translated_billing_chars'],len(target))

    def test_original_letter_basis_is_stable_across_translations(self):
        source='He won 1.5 million dollars.'
        expected=numbers.source_comparison_chars(source,'en')
        self.assertEqual(expected,12)
        for target,code in [('Ganó un millón y medio de dólares.','es'),('Il a gagné deux millions de dollars.','fr')]:
            report=numbers.comparison(source,target,'en',code)
            self.assertEqual(report['source_chars'],expected)

    def test_only_letters_count_in_every_supported_alphabet(self):
        self.assertEqual(numbers.comparison_chars(" Hello 123, world! "),10)
        self.assertEqual(numbers.comparison_chars("¿Hola, qué tal? ¡Sí! 25%"),12)
        self.assertEqual(numbers.comparison_chars("пʼять п’ять п'ять 100 - €"),12)
        self.assertEqual(numbers.comparison_chars('e\u0301é'),2)
        self.assertEqual(numbers.comparison_chars(' 123!? -- 🙂'),0)
        report=numbers.comparison('25 days!','veinticinco días.','en','es')
        self.assertTrue(report['letters_only']);self.assertFalse(report['spaces_included'])
        self.assertEqual((report['source_chars'],report['translated_chars']),(4,4))


if __name__=='__main__':unittest.main()
