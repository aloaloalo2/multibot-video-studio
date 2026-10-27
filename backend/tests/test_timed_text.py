import copy
import importlib.util
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store

spec = importlib.util.spec_from_file_location('studio_engine_text', Path(__file__).resolve().parents[2] / 'engine' / 'render.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class TimedTextTest(unittest.TestCase):
    def test_audio_source_offset_is_preserved_and_clamped(self):
        project=dict(tracks=[dict(id='a',type='universal',clips=[])],duration=0,settings={})
        asset=dict(id='voice',name='fixture.wav',kind='audio',path='/tmp/fixture.wav')
        with patch.object(store,'resolve_asset',return_value=asset),patch.object(store,'media_duration',return_value=10):
            store.apply_universal_action(project,'add_clip',dict(layer_id='a',kind='audio',asset_id='voice',start=0,duration=5,trim_start=7))
        clip=project['tracks'][0]['clips'][0]
        self.assertEqual((clip['trim_start'],clip['duration']),(7,3))

    def words(self):
        return [dict(text='2', start=.4, x=.3, y=.5, width=.1, height=.2),
                dict(text='grams', start=.8, x=.6, y=.5, width=.25, height=.2)]

    def test_validation_preserves_actual_boundaries_and_rejects_stale_text(self):
        words = self.words()
        self.assertEqual(store.validated_text_layout(words, '2 grams', 2), words)
        for changed in ([{**words[0], 'start': 3}], words[::-1]):
            with self.assertRaises(store.StudioError):
                store.validated_text_layout(changed, '2 grams', 2)
        with self.assertRaises(store.StudioError):
            store.validated_text_layout(words, '3 grams', 2)

    def test_text_edit_clears_old_reveal_layout(self):
        project = dict(tracks=[dict(id='a', type='universal', clips=[])], duration=0, settings={})
        store.apply_universal_action(project, 'add_clip', dict(layer_id='a',kind='text', text='2 grams',start=0,duration=2,font_size=72,text_words=self.words()))
        clip = project['tracks'][0]['clips'][0]
        self.assertEqual(clip['text_words'], self.words())
        store.apply_universal_action(project, 'update_clip', dict(clip_id=clip['id'],patch={'text':'New words'}))
        self.assertNotIn('text_words', clip)

    def test_renderer_reveals_each_word_at_native_time_and_keeps_positions(self):
        clip = dict(type='text',start=0,duration=2,x=.5,y=.5,width=1,height=1,text='2 grams',font_size=72,text_words=self.words())
        scene = engine.timeline_scene(0,2,[clip],Path('/tmp'),1920,1080,'#201810')
        self.assertEqual([l['start'] for l in scene['layers']], [.4,.8])
        self.assertEqual([l['text'] for l in scene['layers']], ['2','grams'])
        later = engine.timeline_scene(1,2,[clip],Path('/tmp'),1920,1080,'#201810')
        self.assertEqual([l['start'] for l in later['layers']], [0,0])
        self.assertEqual([l['x'] for l in later['layers']], [.3,.6])

if __name__ == '__main__': unittest.main()
