import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import languages
import translation_recovery as recovery


class StrictReplyTest(unittest.TestCase):
    def test_jsonl_preserves_requested_identity_and_order(self):
        text = '{"id":20,"translation":"Veinte."}\n{"id":21,"translation":"Veintiuno."}'
        self.assertEqual(recovery.answers(text, [20, 21]), ({20: 'Veinte.', 21: 'Veintiuno.'}, None))

    def test_invented_extra_and_duplicate_ids_reject_entire_reply(self):
        for text in ['{"20":"Yes","21":"Invented"}', '{"20":"First","20":"Changed"}',
                     '[{"id":20,"text":"First"},{"id":20,"text":"Changed"}]',
                     '{"id":true,"text":"Wrong"}']:
            with self.subTest(text=text):
                self.assertEqual(recovery.answers(text, [20])[0], {})

    def test_partial_response_keeps_only_valid_existing_ids(self):
        found, issue = recovery.answers('{"20":"Veinte.","21":""}', [20, 21, 22])
        self.assertEqual(found, {20: 'Veinte.'})
        self.assertIn('21, 22', issue)

    def test_malformed_or_prose_is_not_treated_as_translation(self):
        for text in ['{"20":"unfinished', 'Here: {"20":"text"}', None]:
            self.assertEqual(recovery.answers(text, [20])[0], {})

    def test_audit_rejects_contradictions_duplicates_and_unrequested_ids(self):
        invalid = ['{"ok":true,"ids":[0],"issues":[{"id":0,"reason":"Wrong unit"}]}',
                   '{"ok":false,"ok":true,"ids":[0]}', '{"ok":true,"ids":[0,0]}',
                   '{"ok":false,"ids":[0],"issues":[{"id":1,"reason":"Wrong"}]}',
                   '{"ok":false,"ids":[0],"issues":[{"id":0,"reason":"A"},{"id":0,"reason":"B"}]}']
        for text in invalid:
            with self.subTest(text=text):
                self.assertEqual(set(recovery.audit(text, [0])), {0})
        self.assertEqual(recovery.audit('{"ok":true,"ids":[0]}', [0]), {})

    def test_partial_audit_keeps_reported_error_without_approving_missing_neighbours(self):
        answer='{"ok":false,"ids":[43],"issues":[{"id":43,"reason":"Wrong meaning"}]}'
        failed,covered=recovery.audit_evidence(answer,[40,41,42,43,44])
        self.assertEqual(failed,{43:'Wrong meaning'})
        self.assertEqual(covered,[43])
        self.assertEqual(set([40,41,42,43,44])-set(covered),{40,41,42,44})
        for invalid in ['{"ok":true,"ids":[43],"issues":[{"id":43,"reason":"Wrong"}]}',
                        '{"ok":true,"ids":[43,43]}','{"ok":true,"ids":[999]}']:
            with self.assertRaises(recovery.InvalidAudit):recovery.audit_evidence(invalid,[43])


class DraftTest(unittest.TestCase):
    def test_exact_source_model_target_and_timing_identity_required(self):
        with tempfile.TemporaryDirectory() as folder:
            identity = {'project': 'p', 'code': 'es', 'model': 'm', 'script': 'A',
                        'source_units': ['A'], 'timing': [{'start': 0, 'end': 1}]}
            draft = recovery.Draft(folder, identity)
            draft.seed(['Uno.'], 'audit.json')
            self.assertEqual(recovery.Draft(folder, identity).data['lines'], ['Uno.'])
            for key, value in [('project', 'q'), ('code', 'uk'), ('model', 'n'), ('script', 'B'),
                               ('source_units', ['B']), ('timing', [{'start': 0, 'end': 2}])]:
                self.assertEqual(recovery.Draft(folder, {**identity, key: value}).data['lines'], [])
            draft.save(completed=True)
            self.assertEqual(recovery.Draft(folder, identity).data['lines'], [])


    def test_corrupted_cache_fields_cannot_crash_or_poison_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            identity = {'source_units': ['A']}
            draft = recovery.Draft(folder, identity)
            draft.seed(['Uno.'])
            bad = json.loads(draft.path.read_text())
            bad.update(initial_parts='wrong', audited=[], rewrite={'identity': 'id', 'values': []}, cost_usd=float('nan'))
            draft.path.write_text(json.dumps(bad))
            restored = recovery.Draft(folder, identity).data
            self.assertEqual(restored['lines'], ['Uno.'])
            for key in ['initial_parts', 'audited', 'rewrite']:
                self.assertEqual(restored[key], {})
            self.assertEqual(restored['cost_usd'], 0)


class ContinuationTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(languages, 'work_dir', return_value=self.folder))
        self.trace=self.stack.enter_context(patch.object(languages, 'translation_trace', side_effect=lambda *a,**kw:contextlib.nullcontext()))
        self.stack.enter_context(patch.object(languages, 'progress'))
        self.stack.enter_context(patch.object(languages.language_quality, 'require'))
        self.stack.enter_context(patch.object(languages, 'translator', return_value='Translate naturally.'))
        self.stack.enter_context(patch.object(languages, 'target_rule', return_value='Spanish.'))
        self.stack.enter_context(patch.object(languages.store, 'load_project', return_value={'id': 'p','channel_id':'test-channel'}))
        self.stack.enter_context(patch.object(languages.language_defaults,'settings',return_value={}))
        self.stack.enter_context(patch.object(languages, 'original_language', return_value='en'))
        # These fixtures isolate resumable semantic repairs; the number-aware goal
        # is exercised with real plans in test_translation_length_integration.
        self.stack.enter_context(patch.object(languages.translation_budget, 'number_refinement_plan',
                                             return_value={'available': False, 'ids': []}))
        self.job = {'translation_model': languages.DEFAULT_TRANSLATION_MODEL}

    def test_linguist_finishes_only_the_disputed_phrase_after_failed_ordinary_repair(self):
        requests=[]
        def ask(messages,max_tokens=12000):
            system=messages[0]['content'];items=json.loads(messages[1]['content']);requests.append((system,items))
            if 'senior native' in system:
                self.assertEqual(items['id'],1)
                return json.dumps({'id':1,'action':'replace','text':'Correct native phrase.','reason':'Preserved original meaning.'}),.001
            ids=[x['id'] for x in items]
            if 'Independently compare' in system:
                return json.dumps({'ok':False,'ids':ids,'issues':[{'id':1,'reason':'Wrong fact.'}]}),.001
            return json.dumps({'1':'Wrong phrase.'}),.001
        with patch.object(languages,'ask',side_effect=ask):
            values,cost=languages.before_translate('p','es',{'script':'First. Second.'},
                ['Good phrase.','Wrong phrase.'],['First.','Second.'],self.job)
        self.assertEqual(values,['Good phrase.','Correct native phrase.'])
        self.assertEqual(len(requests),4)
        self.assertAlmostEqual(cost,.004)
        self.assertEqual(self.job['translation_linguist']['resolved'],1)

    def test_numeric_spelling_does_not_discard_a_successful_semantic_repair(self):
        calls=[]
        def ask(messages,max_tokens=12000):
            system=messages[0]['content'];items=json.loads(messages[1]['content']);calls.append(system)
            if 'Independently compare' in system:
                bad='ratonesuccessfully' in items[0]['translation']
                return json.dumps({'ok':not bad,'ids':[0],'issues':[{'id':0,'reason':'Corrupted token.'}] if bad else []}),0
            return json.dumps({'0':'En 2014 estudiaron crías de ratón.'}),0
        source='In 2014 they studied baby mice.'
        with patch.object(languages,'ask',side_effect=ask):
            values,_=languages.before_translate('p','es',{'script':source},
                ['En dos mil catorce estudiaron ratonesuccessfully bebés.'],[source],self.job)
        self.assertEqual(values,['En dos mil catorce estudiaron crías de ratón.'])
        self.assertEqual(len(calls),3)
        self.assertFalse(any('senior native' in x for x in calls))

    def test_native_linguist_owns_spelled_years_without_a_local_numeric_veto(self):
        source='In June 1982, the plane entered an ash cloud.'
        text='W czerwcu tysiąc dziewięćset osiemdziesiątego drugiego roku samolot wleciał w chmurę popiołu.'
        with patch.object(languages.translation_budget,'missing_source_years',side_effect=AssertionError('Local year veto')):
            with patch.object(languages,'ask',return_value=(json.dumps({'ok':True,'ids':[0]}),.001)) as ask:
                values,cost=languages.before_translate('p','pl',{'script':source},[text],[source],self.job)
        self.assertEqual(values,[text])
        self.assertAlmostEqual(cost,.001)
        self.assertEqual(ask.call_count,1)

    def test_resume_reuses_linguist_correction_and_good_neighbour_without_paid_rechecks(self):
        from translation_linguist import GUARD_ERROR
        units=['The first phrase.','In January 2022, the volcano erupted.']
        lines=['Pierwsze zdanie.','W styczniu tysiąc dziewięćset dwudziestego drugiego roku wybuchł wulkan.']
        fixed='W styczniu dwa tysiące dwudziestego drugiego roku wybuchł wulkan.'
        src={'script':' '.join(units)}
        draft=languages.translation_draft('p','pl',src,units,self.job)
        draft.seed(lines)
        draft.save(audited={'0':recovery.fingerprint(['number-aware-v2','pl',units[0],lines[0]])},
            semantic_issues={'1':GUARD_ERROR},linguist={'1':{
                'fingerprint':recovery.fingerprint(['linguist-v1','pl',units[1],lines[1]]),
                'status':'blocked','error':GUARD_ERROR,'guard_requested':True,'candidate':fixed,
                'guard_decision':{'id':1,'action':'replace','text':fixed,'reason':'Correct source year.'}}})
        with patch.object(languages,'ask',side_effect=AssertionError('Repeated paid request')):
            values,cost=languages.before_translate('p','pl',src,lines,units,self.job,draft=draft)
        self.assertEqual(values,[lines[0],fixed])
        self.assertEqual(cost,0)
        self.assertEqual(draft.data['semantic_issues'],{})
        self.assertEqual(draft.data['linguist']['1']['status'],'resolved')

    def test_resumed_linguist_wording_is_not_reverted_by_an_old_optional_length_repair(self):
        from translation_linguist import GUARD_ERROR
        source='In January 2022, the volcano erupted.'
        old='W styczniu tysiąc dziewięćset dwudziestego drugiego roku wybuchł wulkan.'
        fixed='W styczniu dwa tysiące dwudziestego drugiego roku wybuchł wulkan.'
        src={'script':source}
        draft=languages.translation_draft('p','pl',src,[source],self.job)
        draft.seed([old])
        draft.save(semantic_issues={'0':GUARD_ERROR},linguist={'0':{
            'fingerprint':recovery.fingerprint(['linguist-v1','pl',source,old]),
            'status':'blocked','error':GUARD_ERROR,'candidate':fixed,
            'guard_decision':{'id':0,'action':'replace','text':fixed,'reason':'Correct year.'}}},
            single_pass_repairs={'0':{'status':'returned','value':old}})
        plan={'available':True,'ids':[0],'report':{'within_budget':True},'pending_ids':[0],
              'phrases':[{'id':0,'source_chars':20,'translated_chars':100,'within_budget':False,'difference_percent':400}]}
        with patch.object(languages.translation_budget,'number_refinement_plan',return_value=plan):
            with patch.object(languages,'ask',side_effect=AssertionError('Repeated paid request')):
                first,cost=languages.before_translate('p','pl',src,[old],[source],self.job,draft=draft)
                # The title may fail after saving this draft, so a second resume
                # must also preserve the accepted wording and exact-pair audit.
                second,again=languages.before_translate('p','pl',src,first,[source],self.job,draft=draft)
        self.assertEqual(first,[fixed])
        self.assertEqual(second,[fixed])
        self.assertEqual(cost+again,0)

    def test_missing_id_retry_does_not_repeat_good_neighbour(self):
        requests, audits = [], []
        def ask(messages, max_tokens=12000):
            items = json.loads(messages[1]['content'])
            ids = [x['id'] for x in items]
            if 'Independently compare' in messages[0]['content']:
                audits.append(ids)
                if len(audits) == 1:
                    return json.dumps({'ok': False, 'ids': ids, 'issues': [{'id': i, 'reason': 'Wrong fact.'} for i in ids]}), 0
                return json.dumps({'ok': True, 'ids': ids}), 0
            requests.append(ids)
            return json.dumps({ids[0]: 't'*49}), 0
        with patch.object(languages, 'ask', side_effect=ask):
            lines, _ = languages.before_translate('p', 'es', {'script': 's'*99},
                ['t'*60]*2, ['s'*49]*2, self.job)
        self.assertEqual(requests, [[0], [1]])
        self.assertEqual(lines, ['t'*49]*2)

    def test_semantic_repair_calls_only_failed_id_and_allows_natural_expansion(self):
        requests, audits = [], []
        def ask(messages, max_tokens=12000):
            items = json.loads(messages[1]['content']);ids = [x['id'] for x in items]
            if 'Independently compare' in messages[0]['content']:
                audits.append(ids)
                if len(audits) == 1:
                    return json.dumps({'ok': False, 'ids': ids, 'issues': [{'id': 1, 'reason': 'Wrong unit.'}]}), 0
                return json.dumps({'ok': True, 'ids': ids}), 0
            requests.append(ids)
            return json.dumps({'1': 'c'*90}), 0
        with patch.object(languages, 'ask', side_effect=ask):
            lines, _ = languages.before_translate('p', 'es', {'script': 's'*99},
                ['a'*49, 'b'*49], ['s'*49]*2, self.job)
        self.assertEqual(requests, [[1]])
        self.assertEqual(audits, [[0, 1], [1]])
        self.assertEqual(lines, ['a'*49, 'c'*90])
        models=[call.kwargs.get('request_model') for call in self.trace.call_args_list]
        self.assertEqual(models,[languages.TRANSLATION_REPAIR_MODEL,
            languages.TRANSLATION_REPAIR_MODEL,languages.TRANSLATION_REPAIR_MODEL])

    def test_uncertain_provider_failure_resumes_without_repeating_any_repair(self):
        src,units,lines={'script':'s'*99},['s'*49]*2,['t'*60]*2
        repairs=[]
        def answer(messages,max_tokens=12000):
            ids=[x['id'] for x in json.loads(messages[1]['content'])]
            if 'Independently compare' in messages[0]['content']:
                return json.dumps({'ok':False,'ids':ids,'issues':[{'id':i,'reason':'Wrong fact'} for i in ids]}),0
            repairs.extend(ids)
            if ids==[0]:return json.dumps({'0':'a'*49}),.01
            raise RuntimeError('Provider unavailable')
        with patch.object(languages,'ask',side_effect=answer):
            with self.assertRaisesRegex(RuntimeError,'Provider unavailable'):
                languages.before_translate('p','es',src,lines,units,self.job)
        calls=[]
        def resume(messages,max_tokens=12000):
            self.assertIn('Independently compare',messages[0]['content'])
            items=json.loads(messages[1]['content']);ids=[x['id'] for x in items];calls.append(ids)
            bad=[{'id':x['id'],'reason':'Wrong fact'} for x in items if x['translation'].startswith('t')]
            return json.dumps({'ok':not bad,'ids':ids,'issues':bad}),0
        with patch.object(languages,'ask',side_effect=resume):
            with self.assertRaisesRegex(RuntimeError,'перевірку змісту'):
                languages.before_translate('p','es',src,lines,units,self.job)
        draft=json.loads((self.folder/'translation-draft.json').read_text())
        self.assertEqual(repairs,[0,1])
        self.assertEqual(draft['lines'][0],'a'*49)
        self.assertEqual(draft['single_pass_repairs']['1']['status'],'requested')
        self.assertTrue(calls)


    def test_partial_checker_response_sends_only_unchecked_neighbours_to_deepseek(self):
        calls=[]
        def reply(messages,max_tokens=12000):
            items=json.loads(messages[1]['content']);ids=[x['id'] for x in items];calls.append(ids)
            if len(calls)==1:return '{"ok":false,"ids":[1],"issues":[{"id":1,"reason":"Wrong fact"}]}',.001
            if len(calls)==2:return '{"ok":true,"ids":[0]}',.001
            if len(calls)==3:return '{"1":"Correct words"}',.001
            return '{"ok":true,"ids":[1]}',.001
        with patch.object(languages,'ask',side_effect=reply):
            result,_=languages.before_translate('p','es',{'script':'A B'},['Good words','Wrong words'],['A','B'],self.job)
        self.assertEqual(result,['Good words','Correct words'])
        self.assertEqual(calls,[[0,1],[0],[1],[1]])
        self.assertEqual(self.trace.call_args_list[1].kwargs['request_model'],languages.TRANSLATION_REPAIR_MODEL)

    def test_seeded_translation_skips_original_generation(self):
        src = {'script': 's'*100, 'title': 'Title', 'duration': 10}
        segments = [{'start': 0, 'end': 10, 'source': 's'*100}]
        self.stack.enter_context(patch.object(languages.store, 'load_project', return_value={'id': 'p','channel_id':'test-channel'}))
        self.stack.enter_context(patch.object(languages.store, 'load_project_plan', return_value={}))
        self.stack.enter_context(patch.object(languages, 'segments_of', return_value=segments))
        self.stack.enter_context(patch.object(languages, 'source', return_value=src))
        seeded = languages.seed_translation_draft('p', 'es', ['t'*100], languages.DEFAULT_TRANSLATION_MODEL,
                                                source_script=src['script'], source_units=['s'*100])
        self.assertEqual(seeded['phrases'], 1)
        with patch.object(languages, 'translate_lines') as initial, \
             patch.object(languages, 'ask', return_value=(json.dumps({'ok': True, 'ids': [0]}), 0)), \
             patch.object(languages, 'save_translation') as publish:
            languages._translate('p', 'es', self.job)
        initial.assert_not_called()
        self.assertEqual(publish.call_args.args[4], 't'*100)

    def test_naturally_long_translation_can_be_saved_without_count_gate(self):
        src = {'script': 'In 1999.', 'title': 'Title', 'duration': 10}
        text = 'En mil novecientos noventa y nueve.'
        with patch.object(languages, 'ask', return_value=('Título', .01)), \
             patch.object(languages, 'update') as update, \
             patch.object(languages, 'copy_out'), patch.object(languages, 'drop_samples'):
            languages.save_translation('p', 'es', {'id': 'p'}, src, text, 0, self.job, None)
        self.assertEqual((self.folder/'text.txt').read_text().strip(), text)
        state = {}
        update.call_args.args[1](state)
        report = state['languages']['es']['translation_length']
        self.assertTrue(report['advisory_only'])
        self.assertTrue(report['numeric_forms_differ'])
        self.assertNotIn('within_budget', report)

    def test_each_semantic_issue_gets_one_independent_repair(self):
        current = ['wrong']*5
        repairs = []
        def ask(messages, max_tokens=12000):
            items = json.loads(messages[1]['content'])
            ids = [item['id'] for item in items]
            if 'Independently compare' in messages[0]['content']:
                failed = [{'id': item['id'], 'reason': 'Wrong fact.'} for item in items if item['translation'] == 'wrong']
                return json.dumps({'ok': not failed, 'ids': ids, 'issues': failed}), 0
            repairs.append(ids)
            return json.dumps({i: ('correct' if i == ids[0] else 'wrong') for i in ids}), 0
        with patch.object(languages, 'ask', side_effect=ask):
            result, _ = languages.before_translate('p', 'es', {'script': 'source'}, current, ['source']*5, self.job)
        self.assertEqual(result, ['correct']*5)
        self.assertEqual(len(repairs), 5)

    def test_source_changed_during_title_request_cannot_replace_published_text(self):
        src = {'script': 's'*100, 'title': 'Title', 'duration': 10}
        segments = [{'start': 0, 'end': 10, 'source': 's'*100}]
        draft = languages.translation_draft('p', 'es', src, ['s'*100], self.job, segments)
        draft.seed(['t'*100])
        (self.folder/'text.txt').write_text('Previously accepted text')
        with patch.object(languages.store, 'load_project', return_value={'id': 'p','channel_id':'test-channel'}), \
             patch.object(languages.store, 'load_project_plan', return_value={}), \
             patch.object(languages, 'source', return_value={**src, 'script': 'Changed source'}), \
             patch.object(languages, 'segments_of', return_value=segments), \
             patch.object(languages, 'ask', return_value=('Título', .01)):
            with self.assertRaisesRegex(RuntimeError, 'Оригінал або таймінги змінилися'):
                languages.save_translation('p', 'es', {'id': 'p'}, src, 't'*100, 0, self.job,
                                           segments, draft=draft)
        self.assertEqual((self.folder/'text.txt').read_text(), 'Previously accepted text')
        self.assertAlmostEqual(json.loads(draft.path.read_text())['cost_usd'], .01)

    def test_unsynced_draft_cannot_publish_after_source_timing_is_added(self):
        src = {'script': 's'*100, 'title': 'Title', 'duration': 10}
        draft = languages.translation_draft('p', 'es', src, ['s'*100], self.job)
        draft.seed(['t'*100])
        (self.folder/'text.txt').write_text('Previously accepted text')
        segments = [{'start': 0, 'end': 10, 'source': 's'*100}]
        with patch.object(languages.store, 'load_project', return_value={'id': 'p','channel_id':'test-channel'}), \
             patch.object(languages.store, 'load_project_plan', return_value={}), \
             patch.object(languages, 'source', return_value=src), \
             patch.object(languages, 'segments_of', return_value=segments), \
             patch.object(languages, 'ask', return_value=('Título', .01)):
            with self.assertRaisesRegex(RuntimeError, 'Оригінал або таймінги змінилися'):
                languages.save_translation('p', 'es', {'id': 'p'}, src, 't'*100, 0, self.job,
                                           None, draft=draft)
        self.assertEqual((self.folder/'text.txt').read_text(), 'Previously accepted text')


if __name__ == '__main__':
    unittest.main()
