import sys
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
    def test_invalid_inputs_and_outside_origin_never_start_work(self):
        with patch.object(reference,'inspect') as inspect,patch.object(ideas,'launch') as launch:
            for patch_body in ({'video_id':'../../x'},{'use_thumbnail':'false'},{'target_words':0},{'request_id':'../x'},{'video_id':'12345678901'}):
                code,data=self.request('/api/trending-videos/use','POST',{**self.body,**patch_body})
                self.assertIn(code,(400,404),data)
            code,data=self.request('/api/trending-videos/use','POST',self.body,headers={'Origin':'https://outside.example'})
            self.assertEqual(code,403)
            inspect.assert_not_called();launch.assert_not_called()
