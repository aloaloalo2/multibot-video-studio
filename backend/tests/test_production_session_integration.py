import json
import re
import threading
from pathlib import Path
import unittest
from unittest.mock import patch

import test_production as production_fixtures
import production
import store


class ScopedProductionTest(unittest.TestCase):
    def setUp(self):
        self.fixture=production_fixtures.ProductionTest();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.project=self.fixture.project;self.project['production_request'].update(frames=45,total_frames=45,script_sha256='script')
        self.frames=[{'number':n,'start':n*2,'end':n*2+2,'format':'razgon_2d'} for n in range(1,46)]
        self.made=set();self.lock=threading.Lock()
        for item in (patch.object(store,'load_project_plan',return_value={'frames':self.frames,'script_sha256':'script'}),
                     patch.object(store,'made_frames',side_effect=lambda *args:sorted(self.made)),
                     patch.object(store,'channel_effort',return_value='high'),patch.object(store,'channel_director_model',return_value='claude-fable-5-2'),
                     patch.object(production.frame_progress,'razgon_project',return_value=None),
                     patch.object(production.frame_progress,'drawn',side_effect=lambda _:sorted(self.made)),
                     patch.object(production.production_quality,'check',return_value={'passed':True,'errors':[]}),
                     patch.object(production,'brief',return_value='Create this scoped film.'),
                     patch.object(production,'mixed_assets_step',return_value=''),patch.object(production.director,'sound_brief',return_value=''),
                     patch.object(production.director,'animation_style',return_value=''),patch.object(production.director,'channel_memory',return_value=''),
                     patch.object(production.logo_layer,'place'),patch.object(production.razgon_sound,'start')):
            item.start();self.addCleanup(item.stop)

    def test_worker_verifies_each_scope_before_a_new_fresh_model_session(self):
        scopes=[]
        def author(cli,prompt,log,*args,**kwargs):
            packet=json.loads(Path(re.search(r'Єдина карта роботи: (.+?\.txt)',prompt).group(1)).with_suffix('.json').read_text())   # each session has its own map
            scopes.append(packet['pending_frames']);self.assertLessEqual(len(packet['pending_frames']),20)
            self.assertEqual(packet['mode'],'batch');self.assertEqual(packet['repair_frames'],[])
            self.assertIsNone(kwargs['resume']);self.assertEqual(kwargs['model'],'claude-fable-5-2');self.assertEqual(kwargs['effort'],'high')
            with self.lock:self.made.update(packet['pending_frames'])
            self.project['tracks']=[{'clips':[{'kind':'animation','title':f'Razgon · кадр {n:03d}'} for n in self.made]}]
            return 0,{'result':'Scoped work saved.','total_cost_usd':.01,'session_id':str(len(scopes))}
        with patch.object(production.director,'claude',side_effect=author) as model:
            production.run(self.project['id'],Path('mock-cli'))
        self.assertEqual(sorted(len(scope) for scope in scopes),[5,10,10,10,10]);self.assertEqual(model.call_count,5)
        request=self.project['production_request'];self.assertEqual(request['status'],'done')
        self.assertEqual(request['session_checkpoint']['remaining_frames'],[]);self.assertAlmostEqual(request['cost_usd'],.05)

    def test_pause_during_handoff_preparation_starts_no_paid_session(self):
        def pause(*args,**kwargs):
            self.project['production_request']['paused']=True
            return Path(self.fixture.tmp.name)/'handoff.json','Paused'
        with patch.object(production.production_context,'write',side_effect=pause),patch.object(production.director,'claude') as model:
            production.run(self.project['id'],Path('mock-cli'))
        model.assert_not_called();self.assertTrue(self.project['production_request']['paused'])

    def test_fresh_sessions_share_the_original_whole_job_timeout(self):
        original=production.production_context.write
        with patch.object(production.time,'monotonic',return_value=10) as clock:
            def expire(*args,**kwargs):
                result=original(*args,**kwargs);clock.return_value=10+production.TIMEOUT+1;return result
            with patch.object(production.production_context,'write',side_effect=expire),patch.object(production.director,'claude') as model:
                production.run(self.project['id'],Path('mock-cli'))
        model.assert_not_called();self.assertEqual(self.project['production_request']['status'],'failed')
        self.assertIn('6 годин',self.project['production_request']['error'])


class KitStageTest(ScopedProductionTest):
    """One kit session before the parallel sessions; the shared scene files stay read-only while they run."""
    def test_kit_runs_once_first_and_shared_files_are_locked_during_the_sessions(self):
        import os, stat, tempfile
        film = Path(tempfile.mkdtemp()) / 'film'; (film / 'scenes').mkdir(parents=True); (film / 'story').mkdir()
        (film / 'scenes' / 'cast.js').write_text('// cast\n')
        prompts, locked_seen, stages = [], [], []
        def author(cli, prompt, log, *args, **kwargs):
            prompts.append(prompt)
            if prompt.startswith('Ти готуєш спільний набір'):
                stages.append(self.project['production_request'].get('stage'))   # the card reads «Підготовка» now
                (film / 'story' / 'kit.json').write_text(json.dumps({'ready': True}))
                return 0, {'result': 'Kit ready.', 'total_cost_usd': .02}
            locked_seen.append(not os.stat(film / 'scenes' / 'cast.js').st_mode & stat.S_IWUSR)
            packet = json.loads(Path(re.search(r'Єдина карта роботи: (.+?\.txt)', prompt).group(1)).with_suffix('.json').read_text())
            with self.lock:self.made.update(packet['pending_frames'])
            self.project['tracks'] = [{'clips': [{'kind': 'animation', 'title': f'Razgon · кадр {n:03d}'} for n in self.made]}]
            return 0, {'result': 'Scoped work saved.', 'total_cost_usd': .01}
        with patch('production_kit.razgon', lambda project: film), \
             patch.object(production.director, 'claude', side_effect=author):
            production.run(self.project['id'], Path('mock-cli'))
        self.assertTrue(prompts[0].startswith('Ти готуєш спільний набір'))
        self.assertEqual(sum(p.startswith('Ти готуєш спільний набір') for p in prompts), 1)
        self.assertTrue(locked_seen and all(locked_seen))
        self.assertTrue(os.stat(film / 'scenes' / 'cast.js').st_mode & stat.S_IWUSR)
        request = self.project['production_request']
        self.assertEqual(request['status'], 'done'); self.assertAlmostEqual(request['cost_usd'], .07)
        self.assertEqual(stages, ['kit']); self.assertIsNone(request.get('stage'))


class FinalLookTest(ScopedProductionTest):
    """The pictures are looked at once at the end, at low effort; only the frames it marks are fixed (15 November 2026)."""

    def test_one_low_look_at_the_end_then_only_bug_frames_are_fixed(self):
        looks, fixes, checks = [], [], []
        def author(cli, prompt, log, *args, **kwargs):
            if prompt.startswith('Ти переглядаєш готові кадри'):
                looks.append((kwargs['effort'], re.search(r'Кадри: ([\d, ]+)', prompt).group(1)))
                return 0, {'result': 'ok', 'total_cost_usd': .001}
            packet = json.loads(Path(re.search(r'Єдина карта роботи: (.+?\.txt)', prompt).group(1)).with_suffix('.json').read_text())
            if 'Огляд знайшов вади' in prompt:
                fixes.append(packet['pending_frames'])
            with self.lock:self.made.update(packet['pending_frames'])
            self.project['tracks'] = [{'clips': [{'kind': 'animation', 'title': f'Razgon · кадр {n:03d}'} for n in self.made]}]
            return 0, {'result': 'drawn', 'total_cost_usd': .01}
        def check(project, request):
            frames = request.get('review_frames') or []
            checks.append(len(frames))
            waiting = frames if not looks else []
            return {'passed': not waiting, 'errors': ['Перевірка кадрів Razgon не підтверджена: not reviewed'] if waiting else [],
                    'pending_review': waiting, 'frames': frames}
        bugs = iter([{7: 'рука крізь стіл'}, {}])
        with patch.object(production.director, 'claude', side_effect=author), \
             patch.object(production.production_quality, 'check', side_effect=check), \
             patch.object(production.production_quality, 'bugs', side_effect=lambda *a: next(bugs, {})), \
             patch.object(production.production_quality, 'refresh_stills'):
            production.run(self.project['id'], Path('mock-cli'))
        self.assertEqual([effort for effort, _ in looks], ['low', 'low'])
        self.assertEqual(looks[1][1].strip(), '7')            # the second look sees only the fixed frame
        self.assertEqual(fixes, [[7]])
        self.assertEqual(self.project['production_request']['status'], 'done')
