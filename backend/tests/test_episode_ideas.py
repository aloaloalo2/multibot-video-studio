import copy
import unittest
from contextlib import nullcontext
from unittest.mock import patch
import test_backend as fixtures
import store
import episode_ideas as ideas

class TitleCleanupTest(unittest.TestCase):
    def test_numbered_suggestions_keep_title_counts_and_ukrainian_translation(self):
        rows = [{'title': f'{i + 1}. {i + 5} Geräusche am Auto!',
                 'uk': f'{i + 1}) {i + 5} звуків в авто!'} for i in range(5)]
        accepted = ideas.validate_titles({'ideas': rows}, {'previous_titles': []})
        self.assertEqual(accepted[0], {'title': '5 Geräusche am Auto!', 'uk': '5 звуків в авто!'})
        self.assertEqual(accepted[4]['title'], '9 Geräusche am Auto!')
        self.assertEqual(ideas.clean_title('1.5 Liter im Motor?'), '1.5 Liter im Motor?')

    def test_invisible_soft_hyphens_do_not_reach_titles_or_translations(self):
        self.assertEqual(ideas.clean_title('Що, якщо ти проки\u00adнешся?'), 'Що, якщо ти прокинешся?')
        self.assertEqual(ideas.clean_title('1. What\u200b If?'), 'What If?')
        self.assertIn('word endings, agreement, person, tense, syntax', ideas.TOPIC_PROMPT)
        self.assertIn('BOTH the original titles and Ukrainian translations', ideas.TOPIC_PROMPT)

    def test_numbering_cannot_hide_a_previous_title(self):
        rows = [{'title': f'{i + 1}. {i + 5} Geräusche am Auto!'} for i in range(5)]
        with self.assertRaises(ValueError):
            ideas.validate_titles({'ideas': rows}, {'previous_titles': ['1. 5 Geräusche am Auto!']})

    def test_reworded_titles_with_same_subject_are_rejected(self):
        rows = [{'title':f'Fresh headline number {i}!', 'subject':f'different subject {i}'} for i in range(5)]
        rows[0]['subject'] = 'choosing winter tyres'
        with self.assertRaises(ValueError):
            ideas.validate_titles({'ideas':rows}, {'previous_titles':[], 'previous_topic_history':[{'title':'Old tyre headline', 'subject':'Choosing winter tyres'}]})
        rows[0]['subject'] = rows[1]['subject']
        with self.assertRaises(ValueError):
            ideas.validate_titles({'ideas':rows}, {'previous_titles':[]})


class ReadingTranslationTest(unittest.TestCase):
    def test_russian_topics_and_hooks_have_no_ukrainian_duplicate_including_saved_rows(self):
        saved={'ideas':[{'title':'Просыпаюсь в 4 утра после 60?', 'uk':'Прокидаюся о 4 ранку після 60?'}],
               'openings':[{'text':'Почему это происходит после 60 лет?', 'uk':'Чому це відбувається після 60 років?'}]}
        with patch.object(ideas, 'reader_language', return_value='ru'):
            shown=ideas.public(saved)
        self.assertEqual(shown['ideas'][0]['uk'], '')
        self.assertEqual(shown['openings'][0]['uk'], '')
        self.assertEqual(shown['ideas'][0]['title'], 'Просыпаюсь в 4 утра после 60?')
        self.assertTrue(saved['ideas'][0]['uk'])  # read-only normalization

    def test_short_russian_titles_without_exclusive_letters_still_need_no_translation(self):
        for title in ('7 причин боли в спине после 60', 'Сон после 60 лет', 'Почему болит спина'):
            with self.subTest(title=title):
                self.assertEqual(ideas.reading_translation(title, 'Український переклад'), '')

    def test_english_and_german_reading_translations_are_preserved_without_detection(self):
        with patch.object(ideas, 'reader_language') as detector:
            self.assertEqual(ideas.reading_translation('7 sounds to check', '7 звуків для перевірки'), '7 звуків для перевірки')
            self.assertEqual(ideas.reading_translation('4 Stunden Schlaf?', '4 години сну?'), '4 години сну?')
            self.assertEqual(ideas.reading_translation('A story about Россия today', 'Історія про Росію'), 'Історія про Росію')
        detector.assert_not_called()

    def test_correct_empty_translation_needs_no_language_classifier(self):
        with patch.object(ideas, 'reader_language') as detector:
            self.assertEqual(ideas.reading_translation('Сон после 60 лет', ''), '')
        detector.assert_not_called()


class EpisodeIdeasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BackendTest.setUpClass()
        cls.cid = store.channel_id(fixtures.BackendTest.channel)
        cls.base_url=fixtures.BackendTest.base_url
    @classmethod
    def tearDownClass(cls): fixtures.BackendTest.tearDownClass()
    def setUp(self):
        ideas.ACTIVE.clear()
        ideas.path(self.cid).unlink(missing_ok=True)
        ideas.topics_path(self.cid).unlink(missing_ok=True)
        ideas.path(self.cid).with_name('episode-idea-history.json').unlink(missing_ok=True)
    request = fixtures.BackendTest.request
    def test_saved_suggestions_are_cleaned_without_resetting_work(self):
        saved = {'status':'done', 'stage':'ideas', 'id':'saved-draft', 'target_words':1200,
                 'ideas':[{'title':'1. 7 Geräusche am Auto!', 'uk':'1. 7 звуків в авто!'}]}
        store.atomic_json(ideas.path(self.cid), saved)
        current = ideas.read(self.cid)
        self.assertEqual(current['ideas'][0]['title'], '7 Geräusche am Auto!')
        self.assertEqual(current['ideas'][0]['uk'], '7 звуків в авто!')
        self.assertEqual((current['id'], current['target_words'], current['status']),
                         ('saved-draft',1200,'done'))
    def test_topics_use_varied_clickworthy_angles_in_one_request(self):
        data=self.begin({'action':'ideas'})
        # A manual edit made after reservation must reach the actual model prompt.
        ledger = ideas.channel_topics.path(store.get_channel_folder(self.cid))
        store.atomic_text(ledger, ledger.read_text(encoding='utf-8') + 'Manual history added after reservation\n')
        titles=["Why your car smells sweet", "5 sounds worth checking before a long trip",
                "The overlooked part behind a rough idle", "Your winter tyres lose grip sooner than you think",
                "This tiny dashboard light can save an expensive repair"]
        with patch.object(ideas,'deepseek',return_value={'ideas':[{'title':t,'uk':''} for t in titles]}) as model:
            result=self.finish(data)
        model.assert_called_once()
        prompt=model.call_args.args[0]
        self.assertIn('Manual history added after reservation', prompt)
        self.assertNotIn('matching the title structure',prompt)
        self.assertIn('at least four different editorial angles',prompt)
        self.assertIn('At least three titles must be one sentence',prompt)
        self.assertIn('at most one may',prompt)
        self.assertIn('do not invent CTR',prompt)
        self.assertEqual([row['title'] for row in result['ideas']],titles)
        with patch.object(ideas,'deepseek') as model:
            self.assertEqual(ideas.read(self.cid)['ideas'],result['ideas'])
        model.assert_not_called()

    def test_german_date_in_six_sentence_hooks_is_accepted_without_paid_retry(self):
        draft = self.begin({'action':'ideas'})
        with patch.object(ideas, 'deepseek', return_value={'ideas':[{'title':f'Original tyre story {i}', 'uk':''} for i in range(5)]}):
            self.finish(draft)
        draft = self.begin({'action':'openings', 'index':0})
        hook = ('Wir prüfen am 1. Oktober 2024 die Reifen. Die erste Zahl steht auf der Flanke. '
                'Du kannst sie selbst lesen. Das Profil prüfen wir danach. Ich zeige dir jeden Schritt. Am Ende kennst du alle Angaben.')
        with patch.object(ideas, 'opus', return_value={'openings':[{'text':hook, 'uk':''} for _ in range(4)]}) as model:
            result = self.finish(draft)
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual([row['text'] for row in result['openings']], [hook]*4)
        model.assert_called_once()

    def test_hook_sentence_counts_do_not_block_saved_results(self):
        draft = self.begin({'action':'ideas'})
        with patch.object(ideas, 'deepseek', return_value={'ideas':[{'title':f'Fresh hook format story {i}', 'uk':''} for i in range(5)]}):
            self.finish(draft)
        draft = self.begin({'action':'openings', 'index':0})
        hooks = [{'text': 'A sentence. ' * count, 'uk':''} for count in (1, 5, 7, 10)]
        with patch.object(ideas, 'opus', return_value={'openings':hooks}) as model, patch('planner.split_sentences', side_effect=AssertionError('Hook sentence counting must not run')):
            result = self.finish(draft)
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(result['openings'], hooks)
        model.assert_called_once()
        self.assertIn('each exactly 6 complete sentences', model.call_args.args[0])

    def test_refresh_retains_more_than_25_old_suggestions_and_subjects(self):
        older = [{'title':f'Older subject headline {i}', 'subject':f'central subject {i}'} for i in range(40)]
        ideas.suggestion_history(self.cid, {'ideas':older})
        latest = self.topics()
        data = self.begin({'action':'ideas','refresh':True})
        self.assertIn(older[0]['title'], data['context']['previous_suggestions'])
        self.assertIn(older[-1], data['context']['previous_topic_history'])
        with patch.object(ideas, 'deepseek', side_effect=ValueError('No new result')) as model:
            self.finish(data)
        prompt = model.call_args.args[0]
        self.assertIn('radically different central SUBJECT', prompt)
        self.assertIn('ALL-CAPS', prompt)
        self.assertIn('question marks and exclamation marks', prompt)
        self.assertIn(older[0]['title'], prompt)
        self.assertEqual(ideas.catalog(self.cid)['ideas'], latest['ideas'])
        history = ideas.suggestion_history(self.cid)
        self.assertEqual(len(history), 45)
        self.assertEqual(history[0], older[0])
        model.assert_called_once()

    def test_http_stage_is_reserved_once_and_hides_private_context(self):
        with patch.object(ideas,'Thread') as thread:
            code,data=self.request('/api/channels/'+self.cid+'/episode-ideas','POST',{'action':'ideas'})
            self.assertEqual(code,202,data);self.assertNotIn('context',data)
            self.request('/api/channels/'+self.cid+'/episode-ideas','POST',{'action':'ideas'})
            self.assertEqual(thread.call_count,1)
            code,data=self.request('/api/channels/'+self.cid+'/episode-ideas')
            self.assertEqual(code,200);self.assertEqual(data['status'],'running');self.assertNotIn('context',data)
    def begin(self, body):
        with patch.object(ideas, 'Thread'):
            ideas.start(self.cid, body)
        return store.read_json(ideas.path(self.cid))
    def finish(self, data):
        ideas.work(self.cid, data)
        return ideas.read(self.cid)
    def topics(self):
        data = self.begin({'action':'ideas'})
        with patch.object(ideas, 'deepseek', return_value={'ideas':[{'title':f'Fresh {self._testMethodName.replace("_", "")[:20]} story number {i}', 'uk':'Українська назва'} for i in range(5)]}):
            return self.finish(data)
    def test_edited_topic_title_reaches_project_and_opus_without_changing_the_catalog(self):
        topics = self.topics()
        original = topics['ideas'][1]['title']
        edited = 'My edited topic with a new detail'
        data = self.begin({'action':'openings','index':1,'title':'  '+edited+'  ',
                           'ideas_id':topics['id'],'new_episode':True})
        self.assertEqual(data['selected']['title'], edited)
        self.assertEqual(data['selected']['uk'], '')
        self.assertEqual(store.load_project(data['project_id'])['name'], edited)
        self.assertEqual(ideas.catalog(self.cid)['ideas'][1]['title'], original)
        hooks = [{'text':('A complete vivid hook with useful natural spoken detail. ')*6,'uk':''} for _ in range(4)]
        with patch.object(ideas,'opus',return_value={'openings':hooks}) as model:
            self.finish(data)
        self.assertIn(edited, model.call_args.args[0])
        self.assertIn('exactly 6 complete sentences', model.call_args.args[0])
        self.assertEqual(ideas.read_project(data['project_id'])['status'], 'done')

    def test_live_writer_wishes_reach_hooks_and_script_without_montage_memory(self):
        self.topics()
        data = self.begin({'action':'openings','index':0,'new_episode':True})
        folder=store.get_channel_folder(self.cid)
        original=store.read_json(folder / store.PLAN_CONFIG)
        try:
            store.update_channel_settings(self.cid, {'script_wishes':'Use a warm greeting and short concrete examples.'})
            hooks=[{'text':'A complete vivid hook with useful spoken details. '*6,'uk':''} for _ in range(4)]
            with patch.object(ideas,'opus',return_value={'openings':hooks}) as model, patch.object(ideas.agent_storage,'get_memory',return_value='Shared channel wishes apply to this writing step'):
                self.finish(data)
            self.assertIn('Shared channel wishes apply to this writing step',model.call_args.args[0])
            self.assertIn('Use a warm greeting',model.call_args.args[0])
            self.assertNotIn('"memory":',model.call_args.args[0])
            data=self.begin({'action':'script','index':0})
            with patch.object(ideas,'opus',side_effect=ValueError('Stop after capturing the script brief')) as model:
                self.finish(data)
            self.assertIn('Use a warm greeting',model.call_args.args[0])
            # An incomplete set of variants stays failed with no hidden paid retry.
            data=self.begin({'action':'openings','index':1,'new_episode':True})
            with patch.object(ideas,'opus',return_value={'openings':[{'text':'A complete vivid hook with useful spoken details. '*10,'uk':''}]*3}) as model:
                result=self.finish(data)
            self.assertEqual(result['status'],'failed');model.assert_called_once()
        finally:
            store.atomic_json(folder / store.PLAN_CONFIG,original)

    def test_blank_edited_title_creates_no_project_or_model_job(self):
        self.topics()
        with patch.object(store,'create_project') as create, patch.object(ideas,'Thread') as thread:
            with self.assertRaises(store.StudioError):
                ideas.start(self.cid, {'action':'openings','index':0,'title':'  ','new_episode':True})
        create.assert_not_called()
        thread.assert_not_called()

    def test_refresh_excludes_previous_suggestions_and_keeps_them_on_empty_response(self):
        previous = self.topics()
        data = self.begin({'action':'ideas','refresh':True})
        with patch.object(ideas,'deepseek',side_effect=ValueError('Empty model response')) as model:
            self.finish(data)
        self.assertIn(previous['ideas'][0]['title'], data['context']['previous_suggestions'])
        self.assertIn('previous_suggestions', model.call_args.args[0])
        self.assertEqual(ideas.catalog(self.cid)['ideas'], previous['ideas'])
        self.assertEqual(ideas.catalog(self.cid)['status'], 'failed')
        with self.assertRaises(ValueError):
            ideas.validate_titles({'ideas':previous['ideas']}, data['context'])

    def test_complete_flow_keeps_selected_title_opening_and_target_without_starting_voice(self):
        previous = store.create_project(self.cid, 'Old fixture')
        store.save_project_source(previous, 'old script words ' * 400)
        data = self.topics()
        self.assertEqual(data['target_words'], 1200)
        self.assertEqual(len(data['ideas']), 5)
        self.assertNotIn('context', ideas.public(data))
        data = self.begin({'action':'openings','index':2,'target_words':1500})
        pid = data['project_id']
        hooks=[{'text':('Opening number '+str(i)+' with meaningful vivid words and natural spoken detail. ')*6,'uk':''} for i in range(4)]
        with patch.object(ideas,'opus',return_value={'openings':hooks}) as model:
            data=self.finish(data)
            self.assertIn('1500', model.call_args.args[0])
            self.assertIn('story number 2',model.call_args.args[0])
        data=self.begin({'action':'script','index':3})
        script=hooks[3]['text']+' Full natural script words.'*370
        metadata={'titles':[data['selected']['title'],'Another fresh angle','A third fresh angle'], 'description':'Thank you for watching! Subscribe for more.\n\nThis video is for entertainment.', 'tags':['story','fiction','curiosity']}
        with patch.object(ideas,'opus',return_value={'script':script,'metadata':metadata}) as model, (patch.object(ideas.author_rules,'check',return_value=(True,'OK')) if hasattr(ideas,'author_rules') else nullcontext()):
            data=self.finish(data)
            self.assertEqual(model.call_count,1)
            self.assertIn('metadata', model.call_args.args[0])
        self.assertTrue(data['completed'])
        project = store.load_project(pid)
        self.assertEqual(ideas.completion_notices.notice(project)['kind'], 'process')
        ideas.completion_notices.seen(pid)
        self.assertIsNone(ideas.completion_notices.notice(project))
        self.assertEqual(store.load_project(pid)['voice_script']['text'],script.strip())
        self.assertFalse(store.load_project(pid).get('plan_source'))
        self.assertEqual(store.read_json(store.project_dir(pid)/'source-timing.json')['timing']['status'],'awaiting_voice')
        with self.assertRaises(store.StudioError):
            self.begin({'action':'openings','index':2,'new_episode':True})
        finished_id = data['id']
        next_episode = self.begin({'action':'openings','index':1,'target_words':1400,'new_episode':True})
        self.assertNotEqual(next_episode['project_id'], pid)
        self.assertNotEqual(next_episode['id'], finished_id)
        self.assertEqual(next_episode['used_idea_indexes'], [2])
        self.assertEqual(store.load_project(pid)['voice_script']['text'], script.strip())
        self.assertTrue((ideas.path(self.cid).parent/'idea-runs'/finished_id/'finished.json').is_file())
        with patch.object(ideas,'Thread') as thread:
            duplicate = ideas.start(self.cid,{'action':'openings','index':1,'new_episode':True})
        self.assertEqual(duplicate['project_id'], next_episode['project_id'])
        thread.assert_not_called()
    def test_duplicates_fail_without_automatic_second_paid_call(self):
        ctx={'previous_titles':['Same title']}
        with self.assertRaises(ValueError): ideas.validate_titles({'ideas':[{'title':'Same title'}]*8},ctx)
        data=self.begin({'action':'ideas'})
        with patch.object(ideas,'deepseek',side_effect=RuntimeError('Service unavailable')) as model:
            failed=self.finish(data)
            self.assertEqual(failed['status'],'failed')
            self.assertEqual(model.call_count,1)
            ideas.read(self.cid)
            self.assertEqual(model.call_count,1)
    def test_double_submit_and_retry_reuse_project(self):
        self.topics()
        data=self.begin({'action':'openings','index':0})
        pid=data['project_id']
        self.assertEqual(ideas.start(self.cid,{'action':'openings','index':0})['project_id'],pid)
        with patch.object(ideas,'opus',side_effect=RuntimeError('limit')): self.finish(data)
        data=self.begin({'action':'openings','index':0})
        self.assertEqual(data['project_id'],pid)
        ideas.ACTIVE.clear()
        self.assertEqual(ideas.read(self.cid)['status'],'failed')
    def test_existing_script_is_never_overwritten(self):
        self.topics();data=self.begin({'action':'openings','index':0});pid=data['project_id']
        hooks=[{'text':'A meaningful opening with enough words. '*6,'uk':''}]*4
        with patch.object(ideas,'opus',return_value={'openings':hooks}): self.finish(data)
        store.save_project_source(store.load_project(pid),'Author text already saved.')
        with patch.object(ideas,'Thread') as thread:
            with self.assertRaises(store.StudioError):
                ideas.start(self.cid, {'action':'script','index':0})
        thread.assert_not_called()
        self.assertEqual(store.load_project(pid)['voice_script']['text'],'Author text already saved.')

if __name__=='__main__': unittest.main()

class LazyIdeasTest(EpisodeIdeasTest):
    def test_yesterday_completed_topics_start_once_instead_of_returning_stale_cache(self):
        self.topics()
        with patch.object(ideas,'today',return_value='2099-01-02'), patch.object(ideas,'Thread') as thread:
            self.assertTrue(ideas.catalog(self.cid)['stale'])
            first=ideas.start(self.cid,{'action':'ideas','if_stale':True,'request_id':'daily-first'})
            self.assertEqual(first['status'],'running')
            self.assertFalse(first['stale'])
            second=ideas.start(self.cid,{'action':'ideas','if_stale':True,'request_id':'daily-second'})
            self.assertEqual(second['id'],first['id'])
            self.assertEqual(thread.call_count,1)
            ideas.ACTIVE.clear()
            failed=ideas.start(self.cid,{'action':'ideas','if_stale':True,'request_id':'after-restart'})
            self.assertEqual(failed['status'],'failed')
            self.assertEqual(thread.call_count,1)

    def test_opening_ideas_reserves_one_attempt_per_day_and_reading_is_free(self):
        with patch.object(ideas, 'Thread') as thread:
            self.assertTrue(ideas.catalog(self.cid)['stale'])
            thread.assert_not_called()
            first = ideas.start(self.cid, {'action':'ideas','if_stale':True})
            self.assertEqual(first['status'], 'running')
            ideas.start(self.cid, {'action':'ideas','if_stale':True})
            self.assertEqual(thread.call_count, 1)
            ideas.ACTIVE.clear()
            failed = ideas.start(self.cid, {'action':'ideas','if_stale':True})
            self.assertEqual(failed['status'], 'failed')
            self.assertEqual(thread.call_count, 1)
            with patch.object(ideas, 'today', return_value='2099-01-02'):
                self.assertTrue(ideas.catalog(self.cid)['stale'])
                ideas.start(self.cid, {'action':'ideas','if_stale':True})
            self.assertEqual(thread.call_count, 2)

    def test_fresh_topics_reused_and_manual_refresh_remains_explicit(self):
        self.topics()
        with patch.object(ideas, 'Thread') as thread:
            self.assertEqual(ideas.start(self.cid, {'action':'ideas','if_stale':True})['status'], 'done')
            thread.assert_not_called()
            ideas.start(self.cid, {'action':'ideas','refresh':True})
            thread.assert_called_once()

    def test_title_punctuation_rule_is_enforced(self):
        for title in ['A title: detail','A title - detail','A title — detail']:
            with self.assertRaises(ValueError): ideas.validate_titles({'ideas':[{'title':title,'uk':''}]*5},{'previous_titles':[]})


class TopicTransportTest(unittest.TestCase):
    def test_empty_response_records_cost_and_stops_once_with_a_clear_error(self):
        import io, json, tempfile
        from pathlib import Path
        result = {'id':'request-1','usage':{'cost':.001},
                  'choices':[{'finish_reason':'length','message':{'content':None}}]}
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(ideas.credentials,'vault') as vault, \
                patch.object(ideas.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(result).encode())) as send, \
                patch.object(ideas.project_costs,'record_at') as cost:
            vault.return_value.read.return_value='test-key'
            with self.assertRaisesRegex(ValueError, 'ліміт відповіді'):
                ideas.deepseek('Five topics',Path(folder),'test-run')
            cost.assert_called_once()
            self.assertEqual(cost.call_args.args[2],.001)
            send.assert_called_once()
            payload=json.loads(send.call_args.args[0].data)
            self.assertEqual(payload['reasoning'],{'effort':'none'})
            self.assertFalse(payload['provider']['allow_fallbacks'])
            self.assertEqual(payload['provider']['ignore'],['relace'])
            self.assertEqual(payload['provider']['sort'],'price')
            diagnostic=json.loads((Path(folder)/'topic-response.json').read_text())
            self.assertEqual(diagnostic['finish_reason'],'length')

    def test_rate_limit_keeps_safe_diagnostics_and_never_retries(self):
        import io, json, tempfile, urllib.error
        from pathlib import Path
        failure = urllib.error.HTTPError('https://openrouter.ai/api/v1/chat/completions', 429, 'Too Many Requests',
            {'Retry-After':'45'}, io.BytesIO(json.dumps({'error':{'metadata':{
                'provider_name':'DeepSeek','limit_source':'upstream_provider','raw':'private provider contents'}}}).encode()))
        with tempfile.TemporaryDirectory() as folder, patch.object(ideas.credentials,'vault') as vault, \
                patch.object(ideas.urllib.request,'urlopen',side_effect=failure) as send, \
                patch.object(ideas.project_costs,'record_at') as cost:
            vault.return_value.read.return_value='test-key'
            with self.assertRaisesRegex(RuntimeError, 'через 45 с'):
                ideas.deepseek('private prompt',Path(folder),'test-run')
            send.assert_called_once()
            cost.assert_not_called()
            text=(Path(folder)/'topic-response.json').read_text()
            self.assertNotIn('private',text)
            self.assertNotIn('test-key',text)
            detail=json.loads(text)['error']
            self.assertEqual(detail['status'],429)
            self.assertEqual(detail['provider_name'],'DeepSeek')
            self.assertEqual(detail['retry_after_seconds'],45)

    def test_connection_failure_is_readable_without_an_automatic_retry(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder, patch.object(ideas.credentials,'vault') as vault, \
                patch.object(ideas.urllib.request,'urlopen',side_effect=ConnectionResetError('private details')) as send:
            vault.return_value.read.return_value='test-key'
            with self.assertRaisesRegex(RuntimeError, 'З’єднання з OpenRouter перервалося'):
                ideas.deepseek('private prompt',Path(folder),'test-run')
            send.assert_called_once()

    def test_null_content_is_not_treated_as_text(self):
        with self.assertRaisesRegex(ValueError, 'не повернула готовий текст'):
            ideas.unpack(None)
