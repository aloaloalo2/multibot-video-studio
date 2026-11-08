"""Camera motion is a directorial choice; placement never invents a trajectory."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import director
import production
import montage_ops
import store


class MotionDirectionTest(unittest.TestCase):
    def place(self, number=1, aspect=16/9, kind='image', **spec):
        ctx=SimpleNamespace(W=1920.,H=1080.,easing='ease_in_out',frames=[],groups={},actions=[],report=[],
            project={'fps':25,'assets':[{'id':'a','kind':kind,'path':'/unused.png'}],'tracks':[{'id':'layer'}]},
            plan={'frames':[{'number':number,'start':2.0,'end':8.0,'format':'host' if kind=='video' else 'generated_photo'}]})
        with patch.object(montage_ops,'_aspect',return_value=aspect), patch.object(store,'media_duration',return_value=30):
            montage_ops.place(ctx,{'frame':number,'asset_id':'a',**spec})
        return [row['payload'] for row in ctx.actions]

    def test_default_stays_still_for_every_frame_number_and_aspect(self):
        for number in range(1,9):
            for aspect in (16/9,.75,2.):
                with self.subTest(number=number,aspect=aspect):
                    for layer in self.place(number,aspect):
                        self.assertFalse(layer.get('keyframes'))

    def test_host_video_has_no_automatic_camera_move(self):
        for layer in self.place(kind='video'):
            self.assertFalse(layer.get('keyframes'))

    def test_director_can_choose_explicit_motion_and_background_stays_still(self):
        layers=self.place(aspect=.75,motion='zoom_out')
        self.assertFalse(layers[0].get('keyframes'))
        self.assertGreater(layers[-1]['keyframes'][0]['scale'],layers[-1]['keyframes'][-1]['scale'])
        for motion in ('pan_left','pan_right'):
            layer=self.place(motion=motion)[-1]
            first,last=layer['keyframes']
            self.assertEqual(first['time'],0)
            self.assertEqual(last['time'],6)
            self.assertEqual(first['x']>last['x'],motion=='pan_left')

    def test_unknown_motion_fails_instead_of_silently_zooming(self):
        with self.assertRaises(montage_ops.OpError):self.place(motion='typo')

    def test_planner_and_both_frame_agents_receive_composition_and_readability_rules(self):
        project={'id':'a'*24,'name':'Directed composition','episode_path':'/tmp/Channel/Episode','channel_id':'c'*16}
        request={'frames':2,'total_frames':2,'start':0.,'end':12.}
        with patch.object(store,'project_dir',return_value=Path('/tmp/episode-draft')), \
             patch.object(director,'channel_settings',return_value={}), \
             patch.object(production,'people_rules',return_value={'rule':'','stock':'','check':''}), \
             patch.object(production,'accents_step',return_value=''), \
             patch.object(production,'mixed_assets_step',return_value=''), \
             patch.object(production.channel_branding,'reserved_zone',return_value='none'):
            briefs=[director.frames_brief(project),director.razgon_brief(project),production.photo_brief(project,request),production.brief(project,request)]
        for brief in briefs:
            with self.subTest(brief=brief[:50]):
                self.assertIn('Постановка руху є відповідальністю режисера',brief)
                self.assertIn('Номер кадру або формат не визначає траєкторію',brief)
                self.assertIn('видимими й читабельними',brief)
        for brief in briefs[2:]:
            self.assertIn('оглянь реальний матеріал',brief)
            self.assertIn('не додавай навіть малий зум лише заради руху',brief)
            self.assertNotIn('до 4%',brief)


if __name__=='__main__':unittest.main()
