import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import idea_reference as reference
import episode_ideas as ideas
import store
import test_backend as fixtures

VIDEO = 'jNQXAC9IVRw'


class ReferenceImportTest(unittest.TestCase):
    def test_only_public_youtube_video_ids_reach_fixed_endpoints(self):
        for url in ('https://youtu.be/' + VIDEO, 'https://www.youtube.com/watch?v=' + VIDEO + '&t=20',
                    'https://youtube.com/shorts/' + VIDEO, 'https://m.youtube.com/live/' + VIDEO):
            self.assertEqual(reference.video_id(url), VIDEO)
        for url in (None, 'http://127.0.0.1:8770/', 'file:///etc/passwd', 'https://youtube.com.evil.test/watch?v=' + VIDEO,
                    'https://youtube.com@127.0.0.1/watch?v=' + VIDEO, 'https://youtube.com:8770/watch?v=' + VIDEO,
                    'https://youtu.be/../../secret', 'https://youtube.com/playlist?list=hello'):
            with self.subTest(url=url), self.assertRaises(store.StudioError):
                reference.video_id(url)

    def test_metadata_and_decoded_picture_are_cached_without_model_work(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(store, 'DATA_ROOT', Path(temp)), \
             patch.object(store, 'get_channel_folder', return_value=Path(temp)):
            picture = io.BytesIO(); Image.new('RGB', (32, 18)).save(picture, format='JPEG')
            with patch.object(reference, 'download', side_effect=[json.dumps({'title': 'Exact title 7?', 'author_name': 'Source channel'}).encode(), picture.getvalue()]) as fetch:
                first = reference.inspect('a' * 16, 'https://youtu.be/' + VIDEO)
                again = reference.inspect('a' * 16, 'https://youtube.com/watch?v=' + VIDEO)
            self.assertEqual(first, again)
            self.assertEqual(first['title'], 'Exact title 7?')
            self.assertEqual(fetch.call_count, 2)
            self.assertTrue(fetch.call_args_list[0].args[0].startswith('https://www.youtube.com/oembed?'))
            self.assertEqual(fetch.call_args_list[1].args[0], f'https://i.ytimg.com/vi/{VIDEO}/maxresdefault.jpg')
            self.assertTrue((reference.folder('a' * 16, VIDEO) / 'thumbnail.jpg').is_file())
            with self.assertRaises(store.StudioError): reference.read('b' * 16, VIDEO)

    def test_empty_metadata_or_invalid_image_creates_no_ready_reference(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(store, 'DATA_ROOT', Path(temp)), \
             patch.object(store, 'get_channel_folder', return_value=Path(temp)):
            for responses in ([b'{"title":null}'], [b'{"title":"Title"}', b'not a picture']):
                with patch.object(reference, 'download', side_effect=responses), self.assertRaises(store.StudioError):
                    reference.inspect('a' * 16, 'https://youtu.be/' + VIDEO)
            self.assertFalse((reference.folder('a' * 16, VIDEO) / 'reference.json').exists())


class CloneEpisodeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.cid = store.channel_id(fixtures.BackendTest.channel)
        cls.base_url = fixtures.BackendTest.base_url

    @classmethod
    def tearDownClass(cls): fixtures.BackendTest.tearDownClass()
    request = fixtures.BackendTest.request

    def setUp(self):
        ideas.ACTIVE.clear()
        self.root = reference.folder(self.cid, VIDEO)
        self.root.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (32, 18)).save(self.root / 'thumbnail.jpg')
        self.data = {'id': VIDEO, 'title': 'Source title', 'url': 'https://youtu.be/' + VIDEO, 'author': 'Presenter'}
        store.atomic_json(self.root / 'reference.json', self.data)

    def test_clone_has_project_bound_reference_and_idempotent_openings_without_consuming_topics(self):
        topics = {'id': 'catalog', 'ideas': [{'title': 'Existing idea'}]}
        store.atomic_json(ideas.topics_path(self.cid), topics)
        body = {'action': 'clone_openings', 'reference_id': VIDEO, 'title': 'My edited title 7?',
                'target_words': 1200, 'request_id': 'clone-openings-1'}
        with patch.object(ideas, 'context', return_value={'channel': 'Test', 'sample_count': 0}), patch.object(ideas, 'Thread') as thread:
            code, first = self.request(f'/api/channels/{self.cid}/episode-ideas', 'POST', body)
            self.assertEqual(code, 202, first)
            code, again = self.request(f'/api/channels/{self.cid}/episode-ideas', 'POST', body)
            self.assertEqual(code, 202, again)
            self.assertEqual(first['project_id'], again['project_id'])
            self.assertEqual(thread.call_count, 1)
        project = store.load_project(first['project_id'])
        self.assertEqual(project['name'], body['title'])
        self.assertEqual(reference.for_project(project['id'])[0], self.data)
        self.assertEqual(ideas.read_project(project['id'])['clone_reference'], self.data)
        self.assertEqual(store.read_json(ideas.topics_path(self.cid)), topics)
        with patch.object(ideas, 'Thread') as thread:
            code, _ = self.request(f'/api/channels/{self.cid}/episode-ideas', 'POST', {**body, 'title': 'Different'})
            self.assertEqual(code, 409); thread.assert_not_called()

    def test_import_and_local_thumbnail_routes_never_start_a_paid_job(self):
        with patch.object(ideas, 'Thread') as thread:
            code, data = self.request(f'/api/channels/{self.cid}/idea-reference', 'POST', {'url': 'https://youtu.be/' + VIDEO})
            self.assertEqual(code, 200)
            code, image = self.request(f'/api/channels/{self.cid}/idea-reference/{VIDEO}/thumbnail')
            self.assertEqual(code, 200)
            self.assertTrue(image.startswith(b'\xff\xd8'))
            thread.assert_not_called()

    def test_auto_thumbnail_is_one_attempt_only_after_accepted_script(self):
        project = store.create_project(self.cid, 'Clone cover')
        data = {'id': 'run', 'channel_id': self.cid, 'project_id': project['id'], 'clone_reference': self.data, 'completed': True}
        with patch('thumbnail_gen.start', return_value={'status': 'running'}) as start, patch.object(ideas, 'save_draft'):
            project['voice_script'] = {'text': 'Our own script'}
            with patch.object(store, 'load_project', return_value=project):
                reference.start_thumbnail(data); reference.start_thumbnail(data)
                self.assertEqual(start.call_count, 1)
                self.assertEqual(start.call_args.kwargs['writer'], 'trending')
                reference.start_thumbnail({**data, 'clone_thumbnail_attempted': False, 'review_required': True})
                self.assertEqual(start.call_count, 1)
