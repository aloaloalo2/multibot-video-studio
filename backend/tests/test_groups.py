import copy
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
import waveforms
import display_text

class GroupTest(unittest.TestCase):
    def test_layer_mute_preserves_clip_volume_and_other_tracks(self):
        p=self.project();voice=p['tracks'][-1]['clips'][0];voice['volume']=.72
        store.apply_universal_action(p,'set_layer_mute',dict(layer_id='voice',muted=True))
        self.assertTrue(p['tracks'][-1]['muted']);self.assertEqual(voice['volume'],.72)
        store.apply_universal_action(p,'set_layer_mute',dict(layer_id='voice',muted=False))
        self.assertFalse(p['tracks'][-1]['muted']);self.assertEqual(voice['volume'],.72)
        with self.assertRaises(store.StudioError):store.apply_universal_action(p,'set_layer_mute',dict(layer_id='a',muted=True))
    def test_project_font_applies_to_existing_and_new_text(self):
        p=self.project();store.apply_universal_action(p,'set_project_font',dict(font_family='Golos'))
        self.assertEqual(p['tracks'][0]['clips'][0]['font_family'],'Golos')
        store.apply_universal_action(p,'add_clip',dict(layer_id='a',kind='text',text='New',duration=1,font_family='Literata'))
        self.assertEqual(p['tracks'][-1]['clips'][0]['font_family'],'Golos')
        store.apply_universal_action(p,'set_project_font',dict(font_family='Manrope'))
        self.assertEqual(p['font_family'],'Manrope')
        self.assertEqual(p['tracks'][0]['clips'][0]['font_family'],'Manrope')
        self.assertEqual(p['tracks'][-1]['clips'][0]['font_family'],'Manrope')
    def test_font_change_reflows_words_without_changing_speech_times(self):
        p=self.project();clip=p['tracks'][0]['clips'][0]
        clip.update(font_size=76,text_role='full_frame',text='Первое второе третье',text_words=[dict(text=text,start=i*.4,end=i*.4+.3,x=.3+i*.17,y=.5,width=.15,height=.1) for i,text in enumerate(['Первое','второе','третье'])])
        before=[(w['text'],w['start'],w['end']) for w in clip['text_words']]
        store.apply_universal_action(p,'set_project_font',dict(font_family='Literata'))
        self.assertEqual(before,[(w['text'],w['start'],w['end']) for w in clip['text_words']])
        for first,second in zip(clip['text_words'],clip['text_words'][1:]):
            if first['y']==second['y']:self.assertLess(first['x']+first['width']/2,second['x']-second['width']/2)
    def test_stack_rows_move_whole_compositions_without_retiming(self):
        p=self.project();store.apply_universal_action(p,'group_clips',dict(clip_ids=['a','b'],title='Frame'))
        before={c['id']:(c['start'],c['duration']) for t in p['tracks'] for c in t['clips']}
        store.apply_universal_action(p,'reorder_stack',dict(source='scenes',target='layer:voice',above=True))
        self.assertEqual([t['id'] for t in p['tracks']],['voice','a','b'])
        self.assertEqual(before,{c['id']:(c['start'],c['duration']) for t in p['tracks'] for c in t['clips']})
        store.apply_universal_action(p,'reorder_stack',dict(source='scenes',target='layer:voice',above=False))
        self.assertEqual([t['id'] for t in p['tracks']],['a','b','voice'])
    def test_terminal_display_punctuation_is_assembly_only(self):
        self.assertEqual(display_text.clean('Hello, world!'),'Hello, world')
        self.assertEqual(display_text.clean('A?'),'A?')
        self.assertEqual(display_text.clean('"Hello!".'),'"Hello"')
        words=[dict(text='Hello,',start=0),dict(text='world!',start=1)]
        self.assertEqual(display_text.clean_words(words)[-1],dict(text='world',start=1))
        self.assertEqual(words[-1]['text'],'world!')
    def project(self):
        return dict(duration=10,tracks=[dict(id='a',type='universal',clips=[dict(id='a',kind='text',text='A',start=1,duration=4)]),dict(id='b',type='universal',clips=[dict(id='b',kind='animation',start=2,duration=3)]),dict(id='voice',type='universal',clips=[dict(id='voice',kind='audio',start=0,duration=10)])])
    def test_grouping_keeps_native_clips_and_moves_them_together(self):
        p=self.project();store.recompute_universal_duration(p);before=copy.deepcopy(p['tracks'])
        store.apply_universal_action(p,'group_clips',dict(clip_ids=['a','b'],title='Frame'))
        self.assertEqual(p['tracks'],before)
        group=p['scene_groups'][0]
        with self.assertRaises(store.StudioError):store.apply_universal_action(p,'group_clips',dict(clip_ids=['a'],title='Duplicate'))
        store.apply_universal_action(p,'move_group',dict(group_id=group['id'],start=3))
        self.assertEqual([t['clips'][0]['start'] for t in p['tracks']],[3,4,0])
        self.assertEqual([t['clips'][0]['duration'] for t in p['tracks']],[4,3,10])
        store.apply_universal_action(p,'ungroup_clips',dict(group_id=group['id']))
        self.assertFalse(p['scene_groups'])
    def test_delete_and_reconcile_members_do_not_touch_other_tracks(self):
        p=self.project();store.apply_universal_action(p,'group_clips',dict(clip_ids=['a','b'],title='Frame'))
        group=p['scene_groups'][0]
        store.apply_universal_action(p,'delete_group',dict(group_id=group['id']))
        self.assertEqual([c['id'] for t in p['tracks'] for c in t['clips']],['voice'])
        self.assertFalse(p['scene_groups'])
    def test_waveform_uses_real_amplitude_and_invalidates_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'voice.wav'
            def write(amplitude):
                with wave.open(str(source),'wb') as out:
                    out.setparams((1,2,8000,0,'NONE','not compressed'))
                    out.writeframes(b''.join(struct.pack('<h',int((amplitude if i<4000 else 16000)*math.sin(i*.1))) for i in range(8000)))
            write(1000);peaks=waveforms.read_peaks(source,root/'cache',8)
            self.assertEqual(peaks['duration'],1)
            self.assertLess(peaks['peaks'][0][1],.04);self.assertGreater(peaks['peaks'][-1][1],.45)
            self.assertEqual(peaks,waveforms.read_peaks(source,root/'cache',8))
            write(8000);changed=waveforms.read_peaks(source,root/'cache',8)
            self.assertGreater(changed['peaks'][0][1],.2)

if __name__=='__main__':unittest.main()
