import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import job_timing
import performance_summary as summary
import project_costs
import store


class PerformanceSummaryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / ('a' * 24)
        self.root.mkdir()
        self.patch = patch.object(store, 'DATA_ROOT', Path(temporary.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def save(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return path

    def run_row(self, workflow, elapsed, **extra):
        return {'workflow': workflow, 'elapsed_ms': elapsed, 'stages': {}, 'status': 'complete', **extra}

    def test_only_main_processes_are_grouped_sorted_and_timed_without_waiting(self):
        rows = [self.run_row('script', 12000, stages={'queue': {'ms': 4000}}),
                self.run_row('script', 9000, status='stopped', stages={'pause': {'ms': 5000}}),
                self.run_row('production', 30000, status='running', stages={'queue': {'ms': 5000}}),
                self.run_row('thumbnail', 3600000, status='running'),
                self.run_row('language_thumbnail', 100000), self.run_row('metadata', 1000),
                self.run_row('language_voice', 8000), self.run_row('language_sample', 2000),
                self.run_row('analysis', 2000)]
        result = summary.project(rows, self.root)
        self.assertEqual([(r['workflow'], r['active_ms']) for r in result['processes']],
                         [('script', 12000), ('analysis', 2000), ('production', 25000), ('language_voice', 10000)])
        self.assertEqual(result['total_ms'], 49000)
        self.assertTrue(result['running'])
        self.assertFalse(summary.project([self.run_row('thumbnail', 20000, status='running')], self.root)['running'])

    def test_failed_and_interrupted_attempts_are_kept_apart_from_useful_time(self):
        rows = [self.run_row('script', 900000, status='interrupted'), self.run_row('script', 675000),
                self.run_row('production', 33000, status='failed')]
        result = summary.project(rows, self.root)
        script, production = result['processes']
        self.assertEqual((script['active_ms'], script['lost_ms'], script['lost_runs']), (675000, 900000, 1))
        self.assertEqual((production['active_ms'], production['lost_ms']), (0, 33000))
        self.assertEqual((result['total_ms'], result['lost_ms']), (675000, 933000))

    def test_stopping_and_resuming_never_adds_the_wall_clock_gap(self):
        rows = [self.run_row('production', 5000, status='stopped', started_at=100, finished_at=105),
                self.run_row('production', 7000, started_at=100000, finished_at=100007)]
        self.assertEqual(summary.project(rows, self.root)['processes'][0]['active_ms'], 12000)
        self.assertEqual(summary.active_ms(self.run_row('script', 2000, stages={'queue': {'ms': 9000}})), 0)

    def test_saved_costs_keep_steps_separate_and_exclude_all_thumbnail_costs(self):
        events = {'claude_code:openings-one': {'provider': 'claude_code', 'amount': 7, 'category': 'script'},
                  'claude_code:script-one': {'provider': 'claude_code', 'amount': 35, 'category': 'script'},
                  'openrouter:one': {'provider': 'openrouter', 'amount': .02, 'category': 'script_editing'},
                  'openrouter:thumb': {'provider': 'openrouter', 'amount': 9, 'category': 'thumbnail'},
                  'heygen:narration-one': {'provider': 'heygen', 'amount': 0, 'category': 'narration'},
                  'elevenlabs:voice': {'provider': 'elevenlabs', 'amount': 100, 'category': 'voice'}}
        index = self.save('project-costs.json', {'events': events})
        (store.DATA_ROOT / 'eleven-credit-usd.json').write_text(json.dumps({'credit_usd_rate': .001}))
        original = index.read_bytes()
        result = summary.saved_costs(self.root)
        self.assertEqual(result['openings']['providers']['claude_code']['usd'], 7)
        self.assertEqual(result['script']['providers']['claude_code']['usd'], 35)
        self.assertEqual(result['script']['providers']['openrouter']['usd'], .02)
        self.assertEqual(result['language_voice']['providers']['elevenlabs']['usd'], .12)
        self.assertEqual(result['narration']['providers']['heygen']['usd'], 0)
        self.assertTrue(result['narration']['recorded'])
        self.assertEqual(index.read_bytes(), original)

    def test_latest_spend_snapshot_is_used_once_without_reading_or_creating_a_log(self):
        log = str(self.root / 'production-one.jsonl')
        report = {'log': log, 'kind': 'production', 'log_modified': 10, 'cost_usd': 5, 'tokens': {'input': 100, 'output': 200}}
        self.save('spend/older.json', report)
        self.save('spend/newer.json', {**report, 'log_modified': 20, 'cost_usd': 7, 'tokens': {'input': 300, 'output': 400}})
        self.save('project-costs.json', {'events': {'claude_code:production-one.jsonl': {'provider': 'claude_code', 'amount': 5, 'category': 'production', 'modified': 10}}})
        original = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = summary.saved_costs(self.root)['production']
        self.assertEqual(result['providers']['claude_code']['usd'], 7)
        self.assertEqual(result['providers']['claude_code']['requests'], 1)
        self.assertEqual(result['tokens'], {'input': 300, 'output': 400})
        self.assertFalse(Path(log).exists())
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, original)

    def test_unknown_paid_costs_never_become_free(self):
        self.save('project-costs.json', {'events': {'openrouter:x': {'provider': 'openrouter', 'amount': None, 'category': 'script'}}})
        result = summary.saved_costs(self.root)
        self.assertEqual(result['script']['providers']['openrouter']['unknown'], 1)
        self.assertFalse(result['planning']['recorded'])
        self.assertTrue(result['analysis']['recorded'])
        self.assertTrue(result['export']['recorded'])

    def test_billing_scope_survives_receipt_refresh(self):
        trace = SimpleNamespace(project_id=self.root.name, workflow='openings', id='b' * 32, language=None)
        token = job_timing.CURRENT.set(trace)
        try:
            project_costs.record_at(self.root, 'claude_code', 1, identity='opening', category='script')
        finally:
            job_timing.CURRENT.reset(token)
        data = store.read_json(self.root / 'project-costs.json')
        event = data['events']['claude_code:opening']
        self.assertEqual(event['workflow'], 'openings')
        trace.workflow = 'production'
        token = job_timing.CURRENT.set(trace)
        try:
            project_costs.record_at(self.root, 'claude_code', 2, identity='opening', category='production')
        finally:
            job_timing.CURRENT.reset(token)
        data = store.read_json(self.root / 'project-costs.json')
        self.assertEqual(data['events']['claude_code:opening']['workflow'], 'openings')
        self.save('spend/scope.json', {'log': 'opening', 'log_modified': 1, 'cost_usd': 2, 'cost_measured': True})
        updated = project_costs.collect(self.root, data)
        self.assertEqual(updated['events']['claude_code:opening']['workflow'], 'openings')

    def test_invalid_small_records_do_not_remove_the_remaining_costs(self):
        self.save('project-costs.json', {'events': []})
        self.save('spend/invalid.json', {'log': 42})
        self.assertFalse(summary.saved_costs(self.root)['script']['recorded'])


if __name__ == '__main__':
    unittest.main()
