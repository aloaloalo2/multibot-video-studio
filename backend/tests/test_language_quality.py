import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import language_quality as quality
import store

ES = 'Durante la tormenta buscamos refugio dentro de un edificio cerrado para protegernos de los rayos.'
PL = 'Podczas burzy szukamy schronienia wewnątrz zamkniętego budynku, aby ochronić się przed uderzeniem pioruna.'
RU = 'Во время грозы мы ищем укрытие внутри закрытого здания, чтобы защититься от удара молнии.'


class LanguageQualityTest(unittest.TestCase):
    def setUp(self):
        quality._check.cache_clear()

    def test_foreign_blocks_have_exact_lines_and_keep_correct_neighbours(self):
        lines = [ES, ES, RU, 'Смотри в небо.', RU, ES, ES]
        report = quality.check('es', lines, [{'start': i*3, 'end': i*3+2} for i in range(7)])
        self.assertEqual(report['state'], 'blocked')
        self.assertEqual([item['index'] for item in report['issues']], [2, 3, 4])
        self.assertEqual(report['issues'][0]['start'], 6)
        with self.assertRaises(store.StudioError):
            quality.require('es', lines)

    def test_same_alphabet_wrong_language_and_correct_text(self):
        self.assertEqual(quality.check('es', [PL]*3)['state'], 'blocked')
        self.assertEqual(quality.check('pl', [ES]*3)['state'], 'blocked')
        self.assertEqual(quality.check('es', [ES]*3)['state'], 'ok')
        self.assertEqual(quality.check('pl', [PL]*3)['state'], 'ok')

    def test_foreign_sentence_inside_a_paragraph_is_detected(self):
        self.assertEqual(quality.check('es', ES+' '+RU+' '+ES)['state'], 'blocked')

    def test_short_names_and_acronyms_are_not_wrong_language_proof(self):
        self.assertEqual(quality.check('es', ['Roy Sullivan.', 'NASA.', 'Sí.'])['state'], 'ok')

    def test_missing_detector_fails_closed_before_any_speech(self):
        with patch.object(quality, 'identify', side_effect=ImportError('missing')):
            self.assertEqual(quality.check('es', [ES])['state'], 'unavailable')
            with self.assertRaises(store.StudioError):
                quality.require('es', [ES])

    def test_parallel_targets_do_not_mutate_one_another(self):
        cases = [('es', ES), ('pl', PL), ('es', RU), ('pl', RU)]*5
        with ThreadPoolExecutor(max_workers=4) as pool:
            states = list(pool.map(lambda pair: quality.check(*pair)['state'], cases))
        self.assertEqual(states, ['ok', 'ok', 'blocked', 'blocked']*5)


if __name__ == '__main__':
    unittest.main()
