import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
import channel_competitors as competitors

IDENTITY='UC'+'a'*22

class CompetitorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.patches=[patch.object(store,'DATA_ROOT',self.root),patch.object(store,'get_channel_folder',return_value=self.root)]
        for item in self.patches:item.start()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()
    def test_channel_links_only_and_normalized_tabs(self):
        for value in ('youtube.com/@Example/videos','https://m.youtube.com/@Example?si=abc'):
            self.assertEqual(competitors.channel_url(value),'https://www.youtube.com/@Example')
        for value in ('https://youtube.com.evil.test/@test','http://127.0.0.1/@test','https://youtube.com@evil.test/@x','https://youtube.com/watch?v=abcdefghijk','https://youtu.be/abcdefghijk','https://youtube.com:999/@x','https://youtube.com/@x/../../test'):
            with self.subTest(value=value),self.assertRaises(store.StudioError):competitors.channel_url(value)
    def test_public_metadata_and_logo_are_saved_and_deduplicated_by_channel_identity(self):
        metadata={'metadata':{'channelMetadataRenderer':{'title':'A & B Channel','externalId':IDENTITY,'avatar':{'thumbnails':[{'url':'https://yt3.ggpht.com/avatar'}]}}}}
        image=io.BytesIO();Image.new('RGB',(400,400)).save(image,format='JPEG')
        with patch.object(competitors,'download',side_effect=[('var ytInitialData = '+json.dumps(metadata)+';').encode(),image.getvalue()]) as fetch:
            result=competitors.add('a'*16,'youtube.com/@Example')
        self.assertEqual(fetch.call_count,2)
        item=result['competitors'][0]
        self.assertEqual(item['name'],'A & B Channel')
        self.assertTrue(item['icon_url'].startswith('data:image/png;base64,'))
        with patch.object(competitors,'inspect') as inspect:
            self.assertEqual(competitors.add('a'*16,'youtube.com/@Example/videos'),result)
            inspect.assert_not_called()
        with patch.object(competitors,'inspect',return_value={**item,'source_url':'https://www.youtube.com/@Alias'}):
            self.assertEqual(len(competitors.add('a'*16,'youtube.com/@Alias')['competitors']),1)
        self.assertEqual(competitors.read('b'*16),[])
        self.assertEqual(competitors.remove('a'*16,IDENTITY),{'competitors':[]})
        self.assertEqual(competitors.read('a'*16),[])
    def test_failure_preserves_list_and_never_fetches_untrusted_avatar(self):
        metadata={'metadata':{'channelMetadataRenderer':{'title':'Channel','externalId':IDENTITY,'avatar':{'thumbnails':[{'url':'http://127.0.0.1/private'}]}}}}
        with patch.object(competitors,'download',return_value=('var ytInitialData = '+json.dumps(metadata)).encode()) as fetch,self.assertRaises(store.StudioError):
            competitors.add('a'*16,'youtube.com/@Bad')
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(competitors.read('a'*16),[])

class CompetitorHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_backend
        cls.fixture=test_backend.BackendTest
        cls.fixture.setUpClass()
        cls.cid=store.channel_id(cls.fixture.channel)
        cls.base_url=cls.fixture.base_url
    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()
    def request(self,*args,**kwargs):return self.fixture.request(self,*args,**kwargs)
    def test_add_list_remove_are_project_independent(self):
        row={'id':IDENTITY,'name':'Competitor','url':'https://www.youtube.com/channel/'+IDENTITY,'source_url':'https://www.youtube.com/@Example','icon_url':'data:image/png;base64,YQ=='}
        endpoint='/api/channels/'+self.cid+'/competitors'
        with patch.object(competitors,'inspect',return_value=row):
            code,data=self.request(endpoint,'POST',{'url':'https://youtube.com/@Example'})
        self.assertEqual(code,200)
        self.assertEqual(data['competitors'],[row])
        self.assertEqual(self.request(endpoint),(200,data))
        code,data=self.request(endpoint+'/'+IDENTITY,'DELETE')
        self.assertEqual((code,data),(200,{'competitors':[]}))
        self.assertEqual(self.request('/api/channels/'+'0'*16+'/competitors')[0],404)
