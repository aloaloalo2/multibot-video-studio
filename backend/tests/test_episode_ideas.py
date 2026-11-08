import copy
import unittest
from contextlib import nullcontext
from unittest.mock import patch
import test_backend as fixtures
import store
import episode_ideas as ideas

class TitleCleanupTest(unittest.TestCase):
    def test_numbered_suggestions_keep_title_counts_and_ukrainian_translation(self):
        rows = [{'title': f'{i + 1}. {i + 5} Geräusche am Auto!',
                 'uk': f'{i + 1}) {i + 5} звуків в авто!'} for i in range(5)]
        accepted = ideas.validate_titles({'ideas': rows}, {'previous_titles': []})
        self.assertEqual(accepted[0], {'title': '5 Geräusche am Auto!', 'uk': '5 звуків в авто!'})
        self.assertEqual(accepted[4]['title'], '9 Geräusche am Auto!')
        self.assertEqual(ideas.clean_title('1.5 Liter im Motor?'), '1.5 Liter im Motor?')

    def test_numbering_cannot_hide_a_previous_title(self):
        rows = [{'title': f'{i + 1}. {i + 5} Geräusche am Auto!'} for i in range(5)]
        with self.assertRaises(ValueError):
            ideas.validate_titles({'ideas': rows}, {'previous_titles': ['1. 5 Geräusche am Auto!']})


class EpisodeIdeasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.cid = store.channel_id(fixtures.BackendTest.channel)
        cls.base_url=fixtures.BackendTest.base_url
    @classmethod
    def tearDownClass(cls): fixtures.BackendTest.tearDownClass()
    def setUp(self):
        ideas.ACTIVE.clear()
        ideas.path(self.cid).unlink(missing_ok=True)
        ideas.topics_path(self.cid).unlink(missing_ok=True)
    request = fixtures.BackendTest.request
    def test_saved_suggestions_are_cleaned_without_resetting_work(self):
        saved = {'status':'done', 'stage':'ideas', 'id':'saved-draft', 'target_words':1200,
                 'ideas':[{'title':'1. 7 Geräusche am Auto!', 'uk':'1. 7 звуків в авто!'}]}
        store.atomic_json(ideas.path(self.cid), saved)
        current = ideas.read(self.cid)
        self.assertEqual(current['ideas'][0]['title'], '7 Geräusche am Auto!')
        self.assertEqual(current['ideas'][0]['uk'], '7 звуків в авто!')
        self.assertEqual((current['id'], current['target_words'], current['status']),
                         ('saved-draft',1200,'done'))
    def test_http_stage_is_reserved_once_and_hides_private_context(self):
        with patch.object(ideas,'Thread') as thread:
            code,data=self.request('/api/channels/'+self.cid+'/episode-ideas','POST',{'action':'ideas'})
            self.assertEqual(code,202,data);self.assertNotIn('context',data)
            self.request('/api/channels/'+self.cid+'/episode-ideas','POST',{'action':'ideas'})
            self.assertEqual(thread.call_count,1)
            code,data=self.request('/api/channels/'+self.cid+'/episode-ideas')
            self.assertEqual(code,200);self.assertEqual(data['status'],'running');self.assertNotIn('context',data)
    def begin(self, body):
        with patch.object(ideas, 'Thread'):
            ideas.start(self.cid, body)
        return store.read_json(ideas.path(self.cid))
    def finish(self, data):
        ideas.work(self.cid, data)
        return ideas.read(self.cid)
    def topics(self):
        data = self.begin({'action':'ideas'})
        with patch.object(ideas, 'deepseek', return_value={'ideas':[{'title':f'A fresh {self._testMethodName[:20]} story number {i}', 'uk':'Українська назва'} for i in range(5)]}):
            return self.finish(data)
    def test_complete_flow_keeps_selected_title_opening_and_target_without_starting_voice(self):
        previous = store.create_project(self.cid, 'Old fixture')
        store.save_project_source(previous, 'old script words ' * 400)
        data = self.topics()
        self.assertEqual(data['target_words'], 1200)
        self.assertEqual(len(data['ideas']), 5)
        self.assertNotIn('context', ideas.public(data))
        data = self.begin({'action':'openings','index':2,'target_words':1500})
        pid = data['project_id']
        hooks=[{'text':('Opening number '+str(i)+' with meaningful vivid words and natural spoken detail. ')*4,'uk':''} for i in range(5)]
        with patch.object(ideas,'opus',return_value={'openings':hooks}) as model:
            data=self.finish(data)
            self.assertIn('1500', model.call_args.args[0])
            self.assertIn('story number 2',model.call_args.args[0])
        data=self.begin({'action':'script','index':3})
        script=hooks[3]['text']+' Full natural script words.'*400
        metadata={'titles':[data['selected']['title'],'Another fresh angle','A third fresh angle'], 'description':'Thank you for watching! Subscribe for more.\n\nThis video is for entertainment.', 'tags':['story','fiction','curiosity']}
        with patch.object(ideas,'opus',return_value={'script':script,'metadata':metadata}) as model, (patch.object(ideas.author_rules,'check',return_value=(True,'OK')) if hasattr(ideas,'author_rules') else nullcontext()):
            data=self.finish(data)
            self.assertEqual(model.call_count,1)
            self.assertIn('metadata', model.call_args.args[0])
        self.assertTrue(data['completed'])
        project = store.load_project(pid)
        self.assertEqual(ideas.completion_notices.notice(project)['kind'], 'process')
        ideas.completion_notices.seen(pid)
        self.assertIsNone(ideas.completion_notices.notice(project))
        self.assertEqual(store.load_project(pid)['voice_script']['text'],script.strip())
        self.assertFalse(store.load_project(pid).get('plan_source'))
        self.assertEqual(store.read_json(store.project_dir(pid)/'source-timing.json')['timing']['status'],'awaiting_voice')
        with self.assertRaises(store.StudioError):
            self.begin({'action':'openings','index':2,'new_episode':True})
        finished_id = data['id']
        next_episode = self.begin({'action':'openings','index':1,'target_words':1400,'new_episode':True})
        self.assertNotEqual(next_episode['project_id'], pid)
        self.assertNotEqual(next_episode['id'], finished_id)
        self.assertEqual(next_episode['used_idea_indexes'], [2])
        self.assertEqual(store.load_project(pid)['voice_script']['text'], script.strip())
        self.assertTrue((ideas.path(self.cid).parent/'idea-runs'/finished_id/'finished.json').is_file())
        with patch.object(ideas,'Thread') as thread:
            duplicate = ideas.start(self.cid,{'action':'openings','index':1,'new_episode':True})
        self.assertEqual(duplicate['project_id'], next_episode['project_id'])
        thread.assert_not_called()
    def test_duplicates_fail_without_automatic_second_paid_call(self):
        ctx={'previous_titles':['Same title']}
        with self.assertRaises(ValueError): ideas.validate_titles({'ideas':[{'title':'Same title'}]*8},ctx)
        data=self.begin({'action':'ideas'})
        with patch.object(ideas,'deepseek',side_effect=RuntimeError('Service unavailable')) as model:
            failed=self.finish(data)
            self.assertEqual(failed['status'],'failed')
            self.assertEqual(model.call_count,1)
            ideas.read(self.cid)
            self.assertEqual(model.call_count,1)
    def test_double_submit_and_retry_reuse_project(self):
        self.topics()
        data=self.begin({'action':'openings','index':0})
        pid=data['project_id']
        self.assertEqual(ideas.start(self.cid,{'action':'openings','index':0})['project_id'],pid)
        with patch.object(ideas,'opus',side_effect=RuntimeError('limit')): self.finish(data)
        data=self.begin({'action':'openings','index':0})
        self.assertEqual(data['project_id'],pid)
        ideas.ACTIVE.clear()
        self.assertEqual(ideas.read(self.cid)['status'],'failed')
    def test_existing_script_is_never_overwritten(self):
        self.topics();data=self.begin({'action':'openings','index':0});pid=data['project_id']
        hooks=[{'text':'A meaningful opening with enough words. '*5,'uk':''}]*5
        with patch.object(ideas,'opus',return_value={'openings':hooks}): self.finish(data)
        store.save_project_source(store.load_project(pid),'Author text already saved.')
        with patch.object(ideas,'Thread') as thread:
            with self.assertRaises(store.StudioError):
                ideas.start(self.cid, {'action':'script','index':0})
        thread.assert_not_called()
        self.assertEqual(store.load_project(pid)['voice_script']['text'],'Author text already saved.')

if __name__=='__main__': unittest.main()

class DailyIdeasTest(EpisodeIdeasTest):
    def test_daily_reservation_prevents_repeated_paid_calls_and_keeps_opening_work(self):
        with patch.object(ideas.credentials,'vault') as vault, patch.object(store,'list_channels',return_value=[{'id':self.cid}]), patch.object(ideas,'Thread'):
            vault.return_value.configured.return_value=True
            ideas.daily_once()
            self.assertIn(self.cid,ideas.ACTIVE)
            data=store.read_json(ideas.path(self.cid));self.assertEqual(data['attempt_day'],ideas.today())
            ideas.ACTIVE.clear()
            ideas.daily_once()
            self.assertFalse(ideas.ACTIVE)
            data.update(attempt_day='2000-01-01',stage='openings',project_id='existing',completed=False)
            store.atomic_json(ideas.path(self.cid),data)
            ideas.daily_once()
            self.assertFalse(ideas.ACTIVE)
    def test_title_punctuation_rule_is_enforced(self):
        for title in ['A title: detail','A title - detail','A title — detail']:
            with self.assertRaises(ValueError): ideas.validate_titles({'ideas':[{'title':title,'uk':''}]*5},{'previous_titles':[]})
