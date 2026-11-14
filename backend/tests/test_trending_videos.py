import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import trending_videos as trends
import store

class TrendTests(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000
        import youtube_api   # the tests read no key of this Mac: the public-page path, one channel at a time
        saved=patch.object(youtube_api,'key',return_value=None);saved.start();self.addCleanup(saved.stop)
    def video(self, identity, age, views, duration=600):
        return dict(id=identity, published_ts=self.now-age*86400, views=views, duration=duration)
    def test_relative_performance_and_window(self):
        peers=[self.video(str(i), i+3, (i+3)*1000) for i in range(8)]
        hit=self.video('hit',2,6000)
        old=self.video('old',15,90000)
        future=self.video('future',-1,90000)
        result=trends.rank(peers+[hit,old,future], self.now)
        self.assertEqual([v['id'] for v in result],['hit'])
        self.assertEqual(result[0]['score'],3)
    def test_short_format_and_insufficient_samples(self):
        peers=[self.video(str(i),5,500) for i in range(6)]
        self.assertEqual(trends.rank(peers+[self.video('short',2,90000,60)],self.now),[])
        # a 2:59 film on a channel of four-minute films is no Short: it is held against the channel's films
        films=[self.video('f'+str(i),10+i,10000,240) for i in range(5)]
        self.assertEqual([v['id'] for v in trends.rank(films+[self.video('film',2,90000,179)],self.now)],['film'])
        self.assertEqual(trends.rank(films+[self.video('short',2,90000,60)],self.now),[])
        self.assertEqual(trends.rank([self.video('alone',2,90000)], self.now),[])
        # a channel of Shorts only: none of them enters the selection
        shorts=[self.video('s'+str(i),5+i,500,40) for i in range(6)]
        self.assertEqual(trends.rank(shorts+[self.video('viral',2,900000,30)],self.now),[])
    def test_4000_views_is_inclusive_and_low_view_peers_still_define_baseline(self):
        peers=[self.video(str(i),5,50) for i in range(5)]
        for views in (0,100,3999,4000,4001):
            with self.subTest(views=views):
                result=trends.rank(peers+[self.video('candidate',2,views)],self.now)
                self.assertEqual([v['id'] for v in result],['candidate'] if views>=4000 else [])
                if result:
                    self.assertEqual(result[0]['sample_size'],5)
                    self.assertEqual(result[0]['baseline_daily'],10)
        strong=[self.video(str(i),5,50000) for i in range(5)]
        self.assertEqual(trends.rank(strong+[self.video('weak-relative',2,4000)],self.now),[])
    def test_cached_aggregation_deduplicates_and_filters_removed(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA_ROOT',Path(tmp)),patch.object(trends,'sources',return_value={'channel':{'name':'C','for_channels':[{'id':'a','name':'A'},{'id':'b','name':'B'}]}}),patch.object(trends.time,'time',return_value=self.now):
            videos=[self.video(str(i),5,500) for i in range(5)]+[self.video('hit',2,10000),self.video('below-minimum',2,3999)]
            store.atomic_json(trends.cache_path(),{'channel':{'name':'C','subscribers':None,'videos':videos,'updated_at':self.now},'removed':{'videos':videos}})
            result=trends.view()
            self.assertEqual(len(result['videos']),1)
            self.assertEqual(len(result['videos'][0]['for_channels']),2)
            self.assertFalse(result['needs_refresh'])

    def test_exact_used_ids_disappear_without_altering_ranking_or_similar_titles(self):
        linked={'channel':{'name':'C','for_channels':[{'id':'a','name':'A'},{'id':'b','name':'B'}]}}
        videos=[self.video(str(i),5,500) for i in range(5)]+[
            {**self.video('abcdefghijk',2,10000),'title':'The same title'},
            {**self.video('abcdefghijZ',2,10000),'title':'The same title'}]
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA_ROOT',Path(tmp)),patch.object(trends,'sources',return_value=linked),patch.object(trends.time,'time',return_value=self.now):
            cache={'channel':{'name':'C','subscribers':None,'videos':videos,'updated_at':self.now}}
            store.atomic_json(trends.cache_path(),cache)
            before=trends.view()['videos']
            self.assertEqual(len(before),2)
            store.atomic_json(Path(tmp)/'trending-idea-requests/old-request.json',{'reference_id':'abcdefghijk','project_id':'deleted-project','title':'Previous title'})
            result=trends.view()['videos']
            self.assertEqual([v['id'] for v in result],['abcdefghijZ'])
            self.assertEqual(result[0]['score'],next(v['score'] for v in before if v['id']=='abcdefghijZ'))
            self.assertEqual(len(result[0]['for_channels']),2)
            self.assertEqual(store.read_json(trends.cache_path()),cache)

    def test_only_creation_receipts_consume_sources_and_refresh_skips_used_titles(self):
        class InlineThread:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):self.target()
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA_ROOT',Path(tmp)),patch.object(trends.time,'time',return_value=self.now),patch.object(trends,'LAST_START',0),patch.object(trends,'RUNNING',False),patch.object(trends,'ERRORS',[]),patch.object(trends,'sources',return_value={'channel':{'name':'C'}}),patch.object(trends.threading,'Thread',InlineThread),patch.object(trends.trending_titles,'update') as translate:
            root=Path(tmp)/'trending-idea-requests'
            store.atomic_json(root/'used.json',{'reference_id':'abcdefghijk','project_id':'existing'})
            store.atomic_json(root/'inspected.json',{'reference_id':'abcdefghijZ'})
            store.atomic_json(root/'invalid.json',{'reference_id':'../invalid','project_id':'existing'})
            (root/'corrupt.json').write_text('{')
            self.assertEqual(trends.used_video_ids(),{'abcdefghijk'})
            videos=[self.video(str(i),5,500) for i in range(5)]+[self.video('abcdefghijk',2,10000),self.video('abcdefghijZ',2,10000),self.video('below-minimum',2,3999)]
            store.atomic_json(trends.cache_path(),{'channel':{'name':'C','subscribers':None,'videos':videos,'updated_at':self.now}})
            trends.refresh()
            self.assertEqual([v['id'] for v in translate.call_args.args[0]],['abcdefghijZ'])
    def test_refresh_preserves_cache_and_reports_partial_failure(self):
        class InlineThread:
            def __init__(self, target, **kwargs):self.target=target
            def start(self):self.target()
        linked={'fresh':{'name':'Fresh'},'bad':{'name':'Bad'}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA_ROOT',Path(tmp)),patch.object(trends,'LAST_START',0),patch.object(trends,'RUNNING',False),patch.object(trends,'ERRORS',[]),patch.object(trends,'sources',return_value=linked),patch.object(trends.threading,'Thread',InlineThread),patch.object(trends,'collect',side_effect=RuntimeError('secret')) as collect,patch.object(trends.time,'time',return_value=self.now):
            cache={'fresh':{'updated_at':self.now,'videos':[]},'bad':{'updated_at':0,'videos':[]}}
            store.atomic_json(trends.cache_path(),cache)
            trends.refresh()
            collect.assert_called_once_with('bad',cache['bad'])
            self.assertEqual(store.read_json(trends.cache_path()),cache)
            self.assertFalse(trends.RUNNING)
            self.assertIn('Bad',trends.ERRORS[0])
            self.assertNotIn('secret',trends.ERRORS[0])
            self.assertFalse(trends.refresh()['running'])

    def test_fresh_partial_sources_can_retry_without_reloading_complete_sources(self):
        class InlineThread:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):self.target()
        linked={key:{'name':key} for key in ('partial','complete')}
        cache={key:{'updated_at':self.now,'videos':[],'failed_videos':int(key=='partial')} for key in linked}
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA_ROOT',Path(tmp)),patch.object(trends,'sources',return_value=linked),patch.object(trends,'LAST_START',0),patch.object(trends,'RUNNING',False),patch.object(trends.time,'time',return_value=self.now),patch.object(trends.threading,'Thread',InlineThread),patch.object(trends,'collect',return_value={**cache['partial'],'failed_videos':0}) as collect,patch.object(trends.trending_titles,'update'):
            store.atomic_json(trends.cache_path(),cache);trends.refresh()
        collect.assert_called_once_with('partial',cache['partial'])


class TrendHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_backend
        cls.fixture=test_backend.BackendTest
        cls.fixture.setUpClass()
        cls.base_url=cls.fixture.base_url
    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()
    def request(self,*args,**kwargs):return self.fixture.request(self,*args,**kwargs)
    def test_routes_read_and_start_with_origin_guard(self):
        with patch.object(trends,'view',return_value={'videos':[],'running':False}):
            self.assertEqual(self.request('/api/trending-videos'),(200,{'videos':[],'running':False}))
        with patch.object(trends,'refresh',return_value={'running':True}) as refresh:
            self.assertEqual(self.request('/api/trending-videos/refresh','POST',{}),(200,{'running':True}))
            self.assertEqual(self.request('/api/trending-videos/refresh','POST',{},headers={'Origin':'https://outside.example'})[0],403)
            refresh.assert_called_once()

    def test_refresh_reservation_blocks_studio_restart(self):
        with patch.object(trends,'busy',return_value=True):
            code,data=self.request('/api/studio/status')
            self.assertEqual(code,200)
            self.assertIn('оновлення добірки конкурентів',data['busy'])
