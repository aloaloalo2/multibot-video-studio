import sys
import shutil
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
import episode_ideas as ideas
import idea_reference as reference
import trending_videos as trends
import test_backend as fixtures

VIDEO='abcdefghijk'

class TrendingUseIdeaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.cid=store.channel_id(fixtures.BackendTest.channel)
        cls.base_url=fixtures.BackendTest.base_url
    @classmethod
    def tearDownClass(cls):fixtures.BackendTest.tearDownClass()
    request=fixtures.BackendTest.request
    def setUp(self):
        ideas.ACTIVE.clear()
        shutil.rmtree(store.DATA_ROOT/'trending-idea-requests',ignore_errors=True)
        self.body={'channel_id':self.cid,'video_id':VIDEO,'title':'Edited idea title','target_words':1200,'use_thumbnail':False,'request_id':self.id().split('.')[-1]}
        self.source={'id':VIDEO,'title':'Original competitor title','author':'Competitor','url':'https://www.youtube.com/watch?v='+VIDEO}
        root=reference.folder(self.cid,VIDEO);root.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(32,18)).save(root/'thumbnail.jpg')
        store.atomic_json(root/'reference.json',self.source)
        store.atomic_json(trends.cache_path(),{'competitor':{'name':'Competitor','videos':[{'id':VIDEO,'title':self.source['title']}]}})
        self.patches=[patch.object(trends,'sources',return_value={'competitor':{}}),patch.object(ideas,'context',return_value={'channel':'Test','sample_count':0}),patch.object(ideas,'Thread')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        ideas.ACTIVE.clear()
    def test_trend_preserves_explicit_channel_host_choice(self):
        with patch.object(reference,'inspect',return_value=self.source),patch('channel_hero.info',return_value={'url':'/host.png'}):
            code,data=self.request('/api/trending-videos/use','POST',{**self.body,'use_thumbnail':True,'use_hero':True})
        self.assertEqual(code,202,data)
        self.assertTrue(ideas.read_project(data['project_id'])['clone_use_hero'])

    def test_title_only_creates_normal_project_without_reference_media_or_thumbnail_job(self):
        with patch.object(reference,'inspect') as inspect:
            code,data=self.request('/api/trending-videos/use','POST',self.body)
            self.assertEqual(code,202,data)
            inspect.assert_not_called()
        project=store.load_project(data['project_id'])
        draft=ideas.read_project(project['id'])
        self.assertEqual(project['name'],self.body['title'])
        self.assertEqual(draft['selected']['title'],self.body['title'])
        self.assertNotIn('clone_reference',draft)
        self.assertFalse((store.project_dir(project['id'])/'idea-reference.jpg').exists())
        self.assertEqual(reference.for_project(project['id']),(None,None))
        self.assertFalse(store.read_json(store.project_dir(project['id'])/'idea-source.json')['use_thumbnail'])
        draft.update(status='done',openings=[{'text':'Selected hook','uk':''}])
        ideas.save_draft(self.cid,draft);ideas.ACTIVE.clear()
        with patch('thumbnail_gen.start') as start:
            ideas.start_project(project['id'],{'action':'script','index':0})
            start.assert_not_called()
    def test_checked_reference_uses_the_existing_clone_prompt_path(self):
        with patch.object(reference,'inspect',return_value=self.source) as inspect:
            code,data=self.request('/api/trending-videos/use','POST',{**self.body,'use_thumbnail':True})
            self.assertEqual(code,202,data)
            inspect.assert_called_once_with(self.cid,self.source['url'])
        pid=data['project_id']
        self.assertEqual(ideas.read_project(pid)['clone_reference'],self.source)
        self.assertEqual(reference.for_project(pid)[0],self.source)
        self.assertEqual((store.project_dir(pid)/'idea-reference.jpg').read_bytes(),(reference.folder(self.cid,VIDEO)/'thumbnail.jpg').read_bytes())
    def test_repeat_is_idempotent_even_after_source_removed_and_option_changes_conflict(self):
        first=trends.use_idea(self.body)
        store.atomic_json(trends.cache_path(),{})
        with patch.object(reference,'inspect') as inspect,patch.object(ideas,'context') as context:
            again=trends.use_idea(self.body)
            self.assertEqual(first['project_id'],again['project_id'])
            with self.assertRaises(store.StudioError) as caught:trends.use_idea({**self.body,'use_thumbnail':True})
            self.assertEqual(caught.exception.status,409)
            inspect.assert_not_called();context.assert_not_called()
    def test_cross_channel_replay_cannot_create_another_project(self):
        first=trends.use_idea(self.body)
        other=store.create_channel('Another target channel')
        with patch.object(ideas,'context') as context,self.assertRaises(store.StudioError) as caught:
            trends.use_idea({**self.body,'channel_id':other['id']})
        self.assertEqual(caught.exception.status,409)
        context.assert_not_called()

    def test_used_source_blocks_new_requests_including_other_channels(self):
        first=trends.use_idea(self.body)
        other=store.create_channel('Other channel for stale tab')
        with patch.object(reference,'inspect') as inspect,patch.object(ideas,'context') as context:
            for cid in (self.cid,other['id']):
                with self.assertRaises(store.StudioError) as caught:
                    trends.use_idea({**self.body,'channel_id':cid,'request_id':'new-'+cid,'title':'A different title'})
                self.assertEqual(caught.exception.status,409)
            inspect.assert_not_called();context.assert_not_called()
        self.assertIn(VIDEO,trends.used_video_ids())
        store.delete_project(first['project_id'])
        self.assertIn(VIDEO,trends.used_video_ids())

    def test_another_source_with_the_same_title_remains_available(self):
        first=trends.use_idea(self.body)
        other='abcdefghijZ'
        store.atomic_json(trends.cache_path(),{'competitor':{'name':'Competitor','videos':[{'id':other,'title':self.source['title']}]}})
        second=trends.use_idea({**self.body,'video_id':other,'request_id':'another-video'})
        self.assertNotEqual(first['project_id'],second['project_id'])
        self.assertEqual(trends.used_video_ids(),{VIDEO,other})

    def test_two_tabs_cannot_create_the_same_source_while_loading_reference(self):
        from concurrent.futures import ThreadPoolExecutor
        barrier=threading.Barrier(2)
        def inspect(*args):
            barrier.wait(timeout=5)
            return self.source
        def create(index):
            try:
                return trends.use_idea({**self.body,'use_thumbnail':True,'request_id':'race-'+str(index)})
            except store.StudioError as error:
                return error.status
        with patch.object(reference,'inspect',side_effect=inspect),ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(create,range(2)))
        self.assertEqual(sum(isinstance(result,dict) for result in results),1)
        self.assertIn(409,results)
        self.assertEqual(len(list((store.DATA_ROOT/'trending-idea-requests').glob('*.json'))),1)
    def test_invalid_inputs_and_outside_origin_never_start_work(self):
        with patch.object(reference,'inspect') as inspect,patch.object(ideas,'launch') as launch:
            for patch_body in ({'video_id':'../../x'},{'use_thumbnail':'false'},{'target_words':0},{'request_id':'../x'},{'video_id':'12345678901'}):
                code,data=self.request('/api/trending-videos/use','POST',{**self.body,**patch_body})
                self.assertIn(code,(400,404),data)
            code,data=self.request('/api/trending-videos/use','POST',self.body,headers={'Origin':'https://outside.example'})
            self.assertEqual(code,403)
            inspect.assert_not_called();launch.assert_not_called()
