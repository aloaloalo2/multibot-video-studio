"""Author-session editorial contract and publication guards, with no paid inference."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import script_editing as editor
import episode_ideas as ideas
import store
import writing_jobs

REAL_REVIEW=editor.self_review

class ResearchFollowupTest(unittest.TestCase):
    def test_fact_check_followups_preserve_report_without_blocking_automation(self):
        report={'editorial_report':{'unresolved':[{'issue':'Check study','needs_fact_check':True}]}}
        with patch.object(editor,'latest',return_value=report):
            self.assertFalse(editor.requires_review('project'))
        self.assertEqual(len(report['editorial_report']['unresolved']),1)

    def test_editorial_notes_are_not_manual_approval_gates(self):
        for row in [{'issue':'Broken logic','needs_fact_check':False},{'issue':'Legacy issue'}]:
            with self.subTest(row=row),patch.object(editor,'latest',return_value={'editorial_report':{'unresolved':[row]}}):
                self.assertFalse(editor.requires_review('project'))

def assessment():
    scores={k:{'score':7,'reason':'Конкретна редакторська причина'} for k in editor.SCORE_KEYS}
    return {'assessment_type':'subjective_editorial','before_scores':scores,'after_scores':scores,
            'weaknesses':[],'changes':[],'unresolved':[],'summary':'Збережено природні фрази.'}

class SelfReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.text='First clear paragraph with useful spoken details. '*20
        self.project={'id':'a'*24,'voice_script':{'text':self.text}}
        self.session={'session_id':'12345678-1234-1234-1234-123456789abc','model':'claude-opus-5-5','effort':'medium'}
        for item in (patch.object(store,'project_dir',return_value=self.root),patch.object(store,'load_project',return_value=self.project)):
            item.start();self.addCleanup(item.stop)
        managed=patch.object(editor.word_blacklist,'managed',return_value=False)
        managed.start();self.addCleanup(managed.stop)
        self.receipt=self.root/'review-receipt.json'
        for phase in ['main','refinement']:
            store.atomic_json(self.root/('review-'+phase+'-receipt.json'),{'identity':'review-'+phase,'session_id':self.session['session_id'],'total_cost_usd':.2,'incremental_cost_usd':.12,'usage':{'input_tokens':100,'output_tokens':80}})
    def review(self,ask,ctx=None,target=None):
        return REAL_REVIEW(self.project['id'],self.text,ctx or {},target or editor.word_count(self.text),self.session,lambda prompt,phase:ask(prompt),self.receipt)
    def response(self,text=None):return {'script':text or self.text,'editorial_report':assessment(),'refinement_report':{'remaining_weaknesses':[],'actions':[],'unresolved':[],'summary':'Доопрацювання перевірено.'}}
    def test_same_session_and_effort_are_used_for_draft_then_author_revision(self):
        seen=[]
        def run(cmd,prompt,root,identity,**options):
            seen.append(cmd)
            return 0,{'session_id':self.session['session_id'],'result':'{"script":"example"}'}
        with patch.object(ideas.director,'executable',return_value=Path('claude')),patch.object(writing_jobs,'run',side_effect=run),patch.object(store,'channel_effort',return_value='low'):
            ideas.opus('draft',self.root,'draft','channel',session=self.session)
            ideas.opus('review',self.root,'review','channel',session=self.session,resume=True)
            ideas.opus('refine',self.root,'refine','channel',session=self.session,resume=True)
        self.assertIn('--session-id',seen[0]);self.assertNotIn('--resume',seen[0])
        self.assertEqual(seen[0][seen[0].index('--session-id')+1],self.session['session_id'])
        self.assertEqual(seen[1][seen[1].index('--resume')+1],self.session['session_id'])
        self.assertEqual(seen[2][seen[2].index('--resume')+1],self.session['session_id'])
        for cmd in seen:
            self.assertEqual(cmd[cmd.index('--effort')+1],'medium')
            self.assertEqual(cmd[cmd.index('--model')+1],'claude-opus-5-5')
            self.assertEqual(cmd[cmd.index('--tools')+1],'')
    def test_wrong_returned_session_is_not_accepted(self):
        with patch.object(ideas.director,'executable',return_value=Path('claude')),patch.object(writing_jobs,'run',return_value=(0,{'session_id':'other','result':'{"script":"example"}'})):
            with self.assertRaisesRegex(RuntimeError,'ту саму сесію'):ideas.opus('review',self.root,'review','channel',session=self.session,resume=True)
    def test_session_cost_baseline_advances_without_double_counting_prior_turns(self):
        baselines=[]
        def run(cmd,prompt,root,identity,**options):
            baselines.append(options['previous_session_cost'])
            return 0,{'session_id':self.session['session_id'],'total_cost_usd':1 if len(baselines)==1 else 1.2,'result':'{"script":"example"}'}
        with patch.object(ideas.director,'executable',return_value=Path('claude')),patch.object(writing_jobs,'run',side_effect=run):
            ideas.opus('draft',self.root,'draft','channel',session=self.session)
            ideas.opus('review',self.root,'review','channel',session=self.session,resume=True)
        self.assertEqual(baselines,[0,1]);self.assertEqual(self.session['api_cost_usd'],1.2)
    def test_report_is_separate_from_voice_text_and_before_after_are_immutable(self):
        changed=self.text.replace('clear','natural')
        with patch.object(ideas,'deepseek',side_effect=AssertionError('No separate editor')):
            result=self.review(lambda prompt:self.response(changed),{'studio_word_blacklist':['banned'],'selected_title':'Test promise','script_wishes':'Keep examples'})
        self.assertEqual(result,changed.strip());self.assertNotIn('before_scores',result)
        d=editor.view(self.project['id']);folder=self.root/'script-editing'/d['id']
        self.assertEqual((folder/'before.txt').read_text(),self.text)
        self.assertEqual((folder/'after.txt').read_text(),changed.strip())
        self.assertEqual(d['session_id'],self.session['session_id']);self.assertEqual(d['receipt_session_id'],d['session_id'])
        self.assertEqual(d['provider'],'claude_code');self.assertEqual(d['cost_basis'],'api_equivalent');self.assertEqual(d['cost_usd'],.24)
        self.assertEqual(d['completed_passes'],2)
        self.assertEqual(d['editorial_report']['intermediate_scores'],assessment()['after_scores'])
        self.assertTrue((folder/'intermediate.txt').is_file())
        prompt=(folder/'prompt.txt').read_text();self.assertIn('Keep examples',prompt);self.assertIn('banned',prompt)
        self.assertEqual(self.project['voice_script']['text'],self.text)
    def test_failure_keeps_original_and_no_final_version(self):
        def failed(prompt):raise OSError('service unavailable')
        with self.assertRaises(OSError):self.review(failed)
        d=editor.latest(self.project['id']);self.assertEqual(d['status'],'failed');self.assertEqual(d['before'],self.text)
        self.assertNotIn('after',d);self.assertEqual(d['cost_usd'],.12)
    def test_ready_script_survives_advisory_blacklist_report_and_length_findings(self):
        for response,ctx,target in [(self.response(self.text+' banned'),{'studio_word_blacklist':['banned']},None),
                 ({'script':self.text}, {},None),(self.response(),{},1000)]:
            with self.subTest(ctx=ctx,target=target):
                self.assertEqual(self.review(lambda prompt:response,ctx,target),response['script'].strip())
            self.assertEqual(editor.latest(self.project['id'])['status'],'done')
            self.assertEqual(self.project['voice_script']['text'],self.text)
    def test_new_numeric_examples_and_punctuation_do_not_block_ready_author_text(self):
        candidate=self.text+'\n\nIn a town with 1,000 dollars and 1,000 bags of rice, each bag costs a dollar. — A hypothetical example.'
        self.assertEqual(self.review(lambda prompt:self.response(candidate)),candidate)
        self.assertEqual(editor.latest(self.project['id'])['completed_passes'],2)
        self.assertFalse(editor.requires_review(self.project['id']))
    def test_empty_or_malformed_script_still_stops_without_automatic_retry(self):
        for response in ({'script':''},{'script':None},{}):
            calls=[]
            def reply(prompt):calls.append(prompt);return response
            with self.subTest(response=response),self.assertRaises(ValueError):self.review(reply)
            self.assertEqual(len(calls),1)
            self.assertEqual(self.project['voice_script']['text'],self.text)
    def test_concurrent_author_edit_wins(self):
        def reply(prompt):self.project['voice_script']['text']='Author replacement';return self.response()
        with self.assertRaisesRegex(ValueError,'Автор змінив'):self.review(reply)
        self.assertEqual(self.project['voice_script']['text'],'Author replacement')
    def test_cancellation_never_publishes_candidate(self):
        job={}
        def reply(prompt):job['cancelled']=True;return self.response()
        with writing_jobs.scope(job),self.assertRaises(writing_jobs.Cancelled):self.review(reply)
        self.assertEqual(editor.latest(self.project['id'])['status'],'cancelled')
        self.assertEqual(self.project['voice_script']['text'],self.text)
    def test_score_and_example_validation(self):
        value=assessment();value['before_scores']['clarity']['score']=11
        with self.assertRaises(ValueError):editor.validate_editorial_report(value)
        response=self.response();response['editorial_report']['changes']=[{'before':'invented quote','after':'absent quote','reason':'wrong example'}]
        self.review(lambda prompt:response)
        report=editor.latest(self.project['id'])['editorial_report']
        self.assertFalse(report['changes'][0]['comparison_verified'])
        self.assertTrue(report['unresolved'])

    def test_slop_prompt_requests_approved_length_without_a_local_veto(self):
        prompts=[]
        def reply(prompt):prompts.append(prompt);return self.response()
        self.review(reply)
        self.assertIn('слід видалити',prompts[0])
        self.assertIn('ціле речення або завершена думка',prompts[0])
        self.assertIn('Косметичні заміни синонімів не рахуються',prompts[0])
        self.assertIn('найпоказовіших ПОВНИХ речень',prompts[0])
        self.assertIn('вся надежда сегодняшнего разговора',prompts[0])
        self.assertIn('перемены в тарелке имеют смысл',prompts[0])
        self.assertIn('Нижня межа не виправдовує',prompts[0])
        self.review(lambda prompt:self.response(),target=1000)
        self.assertEqual(editor.latest(self.project['id'])['status'],'done')
        self.assertFalse(editor.latest(self.project['id'])['length']['passed'])
        self.assertTrue(editor.latest(self.project['id']).get('after'))

    def test_current_blacklist_is_injected_and_reread_after_author_response(self):
        entries=['clear']
        def reply(prompt):
            self.assertIn('"blacklist": '+json.dumps(entries),prompt)
            entries[:]=['useful']
            return self.response(self.text.replace('clear','natural'))
        with patch.object(editor.word_blacklist,'managed',return_value=True),patch.object(editor.word_blacklist,'current',side_effect=lambda:list(entries)):
            self.review(reply,{'studio_word_blacklist':['obsolete']})
        report=editor.latest(self.project['id'])
        self.assertEqual(report['blacklist_snapshot'],['clear'])
        self.assertEqual(report['blacklist_final_check']['entries'],['useful'])
        self.assertTrue(report['blacklist_final_check']['changed_during_review'])
        self.assertEqual(report['blacklist_final_check']['matches'],['useful'])

    def test_both_editorial_turns_receive_whole_scenario_and_final_waits_for_refinement(self):
        self.text='\n\n'.join([('Paragraph '+name+' has clear useful spoken facts. ')*8 for name in ['one','two','three']])
        self.project['voice_script']['text']=self.text
        prompts=[]
        def reply(prompt):
            prompts.append(prompt)
            if len(prompts)==1:
                for part in editor.paragraphs(self.text):self.assertIn(part,prompt)
                return self.response(self.text.replace('clear','natural'))
            self.assertIn(self.text,prompt)
            self.assertIn(self.text.replace('clear','natural').strip(),prompt)
            self.assertEqual(self.project['voice_script']['text'],self.text)
            return self.response(self.text.replace('clear','precise'))
        result=self.review(reply)
        self.assertEqual(len(prompts),2)
        self.assertEqual(result,self.text.replace('clear','precise').strip())
        report=editor.latest(self.project['id'])
        self.assertEqual([r['phase'] for r in report['requests']],['main','refinement'])
        self.assertEqual(report['required_passes'],2);self.assertEqual(report['completed_passes'],2)

    def test_named_remaining_problems_remain_report_evidence_without_vetoing_script(self):
        response=self.response()
        response['refinement_report']['remaining_weaknesses']=[{'location':'Opening','problem':'Empty conclusion'}]
        self.review(lambda prompt:response)
        report=editor.latest(self.project['id'])
        self.assertEqual(report['status'],'done')
        self.assertEqual(report['completed_passes'],2)
        self.assertTrue(report['report_warnings'])
        self.assertEqual(self.project['voice_script']['text'],self.text)

    def test_both_live_prompts_cover_all_agreed_quality_checks(self):
        prompts=[]
        def reply(prompt):prompts.append(prompt);return self.response()
        self.review(reply)
        checks=['Референти займенників','Діяч і дія','Звірка сенсу кожної суттєвої правки',
                'Глобальні повтори конструкцій і образів','Узгодженість конкретних порад',
                'Інформаційна користь і темп','Природність під чорним списком',
                'Перевірка результату та доказовий звіт']
        self.assertEqual(len(prompts),2)
        for prompt in prompts:
            for check in checks:self.assertIn(check,prompt)
            self.assertIn('тонометр и меряйте его',prompt)
            self.assertIn('Измеряйте давление утром в спокойном состоянии',prompt)
            self.assertIn('пять ложек сладкого',prompt)
            self.assertIn('менять по одному продукту в неделю',prompt)
            self.assertIn('чайну ложку',prompt)
            self.assertIn('Не вигадуй нові твердження заради обсягу',prompt)

    def test_prompt_resource_updates_apply_without_module_or_server_reload(self):
        folder=self.root/'live-prompts';folder.mkdir()
        main=folder/'script_self_review.txt';refine=folder/'script_self_refine.txt'
        main.write_text(editor.PROMPT_PATH.read_text()+'\nMAIN_LIVE_RESOURCE')
        refine.write_text((editor.PROMPT_PATH.parent/'script_self_refine.txt').read_text()+'\nREFINE_OLD_RESOURCE')
        prompts=[]
        def reply(prompt):
            prompts.append(prompt)
            if len(prompts)==1:
                self.assertIn('MAIN_LIVE_RESOURCE',prompt)
                refine.write_text(refine.read_text().replace('REFINE_OLD_RESOURCE','REFINE_LIVE_RESOURCE'))
            else:
                self.assertIn('REFINE_LIVE_RESOURCE',prompt)
                self.assertNotIn('REFINE_OLD_RESOURCE',prompt)
            return self.response()
        with patch.object(editor,'PROMPT_PATH',main):self.review(reply)
        self.assertEqual(len(prompts),2)

class SelfReviewWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_backend
        cls.fixture=test_backend.BackendTest;cls.fixture.setUpClass()
    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()
    def run_workflow(self,fail=False,mutate=False,fail_refinement=False):
        import episode_automation
        p=store.create_project(store.channel_id(self.fixture.channel),'Author revision fixture')
        text='A selected opening. '+'Natural spoken words for the audience. '*33
        intermediate=text.replace('Natural','Clear')
        after=intermediate.replace('audience','listener')
        metadata={'titles':['Author revision fixture','Another useful angle','A different angle'],'description':'Thank you for watching. Subscribe.\n\nFor entertainment.','tags':['story','fiction','curiosity']}
        data={'id':p['id'],'project_id':p['id'],'channel_id':p['channel_id'],'context':{},'stage':'script','status':'running','selected':{'title':p['name']},'opening':'A selected opening.','target_words':editor.word_count(text)}
        sessions=[]
        def opus(prompt,root,identity,cid,**kwargs):
            sessions.append(kwargs)
            if len(sessions)==1:return {'script':text,'metadata':metadata}
            if mutate:store.save_project_source(store.load_project(p['id']),'The author replacement.')
            if fail or (fail_refinement and len(sessions)==3):raise OSError('Review unavailable')
            if len(sessions)==3:
                self.assertEqual(store.load_project(p['id'])['voice_script']['text'],text.strip())
                self.assertFalse(data.get('completed'))
            return {'script':intermediate if len(sessions)==2 else after,'editorial_report':assessment(),'refinement_report':{'remaining_weaknesses':[],'actions':[],'unresolved':[],'summary':'Перевірено.'}}
        with patch.object(editor,'self_review',wraps=REAL_REVIEW),patch.object(ideas,'opus',side_effect=opus),patch.object(ideas,'deepseek',side_effect=AssertionError('Separate editor forbidden')),patch.object(ideas.author_rules,'check',return_value=(True,'OK')),patch.object(episode_automation,'after_script') as handoff:
            ideas.work(p['channel_id'],data)
            return p,data,text,after,sessions,handoff.call_count
    def test_draft_and_revision_share_one_session_before_completion(self):
        p,data,before,after,calls,handoffs=self.run_workflow()
        self.assertEqual(data['status'],'done',data.get('error'));self.assertTrue(data['completed'])
        self.assertEqual(len(calls),3);self.assertEqual(calls[0]['session'],calls[1]['session']);self.assertEqual(calls[1]['session'],calls[2]['session']);self.assertTrue(calls[1]['resume']);self.assertTrue(calls[2]['resume'])
        self.assertEqual(store.load_project(p['id'])['voice_script']['text'],after.strip());self.assertEqual(handoffs,1)
        self.assertEqual(editor.latest(p['id'])['before'],before)
    def test_failed_revision_blocks_completion_voice_and_metadata_bypass(self):
        p,data,before,after,calls,handoffs=self.run_workflow(fail=True)
        self.assertEqual(data['status'],'failed');self.assertFalse(data['completed']);self.assertEqual(handoffs,0)
        self.assertEqual(store.load_project(p['id'])['voice_script']['text'],before.strip())
        with self.assertRaisesRegex(store.StudioError,'саморедактуру'):ideas.start_project(p['id'],{'action':'metadata'})
    def test_author_change_during_revision_is_preserved(self):
        p,data,*_=self.run_workflow(mutate=True)
        self.assertEqual(data['status'],'failed');self.assertEqual(store.load_project(p['id'])['voice_script']['text'],'The author replacement.')

    def test_refinement_failure_keeps_intermediate_without_publishing_it(self):
        p,data,before,after,calls,handoffs=self.run_workflow(fail_refinement=True)
        self.assertEqual(len(calls),3);self.assertEqual(data['status'],'failed');self.assertFalse(data['completed'])
        self.assertEqual(handoffs,0)
        self.assertEqual(store.load_project(p['id'])['voice_script']['text'],before.strip())
        report=editor.latest(p['id']);self.assertEqual(report['completed_passes'],1)
        self.assertTrue(report.get('intermediate'));self.assertNotIn('after',report)
