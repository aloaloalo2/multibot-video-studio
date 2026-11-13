import json
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
        self.made=set()
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
            packet=json.loads((Path(self.fixture.tmp.name)/'production-context.json').read_text())
            scopes.append(packet['pending_frames']);self.assertLessEqual(len(packet['pending_frames']),20)
            self.assertEqual(packet['mode'],'batch');self.assertEqual(packet['repair_frames'],[])
            self.assertIsNone(kwargs['resume']);self.assertEqual(kwargs['model'],'claude-fable-5-2');self.assertEqual(kwargs['effort'],'high')
            self.made.update(packet['pending_frames'])
            self.project['tracks']=[{'clips':[{'kind':'animation','title':f'Razgon · кадр {n:03d}'} for n in self.made]}]
            return 0,{'result':'Scoped work saved.','total_cost_usd':.01,'session_id':str(len(scopes))}
        with patch.object(production.director,'claude',side_effect=author) as model:
            production.run(self.project['id'],Path('mock-cli'))
        self.assertEqual([len(scope) for scope in scopes],[10,10,10,10,5]);self.assertEqual(model.call_count,5)
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
