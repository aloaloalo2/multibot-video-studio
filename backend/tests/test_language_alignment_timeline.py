import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store,languages

class AlignmentTimelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name);self.work.joinpath('parts').mkdir()
        self.voice={'made_at':1000,'text_hash':'accepted'}
        self.phrases=[{'index':0,'start':1,'end':3,'original_start':0,'original_end':4,'text':'Переклад'}]
        stub=patch.object(languages,'work_dir',return_value=self.work);stub.start();self.addCleanup(stub.stop)
        language=patch.object(languages,'original_language',return_value='en');language.start();self.addCleanup(language.stop)

    def test_current_snapshot_wins_over_partial_retry(self):
        store.atomic_json(self.work/'voice-timing.json',{**self.voice,'phrases':self.phrases})
        store.atomic_json(self.work/'parts/manifest.json',[{'index':0,'start':99}])
        self.assertEqual(languages.completed_voice_phrases('p','uk',self.voice),self.phrases)
        self.assertEqual(languages.completed_voice_phrases('p','uk',{**self.voice,'text_hash':'changed'}),[])
        self.assertEqual(languages.completed_voice_phrases('p','uk',{**self.voice,'made_at':1001}),[])

    def test_legacy_timing_must_predate_the_published_audio(self):
        path=self.work/'parts/manifest.json';store.atomic_json(path,self.phrases)
        os.utime(path,(999,999))
        self.assertEqual(languages.completed_voice_phrases('p','uk',self.voice),self.phrases)
        os.utime(path,(1010,1010))
        self.assertEqual(languages.completed_voice_phrases('p','uk',self.voice),[])

    def test_endpoint_preserves_shared_phrase_ids_and_hides_stale_voice(self):
        with patch.object(store,'load_project',return_value={'id':'p'}),patch.object(languages,'source',return_value={'duration':10,'voice':True}),\
             patch.object(languages,'synced_segments',return_value=[{'start':0,'end':4,'source':'Original'}]),\
             patch.object(languages,'load_state',return_value={'languages':{'uk':{'voice':self.voice}}}),\
             patch.object(languages,'final_voice',return_value=True),patch.object(languages,'voice_current',return_value=True) as current,\
             patch.object(languages,'completed_voice_phrases',return_value=self.phrases) as timing:
            data=languages.alignment_timeline('p','uk')
            self.assertEqual(data['status'],'ready');self.assertEqual(data['duration'],10)
            self.assertEqual(data['translated'][0]['shift'],1)
            self.assertEqual(data['original'][0]['index'],data['translated'][0]['index'])
            self.assertTrue(data['alignment']['within_limit'])
            self.assertEqual(data['synchronization']['percent'],73.5)
            self.assertEqual(data['character_comparisons'][0]['source_chars'],8)
            self.assertEqual(data['character_comparisons'][0]['translated_chars'],8)
            current.return_value=False;timing.reset_mock()
            data=languages.alignment_timeline('p','uk')
            self.assertEqual(data['status'],'outdated');self.assertFalse(data['translated_audio'])
            self.assertIsNone(data['synchronization'])
            self.assertEqual(data['character_comparisons'],[])
            timing.assert_not_called()

    def test_polish_phrase_counts_use_number_words_without_changing_saved_text(self):
        original='On October 4, 2021, something like that happened to Facebook.'
        translated='Cztery października dwa tysiące dwudziestego pierwszego roku coś takiego spotkało Facebooka.'
        phrases=[{**self.phrases[0],'text':translated}]
        with patch.object(store,'load_project',return_value={'id':'p'}),patch.object(languages,'source',return_value={'duration':10,'voice':True}),\
             patch.object(languages,'synced_segments',return_value=[{'start':0,'end':4,'source':original}]),\
             patch.object(languages,'load_state',return_value={'languages':{'pl':{'voice':self.voice}}}),\
             patch.object(languages,'final_voice',return_value=True),patch.object(languages,'voice_current',return_value=True),\
             patch.object(languages,'completed_voice_phrases',return_value=phrases),patch.object(languages,'save_state') as save:
            data=languages.alignment_timeline('p','pl')
        report=data['character_comparisons'][0]
        self.assertTrue(report['available'])
        self.assertEqual(report['source_chars'],len(original))
        self.assertEqual(report['translated_chars'],len('4 października 2021 roku coś takiego spotkało Facebooka.'))
        self.assertEqual(report['source_numbers'],2);self.assertEqual(report['translated_numbers'],2)
        self.assertLess(report['difference_percent'],0)
        self.assertEqual(data['translated'][0]['text'],translated)
        self.assertEqual(phrases[0]['text'],translated)
        save.assert_not_called()

if __name__=='__main__':unittest.main()
