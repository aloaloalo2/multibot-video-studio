import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import language_quality
import languages
import store


class LinguistLanguageTest(unittest.TestCase):
    """The detector's doubt is decided by the linguist (user, 15 November 2026)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(store, 'DATA_ROOT', Path(self.tmp.name)); patcher.start(); self.addCleanup(patcher.stop)
        self.line = 'Строка, которую детектор посчитал чужой.'
        doubt = {'version': 5, 'target': 'ru', 'state': 'blocked', 'checked_lines': 1, 'method': 'test',
                 'issues': [{'index': 0, 'detected': 'uk', 'reason': 'language', 'text': self.line}]}
        patcher = patch.object(language_quality, '_check', return_value=doubt); patcher.start(); self.addCleanup(patcher.stop)

    def test_a_line_the_linguist_confirms_passes_for_good(self):
        with patch.object(languages, 'ask', return_value=(json.dumps({'1': True}), .001)) as ask:
            report, cost = languages.linguist_language_check('ru', [self.line])
        self.assertEqual(report['state'], 'ok'); self.assertEqual(ask.call_count, 1)
        self.assertEqual(language_quality.check('ru', [self.line])['state'], 'ok')   # the voice check honours it too
        language_quality.require('ru', [self.line])

    def test_a_line_the_linguist_rejects_stays_blocked(self):
        with patch.object(languages, 'ask', return_value=(json.dumps({'1': False}), .001)):
            report, _ = languages.linguist_language_check('ru', [self.line])
        self.assertEqual(report['state'], 'blocked')
        with self.assertRaises(store.StudioError):
            language_quality.require('ru', [self.line])


if __name__ == '__main__':
    unittest.main()
