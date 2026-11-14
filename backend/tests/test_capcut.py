"""CapCut transitions and effects: seams, effect rows, channel settings, the manifest clips."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joins
import store


def clip(i, start, dur):
    return dict(id=i, kind='image', asset_id=None, start=start, duration=dur, title=i, x=.5, y=.5, width=1, height=1, scale=1, opacity=1, keyframes=[])


def project():
    return dict(id='x', fps=25, width=1280, height=720,
                tracks=[dict(id='l1', clips=[clip('A', 0, 4)]), dict(id='l2', clips=[clip('B', 4, 3)]), dict(id='lp', clips=[clip('P', 0, 7)])],
                scene_groups=[dict(id='g1', clip_ids=['A'], title='Кадр 1'), dict(id='g2', clip_ids=['B'], title='Кадр 2'),
                              dict(id='gp', role='overlay', clip_ids=['P'])], join_transitions=[])


def layers_of(p):
    return [dict(id=l['id'], z=z, clips=[dict(id=c['id'], type='image', content_type=c.get('content_type'), start=c['start'], duration=c['duration'])
                                          for c in l['clips']]) for z, l in enumerate(p['tracks'])]


class CapcutTest(unittest.TestCase):
    def test_catalog_has_forty_transitions_and_thirteen_effects(self):
        self.assertEqual(len(joins.CAPCUT), 40)
        self.assertEqual(len(store.capcut_effects()), 13)
        self.assertTrue(set(joins.CAPCUT) <= joins.TYPES)

    def test_a_capcut_seam_becomes_one_clip_under_the_plate_that_draws_both_sides(self):
        p = project()
        joins.set_transition(p, dict(from_ref='group:g1', to_ref='group:g2', type='capcut_t06', duration=1.0))
        layers = layers_of(p)
        joins.transport(p, layers)
        cover = next(c for l in layers for c in l['clips'] if c.get('content_type') == 'capcut_transition')
        self.assertEqual((cover['start'], cover['duration'], cover['capcut_type']), (4, 1.0, 'capcut_t06'))
        self.assertEqual((cover['capcut_a_drop'], cover['capcut_b_drop'], cover['capcut_exclude']), (['B'], ['A'], ['P']))
        cover_z = next(l['z'] for l in layers if cover in l['clips'])
        self.assertTrue(1 < cover_z < 2)
        a = next(c for l in layers for c in l['clips'] if c['id'] == 'A')
        self.assertEqual(a['duration'], 5.0)                      # the outgoing picture goes on under the transition
        self.assertNotIn('join_out', a)                           # and takes no dissolve of its own
        self.assertNotIn('join_in', next(c for l in layers for c in l['clips'] if c['id'] == 'B'))

    def test_an_effect_on_a_frame_stands_over_it_and_one_on_the_film_under_the_plate(self):
        p = project()
        self.assertTrue(store.apply_universal_action(p, 'add_capcut_effect', dict(effect='capcut_e02', group_id='g2')))
        self.assertTrue(store.apply_universal_action(p, 'add_capcut_effect', dict(effect='capcut_e12')))
        names = [l.get('name', l['id']) for l in p['tracks']]
        self.assertEqual(names, ['l1', 'l2', 'CapCut · Шум і пил', 'CapCut · Зелений CRT', 'lp'])
        frame, film = p['tracks'][2]['clips'][0], p['tracks'][3]['clips'][0]
        self.assertEqual((frame['start'], frame['duration']), (4.0, 3.0))
        self.assertEqual((film['start'], film['duration']), (0.0, 7.0))
        self.assertIn(frame['id'], p['scene_groups'][1]['clip_ids'])
        with self.assertRaises(store.StudioError):
            store.apply_universal_action(p, 'add_capcut_effect', dict(effect='nope'))

    def test_a_transition_stays_under_the_effect_of_its_frame(self):
        p = project()
        store.apply_universal_action(p, 'add_capcut_effect', dict(effect='capcut_e02', group_id='g2'))
        joins.set_transition(p, dict(from_ref='group:g1', to_ref='group:g2', type='capcut_t01', duration=1.0))
        layers = layers_of(p)
        joins.transport(p, layers)
        cover_z = next(l['z'] for l in layers if any(c.get('content_type') == 'capcut_transition' for c in l['clips']))
        self.assertEqual(cover_z, 1.5)

    def test_channel_transitions_setting(self):
        base = store.validate_settings.__wrapped__ if hasattr(store.validate_settings, '__wrapped__') else None
        for bad in ({'allowed': ['nope'], 'share': .5}, {'allowed': ['cut'], 'share': .5}, {'allowed': [], 'share': 2}, 'x'):
            with self.assertRaises(store.StudioError):
                store.validate_settings({'transitions': bad})
        self.assertIsNone(base)


if __name__ == '__main__':
    unittest.main()
