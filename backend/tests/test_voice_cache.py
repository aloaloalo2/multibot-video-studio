import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import voice_cache
import store
import languages


class VoiceCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name)
        self.identity={'provider':'elevenlabs','language':'pl','engine':'v4','reference':'abc','settings':{'stability':.5}}

    def test_legacy_exact_words_are_available_but_another_voice_is_not(self):
        parts=self.work/'parts';parts.mkdir()
        (parts/'00000.mp3').write_bytes(b'paid audio'*200)
        store.atomic_json(parts/'request.json',{'provider':'elevenlabs','voice_key':'original','translations':['Pierwsza.']})
        self.assertEqual(voice_cache.candidates(self.work,self.identity,{'original'}),{'Pierwsza.':parts/'00000.mp3'})
        self.assertEqual(voice_cache.candidates(self.work,self.identity,{'new-voice'}),{})

    def test_uncertain_request_is_not_promoted_as_a_complete_take(self):
        parts=self.work/'parts';parts.mkdir()
        (parts/'00000.mp3').write_bytes(b'incomplete audio'*200)
        store.atomic_json(parts/'request.json',{'provider':'elevenlabs','identity':self.identity,'translations':['Pierwsza.']})
        store.atomic_json(parts/'requests.json',[{'text':'Pierwsza.','file':'00000.mp3','kind':'original','status':'uncertain'}])
        self.assertEqual(voice_cache.candidates(self.work,self.identity,set()),{})

    def test_validated_take_survives_archival_and_rejects_tampering(self):
        source=self.work/'raw.mp3';source.write_bytes(b'paid audio'*200)
        with patch.object(store,'media_duration',return_value=1.5):
            cached=voice_cache.remember(self.work,self.identity,'Pierwsza.',source)
        source.unlink()
        self.assertEqual(voice_cache.candidates(self.work,self.identity,set()),{'Pierwsza.':cached})
        cached.write_bytes(b'different audio'*200)
        self.assertEqual(voice_cache.candidates(self.work,self.identity,set()),{})

    def test_invalid_audio_cannot_be_cached(self):
        source=self.work/'raw.mp3';source.write_bytes(b'bad audio'*200)
        with patch.object(store,'media_duration',return_value=0):
            with self.assertRaises(store.StudioError):voice_cache.remember(self.work,self.identity,'Pierwsza.',source)
        self.assertFalse((self.work/'voice-cache/index.json').exists())

    def test_same_words_in_other_languages_or_models_never_share_audio(self):
        key=voice_cache.take_key(self.identity,'Video.')
        for update in ({'language':'es'},{'engine':'turbo'},{'reference':'different'},{'settings':{'stability':.7}}):
            self.assertNotEqual(voice_cache.take_key({**self.identity,**update},'Video.'),key)

    def test_publishing_retranslation_reuses_unchanged_takes_and_prices_only_changed_words(self):
        original = self.work/'paid.mp3'
        original.write_bytes(b'paid recording'*200)
        with patch.object(store, 'media_duration', return_value=2):
            cached = voice_cache.remember(self.work, self.identity, 'Pierwsza.', original)
        before = cached.read_bytes()
        (self.work/'sample.mp3').write_bytes(b'old assembled sample')
        (self.work/'voice.mp3').write_bytes(b'previous completed voice')
        text = 'Pierwsza.\nNowe zdanie.'
        segments = [{'start': 0, 'end': 2, 'source': 'First.'},
                    {'start': 2, 'end': 4, 'source': 'New sentence.'}]
        with patch.object(languages, 'work_dir', return_value=self.work), \
             patch.object(languages, 'ask', return_value=('Nowy tytuł', 0)), \
             patch.object(languages, 'progress'), patch.object(languages, 'update'), \
             patch.object(languages, 'copy_out'), patch.object(languages.language_quality, 'require'), \
             patch.object(languages, 'provider_engine', return_value='eleven_v4_turbo'), \
             patch.object(languages, 'voice_cache_context', return_value=(self.identity, set())), \
             patch.object(languages, 'fixed_price', return_value=lambda value: len(value)*.26), \
             patch.object(languages, 'speak') as speak:
            languages.save_translation('p', 'pl', {'id':'p'},
                {'script':'First.\nNew sentence.', 'language':'en', 'title':'Title'}, text, 0, {}, segments)
            estimate = languages.voice_estimate('p', 'pl', 'elevenlabs', text)
        self.assertEqual((estimate['reused'], estimate['generate']), (1, 1))
        self.assertEqual(estimate['characters'], len('Nowe zdanie.'))
        self.assertEqual(estimate['base'], round(len('Nowe zdanie.')*.26, 2))
        self.assertEqual(cached.read_bytes(), before)
        self.assertEqual((self.work/'voice.mp3').read_bytes(), b'previous completed voice')
        speak.assert_not_called()
