import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis_jobs
import status_views as views
import store


class StatusViewsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);views.CACHE.clear()

    def test_compact_report_is_small_and_keeps_readiness_and_order_evidence(self):
        full = {'recognized_text':'speech ' * 30000,'words':[{'text':'speech','start':n} for n in range(5000)],
                'status':'complete','applied':True,'script_sha256':'hash','timing_source':'generated_takes',
                'sequence_verification':{'version':2,'verified':True,'parts':['private path'] * 5000},
                'phrases':[{'number':n,'issues':['text_difference'],'text':'long sentence ' * 100} for n in range(50)]}
        small = views.report(full)
        self.assertTrue(small['applied']);self.assertEqual(small['sequence_verification'],{'version':2,'verified':True})
        self.assertLess(len(json.dumps(small)),2000);self.assertGreater(len(json.dumps(full)),500000)
        self.assertNotIn('recognized_text',small);self.assertEqual(len(small['phrases']),8)

    def test_summary_cache_is_read_only_and_invalidates_after_atomic_replacement(self):
        path = self.root/'report.json';store.atomic_json(path,{'applied':False,'words':['old']})
        with patch.object(store,'read_json',wraps=store.read_json) as read:
            self.assertFalse(views.analysis_report(path)['applied']);views.analysis_report(path)
            self.assertEqual(read.call_count,1)
            store.atomic_json(path,{'applied':True,'words':['new']})
            self.assertTrue(views.analysis_report(path)['applied']);self.assertEqual(read.call_count,2)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['report.json'])

    def test_compact_analysis_retains_owner_validation_without_returning_scripts(self):
        pid='a'*24;folder=self.root/'analysis'/'job';folder.mkdir(parents=True)
        store.atomic_json(self.root/'analysis-state.json',{'job_id':'job'})
        store.atomic_json(folder/'result.json',{'applied':True,'script_sha256':'h','recognized_text':'full text'})
        job={'id':'job','project_id':pid,'type':'speech','status':'complete','script':'private script','progress':100}
        with patch.object(store,'load_project'),patch.object(store,'project_dir',return_value=self.root):
            full=analysis_jobs.latest(pid,lambda _:job)
            small=analysis_jobs.latest(pid,lambda _:job,compact=True)
            self.assertEqual(full['report']['recognized_text'],'full text');self.assertNotIn('script',small['job'])
            self.assertTrue(small['report']['applied']);self.assertTrue(small['compact'])
            with self.assertRaises(store.StudioError):analysis_jobs.latest(pid,lambda _:{**job,'project_id':'another'},compact=True)

    def test_projection_cache_is_bounded(self):
        with patch.object(views,'MAX_CACHE',3):
            for number in range(8):
                path=self.root/f'{number}.json';store.atomic_json(path,{'applied':True});views.analysis_report(path)
        self.assertEqual(len(views.CACHE),3)

    def test_compact_diagnostics_keep_blocking_sentence_numbers_first(self):
        full={'phrases':[{'number':n,'issues':['text_difference']} for n in range(10)]+[{'number':99,'issues':['out_of_order']}]}
        self.assertEqual(views.report(full)['phrases'][0]['number'],99)
