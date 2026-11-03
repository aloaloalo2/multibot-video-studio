import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import voice_cache
import store


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
