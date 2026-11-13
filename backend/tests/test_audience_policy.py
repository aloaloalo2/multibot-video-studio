import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audience_policy
import author_rules
import episode_metadata
import languages
import store
import writer_context


class AudiencePolicyTest(unittest.TestCase):
    def test_policy_covers_all_authored_languages_and_keeps_the_original_language(self):
        text=audience_policy.text()
        for part in ('Україні', 'Європі', 'Казахстані', 'Росії', 'Москви', 'діячів', 'референсами',
                     'Зберігай задану мову каналу', 'незалежний перевірений приклад',
                     'Готові тексти та озвучку автоматично не переписуй'):
            self.assertIn(part,text)

    def test_imported_channel_rules_cannot_replace_current_studio_audience_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);channel=root/'Channel';channel.mkdir()
            source={'author':{'author_writing_rules':'Keep this unique imported author wish.',
                              'studio_audience_policy':'Old country-specific audience.'}}
            snapshot=copy.deepcopy(source)
            with patch.object(store,'read_json',return_value=source), \
                 patch.object(author_rules.word_blacklist,'current',return_value=[]), \
                 patch.object(author_rules.word_blacklist,'managed',return_value=False):
                result=author_rules.for_channel(channel,root)
            self.assertEqual(result['author_writing_rules'],source['author']['author_writing_rules'])
            self.assertEqual(result['studio_audience_policy'],audience_policy.text())
            self.assertEqual(source,snapshot)

    def test_compaction_preserves_current_policy_and_removes_exact_duplicated_paragraphs(self):
        policy=audience_policy.text()
        ctx={'studio_audience_policy':policy,'youtube_script_rules':policy,
             'script_wishes':'Keep the selected channel voice.'}
        result,metrics=writer_context.compact(ctx)
        self.assertEqual(result['studio_audience_policy'],policy)
        self.assertNotIn('Наша аудиторія міжнародна',result['youtube_script_rules'])
        self.assertGreater(metrics['duplicate_paragraphs'],0)
        self.assertEqual(result['script_wishes'],ctx['script_wishes'])

    def test_new_steps_read_latest_policy_without_reusing_old_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'policy.json'
            with patch.object(audience_policy,'PATH',file):
                file.write_text(json.dumps({'writer':'First audience rule','translation':'First localization rule'}))
                self.assertEqual(audience_policy.text(),'First audience rule')
                file.write_text(json.dumps({'writer':'Current audience rule','translation':'Current localization rule'}))
                self.assertEqual(audience_policy.text(),'Current audience rule')
                self.assertIn('Current audience rule',episode_metadata.prompt())
                self.assertIn('Current localization rule',languages.localization('ru'))

    def test_localization_has_international_audience_and_preserves_actual_source_identities(self):
        for code in ('ru','uk','en','de','es'):
            result=languages.localization(code)
            for part in ('Ukraine, Europe, Kazakhstan', 'Never localize a script toward Russia',
                         'Do not introduce Russia, Moscow', 'preserve the source', 'never relocate or rename'):
                self.assertIn(part,result)
        self.assertIn("Russian examples, only for Russian output",languages.localization('ru'))
        self.assertNotIn("Russian examples, only for Russian output",languages.localization('es'))

    def test_missing_or_empty_policy_is_not_silently_treated_as_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'policy.json'
            with patch.object(audience_policy,'PATH',file):
                with self.assertRaises(OSError):audience_policy.text()
                file.write_text('{"writer":"","translation":""}')
                with self.assertRaises(ValueError):audience_policy.text()
