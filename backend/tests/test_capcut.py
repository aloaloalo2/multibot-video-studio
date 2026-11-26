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
        # its hit on the seam: it starts that far before it
        self.assertEqual((round(cover['start'], 3), cover['duration'], cover['capcut_type']), (round(4 - joins.lead_seconds(p, p['join_transitions'][0]), 3), joins.MAX_TRANSITION, 'capcut_t06'))
        self.assertEqual((cover['capcut_a_drop'], cover['capcut_b_drop'], cover['capcut_exclude']), (['B'], ['A'], ['P']))
        cover_z = next(l['z'] for l in layers if cover in l['clips'])
        self.assertTrue(1 < cover_z < 2)
        a = next(c for l in layers for c in l['clips'] if c['id'] == 'A')
        self.assertAlmostEqual(a['duration'], cover['start'] + cover['duration'])   # on under the rest of it
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
        for bad in ({'allowed': ['nope']}, {'allowed': ['cut']}, 'x'):
            with self.assertRaises(store.StudioError):
                store.validate_settings({'transitions': bad})
        self.assertIsNone(base)
        # the share left the settings: the studio decides itself where a seam takes a transition (25 November 2026)
        self.assertEqual(store.validate_settings({'weights': {'stock_photo': 100}, 'transitions': {'allowed': ['crossfade'], 'share': .4}})['transitions'],
                         {'allowed': ['crossfade']})


if __name__ == '__main__':
    unittest.main()


class CapcutCodeSideTest(unittest.TestCase):
    """A seam into a Razgon code block shows the live picture in the editor (25 November 2026)."""

    def test_a_code_block_side_is_detected(self):
        import app
        project = {"scene_groups": [{"id": "a", "clip_ids": ["p"]}, {"id": "b", "clip_ids": ["r"]}, {"id": "c", "clip_ids": ["q"]}],
                   "tracks": [{"clips": [{"id": "p", "kind": "image", "title": "Кадр 1"},
                                         {"id": "r", "kind": "animation", "title": "Razgon · кадр 002"},
                                         {"id": "q", "kind": "image", "title": "Кадр 3"}]}]}
        self.assertTrue(app.capcut_touches_code(project, {"from_ref": "group:a", "to_ref": "group:b"}))
        self.assertFalse(app.capcut_touches_code(project, {"from_ref": "group:a", "to_ref": "group:c"}))



class RazgonWindowTest(unittest.TestCase):
    """The Razgon side drawn for a CapCut preview covers every frame the transition draws (25 November 2026: the
    window ended at round(160.5) = 160 while CapCut drew frame 160 too, a black last frame after the transition)."""

    def test_window_covers_the_transitions_last_frame(self):
        import tempfile
        from unittest import mock
        import app
        import joins as joins_module
        frame_index = lambda seconds, fps: int(seconds * fps + .5 + 1e-8)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            razgon = root / "home" / "projects" / "film"
            razgon.mkdir(parents=True)
            project = {"id": "x", "fps": 25,
                       "scene_groups": [{"id": "a", "clip_ids": ["p"]}, {"id": "b", "clip_ids": ["r"]}],
                       "tracks": [{"clips": [{"id": "p", "kind": "image", "title": "K001", "start": 0, "duration": 5.16},
                                             {"id": "r", "kind": "animation", "title": "Razgon · кадр 002", "start": 5.16, "duration": 17.28}]}]}
            join = {"from_ref": "group:a", "to_ref": "group:b", "seam": 5.16, "duration": 1.5, "lead": .24}
            manifest = {"fps": 25, "width": 1920, "timeline_layers": [{"clips": [{"id": "r", "start": 5.16, "duration": 17.28}]}]}
            calls = []

            def run(command, **kwargs):
                calls.append(command)
                Path(command[command.index("--out") + 1]).write_bytes(b"")

            with mock.patch.object(app.store, "razgon_link", return_value={"project": str(razgon)}), \
                    mock.patch.object(app.store, "cache_dir", return_value=root / "cache"), \
                    mock.patch.object(app.subprocess, "run", side_effect=run):
                app.razgon_windows(project, join, manifest, 1280)
            begin, end = joins_module.window(join)
            command = calls[0]
            first, last = float(command[command.index("--from") + 1]), float(command[command.index("--to") + 1])
            self.assertLessEqual(first * 25, frame_index(begin, 25) + 1e-6)
            self.assertGreaterEqual(last * 25, frame_index(end, 25) + 1 - 1e-6)   # frames up to index(end) - 1 drawn, with a spare
            clip = manifest["timeline_layers"][0]["clips"][0]
            self.assertAlmostEqual(clip["start"], first)
            self.assertAlmostEqual(clip["start"] + clip["duration"], last)


class CapcutReadyFilmTest(unittest.TestCase):
    """Drawn seams are handed to the editor with their films, so it plays them at once, also after a restart; a seam
    whose frames changed since is not (user, 26 November 2026: «переходи в прев'ю… моментально»)."""

    def test_ready_films_survive_a_restart_and_follow_their_frames(self):
        import tempfile
        from unittest.mock import patch
        import app
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'capcut-cache').mkdir()
            film = root / 'capcut-cache' / ('transition-direct-capcut-' + 'a' * 24 + '.mp4')
            film.write_bytes(b'x')
            p = project()
            joins.set_transition(p, dict(from_ref='group:g1', to_ref='group:g2', type='capcut_t06', duration=1.0))
            join = p['join_transitions'][0]
            url = '/api/capcut/media/' + film.name
            with patch.object(store, 'DATA_ROOT', root), patch.object(store, 'project_dir', lambda pid: root / pid), \
                 patch.dict(app.CAPCUT_READY, {}, clear=True), patch.dict(app.CAPCUT_URLS, {}, clear=True):
                app.capcut_mark_ready('x', join, url, p)
                ready = app.capcut_ready(p)
                self.assertEqual(app.capcut_ready_urls(p, ready), {join['id']: url})
                app.CAPCUT_READY.clear(); app.CAPCUT_URLS.clear()   # a restart: only the saved list is left
                ready = app.capcut_ready(p)
                self.assertEqual(app.capcut_ready_urls(p, ready), {join['id']: url})
                p['tracks'][1]['clips'][0]['keyframes'] = [{'time': 0, 'scale': 1.1}]   # the frame after the seam moves now
                self.assertEqual(app.capcut_ready_urls(p, app.capcut_ready(p)), {})
                film.unlink()
                app.CAPCUT_READY.clear(); app.CAPCUT_URLS.clear()
                self.assertEqual(app.capcut_ready(p), [])   # its film gone, the seam is drawn again
