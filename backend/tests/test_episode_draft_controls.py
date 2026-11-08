"""Project-bound writing drafts; all providers are replaced with local fixtures."""
import unittest
from unittest.mock import patch
import test_backend as fixtures
import store
import episode_ideas as ideas


class EpisodeDraftControlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.cid = store.channel_id(fixtures.BackendTest.channel)
        cls.base_url = fixtures.BackendTest.base_url

    @classmethod
    def tearDownClass(cls):
        fixtures.BackendTest.tearDownClass()

    request = fixtures.BackendTest.request

    def setUp(self):
        ideas.ACTIVE.clear()
        ideas.path(self.cid).unlink(missing_ok=True)
        ideas.topics_path(self.cid).unlink(missing_ok=True)
        self.ctx = {'channel':'Fixture', 'previous_titles':[], 'samples':[], 'target_words':1200, 'sample_count':0}
        self.context = patch.object(ideas, 'context', return_value=self.ctx)
        self.context.start()
        self.addCleanup(self.context.stop)
        self.hooks = [{'text':f'Opening {n}. ' + 'Natural complete spoken words. '*10,'uk':''} for n in range(5)]
        self.topics = {'id':'topics-fixture', 'ideas':[{'title':f'A fresh topic number {n}', 'uk':''} for n in range(5)],
                       'day':ideas.today(), 'target_words':1200, 'sample_count':0, 'context':self.ctx, 'status':'done', 'stage':'ideas'}
        store.atomic_json(ideas.path(self.cid), self.topics)

    def begin(self, index=0):
        with patch.object(ideas, 'Thread'):
            ideas.start(self.cid, {'action':'openings', 'index':index, 'new_episode':True})
        return store.read_json(ideas.path(self.cid))

    def ready(self, index=0):
        data = self.begin(index)
        with patch.object(ideas, 'opus', return_value={'openings':self.hooks}):
            ideas.work(self.cid, data)
        return ideas.read_project(data['project_id'])

    def test_new_episode_never_resumes_hooks_and_project_endpoint_recovers_them(self):
        first = self.ready()
        code, topics = self.request(f'/api/channels/{self.cid}/episode-ideas?view=topics')
        self.assertEqual(code, 200)
        self.assertNotIn('project_id', topics)
        self.assertNotIn('openings', topics)
        self.assertNotIn('context', topics)
        self.assertEqual(topics['used_idea_indexes'], [0])
        second = self.ready(1)
        code, draft = self.request(f"/api/projects/{first['project_id']}/episode-draft")
        self.assertEqual(code, 200)
        self.assertEqual(draft['openings'], self.hooks)
        self.assertEqual(draft['selected_index'], 0)
        self.assertNotIn('context', draft)
        self.assertNotEqual(first['project_id'], second['project_id'])
        self.assertEqual(ideas.catalog(self.cid)['used_idea_indexes'], [0,1])

    def test_deleted_legacy_project_does_not_block_same_topic_for_new_episode(self):
        data = {**self.topics, 'project_id':'a'*24, 'selected_index':0, 'selected':self.topics['ideas'][0],
                'stage':'openings', 'openings':self.hooks}
        store.atomic_json(ideas.path(self.cid), data)
        with patch.object(ideas, 'opus') as model:
            topics = ideas.catalog(self.cid)
            self.assertEqual(topics['used_idea_indexes'], [])
            self.assertNotIn('project_id', topics)
            next_run = self.begin(0)
        model.assert_not_called()
        self.assertNotEqual(next_run['project_id'], 'a'*24)

    def test_regenerate_is_explicit_idempotent_and_preserves_previous_hooks(self):
        data = self.ready()
        root = store.project_dir(data['project_id'])
        body = {'action':'openings','refresh':True,'request_id':'regenerate-once'}
        with patch.object(ideas, 'Thread') as thread:
            code, running = self.request(f"/api/projects/{data['project_id']}/episode-draft", 'POST', body)
            self.assertEqual(code, 202)
            self.assertEqual(running['previous_openings'], self.hooks)
            self.request(f"/api/projects/{data['project_id']}/episode-draft", 'POST', body)
            self.assertEqual(thread.call_count, 1)
        self.assertEqual(len(list((root/'draft-history').glob('*.json'))), 1)
        changed = [{'text':row['text']+' A different ending.', 'uk':''} for row in self.hooks]
        with patch.object(ideas, 'opus', return_value={'openings':changed}) as model:
            ideas.work(self.cid, store.read_json(root/'episode-draft.json'))
            self.assertIn('different angles', model.call_args.args[0])
        with patch.object(ideas, 'Thread') as thread:
            replay = ideas.start_project(data['project_id'], body)
        thread.assert_not_called()
        self.assertEqual(replay['openings'], changed)
        self.assertEqual(store.load_project(data['project_id'])['name'], data['selected']['title'])

    def test_cancel_releases_topic_without_deleting_project_or_starting_a_model(self):
        data = self.ready()
        with patch.object(ideas, 'Thread') as thread:
            code, cancelled = self.request(f"/api/projects/{data['project_id']}/episode-draft", 'POST', {'action':'cancel'})
        self.assertEqual(code, 202)
        self.assertTrue(cancelled['cancelled'])
        thread.assert_not_called()
        self.assertEqual(ideas.catalog(self.cid)['used_idea_indexes'], [])
        self.assertEqual(store.load_project(data['project_id'])['id'], data['project_id'])
        self.assertEqual(ideas.read_project(data['project_id'])['openings'], self.hooks)
        self.assertNotEqual(self.begin(0)['project_id'], data['project_id'])

    def test_refresh_topics_preserves_project_and_old_project_does_not_replace_new_topics(self):
        old = self.ready()
        with patch.object(ideas, 'Thread'):
            ideas.start(self.cid, {'action':'ideas','refresh':True})
        current = store.read_json(ideas.path(self.cid))
        new_topics = [{'title':f'Other useful topic {i}', 'uk':''} for i in range(5)]
        with patch.object(ideas, 'deepseek', return_value={'ideas':new_topics}): ideas.work(self.cid, current)
        with patch.object(ideas, 'Thread'):
            ideas.start_project(old['project_id'], {'action':'openings','refresh':True})
        self.assertEqual(ideas.catalog(self.cid)['ideas'], new_topics)
        self.assertEqual(ideas.read_project(old['project_id'])['selected'], old['selected'])

    def test_projects_in_one_channel_run_independently_and_finish_in_reverse_order(self):
        first = self.begin(0)
        second = self.begin(1)
        self.assertNotEqual(first['project_id'], second['project_id'])
        self.assertEqual(len(ideas.active_work()), 2)
        code, status = self.request('/api/studio/status')
        self.assertEqual(code, 200)
        own = [row for row in status['activities'] if row['project_id'] in {first['project_id'], second['project_id']}]
        self.assertEqual(len(own), 2)
        self.assertTrue(all(row['kind'] == 'створення зачинів' for row in own))
        self.assertEqual(ideas.read_project(first['project_id'])['status'], 'running')
        with patch.object(ideas, 'opus', return_value={'openings':self.hooks}):
            ideas.work(self.cid, second)
            self.assertIn(first['project_id'], ideas.ACTIVE)
            self.assertEqual(ideas.read_project(first['project_id'])['status'], 'running')
            ideas.work(self.cid, first)
        self.assertFalse(ideas.ACTIVE)
        self.assertEqual(ideas.read(self.cid)['project_id'], second['project_id'])
        for data in (first, second):
            saved = ideas.read_project(data['project_id'])
            self.assertEqual(saved['status'], 'done')
            self.assertEqual(saved['openings'], self.hooks)
            self.assertEqual(saved['selected'], data['selected'])

    def test_topic_refresh_can_run_beside_openings_and_keeps_its_own_progress(self):
        first = self.begin()
        with patch.object(ideas, 'Thread'):
            ideas.start(self.cid, {'action':'ideas','refresh':True})
            ideas.start(self.cid, {'action':'ideas','refresh':True})
        self.assertEqual(len(ideas.ACTIVE), 2)
        self.assertEqual(ideas.catalog(self.cid)['status'], 'running')
        topic_job = ideas.ACTIVE[self.cid].copy()
        with patch.object(ideas, 'deepseek', return_value={'ideas':[{'title':f'Updated useful topic {i}'} for i in range(5)]}):
            ideas.work(self.cid, topic_job)
        self.assertEqual(ideas.catalog(self.cid)['status'], 'done')
        self.assertIn(first['project_id'], ideas.ACTIVE)
        ideas.ACTIVE.clear()
        self.assertEqual(ideas.read_project(first['project_id'])['status'], 'failed')

    def test_same_project_rejects_overlapping_steps_and_other_project_can_cancel(self):
        first = self.ready(0)
        second = self.begin(1)
        with patch.object(ideas, 'Thread') as thread:
            cancelled = ideas.start_project(first['project_id'], {'action':'cancel'})
            self.assertTrue(cancelled['cancelled'])
            with self.assertRaises(store.StudioError) as error:
                ideas.start_project(second['project_id'], {'action':'openings','refresh':True})
        self.assertEqual(error.exception.status, 409)
        thread.assert_not_called()
        self.assertEqual(ideas.read(self.cid)['project_id'], second['project_id'])

    def test_stale_topic_selection_cannot_create_a_different_episode(self):
        ideas.catalog(self.cid)
        with patch.object(ideas, 'Thread') as thread:
            with self.assertRaises(store.StudioError):
                ideas.start(self.cid, {'action':'openings','index':0,'new_episode':True,'ideas_id':'obsolete'})
        thread.assert_not_called()

    def test_daily_reservation_survives_failed_refresh_and_reopening_an_old_project(self):
        old = self.ready()
        topics = store.read_json(ideas.topics_path(self.cid))
        topics.update(day='2000-01-01', attempt_day='2000-01-01')
        store.atomic_json(ideas.topics_path(self.cid), topics)
        with patch.object(ideas, 'Thread'):
            ideas.start(self.cid, {'action':'ideas','refresh':True})
        with patch.object(ideas, 'deepseek', side_effect=RuntimeError('Provider unavailable')):
            ideas.work(self.cid, store.read_json(ideas.path(self.cid)))
        old['attempt_day'] = '2000-01-01'
        ideas.save_draft(self.cid, old)
        catalog = ideas.catalog(self.cid)
        self.assertEqual(catalog['attempt_day'], ideas.today())
        self.assertFalse(catalog['stale'])
        with patch.object(ideas.credentials, 'vault') as vault, patch.object(store, 'list_channels', return_value=[{'id':self.cid}]), patch.object(ideas, 'Thread') as thread:
            vault.return_value.configured.return_value = True
            ideas.daily_once()
        thread.assert_not_called()

    def test_saved_script_blocks_paid_regeneration(self):
        data = self.ready()
        store.save_project_source(store.load_project(data['project_id']), 'Saved author script.')
        with patch.object(ideas, 'Thread') as thread:
            with self.assertRaises(store.StudioError):
                ideas.start_project(data['project_id'], {'action':'openings','refresh':True})
        thread.assert_not_called()
        self.assertEqual(store.load_project(data['project_id'])['voice_script']['text'], 'Saved author script.')


if __name__ == '__main__': unittest.main()
