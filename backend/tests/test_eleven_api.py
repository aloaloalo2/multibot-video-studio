import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import eleven_api
import languages


class ElevenModelsTest(unittest.TestCase):
    def test_balance_is_read_only_cached_and_refreshes_after_a_voice_job(self):
        eleven_api._balances.clear();self.addCleanup(eleven_api._balances.clear)
        vault=MagicMock();vault.read.return_value='account-one'
        with patch.object(eleven_api.credentials,'vault',return_value=vault),patch.object(eleven_api,'get') as get:
            get.return_value={'character_limit':100000,'character_count':73456}
            first=eleven_api.balance()
            self.assertEqual(first['remaining_credits'],26544)
            self.assertEqual(first['state'],'ready')
            self.assertEqual(eleven_api.balance(),first)
            get.assert_called_once_with('/user/subscription','account-one')
            get.return_value={'character_limit':100000,'character_count':74000}
            eleven_api.invalidate_balance()
            self.assertEqual(eleven_api.balance()['remaining_credits'],26000)
            get.return_value={'character_limit':100000,'character_count':75000}
            self.assertEqual(eleven_api.balance(refresh=True)['remaining_credits'],25000)
            vault.read.return_value='account-two'
            self.assertEqual(eleven_api.balance()['remaining_credits'],25000)
            self.assertEqual(get.call_count,4)

    def test_balance_failure_is_not_a_zero_or_a_falsely_current_number(self):
        eleven_api._balances.clear();self.addCleanup(eleven_api._balances.clear)
        vault=MagicMock();vault.read.return_value='key'
        with patch.object(eleven_api.credentials,'vault',return_value=vault),patch.object(eleven_api,'get') as get:
            get.side_effect=RuntimeError('permission denied')
            self.assertEqual(eleven_api.balance()['state'],'unavailable')
            self.assertNotIn('remaining_credits',eleven_api.balance())
            get.side_effect=None;get.return_value={'character_limit':40000,'character_count':1000}
            self.assertEqual(eleven_api.balance(refresh=True)['remaining_credits'],39000)
            get.side_effect=RuntimeError('offline')
            stale=eleven_api.balance(refresh=True)
            self.assertEqual((stale['state'],stale['remaining_credits']),('stale',39000))
            vault.read.side_effect=RuntimeError('no key')
            self.assertNotIn('remaining_credits',eleven_api.balance())

    def test_catalog_uses_account_rates_languages_and_capabilities(self):
        models = eleven_api.normalize_models([
            {"model_id": "eleven_v4", "can_do_text_to_speech": True, "name": "v4",
             "model_rates": {"character_cost_multiplier": 2, "cost_discount_multiplier": 0.5},
             "languages": [{"language_id": "uk"}], "maximum_text_length_per_request": 10000},
            {"model_id": "eleven_v4_turbo", "can_do_text_to_speech": False},
            {"model_id": "speech_to_speech", "can_do_voice_conversion": True},
            {"model_id": "eleven_v3", "can_do_text_to_speech": True},
            {"model_id": "eleven_flash_v2_5", "can_do_text_to_speech": True},
            {"model_id": "retired", "can_do_text_to_speech": True, "is_deprecated": True},
        ])
        self.assertEqual([x["id"] for x in models], ["eleven_v4", "eleven_v4_turbo"])
        self.assertEqual(models[0]["credits_per_char"], 1)
        self.assertEqual(models[0]["languages"], ["uk"])
        self.assertLessEqual(models[0]["max_chars"], 2000)

    def test_discovery_is_cached_and_an_api_failure_is_not_reported_as_verified(self):
        eleven_api._cache.clear()
        vault = MagicMock()
        vault.read.return_value = "test-secret"
        with patch.object(eleven_api.credentials, "vault", return_value=vault), patch.object(eleven_api, "get") as get:
            get.side_effect = [[{"model_id": "eleven_v4", "can_do_text_to_speech": True}],
                               {"character_limit": 40000, "character_count": 1000}, {"history": []}]
            self.assertEqual(eleven_api.catalog()["remaining_credits"], 39000)
            self.assertTrue(eleven_api.catalog()["verified"])
            self.assertEqual(get.call_count, 3)
            get.side_effect = RuntimeError("not available")
            failed = eleven_api.catalog(refresh=True)
            self.assertFalse(failed["verified"])
            self.assertEqual(failed["models"][0]["id"], "eleven_v4")
        eleven_api._cache.clear()

    def test_observed_rate_uses_actual_debits_and_rejects_unrelated_or_inconsistent_records(self):
        rows=[{"model_id":"eleven_v4_turbo","dialogue":[{"text":"x"*50}],"character_count_change_from":n*20,"character_count_change_to":n*20+10} for n in range(5)]
        self.assertEqual(eleven_api.observed_credit_rate(rows,"eleven_v4_turbo"),.2)
        self.assertIsNone(eleven_api.observed_credit_rate(rows,"eleven_v4"))
        rows[0]["character_count_change_to"]=1
        self.assertIsNone(eleven_api.observed_credit_rate(rows,"eleven_v4_turbo"))

    def test_rounded_stream_chunks_do_not_inflate_or_invent_an_account_tariff(self):
        points=[(41,9),(36,8),(42,9),(44,10),(21,5),(21,5),(33,7),(27,6),(25,6),
                (34,7),(34,7),(36,8),(33,7),(37,8),(28,6),(38,8),(32,7)]
        def rows(values):
            return [{'model_id':'eleven_v4_turbo','text':'x'*n,'character_count_change_from':0,
                     'character_count_change_to':c} for n,c in values]
        self.assertEqual(eleven_api.observed_credit_rate(rows(points),'eleven_v4_turbo'),.2)
        self.assertIsNone(eleven_api.observed_credit_rate(rows([(20,5)]*15),'eleven_v4_turbo'))

    def test_short_or_unavailable_history_keeps_recent_account_rate_until_metadata_changes(self):
        eleven_api._cache.clear();self.addCleanup(eleven_api._cache.clear)
        vault=MagicMock();vault.read.return_value='test-account'
        metadata=[{'model_id':'eleven_v4_turbo','model_rates':{'character_cost_multiplier':.5}}]
        rows=[{'model_id':'eleven_v4_turbo','text':'x'*100,'character_count_change_from':0,
               'character_count_change_to':20} for _ in range(5)]
        account={'character_limit':40000,'character_count':1000}
        with patch.object(eleven_api.credentials,'vault',return_value=vault),patch.object(eleven_api,'get') as get:
            get.side_effect=[metadata,account,{'history':rows}]
            first=eleven_api.catalog(True)['models'][0]
            self.assertEqual(first['credits_per_char'],.2)
            for history in ({'history':[]},RuntimeError('temporarily unavailable')):
                get.side_effect=[metadata,account,history]
                self.assertEqual(eleven_api.catalog(True)['models'][0]['credits_per_char'],.2)
            get.side_effect=[metadata,account,{'history':[]}]
            with patch.object(eleven_api.time,'time',return_value=first['credit_rate_observed_at']+86401):
                self.assertEqual(eleven_api.catalog(True)['models'][0]['credits_per_char'],.5)

    def test_modern_models_use_the_dialogue_http_route_and_no_unsupported_speed(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "out.mp3"
            with patch.object(languages, "key", return_value="secret"), patch.object(eleven_api, "model", return_value={"max_chars": 1800}), \
                    patch.object(languages, "request", return_value=b"x" * 2000) as request:
                languages.speak("elevenlabs", {"id": "cloned", "engine": "eleven_v4", "language": "uk"},
                                "Привіт.", target, "До цього", "Після цього", speed=1.15)
            url, raw, _, _ = request.call_args.args
            payload = json.loads(raw)
            self.assertIn("/text-to-dialogue/stream?", url)
            self.assertEqual(payload["inputs"], [{"text": "Привіт.", "voice_id": "cloned"}])
            self.assertEqual(payload["model_id"], "eleven_v4")
            self.assertEqual(payload["settings"], {"stability": 0.5, "similarity_boost": 0.75})
            self.assertEqual(payload["language_code"], "uk")
            self.assertNotIn("voice_settings", payload)
            self.assertTrue(target.is_file())

    def test_turbo_routes_through_websocket_instead_of_the_tts_endpoint(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(languages, "key", return_value="secret"), \
                patch.object(eleven_api, "model", return_value={"max_chars": 1800}), \
                patch.object(eleven_api, "streamed_dialogue", return_value=b"x" * 2000) as streamed, \
                patch.object(languages, "request") as request:
            languages.speak("elevenlabs", {"id": "clone", "engine": "eleven_v4_turbo"}, "Привіт.", Path(folder) / "out.mp3")
            streamed.assert_called_once_with("secret", "clone", "Привіт.", "eleven_v4_turbo")
            request.assert_not_called()

    def test_a_long_sample_is_split_and_joined_into_a_decodable_mp3(self):
        import subprocess
        import shutil
        if not shutil.which("ffmpeg"):
            self.skipTest("needs ffmpeg")
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            tone = folder / "tone.mp3"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=0.3", str(tone)], check=True)
            target, spoken = folder / "joined.mp3", []
            def request(url, raw, headers, what):
                text = json.loads(raw)["inputs"][0]["text"]
                spoken.append(text)
                return tone.read_bytes()
            with patch.object(languages, "key", return_value="secret"), patch.object(eleven_api, "model", return_value={"max_chars": 30}), \
                    patch.object(languages, "request", side_effect=request):
                text = " ".join(["Це перевірка довгого зразка."] * 6)
                languages.speak("elevenlabs", {"id": "clone", "engine": "eleven_v4"}, text, target)
            self.assertGreater(len(spoken), 1)
            self.assertTrue(all(len(text) <= 30 for text in spoken))
            self.assertEqual(" ".join(spoken), text)
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(target), "-f", "null", "-"], check=True)

    def test_websocket_flushes_short_text_and_requires_a_final_message(self):
        from websockets.sync import client
        socket = MagicMock()
        socket.recv.side_effect = [json.dumps({"audio": base64.b64encode(b"audio").decode()}), json.dumps({"is_final": True})]
        context = MagicMock()
        context.__enter__.return_value = socket
        with patch.object(client, "connect", return_value=context) as connect:
            self.assertEqual(eleven_api.streamed_dialogue("secret", "clone", "Short.", "eleven_v4_turbo"), b"audio")
            self.assertIn("/text-to-dialogue/stream-input?", connect.call_args.args[0])
            sent = [json.loads(call.args[0]) for call in socket.send.call_args_list]
            self.assertEqual(sent[0]["voices"], ["clone"])
            self.assertEqual(sent[-1], {"close_socket": True})
        socket.recv.side_effect = [json.dumps({"audio": base64.b64encode(b"partial").decode()}), TimeoutError()]
        with patch.object(client, "connect", return_value=context):
            with self.assertRaisesRegex(RuntimeError, "неповний звук не збережено"):
                eleven_api.streamed_dialogue("secret", "clone", "Short.", "eleven_v4_turbo")


if __name__ == "__main__":
    unittest.main()
