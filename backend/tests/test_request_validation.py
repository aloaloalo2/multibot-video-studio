"""Malformed API input must fail before any project, provider or settings mutation."""
import io
import json
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import test_backend as fixtures
import app
import store


class RequestValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.base_url = fixtures.BackendTest.base_url

    @classmethod
    def tearDownClass(cls):
        fixtures.BackendTest.tearDownClass()

    def test_non_object_and_non_finite_json_never_reaches_a_mutation(self):
        inputs = ['null', 'false', '0', '[]', '[1]', '"text"',
                  '{"speed": NaN}', '{"speed": Infinity}', '{"speed": -Infinity}',
                  '{"speed": 1e999}', '{"nested": [1, 1e999]}',
                  '{"nested":' + '[' * 1200 + '0' + ']' * 1200 + '}']
        with patch.object(app.Handler, 'route_mutation') as mutation:
            for raw in inputs:
                with self.subTest(raw=raw[:45]):
                    request = urllib.request.Request(self.base_url + '/api/settings',
                        data=raw.encode(), method='PATCH', headers={'Content-Type': 'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(request, timeout=5)
                    self.assertEqual(error.exception.code, 400)
                    self.assertIn('error', json.loads(error.exception.read()))
            mutation.assert_not_called()

    def test_valid_object_keeps_ordinary_number_types(self):
        handler = object.__new__(app.Handler)
        raw = b'{"speed": 0.91, "count": 3, "enabled": true}'
        handler.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        self.assertEqual(handler.read_json_body(), {'speed': .91, 'count': 3, 'enabled': True})

    def test_truncated_but_otherwise_valid_json_is_not_accepted(self):
        handler = object.__new__(app.Handler)
        handler.headers = {'Content-Type': 'application/json', 'Content-Length': '4'}
        handler.rfile = io.BytesIO(b'{}')
        with self.assertRaisesRegex(store.StudioError, 'не повністю'):
            handler.read_json_body()

    def test_media_accepts_suffix_ranges_and_rejects_empty_or_reversed_ranges(self):
        sample=store.DATA_ROOT/'range-sample.mp4'
        sample.parent.mkdir(parents=True,exist_ok=True)
        sample.write_bytes(b'0123456789')
        def serve(handler,path,query):
            return handler.serve_media(sample)
        with patch.object(app.Handler,'route_get',serve):
            for header,expected,content_range in [('bytes=-3',b'789','bytes 7-9/10'),
                ('bytes=-30',b'0123456789','bytes 0-9/10'),('bytes=3-',b'3456789','bytes 3-9/10')]:
                with self.subTest(header=header):
                    request=urllib.request.Request(self.base_url+'/media',headers={'Range':header})
                    with urllib.request.urlopen(request,timeout=5) as response:
                        self.assertEqual(response.status,206);self.assertEqual(response.read(),expected)
                        self.assertEqual(response.headers['Content-Range'],content_range)
            for header in ['bytes=-0','bytes=-','bytes=5-3','bytes=10-','bytes=0-1,3-4']:
                request=urllib.request.Request(self.base_url+'/media',headers={'Range':header})
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request,timeout=5)
                self.assertEqual(error.exception.code,416)
