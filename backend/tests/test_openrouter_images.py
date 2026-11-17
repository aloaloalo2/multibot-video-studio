import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import openrouter_images as images
import store


class OpenRouterSheetsTest(unittest.TestCase):
    # 17 November 2026: Codex's limit was out, the author had one episode's props drawn through OpenRouter
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for stub in (patch.object(store, 'project_dir', return_value=self.root),
                     patch.object(store, 'load_project', return_value={'id': 'p' * 24})):
            stub.start(); self.addCleanup(stub.stop)

    def png(self):
        buffer = io.BytesIO(); Image.new('RGBA', (6, 4), (0, 0, 0, 0)).save(buffer, 'PNG')
        return base64.b64encode(buffer.getvalue()).decode()

    def test_an_episode_on_openrouter_draws_a_sheet_and_records_its_cost(self):
        self.assertEqual(images.setting('p' * 24), {})
        images.set_provider('p' * 24, 'openrouter')
        answer = json.dumps({'id': 'gen-1', 'usage': {'cost': 0.0127}, 'data': [{'b64_json': self.png()}]}).encode()
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with patch.object(images.credentials, 'vault') as vault, \
             patch.object(images.urllib.request, 'urlopen', return_value=Response(answer)) as call:
            vault.return_value.read.return_value = 'key'
            result = images.draw('p' * 24, 'six props')
        sent = json.loads(call.call_args.args[0].data)
        self.assertEqual((sent['model'], sent['background']), ('openai/gpt-image-1-mini', 'transparent'))
        self.assertEqual(result['cost'], 0.0127)
        self.assertEqual(images.spent('p' * 24), {'sheets': 1, 'usd': 0.0127})
        images.set_provider('p' * 24, 'codex')
        with self.assertRaises(store.StudioError):
            images.draw('p' * 24, 'six props')


    def test_continue_through_openrouter_draws_every_picture_and_an_opaque_one_comes_back_as_png(self):
        # Codex ran out of its limit mid-film and the host's sheet on grey was waiting for it (17 November 2026)
        self.assertNotIn('all', images.set_provider('p' * 24, 'openrouter'))
        self.assertTrue(images.set_provider('p' * 24, 'openrouter', everything=True)['all'])
        self.assertTrue(images.setting('p' * 24)['all'])
        buffer = io.BytesIO(); Image.new('RGB', (6, 4), (128, 128, 128)).save(buffer, 'JPEG')
        answer = json.dumps({'id': 'gen-2', 'usage': {'cost': 0.02}, 'data': [{'b64_json': base64.b64encode(buffer.getvalue()).decode()}]}).encode()
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with patch.object(images.credentials, 'vault') as vault, \
             patch.object(images.urllib.request, 'urlopen', return_value=Response(answer)) as call:
            vault.return_value.read.return_value = 'key'
            result = images.draw('p' * 24, 'six poses on grey', transparent=False)
        self.assertEqual(json.loads(call.call_args.args[0].data)['background'], 'opaque')
        with Image.open(io.BytesIO(base64.b64decode(result['png']))) as image:
            self.assertEqual(image.format, 'PNG')


    def test_a_picture_from_the_hosts_avatar_goes_to_the_stronger_model(self):
        images.set_provider('p' * 24, 'openrouter')
        avatar = self.root / 'avatar.png'; Image.new('RGB', (4, 4)).save(avatar)
        answer = json.dumps({'id': 'gen-3', 'usage': {'cost': 0.06}, 'data': [{'b64_json': self.png()}]}).encode()
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with patch.object(images.credentials, 'vault') as vault, \
             patch.object(images.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response(answer)) as call:
            vault.return_value.read.return_value = 'key'
            images.draw('p' * 24, 'the host in three poses', refs=[avatar])
            face = json.loads(call.call_args.args[0].data)['model']
            images.draw('p' * 24, 'six props')
            props = json.loads(call.call_args.args[0].data)['model']
        self.assertEqual((face, props), (images.FACE_MODEL, images.DEFAULT_MODEL))


    def test_an_animated_film_draws_through_openrouter_with_nothing_to_choose(self):
        with patch.object(store, 'get_channel_folder', return_value=self.root), \
             patch.object(store, 'read_channel_settings', return_value={}), \
             patch.object(store, 'project_animated', return_value=True):
            self.assertEqual(images.setting('p' * 24)['provider'], 'openrouter')
            images.set_provider('p' * 24, 'codex')   # an episode switched back by hand keeps Codex
            self.assertEqual(images.setting('p' * 24), {})
        with patch.object(store, 'get_channel_folder', return_value=self.root), \
             patch.object(store, 'read_channel_settings', return_value={}), \
             patch.object(store, 'project_animated', return_value=False):
            images.path('p' * 24).unlink()
            self.assertEqual(images.setting('p' * 24), {})   # a photo channel's pictures stay with Codex


if __name__ == '__main__':
    unittest.main()
