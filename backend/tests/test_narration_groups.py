"""A few sentences of a paragraph in one HeyGen request (user, 17 November 2026: «по три речення віддавати… щоб можна
було змінювати… 4, 5»)."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import channel_voice_lab as lab
import project_narration as narration
import store


class UnitsTest(unittest.TestCase):
    text = 'One went home. Two went out. Three stayed. Four sang. Five slept.\nSix woke up. Seven left.'

    def test_a_paragraph_is_grouped_evenly_and_a_break_starts_a_new_request(self):
        units = narration.units(self.text, 3)
        self.assertEqual([u['sentences'] for u in units], [3, 2, 2])
        self.assertEqual([u['text'] for u in units],
                         ['One went home. Two went out. Three stayed.', 'Four sang. Five slept.', 'Six woke up. Seven left.'])

    def test_the_count_is_a_number_to_change(self):
        self.assertEqual([u['sentences'] for u in narration.units(self.text, 5)], [5, 2])
        self.assertEqual([u['sentences'] for u in narration.units(self.text, 4)], [3, 2, 2])   # 5 by 4: 3 and 2
        self.assertEqual([u['text'] for u in narration.units(self.text, 1)], narration.phrases(self.text))
        self.assertEqual(len(narration.phrases(self.text)), 7)   # the sentences, as a revision reads them

    def test_ten_sentences_run_on_across_paragraphs_only_when_asked(self):
        self.assertEqual([u['sentences'] for u in narration.units(self.text, 10)], [5, 2])
        joined = narration.units(self.text, 10, join=True)
        self.assertEqual([u['sentences'] for u in joined], [7])
        self.assertEqual(joined[0]['text'], ' '.join(narration.phrases(self.text)))   # as a revision rebuilds it
        free = lab.validated({'provider': 'heygen', 'heygen_join_paragraphs': True})
        self.assertTrue(lab.joins_paragraphs(free))
        self.assertFalse(lab.joins_paragraphs({**free, 'heygen_sentences': 1}))
        with self.assertRaises(store.StudioError):
            lab.validated({'heygen_join_paragraphs': 'yes'})

    def test_long_sentences_and_cut_parts_keep_their_own_request(self):
        long = ' '.join(['Word number %d is here.' % i for i in range(3)])
        wide = ' '.join(('A' + 'b' * 1190 + ' end %d.' % i) for i in range(3))
        self.assertEqual([u['sentences'] for u in narration.units(long, 3)], [3])
        self.assertEqual([u['sentences'] for u in narration.units(wide, 3)], [1, 1, 1])   # 1800 characters together
        cut = narration.units('Short one here. ' + 'x' * 2000 + '.', 3)
        self.assertEqual([u['sentences'] for u in cut], [1, 0, 0])


class SettingTest(unittest.TestCase):
    def test_turbo_free_reads_three_by_default_and_paid_models_one(self):
        free = lab.validated({'provider': 'heygen', 'heygen_model': 'heygen-voice-1-turbo-free'})
        paid = lab.validated({'provider': 'heygen', 'heygen_model': 'heygen-voice-1-turbo'})
        self.assertEqual(free['heygen_sentences'], 0)
        self.assertEqual(lab.sentences_per_request(free), 3)
        self.assertEqual(lab.sentences_per_request(paid), 1)
        self.assertEqual(lab.sentences_per_request({**paid, 'heygen_sentences': 4}), 4)
        self.assertEqual(lab.sentences_per_request({**free, 'heygen_sentences': 1}), 1)
        self.assertEqual(lab.sentences_per_request({**free, 'heygen_model': 'starfish', 'heygen_sentences': 5}), 1)
        self.assertEqual(lab.sentences_per_request(lab.validated({'provider': 'elevenlabs', 'heygen_sentences': 5})), 1)

    def test_the_setting_is_one_to_five(self):
        self.assertEqual(lab.validated({'heygen_sentences': 5})['heygen_sentences'], 5)
        self.assertEqual(lab.validated({'heygen_sentences': 10})['heygen_sentences'], 10)
        for wrong in (11, -1, 2.5, '3', True):
            with self.subTest(wrong=wrong), self.assertRaises(store.StudioError):
                lab.validated({'heygen_sentences': wrong})

    def test_the_cache_key_does_not_follow_the_setting(self):
        settings = lab.validated({'provider': 'heygen', 'heygen_voice_id': 'v', 'text': 'Some text to read.'})
        self.assertEqual(lab.fingerprint(settings, {'sha256': 'x'}), lab.fingerprint({**settings, 'heygen_sentences': 4}, {'sha256': 'x'}))


class SpecTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / 'narration'
        self.folder.mkdir()
        self.settings = lab.validated({'provider': 'heygen', 'heygen_voice_id': 'voice', 'heygen_model': 'heygen-voice-1-turbo-free'})
        for item in (patch.object(narration, 'root', return_value=self.folder),
                     patch.object(lab, 'snapshot', return_value={'settings': self.settings, 'reference': None}),
                     patch.object(lab, 'effective_reference', return_value={'sha256': 'ref'}),
                     patch.object(lab, 'original_path', side_effect=lambda params, ref: self.folder / 'raw' / (lab.fingerprint(params, ref) + '.mp3'))):
            item.start()
            self.addCleanup(item.stop)

    def test_a_turbo_free_narration_sends_a_request_a_group(self):
        _, _, entries, quote = narration.spec({'id': 'a' * 24, 'channel_id': 'c' * 16}, UnitsTest.text)
        self.assertEqual([e['sentences'] for e in entries], [3, 2, 2])
        self.assertEqual(quote['total'], 3)

    def test_sentences_voiced_one_by_one_before_are_not_sent_again(self):
        ref = {'sha256': 'ref'}
        for sentence in ('One went home.', 'Two went out.', 'Three stayed.'):
            (self.folder / (lab.fingerprint({**self.settings, 'text': sentence}, ref) + '.mp3')).write_bytes(b'take')
        _, _, entries, quote = narration.spec({'id': 'a' * 24, 'channel_id': 'c' * 16}, UnitsTest.text)
        self.assertEqual([e['sentences'] for e in entries], [1, 1, 1, 2, 2])
        self.assertTrue(all(e['cached'] for e in entries[:3]))
        self.assertEqual(quote['cached'], 3)


    def test_takes_of_another_grouping_are_used_again_when_paragraphs_are_joined_mid_narration(self):
        # 18 November 2026: Jupiter was voiced by paragraph, the paragraphs were then joined and «Продовжити» started over
        ref = {'sha256': 'ref'}
        first = narration.units(UnitsTest.text, 10)[0]   # the first paragraph, voiced already
        (self.folder / (lab.fingerprint({**self.settings, 'text': first['text']}, ref) + '.mp3')).write_bytes(b'take')
        joined = {**self.settings, 'heygen_sentences': 10, 'heygen_join_paragraphs': True}
        with patch.object(lab, 'snapshot', return_value={'settings': joined, 'reference': None}):
            _, _, entries, quote = narration.spec({'id': 'a' * 24, 'channel_id': 'c' * 16}, UnitsTest.text)
        self.assertEqual([e['sentences'] for e in entries], [5, 2])
        self.assertTrue(entries[0]['cached'])
        self.assertEqual(quote['cached'], 1)
        self.assertEqual(' '.join(e['text'] for e in entries), ' '.join(narration.phrases(UnitsTest.text)))


if __name__ == '__main__':
    unittest.main()
