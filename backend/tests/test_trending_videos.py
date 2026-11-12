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
    def video(self, identity, age, views, duration=600):
        return dict(id=identity, published_ts=self.now-age*86400, views=views, duration=duration)
    def test_relative_performance_and_window(self):
        peers=[self.video(str(i), i+3, (i+3)*100) for i in range(8)]
        hit=self.video('hit',2,600)
        old=self.video('old',15,90000)
        future=self.video('future',-1,90000)
        result=trends.rank(peers+[hit,old,future], self.now)
        self.assertEqual([v['id'] for v in result],['hit'])
        self.assertEqual(result[0]['score'],3)
    def test_short_format_and_insufficient_samples(self):
        peers=[self.video(str(i),5,500) for i in range(6)]
        self.assertEqual(trends.rank(peers+[self.video('short',2,90000,60)],self.now),[])
        self.assertEqual(trends.rank([self.video('alone',2,90000)], self.now),[])
    def test_no_fixed_view_threshold(self):
        peers=[self.video(str(i),5,50) for i in range(5)]
        self.assertEqual(trends.rank(peers+[self.video('small',2,100)],self.now)[0]['id'],'small')
    def test_cached_aggregation_deduplicates_and_filters_removed(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA_ROOT',Path(tmp)),patch.object(trends,'sources',return_value={'channel':{'name':'C','for_channels':[{'id':'a','name':'A'},{'id':'b','name':'B'}]}}),patch.object(trends.time,'time',return_value=self.now):
            videos=[self.video(str(i),5,500) for i in range(5)]+[self.video('hit',2,1000)]
            store.atomic_json(trends.cache_path(),{'channel':{'name':'C','subscribers':None,'videos':videos,'updated_at':self.now},'removed':{'videos':videos}})
            result=trends.view()
            self.assertEqual(len(result['videos']),1)
            self.assertEqual(len(result['videos'][0]['for_channels']),2)
            self.assertFalse(result['needs_refresh'])
    def test_refresh_preserves_cache_and_reports_partial_failure(self):
        class InlineThread:
            def __init__(self, target, **kwargs):self.target=target
            def start(self):self.target()
        linked={'fresh':{'name':'Fresh'},'bad':{'name':'Bad'}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'DATA_ROOT',Path(tmp)),patch.object(trends,'LAST_START',0),patch.object(trends,'RUNNING',False),patch.object(trends,'ERRORS',[]),patch.object(trends,'sources',return_value=linked),patch.object(trends.threading,'Thread',InlineThread),patch.object(trends,'collect',side_effect=RuntimeError('secret')) as collect,patch.object(trends.time,'time',return_value=self.now):
            cache={'fresh':{'updated_at':self.now,'videos':[]},'bad':{'updated_at':0,'videos':[]}}
            store.atomic_json(trends.cache_path(),cache)
            trends.refresh()
            collect.assert_called_once_with('bad')
            self.assertEqual(store.read_json(trends.cache_path()),cache)
            self.assertFalse(trends.RUNNING)
            self.assertIn('Bad',trends.ERRORS[0])
            self.assertNotIn('secret',trends.ERRORS[0])
            self.assertFalse(trends.refresh()['running'])


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
