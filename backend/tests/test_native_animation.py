import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import native_animation
import montage_ops
import store


class NativeAnimationTest(unittest.TestCase):
    def context(self):
        return SimpleNamespace(project={'id':'test','fps':25,'assets':[], 'tracks':[{'id':'base','clips':[]}]},
            plan={'frames':[{'number':3,'format':'animation','start':10.03,'end':16.02}]},
            frames=[],groups={},actions=[],report=[])

    def spec(self):
        return {'frame':3,'clips':[{'kind':'animation','content_type':'shape','width':.2,'height':.2,'mask':'circle',
            'keyframes':[{'time':0,'x':.2},{'time':5,'x':.8}]},
            {'kind':'text','text':'Глюкоза','start':1,'duration':4,'font_size':60}]}

    def test_layers_go_to_timeline_without_a_video_process_and_keep_plan_times(self):
        ctx=self.context();spec=self.spec();saved=copy.deepcopy(spec)
        with patch('subprocess.Popen',side_effect=AssertionError('No encoding during creation')):
            native_animation.place(ctx,spec)
        self.assertEqual(spec,saved)
        self.assertEqual(len(ctx.actions),3)
        background,circle,text=[a['payload'] for a in ctx.actions]
        self.assertEqual((background['start'],background['duration']),(10.04,6.0))
        self.assertEqual((background['color'],background['opacity']),('#000000',1))
        self.assertEqual(text['start'],11.04)
        self.assertEqual(circle['keyframes'],spec['clips'][0]['keyframes'])
        self.assertEqual(set(ctx.groups.values()),{'Кадр 3'})
        self.assertFalse(any(a['payload'].get('kind')=='video' for a in ctx.actions))
        plan={'frames':[{'number':3,'format':'animation','start':10.03,'end':16.02}]}
        project={**ctx.project,'tracks':[{'clips':[dict(a['payload'],id=str(i)) for i,a in enumerate(ctx.actions)]}]}
        with patch.object(store,'project_animated',return_value=False):
            self.assertEqual(store.made_frames(project,plan),[3])

    def test_custom_background_sits_above_the_black_base(self):
        ctx=self.context()
        native_animation.place(ctx,{**self.spec(),'background':'#15304a'})
        black,design,_,_=[a['payload'] for a in ctx.actions]
        self.assertEqual((black['color'],design['color']),('#000000','#15304a'))
        self.assertEqual((black['start'],black['duration']),(design['start'],design['duration']))

    def test_repair_reuses_group_and_removes_only_its_old_layers_after_adding_new(self):
        ctx=self.context()
        old={'number':3,'group':{'id':'group-3'},'clips':[{'id':'old-1'},{'id':'old-2'}]}
        ctx.frames=[old,{'number':4,'group':{'id':'group-4'},'clips':[{'id':'untouched'}]}]
        with self.assertRaises(store.StudioError):native_animation.place(ctx,self.spec())
        native_animation.place(ctx,{**self.spec(),'replace':True})
        self.assertTrue(all(a['payload']['group_id']=='group-3' for a in ctx.actions[:3]))
        self.assertEqual([a['payload']['clip_id'] for a in ctx.actions[3:]],['old-1','old-2'])
        self.assertEqual(ctx.groups,{})
        self.assertNotIn('untouched',str(ctx.actions))

    def test_media_files_invalid_timing_and_duplicate_frames_are_rejected(self):
        for part in [{'kind':'video','asset_id':'mp4'}, {'kind':'animation','content_type':'video'},
                     {'kind':'text','text':'x','start':5,'duration':2},
                     {'kind':'animation','content_type':'image','asset_id':'mp4'},
                     {'keyframes':[{'time':7,'x':.2}]}]:
            with self.subTest(part=part),self.assertRaises(store.StudioError):
                native_animation.place(self.context(),{'frame':3,'clips':[part]})
        ctx=self.context();native_animation.place(ctx,self.spec())
        with self.assertRaises(store.StudioError):native_animation.place(ctx,self.spec())

    def test_place_and_replace_cannot_bake_animation_frames_into_mp4(self):
        ctx=self.context()
        with self.assertRaisesRegex(store.StudioError,'op: animation'):
            montage_ops.place(ctx,{'frame':3,'path':'rendered.mp4'})
        ctx.project['tracks'][0]['clips']=[{'id':'old','kind':'video'}]
        ctx.frames=[{'number':3,'plan':{'format':'animation'},'clips':[{'id':'old','kind':'video'}]}]
        with self.assertRaisesRegex(store.StudioError,'op: animation'):
            montage_ops.replace(ctx,{'clip':'old','path':'rendered-again.mp4'})
        self.assertEqual(ctx.actions,[])

class SeamProtectionTest(NativeAnimationTest):
    def test_text_overflow_is_rejected_before_timeline_actions(self):
        bad=[{'kind':'text','text':'Важливо','width':.4,'height':.1,'x':.9},
             {'kind':'text','text':'Довгий підпис у вузькому рядку','width':.12,'height':.02,'font_size':42},
             {'kind':'text','text':'Заголовок','width':.2,'height':.1,'keyframes':[{'time':0,'x':.5},{'time':3,'x':1.}]}]
        for part in bad:
            ctx=self.context()
            with self.subTest(part=part),self.assertRaises(store.StudioError):
                native_animation.place(ctx,{'frame':3,'clips':[part]})
            self.assertEqual(ctx.actions,[])

    def test_hidden_offscreen_entrance_is_allowed_when_readable_pose_fits(self):
        ctx=self.context()
        native_animation.place(ctx,{'frame':3,'clips':[{'kind':'animation','width':.2,'height':.2},
            {'kind':'text','text':'Назва','width':.3,'height':.15,
            'keyframes':[{'time':0,'x':-.2,'opacity':0},{'time':.4,'x':.5,'opacity':1}]}]})
        self.assertEqual(len(ctx.actions),3)

    def test_permanently_translucent_text_cannot_bypass_geometry(self):
        for opacity in (.4, .9):
            ctx=self.context()
            with self.subTest(opacity=opacity), self.assertRaises(store.StudioError):
                native_animation.place(ctx, {'frame':3, 'clips':[{'kind':'text','text':'Label',
                    'x':.99, 'width':.3, 'height':.15, 'opacity':opacity}]})
            self.assertEqual(ctx.actions,[])

    def test_one_frame_tail_is_closed_before_placement(self):
        ctx=self.context();ctx.plan['frames'][0].update(start=54.36,end=62.16)
        native_animation.place(ctx,{'frame':3,'clips':[{'kind':'text','text':'Content','duration':7.76}]})
        self.assertEqual(ctx.actions[1]['payload']['duration'],7.8)
    def test_background_only_frame_is_rejected_without_timeline_mutation(self):
        ctx=self.context()
        with self.assertRaisesRegex(store.StudioError,'тільки фон'):
            native_animation.place(ctx,{'frame':3,'clips':[{'kind':'text','text':'Too short','duration':5.8}]})
        self.assertEqual(ctx.actions,[])
    def test_labels_stay_above_later_chart_shapes(self):
        ctx=self.context()
        native_animation.place(ctx,{'frame':3,'clips':[{'kind':'text','text':'Label'}, {'kind':'animation','title':'Bar'}]})
        self.assertEqual(ctx.actions[-1]['payload']['text'],'Label')


class CameraMoveTest(unittest.TestCase):
    """The whole frame moves together on one word from the agent; the black backing stays (26 November 2026)."""
    def context(self):
        return NativeAnimationTest.context(self)

    def place(self, camera):
        ctx = self.context()
        spec = {'frame': 3, 'camera': camera, 'clips': [
            {'kind': 'animation', 'content_type': 'shape', 'width': 1, 'height': 1},
            {'kind': 'animation', 'content_type': 'shape', 'x': .8, 'y': .3, 'width': .1, 'height': .1,
             'keyframes': [{'time': 0, 'opacity': 0}, {'time': .4, 'opacity': 1}]}]}
        native_animation.place(ctx, spec)
        return ctx, [a['payload'] for a in ctx.actions]

    def at(self, clip, prop, t):
        return montage_ops.keyframe_value(clip, prop, t)

    def test_pan_moves_every_layer_together_and_keeps_the_picture_covering_the_frame(self):
        ctx, (black, picture, marker) = self.place('pan_right')
        self.assertFalse(black.get('keyframes'))
        for t in (0, 3, picture['duration'] - .01):
            s = self.at(picture, 'scale', t)
            self.assertGreaterEqual(s / 2 - abs(self.at(picture, 'x', t) - .5), .5 - 1e-6)   # no edge comes into view
            # the marker keeps its place on the picture: its offset from the picture's centre scales with it
            self.assertAlmostEqual(self.at(marker, 'x', t) - self.at(picture, 'x', t), .3 * s, places=4)
        self.assertGreater(self.at(picture, 'x', 0), self.at(picture, 'x', picture['duration'] - .01))
        self.assertAlmostEqual(self.at(marker, 'opacity', 0), 0)
        self.assertAlmostEqual(self.at(marker, 'opacity', 1), 1)
        self.assertIn('камера pan_right 5%', ' '.join(ctx.report))

    def test_zoom_in_grows_from_the_frame_and_unknown_moves_are_refused(self):
        _, (_, picture, _) = self.place('zoom_in')
        self.assertAlmostEqual(self.at(picture, 'scale', 0), 1)
        self.assertAlmostEqual(self.at(picture, 'scale', picture['duration'] - .01), 1.05, places=2)
        with self.assertRaises(store.StudioError):
            self.place('spin')
        _, (_, plain, _) = self.place(None)
        self.assertFalse(plain.get('keyframes'))
