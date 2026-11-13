import unittest
from unittest.mock import patch
import urllib.request

from PIL import Image
import test_backend as fixtures
import app
import store
import thumbnail_compare


class StatusAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass();cls.base_url=fixtures.BackendTest.base_url
        cls.cid=store.channel_id(fixtures.BackendTest.channel)
    @classmethod
    def tearDownClass(cls):fixtures.BackendTest.tearDownClass()
    request=fixtures.BackendTest.request

    def setUp(self):self.project=store.create_project(self.cid,'Read-only status fixture')

    def test_thumbnail_poll_never_builds_script_frames_or_gallery(self):
        with patch.object(app.thumbnail_gen,'defaults',side_effect=AssertionError('full thumbnail context')),patch.object(app.languages,'thumbnail_gallery',side_effect=AssertionError('full gallery')), \
                patch.object(app.thumbnail_gen,'state',return_value={'status':'running','writer':'claude','wishes':'private '*10000}),patch.object(app.languages,'thumbnail_status',return_value=[]):
            status,data=self.request('/api/projects/'+self.project['id']+'/thumbnail?compact=1')
        self.assertEqual(status,200);self.assertTrue(data['compact']);self.assertNotIn('wishes',data['job'])
        self.assertEqual(data['job']['writer'],'claude');self.assertNotIn('script',data)

    def test_analysis_summary_retains_full_report_for_explicit_detail_reads(self):
        pid=self.project['id'];identity='f'*24
        store.atomic_json(store.project_dir(pid)/'analysis-state.json',{'job_id':identity})
        report={'applied':True,'script_sha256':'h','recognized_text':'spoken '*10000,'words':[{'word':'one'}]*10000}
        store.atomic_json(store.project_dir(pid)/'analysis'/identity/'result.json',report)
        with patch.object(app,'load_job',return_value={'id':identity,'project_id':pid,'type':'speech','status':'complete'}):
            self.assertTrue(self.request(f'/api/projects/{pid}/analysis?compact=1')[1]['report']['applied'])
            self.assertNotIn('words',self.request(f'/api/projects/{pid}/analysis?compact=1')[1]['report'])
            self.assertEqual(self.request(f'/api/projects/{pid}/analysis')[1]['report']['recognized_text'],report['recognized_text'])

    def test_comparison_image_is_local_and_unknown_names_are_unavailable(self):
        pid=self.project['id'];source=store.project_dir(pid)/'reference.jpg';Image.new('RGB',(16,9),'blue').save(source)
        thumbnail_compare.record(pid,'Превью v1.png',reference={'id':'source'},image=source)
        url=thumbnail_compare.describe(pid,'Превью v1.png')['url']
        with urllib.request.urlopen(self.base_url+url) as response:
            self.assertEqual(response.headers.get_content_type(),'image/jpeg');self.assertEqual(response.read()[:2],b'\xff\xd8')
        self.assertEqual(self.request('/api/projects/'+'0'*24+'/thumbnail?compact=1')[0],404)

    def test_channel_notice_follows_real_receipt_without_starting_work(self):
        from channel_activity import Notices
        task={'channel_id':self.cid,'project_id':self.project['id'],'kind':'створення кадрів','status':'running'}
        with patch.object(app.channel_activity,'notices',Notices()), \
                patch.object(app,'studio_work_status',return_value={'busy':['work'],'active_channels':[self.cid],'activities':[task]}), \
                patch.object(app,'project_jobs',return_value={'створення кадрів':'done'}) as receipts:
            code,data=self.request('/api/studio/status')
            self.assertEqual(code,200)
            self.assertEqual(data['channel_notices'],{})
            receipts.assert_not_called()
            with patch.object(app,'studio_work_status',return_value={'busy':[],'active_channels':[],'activities':[]}):
                code,data=self.request('/api/studio/status')
            self.assertEqual(code,200)
            self.assertEqual(data['channel_notices'][self.cid]['status'],'done')
            receipts.assert_called_once_with(self.project['id'])
