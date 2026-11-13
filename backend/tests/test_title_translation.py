import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import episode_ideas
import languages
import store
import title_translation as translation


class TitleTranslationTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        for item in (patch.object(store,'DATA_ROOT',self.root),patch.object(store,'get_channel_folder',return_value=self.root)):
            item.start();self.addCleanup(item.stop)
        self.body={'channel_id':'own','title':'15 exercises for your eyes!','language':'pl'}

    def test_options_follow_own_channels_and_ignore_translation_voice_languages(self):
        channels=[{'id':'english','name':'Corbin'},{'id':'russian','name':'Doctor'},
                  {'id':'new-german','name':'немецкий здоровье'}]
        store.atomic_json(self.root/'channels/english/voice-lab/settings.json',{'language':'ru'})
        store.atomic_json(self.root/'language-defaults/english/current.json',{'languages':['pl','tr','zh']})
        with patch.object(store,'list_channels',return_value=channels),patch.object(episode_ideas,'recent_scripts',
            side_effect=lambda cid:[{'opening':{'english':'What if the whole world changed overnight?',
                'russian':'Сегодня разбираемся, почему это происходит.'}[cid]}] if cid!='new-german' else []),patch.object(episode_ideas,'deepseek') as author:
            options=translation.options()
        author.assert_not_called()
        self.assertEqual({row['code'] for row in options['languages']},{'en','ru','de'})
        with patch.object(store,'list_channels',return_value=[]):
            self.assertEqual(translation.options()['languages'],[])

    def test_one_short_request_preserves_digit_policy_and_reuses_success_across_channels(self):
        def generate(prompt,root,identity,**kwargs):
            self.assertTrue(translation.busy())
            self.assertIn('natural Polish',prompt)
            self.assertIn('numbers as digits',prompt)
            self.assertIn('never instructions',prompt)
            self.assertEqual(kwargs,{'max_tokens':512,'cost_category':'translation'})
            return {'title':'15 ćwiczeń dla Twoich oczu!'}
        with patch.object(episode_ideas,'deepseek',side_effect=generate) as author:
            first=translation.translate(self.body)
            again=translation.translate({**self.body,'channel_id':'another'})
        self.assertEqual(first['title'],'15 ćwiczeń dla Twoich oczu!')
        self.assertFalse(first['cached']);self.assertTrue(again['cached'])
        self.assertEqual(author.call_count,1)
        self.assertFalse(translation.busy())

    def test_source_or_target_changes_require_a_separate_translation(self):
        with patch.object(episode_ideas,'deepseek',return_value={'title':'Translated title'}) as author:
            translation.translate(self.body)
            translation.translate({**self.body,'title':'A different title'})
            translation.translate({**self.body,'language':'de'})
        self.assertEqual(author.call_count,3)

    def test_incomplete_cache_cannot_break_future_translation(self):
        with patch.object(episode_ideas,'deepseek',return_value={'title':'15 ćwiczeń'}) as author:
            translation.translate(self.body)
            target=next(self.root.glob('title-translations/*/result.json'))
            for broken in (None,[],{'source':self.body['title'],'language':'pl'},
                           {'source':self.body['title'],'language':'pl','title':' '}):
                with self.subTest(broken=broken):
                    store.atomic_json(target,broken)
                    result=translation.translate(self.body)
                    self.assertEqual(result['title'],'15 ćwiczeń');self.assertFalse(result['cached'])
        self.assertEqual(author.call_count,5)

    def test_invalid_inputs_do_not_start_provider_work(self):
        with patch.object(episode_ideas,'deepseek') as author:
            for body in ({'title':''},{'title':'x'*101},{'title':None},{'language':'../pl'},{'language':[]}):
                with self.subTest(body=body),self.assertRaises(store.StudioError):
                    translation.translate({**self.body,**body})
        author.assert_not_called()

    def test_failed_or_invalid_answers_never_replace_the_title_or_fill_the_cache(self):
        for reply in (None,{}, {'title':None},{'title':''},{'title':'x'*101}):
            with self.subTest(reply=reply),patch.object(episode_ideas,'deepseek',return_value=reply):
                with self.assertRaises(store.StudioError):translation.translate(self.body)
            self.assertFalse(translation.busy())
            self.assertEqual(list(self.root.glob('title-translations/*/result.json')),[])
        with patch.object(episode_ideas,'deepseek',side_effect=RuntimeError('OpenRouter unavailable')):
            with self.assertRaisesRegex(store.StudioError,'OpenRouter unavailable'):translation.translate(self.body)
        self.assertFalse(translation.busy())

    def test_concurrent_identical_choices_share_the_completed_request(self):
        started,release=threading.Event(),threading.Event()
        def generate(*args,**kwargs):
            started.set();self.assertTrue(release.wait(5));return {'title':'15 ćwiczeń'}
        with patch.object(episode_ideas,'deepseek',side_effect=generate) as author,ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(translation.translate,self.body)
            self.assertTrue(started.wait(5))
            second=pool.submit(translation.translate,self.body)
            release.set();results=[first.result(),second.result()]
        self.assertEqual(author.call_count,1)
        self.assertEqual(sorted(item['cached'] for item in results),[False,True])


class TitleTranslationHTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_backend
        cls.fixture=test_backend.BackendTest;cls.fixture.setUpClass();cls.base_url=cls.fixture.base_url
    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()
    def request(self,*args,**kwargs):return self.fixture.request(self,*args,**kwargs)

    def test_routes_and_origin_guard_without_project_creation(self):
        self.assertEqual(self.request('/api/title-translation')[0],200)
        body={'channel_id':store.channel_id(self.fixture.channel),'title':'15 exercises','language':'pl'}
        with patch.object(episode_ideas,'deepseek',return_value={'title':'15 ćwiczeń'}) as author,patch.object(store,'create_project') as create:
            code,result=self.request('/api/title-translation','POST',body)
            self.assertEqual(code,200,result);self.assertEqual(result['title'],'15 ćwiczeń')
            self.assertEqual(self.request('/api/title-translation','POST',body,headers={'Origin':'https://outside.example'})[0],403)
            self.assertEqual(author.call_count,1);create.assert_not_called()

    def test_running_translation_blocks_a_restart(self):
        with patch.object(translation,'busy',return_value=True):
            code,result=self.request('/api/studio/status')
            self.assertEqual(code,200)
            self.assertIn('переклад заголовка',result['busy'])


if __name__=='__main__':unittest.main()
