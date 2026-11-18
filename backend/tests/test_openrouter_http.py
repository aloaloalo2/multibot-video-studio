import io, sys, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openrouter_http


def busy(code=429, retry=None):
    return urllib.error.HTTPError('https://openrouter.ai', code, 'busy', {'Retry-After': retry} if retry else {}, io.BytesIO(b''))


class OpenRouterHttpTest(unittest.TestCase):
    def test_busy_provider_is_retried_until_it_answers(self):
        waits = []
        with patch.object(openrouter_http.urllib.request, 'urlopen', side_effect=[busy(), busy(503, '3'), 'ok']) as send:
            self.assertEqual(openrouter_http.urlopen('req', 10, sleep=waits.append), 'ok')
        self.assertEqual(send.call_count, 3)
        self.assertEqual(waits, [2, 3])

    def test_a_refused_request_is_not_repeated(self):
        with patch.object(openrouter_http.urllib.request, 'urlopen', side_effect=busy(400)) as send:
            with self.assertRaises(urllib.error.HTTPError):
                openrouter_http.urlopen('req', 10, sleep=lambda s: None)
        send.assert_called_once()

    def test_fallbacks_keep_the_other_provider_settings(self):
        payload = openrouter_http.fallbacks({'provider': {'allow_fallbacks': False, 'sort': 'price'}})
        self.assertEqual(payload['provider'], {'allow_fallbacks': True, 'sort': 'price'})


if __name__ == '__main__':
    unittest.main()
