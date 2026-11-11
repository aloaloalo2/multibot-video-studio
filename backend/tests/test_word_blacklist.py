from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import author_rules
import store
import word_blacklist as words


class WordBlacklistTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        p=patch.object(store,'GLOBAL_SETTINGS_PATH',self.root/'settings.json');p.start();self.addCleanup(p.stop)

    def test_normalizes_lines_and_duplicates_without_losing_phrases(self):
        self.assertEqual(words.normalize('  Слово\nслово\nНУ,   КОРОТШЕ\n\n'),['Слово','НУ, КОРОТШЕ'])
        self.assertEqual(words.matches('Це СЛОВО і ну,\nкоротше кажучи.', ['слово','ну, коротше']),['слово','ну, коротше'])
        self.assertEqual(words.matches('Сад, адекватний опис.', ['ад']),[])
        self.assertEqual(words.matches('Знак [x] тут.', ['[x]']),['[x]'])

    def test_preserves_migrated_forms_and_the_existing_shower_exception(self):
        for text,entry in [('сахарозаменитель','сахар'),('бессахарный','сахар'),('белка','белок'),('белковый','белок'),('білковий','білок'),('гвоздичный','гвоздика'),('душой','душа'),('в душе','душа'),('сто́ит','стоит')]:
            self.assertEqual(words.matches(text,[entry]),[entry])
        self.assertEqual(words.matches('Под душем тепло.', ['душа']),[])
        self.assertEqual(words.matches('Сахарный продукт.', []),[])

    def test_global_settings_persist_edits_and_reject_invalid_entries(self):
        updated=store.update_global_settings({'word_blacklist':['Первое','первое','Два слова']})
        self.assertEqual(updated['word_blacklist'],['Первое','Два слова'])
        self.assertEqual(words.current(),['Первое','Два слова'])
        for value in [42,{},['x'*161],[None],['слово']*301]:
            with self.assertRaises(store.StudioError):store.update_global_settings({'word_blacklist':value})
        store.update_global_settings({'word_blacklist':[]});self.assertEqual(words.current(),[])

    def test_writer_context_uses_current_studio_list_and_keeps_other_writing_rules(self):
        store.update_global_settings({'word_blacklist':['Нове слово']})
        old='Без тире.\n\nЗаборонено слова «сахар» і «белок».\n\nОснову «мест» заборонено лише для цього каналу.'
        with patch.object(author_rules,'writing_rules',return_value=old),patch.object(author_rules,'script_sections',return_value=''),patch.object(author_rules,'claude_memory',return_value=''),patch.object(store,'DATA_ROOT',self.root):
            ctx=author_rules.for_channel(self.root/'channel',self.root)
        self.assertEqual(ctx['studio_word_blacklist'],['Нове слово'])
        self.assertIn('Без тире',ctx['author_writing_rules']);self.assertIn('«мест»',ctx['author_writing_rules'])
        self.assertNotIn('сахар',ctx['author_writing_rules'])
        with patch.object(author_rules,'PROVERKA',self.root/'absent.py'):
            passed,message=author_rules.check('Тут нове слово.',self.root)
        self.assertFalse(passed);self.assertIn('Нове слово',message)
