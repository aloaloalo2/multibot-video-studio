import base64
import hashlib
import json
import sys
import tempfile
import urllib.parse
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import eleven_api
import languages


class ElevenModelsTest(unittest.TestCase):
    NOW = 1793715000

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for mocked in (patch.object(eleven_api.store,'DATA_ROOT',Path(self.temp.name)),
                       patch.object(eleven_api.time,'time',return_value=self.NOW)):
            mocked.start();self.addCleanup(mocked.stop)
        for state in (eleven_api._cache,eleven_api._credit_rates,eleven_api._credit_scopes,eleven_api._balances):
            state.clear();self.addCleanup(state.clear)

    def history_rows(self, rate=.2, count=5, stamp=None):
        return [{'history_item_id':f'row-{number}','model_id':'eleven_v4_turbo','source':'TTS',
                 'text':'x'*100,'character_count_change_from':0,'character_count_change_to':100*rate,
                 'date_unix':self.NOW-10 if stamp is None else stamp} for number in range(count)]

    def metadata(self, rate=.5):
        return [{'model_id':'eleven_v4_turbo','model_rates':{'character_cost_multiplier':rate}}]

    def account(self, tier='creator'):
        return {'tier':tier,'status':'active','currency':'usd','character_limit':40000,'character_count':1000}

    def discovery(self, history, secret='test-account', metadata=None, account=None):
        vault=MagicMock();vault.read.return_value=secret
        with patch.object(eleven_api.credentials,'vault',return_value=vault),patch.object(eleven_api,'get') as get:
            get.side_effect=[metadata or self.metadata(),self.account() if account is None else account,history]
            return eleven_api.catalog(True)['models'][0]

    def reset_memory(self):
        eleven_api._cache.clear();eleven_api._credit_rates.clear();eleven_api._credit_scopes.clear()

    def rate_path(self, secret='test-account'):
        return eleven_api.credit_rate_path(hashlib.sha256(secret.encode()).hexdigest(),'eleven_v4_turbo')

    def test_observed_rate_survives_a_process_cache_reset_with_short_or_forbidden_history(self):
        first=self.discovery({'history':self.history_rows()})
        self.assertEqual(first['credits_per_char'],.2)
        self.assertTrue(first['credit_rate_estimate'])
        self.assertTrue(self.rate_path().is_file())
        self.assertNotIn('test-account',self.rate_path().read_text())
        self.assertNotIn('xxxxx',self.rate_path().read_text())
        for history in ({'history':[]},RuntimeError('history permission denied')):
            self.reset_memory()
            observed=self.discovery(history)
            self.assertEqual(observed['credits_per_char'],.2)
            self.assertEqual(observed['credit_rate_observed_at'],self.NOW-10)

    def test_retained_rate_is_scoped_to_key_model_catalog_and_subscription(self):
        self.discovery({'history':self.history_rows()})
        self.reset_memory()
        self.assertEqual(self.discovery({'history':[]},secret='different-account')['credits_per_char'],.5)
        self.reset_memory()
        # The same old history must not be stamped as evidence for a newly seen tier.
        self.assertEqual(self.discovery({'history':self.history_rows()},account=self.account('pro'))['credits_per_char'],.5)
        self.reset_memory()
        self.assertEqual(self.discovery({'history':self.history_rows()},metadata=self.metadata(.6),account=self.account('pro'))['credits_per_char'],.6)
        with patch.object(eleven_api.time,'time',return_value=self.NOW+2):
            self.assertEqual(self.discovery({'history':self.history_rows(stamp=self.NOW+1)},metadata=self.metadata(.6),account=self.account('pro'))['credits_per_char'],.2)

    def test_subscription_failure_cannot_reuse_or_persist_an_unscoped_rate(self):
        self.discovery({'history':self.history_rows()})
        self.reset_memory()
        self.assertEqual(self.discovery({'history':self.history_rows()},account=RuntimeError('no user permission'))['credits_per_char'],.5)
        self.reset_memory()
        restored=self.discovery({'history':[]})
        self.assertEqual(restored['credits_per_char'],.2)
        self.assertEqual(restored['credit_rate_observed_at'],self.NOW-10)

    def test_old_evidence_is_not_refreshed_by_reading_the_same_records_again(self):
        rows=self.history_rows(stamp=self.NOW-50)
        self.discovery({'history':rows})
        with patch.object(eleven_api.time,'time',return_value=self.NOW+100):
            self.assertEqual(self.discovery({'history':rows})['credit_rate_observed_at'],self.NOW-50)
        self.reset_memory()
        with patch.object(eleven_api.time,'time',return_value=self.NOW+eleven_api.CREDIT_RATE_TTL):
            self.assertEqual(self.discovery({'history':rows})['credits_per_char'],.5)

    def test_new_conflicting_debit_invalidates_disk_and_memory_even_when_history_then_fails(self):
        self.discovery({'history':self.history_rows()})
        mixed=self.history_rows(count=10)
        mixed[-1].update(character_count_change_to=50,date_unix=self.NOW)
        self.assertIsNone(eleven_api.observed_credit_rate(mixed,'eleven_v4_turbo'))
        self.assertEqual(self.discovery({'history':[mixed[-1]]})['credits_per_char'],.5)
        self.assertEqual(self.discovery(RuntimeError('offline'))['credits_per_char'],.5)
        self.reset_memory()
        self.assertEqual(self.discovery({'history':[]})['credits_per_char'],.5)
        self.assertEqual(json.loads(self.rate_path().read_text())['reason'],'conflicting_debit')

    def test_all_debits_in_the_newest_second_can_veto_regardless_of_row_order(self):
        rows=self.history_rows(count=10)
        rows[-1].update(date_unix=self.NOW,character_count_change_to=50)
        rows[-2]['date_unix']=self.NOW
        self.assertIsNone(eleven_api.observed_credit_rate(rows,'eleven_v4_turbo'))
        self.assertIsNone(eleven_api.observed_credit_rate(list(reversed(rows)),'eleven_v4_turbo'))

    def test_expired_future_mismatched_and_malformed_cache_is_rejected(self):
        self.discovery({'history':self.history_rows()})
        good=json.loads(self.rate_path().read_text())
        invalid=[{'rate':True},{'rate':float('nan')},{'rate':float('inf')},{'rate':0},
                 {'observed_at':self.NOW+1},{'observed_at':self.NOW-eleven_api.CREDIT_RATE_TTL-1},
                 {'checked_at':self.NOW+1},{'evidence_latest_at':self.NOW+1},{'schema':2},
                 {'key_signature':'other'},{'model':'eleven_v4'},{'samples':True},{'characters':10},
                 {'subscription_signature':'other'},{'catalog_credits_per_char':.7}]
        for change in invalid:
            with self.subTest(change=change):
                self.reset_memory();self.rate_path().write_text(json.dumps({**good,**change}))
                self.assertEqual(self.discovery({'history':[]})['credits_per_char'],.5)
        for raw in ('{broken','null','[]'):
            self.reset_memory();self.rate_path().write_text(raw)
            self.assertEqual(self.discovery({'history':[]})['credits_per_char'],.5)

    def test_history_pages_find_longer_records_and_stop_once_rate_is_unambiguous(self):
        short=self.history_rows()
        for row in short:row['text']='short';row['character_count_change_to']=1
        pages=[{'history':short,'has_more':True,'last_history_item_id':'cursor-1'},
               {'history':self.history_rows(),'has_more':True,'last_history_item_id':'cursor-2'}]
        with patch.object(eleven_api,'get',side_effect=pages) as get:
            rows=eleven_api.recent_history('secret','eleven_v4_turbo',self.NOW)
        self.assertEqual(eleven_api.observed_credit_rate(rows,'eleven_v4_turbo'),.2)
        self.assertEqual(get.call_count,2)
        query=urllib.parse.parse_qs(urllib.parse.urlsplit(get.call_args_list[1].args[0]).query)
        self.assertEqual(query['start_after_history_item_id'],['cursor-1'])

    def test_history_page_limit_repeated_cursor_duplicate_and_missing_ids(self):
        single=self.history_rows(count=1)
        repeat={'history':single*8,'has_more':True,'last_history_item_id':'same'}
        with patch.object(eleven_api,'get',return_value=repeat) as get:
            rows=eleven_api.recent_history('secret','eleven_v4_turbo',self.NOW)
        self.assertEqual((get.call_count,len(rows)),(2,1))
        pages=[{'history':[],'has_more':True,'last_history_item_id':str(index)} for index in range(10)]
        with patch.object(eleven_api,'get',side_effect=pages) as get:
            self.assertEqual(eleven_api.recent_history('secret','eleven_v4_turbo',self.NOW),[])
            self.assertEqual(get.call_count,3)
        anonymous=self.history_rows()
        for row in anonymous:row.pop('history_item_id')
        with patch.object(eleven_api,'get',return_value={'history':anonymous}):
            self.assertEqual(eleven_api.recent_history('secret','eleven_v4_turbo',self.NOW),[])

    def test_history_ignores_old_future_wrong_source_and_invalid_debits(self):
        rows=self.history_rows(count=7)
        rows[0]['date_unix']=self.NOW-eleven_api.CREDIT_RATE_TTL-1
        rows[1]['date_unix']=self.NOW+1
        rows[2]['source']='voice_changer'
        rows[3]['character_count_change_to']=True
        rows[4]['character_count_change_to']=float('nan')
        rows[5]['date_unix']=True
        rows[6]['character_count_change_to']=float('inf')
        with patch.object(eleven_api,'get',return_value={'history':rows}):
            self.assertEqual(eleven_api.recent_history('secret','eleven_v4_turbo',self.NOW),[])
        for rate in (True,float('inf'),float('nan')):
            self.assertIsNone(eleven_api.normalize_models(self.metadata(rate))[0]['credits_per_char'])

    def test_cache_io_failure_does_not_break_current_discovery(self):
        with patch.object(eleven_api.store,'atomic_json',side_effect=OSError('read-only disk')):
            self.assertEqual(self.discovery({'history':self.history_rows()})['credits_per_char'],.2)
            self.assertEqual(self.discovery(RuntimeError('history permission denied'))['credits_per_char'],.2)
        self.reset_memory()
        self.rate_path().parent.mkdir(parents=True,exist_ok=True)
        self.rate_path().mkdir()
        self.assertEqual(self.discovery({'history':[]})['credits_per_char'],.5)

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
        rows=self.history_rows()
        account=self.account()
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
