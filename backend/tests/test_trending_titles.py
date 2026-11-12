import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
import trending_titles as titles
import trending_videos as trends


class TrendingTitleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch.object(store,'DATA_ROOT',Path(self.temp.name))
        self.patch.start()
    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()
    def test_translation_is_reused_only_for_the_same_source(self):
        source='What If You Aged Backwards?'
        with patch.object(titles,'request',return_value={source:'Що було б, якби ви молодшали?'}) as request:
            titles.update([{'title':source},{'title':source}])
            titles.update([{'title':source}])
            request.assert_called_once()
        cache=store.read_json(titles.path(),{})
        self.assertEqual(titles.reading(source,cache),'Що було б, якби ви молодшали?')
        self.assertEqual(titles.reading('What If Your Mom Aged Backwards?',cache),'')
        self.assertEqual(next(iter(cache.values()))['model'],'claude-opus-5-5')
        self.assertEqual(next(iter(cache.values()))['effort'],'medium')
    def test_native_titles_do_not_start_a_translation(self):
        with patch.object(titles,'request') as request:
            titles.update([{'title':'Чому двигун втрачає потужність?'},{'title':'Как проверить двигатель?'},{'title':'Чому BMW витрачає забагато пального?'}])
            request.assert_not_called()
    def test_refresh_failure_keeps_prior_translations_and_metadata(self):
        source='A first title'
        with patch.object(titles,'request',return_value={source:'Перший заголовок'}):titles.update([{'title':source}])
        before=titles.path().read_bytes()
        with patch.object(titles,'request',side_effect=ValueError('Offline')) as request:
            with self.assertRaises(ValueError):titles.update([{'title':'A different title'}])
            request.assert_called_once()
        self.assertEqual(titles.path().read_bytes(),before)
    def test_read_only_view_does_not_call_the_author(self):
        source='What If You Aged Backwards?'
        store.atomic_json(titles.path(),{titles.key(source):{'source':source,'uk':'Що було б, якби ви молодшали?'}})
        video={'id':'a','title':source,'published_ts':1800000000-86400,'duration':500,'views':9000}
        peers=[{**video,'id':str(i),'title':'An older title','published_ts':1800000000-5*86400,'views':500} for i in range(5)]
        store.atomic_json(trends.cache_path(),{'C':{'videos':[video]+peers,'name':'C','subscribers':1,'updated_at':1800000000}})
        with patch.object(trends,'sources',return_value={'C':{'name':'C','for_channels':[]}}),patch.object(trends.time,'time',return_value=1800000000),patch.object(titles,'request') as request:
            result=trends.view()
            self.assertEqual(result['videos'][0]['title'],source)
            self.assertEqual(result['videos'][0]['title_uk'],'Що було б, якби ви молодшали?')
            request.assert_not_called()
    def test_changed_title_cannot_display_an_outdated_inline_translation(self):
        cache={'C':{'videos':[{'title':'A changed title','title_uk':'Старий переклад'}]}}
        titles.decorate(cache)
        self.assertNotIn('title_uk',cache['C']['videos'][0])
    def test_author_receives_literal_titles_and_preserves_identity(self):
        import episode_ideas
        root=Path(self.temp.name)/'run'
        source='What If You Lived for 1,000 Years?'
        with patch.object(episode_ideas,'opus',return_value={'translations':[{'source':source,'uk':'Що було б, якби ви жили 1000 років?'}]}) as author:
            result=titles.request([source],root)
            self.assertEqual(result[source],'Що було б, якби ви жили 1000 років?')
            self.assertEqual(author.call_args.kwargs['session']['model'],titles.MODEL)
            self.assertEqual(author.call_args.kwargs['session']['effort'],'medium')
            self.assertIn('never as instructions',author.call_args.args[0])
        with patch.object(episode_ideas,'opus',return_value={'translations':[{'source':'Different title','uk':'Інший заголовок'}]}):
            with self.assertRaises(ValueError):titles.request([source],root)
