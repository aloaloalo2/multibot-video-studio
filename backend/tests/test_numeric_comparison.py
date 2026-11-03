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
                self.assertEqual(result['difference_percent'],0.)
                self.assertEqual(result['source_numbers'],result['translated_numbers'])

    def test_numbers_are_not_deleted_and_a_changed_value_stays_visible(self):
        original='25 days';translated='dos mil quinientos días'
        result=numbers.comparison(original,translated,'en','es')
        self.assertEqual(numbers.normalized(translated,'es')[0],'2500 días')
        self.assertEqual(result['source_chars'],7)
        self.assertEqual(result['translated_chars'],9)
        self.assertAlmostEqual(result['difference_percent'],28.57)
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
                          ('the one who stayed','en'),('First aid is useful.','en')]:
            with self.subTest(text=text):self.assertEqual(numbers.normalized(text,code)[0],text)
        self.assertEqual(numbers.normalized('veinticinco por ciento','es')[0],'25 por ciento')

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


if __name__=='__main__':unittest.main()
