"""Author self-review in the original Claude session, plus immutable historical comparisons."""
import difflib
import hashlib
import json
import re
import time
import uuid
from pathlib import Path

import store
import word_blacklist
import writing_jobs

CRITERIA = [
    'Unnecessary claims of significance, symbolism or historical importance',
    'Name-dropping media or fame without useful information',
    'Superficial analysis and abstract claims instead of concrete explanations',
    'Promotional praise, empty hype or guaranteed outcomes',
    'Unnecessary didactic disclaimers and editorial reminders',
    'Repetitive summaries that add no viewer value',
    'Generic optimistic future prospects',
    'Treating a title as a defined technical term',
    'Broken or fabricated source references',
    'Invented publications or source claims; never invent replacements',
    'Chatbot tracking parameters in links',
    'Leftover assistant conversation or offers to help',
    'Model knowledge-cutoff disclaimers or speculative gap filling',
    'Unfilled template placeholders and generic formal addresses',
    'Overlong, illogical participial constructions and bureaucratic wording',
    'Formulaic negative parallelisms and antitheses',
    'Forced groups of three',
    'Vague unnamed doctors, experts or researchers used as rhetorical authority',
    'Unnatural synonym cycling, respecting the actual word blacklist',
    'Meaningless ranges between unrelated extremes',
    'Inappropriate markup for spoken narration',
    'Invented wiki categories, where applicable',
    'Unnatural title capitalization',
    'Mechanical bold emphasis',
    'Outline-like lists with repetitive inline headings',
    'Excessive long dashes',
]
EDITOR_MODE = 'author_self_review_v1'
EDITOR_POLICY = 'slop_check_v3'

PROMPT_PATH=Path(__file__).parent/'prompts'/'script_self_review.txt'
PROMPT=PROMPT_PATH.read_text(encoding='utf-8')
SCORE_KEYS=('clarity','grammar','naturalness','logic','originality','title_promise')


def validate_editorial_report(value):
    if not isinstance(value,dict) or value.get('assessment_type')!='subjective_editorial':
        raise ValueError('Opus не повернув окремий редакторський звіт')
    for name in ('before_scores','after_scores'):
        scores=value.get(name)
        if not isinstance(scores,dict):raise ValueError('Немає оцінок редактури до/після')
        for key in SCORE_KEYS:
            row=scores.get(key)
            if (not isinstance(row,dict) or type(row.get('score')) is not int or not 1<=row['score']<=10
                    or not isinstance(row.get('reason'),str) or not row['reason'].strip()):
                raise ValueError('Некоректна редакторська оцінка або відсутнє пояснення')
    for name,fields in [('weaknesses',('location','problem')),('changes',('before','after','reason')),
                        ('unresolved',('location','issue'))]:
        rows=value.get(name)
        if not isinstance(rows,list) or any(not isinstance(row,dict) or any(not isinstance(row.get(k),str) for k in fields) for row in rows):
            raise ValueError('Некоректний список у редакторському звіті: '+name)
    if any(type(row.get('needs_fact_check')) is not bool for row in value['unresolved']):
        raise ValueError('Не вказано потребу перевірки невирішених питань')
    if not isinstance(value.get('summary'),str):raise ValueError('Немає підсумку редактури')
    return value


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def root(pid):
    store.load_project(pid)
    return store.project_dir(pid) / 'script-editing'


def availability(pid):
    """A lightweight existence read for the script toolbar; never load full before/after text."""
    import script_revisions
    return {**script_revisions.availability(pid), 'available': (root(pid)/'latest.json').is_file(), 'editor_mode':EDITOR_MODE,
            'editor_policy':EDITOR_POLICY,'required_editorial_passes':2,'author_session_review':True}


def latest(pid):
    return store.read_json(root(pid) / 'latest.json', {}) or {}


def requires_review(pid):
    """Compatibility for callers: the author's ready script needs no local approval."""
    return False


def author_report(value, warnings, phase, *, refinement=False):
    """Keep usable report evidence without discarding a ready script over report defects."""
    result = dict(value) if isinstance(value, dict) else {}
    if not refinement:
        try:
            validate_editorial_report(value)
        except ValueError as error:
            warnings.append({'phase': phase, 'message': str(error)})
        for name in ('before_scores', 'after_scores'):
            scores = result.get(name)
            result[name] = {key: dict(row) for key, row in (scores.items() if isinstance(scores, dict) else [])
                           if key in SCORE_KEYS and isinstance(row, dict) and type(row.get('score')) is int
                           and 1 <= row['score'] <= 10 and isinstance(row.get('reason'), str)}
    fields = [('remaining_weaknesses' if refinement else 'weaknesses', ('location', 'problem')),
              ('actions' if refinement else 'changes', ('before', 'after', 'reason')),
              ('unresolved', ('location', 'issue'))]
    for name, required in fields:
        rows = result.get(name)
        valid = [dict(row) for row in rows if isinstance(row, dict)
                 and all(isinstance(row.get(key), str) for key in required)] if isinstance(rows, list) else []
        if refinement and (not isinstance(rows, list) or len(valid) != len(rows)):
            warnings.append({'phase': phase, 'message': 'Некоректний список у звіті: ' + name})
        result[name] = valid
    if not isinstance(result.get('summary'), str):
        result['summary'] = ''
    return result


def _save(folder, data):
    store.atomic_json(folder / 'report.json', data)
    store.atomic_json(folder.parent / 'latest.json', data)


def receipt_path(folder, identity):
    return folder / 'requests' / identity / 'receipt.json'



def paragraphs(text):
    return [part.strip() for part in re.split(r'\n\s*\n',text.strip()) if part.strip()]


def validate(response, before, blacklist, *, paragraph_ids=None, allow_empty=False):
    rows=response.get('paragraphs') if isinstance(response,dict) else None
    if not isinstance(rows,list) or len(rows)!=len(before):raise ValueError('Редактор повернув неповний список абзаців')
    result=[]
    ids=list(range(1,len(before)+1)) if paragraph_ids is None else paragraph_ids
    if len(ids)!=len(before):raise ValueError('Некоректний список цільових абзаців')
    for i,old,row in zip(ids,before,rows):
        if not isinstance(row,dict) or type(row.get('id')) is not int or row['id']!=i or not isinstance(row.get('text'),str):
            raise ValueError('Редактор змінив нумерацію або формат абзаців')
        new=row['text'].strip()
        # Deletion is allowed. Changed numeric facts must not silently enter an edited paragraph.
        numbers=lambda s:set(re.findall(r'\d+(?:[.,]\d+)?',s))
        if numbers(new)-numbers(old):raise ValueError(f'Редактор додав або змінив число в абзаці {i}')
        if '—' in new or '–' in new:raise ValueError(f'Редактор додав довге тире в абзаці {i}')
        issues=row.get('criteria',[])
        if not isinstance(issues,list) or any(type(n) is not int or not 1<=n<=26 for n in issues):raise ValueError('Некоректні критерії редактури')
        reason=row.get('reason','')
        if not isinstance(reason,str):raise ValueError('Некоректне пояснення редактури')
        result.append({'id':i,'before':old,'after':new,'criteria':issues,'reason':reason[:1000],'changed':old!=new})
    text='\n\n'.join(row['after'] for row in result if row['after'])
    if not text and not allow_empty:raise ValueError('Редактор видалив увесь сценарій')
    blocked=word_blacklist.message(text,blacklist)
    if blocked:raise ValueError(blocked)
    return text,result


def word_count(text):
    return len(re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)*",text))


def self_review(pid, text, ctx, target_words, session, ask, receipt_file):
    """Two bounded whole-script turns in the original author session; never publish here."""
    writing_jobs.check()
    base=root(pid);identity=uuid.uuid4().hex;folder=base/identity
    blacklist=word_blacklist.normalize(word_blacklist.current() if word_blacklist.managed() else ctx.get('studio_word_blacklist',[]))
    source=(store.load_project(pid).get('voice_script') or {}).get('text','')
    report={'id':identity,'project_id':pid,'mode':EDITOR_MODE,'status':'running','started_at':time.time(),
            'model':session['model'],'reasoning_effort':session['effort'],'session_id':session['session_id'],
            'provider':'claude_code','cost_basis':'api_equivalent','cost_usd':None,'requests':[],
            'before':text,'before_sha256':digest(text),'before_words':word_count(text),'paragraphs':[],
            'editor_policy':EDITOR_POLICY,'blacklist_snapshot':blacklist,'required_passes':2,'completed_passes':0,
            'report_warnings':[],'checks_advisory':True}
    store.atomic_text(folder/'before.txt',text);_save(folder,report)

    def check_source():
        writing_jobs.check()
        if (store.load_project(pid).get('voice_script') or {}).get('text','')!=source:
            raise ValueError('Автор змінив сценарій під час саморедактури. Обидві версії збережено окремо.')

    def call(prompt, phase):
        check_source();report['phase']=phase
        store.atomic_text(folder/(phase+'-prompt.txt'),prompt);_save(folder,report)
        try:
            result=ask(prompt,phase)
            store.atomic_json(folder/(phase+'-response.json'),result)
            return result
        finally:
            path=receipt_file.with_name(receipt_file.name.removesuffix('-receipt.json')+'-'+phase+'-receipt.json')
            receipt=store.read_json(path,{}) or {}
            report['requests'].append({'phase':phase,'provider':'claude_code','cost_basis':'api_equivalent',
                'request_id':receipt.get('identity'),'session_id':receipt.get('session_id'),
                'cost_usd':receipt.get('incremental_cost_usd'),'usage':receipt.get('usage')})
            if receipt:store.atomic_json(folder/'author-receipts'/(phase+'.json'),receipt)
            known=[r['cost_usd'] for r in report['requests'] if type(r.get('cost_usd')) in (int,float)]
            report.update(known_cost_usd=sum(known),unknown_request_costs=len(report['requests'])-len(known),
                cost_usd=sum(known) if len(known)==len(report['requests']) else None,
                request_id=receipt.get('identity'),receipt_session_id=receipt.get('session_id'),
                session_cumulative_api_cost_usd=receipt.get('total_cost_usd'))
            usage={}
            for key in ('input_tokens','cache_creation_input_tokens','cache_read_input_tokens','output_tokens'):
                values=[(row.get('usage') or {}).get(key) for row in report['requests']]
                if all(type(v) is int for v in values):usage[key]=sum(values)
            report['usage']=usage;_save(folder,report)

    try:
        minimum=(target_words*93+99)//100;maximum=target_words*107//100
        policy=PROMPT_PATH.read_text(encoding='utf-8')
        report['prompt_sha256']=digest(policy)
        requirements={'title':ctx.get('selected_title'),'approved_opening':ctx.get('approved_opening'),
            'channel_context':{k:ctx.get(k) for k in ('channel','audience','language','narrator',
                'channel_agent_rules','script_wishes','author_writing_rules','youtube_script_rules','channel_script_rules','claude_memory_notes')},
            'minimum_words':minimum,'maximum_words':maximum,'blacklist':blacklist,
            'blacklist_matching':'Case-insensitive complete words/phrases; whitespace normalized, ё=е, apostrophes normalized. '
                'Only listed legacy families белок/белка, білок, сахар/сахара, гвоздика, душа have special derived-form matching. '
                'Other entries are literal complete words/phrases, not arbitrary roots.',
            'blacklist_findings':word_blacklist.message(text,blacklist)}
        prompt=policy+'\nEDITORIAL CLUES:\n'+json.dumps(dict(enumerate(CRITERIA,1)),ensure_ascii=False)
        prompt+='\nCURRENT REQUIREMENTS:\n'+json.dumps(requirements,ensure_ascii=False)
        prompt+='\nCURRENT COMPLETE DRAFT TO REVISE:\n'+text
        store.atomic_text(folder/'prompt.txt',prompt)
        main=call(prompt,'main')
        intermediate=main.get('script') if isinstance(main,dict) else None
        if not isinstance(intermediate,str) or not intermediate.strip():
            raise ValueError('Opus не повернув повну основну редакцію сценарію')
        intermediate=intermediate.strip()
        store.atomic_text(folder/'intermediate.txt',intermediate)
        report.update(intermediate=intermediate,intermediate_words=word_count(intermediate))
        main_report=author_report(main.get('editorial_report'),report['report_warnings'],'main')
        report.update(main_editorial_report=main_report,completed_passes=1)
        store.atomic_json(folder/'main-editorial-report.json',main_report);_save(folder,report)
        check_source()
        current_blacklist=word_blacklist.current() if word_blacklist.managed() else blacklist
        refine_policy=(PROMPT_PATH.parent/'script_self_refine.txt').read_text(encoding='utf-8')
        refine_prompt=refine_policy+'\nCURRENT REQUIREMENTS:\n'+json.dumps({
            **requirements,'blacklist':current_blacklist,
            'blacklist_findings':word_blacklist.message(intermediate,current_blacklist)},ensure_ascii=False)
        refine_prompt+='\nORIGINAL COMPLETE DRAFT (READ ONLY):\n'+text
        refine_prompt+='\nCOMPLETE MAIN EDITION TO ASSESS AND REFINE:\n'+intermediate
        refine_prompt+='\nMAIN EDITORIAL REPORT:\n'+json.dumps(main_report,ensure_ascii=False)
        result=call(refine_prompt,'refinement')
        store.atomic_json(folder/'author-response.json',result)
        candidate=result.get('script') if isinstance(result,dict) else None
        if not isinstance(candidate,str) or not candidate.strip():
            raise ValueError('Opus не повернув повний сценарій після доопрацювання')
        candidate=candidate.strip()
        report.update(after=candidate,after_sha256=digest(candidate),after_words=word_count(candidate))
        store.atomic_text(folder/'after.txt',candidate)
        final_report=author_report(result.get('editorial_report'),report['report_warnings'],'refinement')
        refinement=author_report(result.get('refinement_report'),report['report_warnings'],'refinement',refinement=True)
        if refinement['remaining_weaknesses'] and not refinement['unresolved'] and (not refinement['actions'] or candidate==intermediate):
            report['report_warnings'].append({'phase':'refinement',
                'message':'Opus назвав залишкові недоліки без зафіксованих правок у звіті.'})
        final_report['before_scores']=main_report['before_scores']
        final_report['intermediate_scores']=main_report['after_scores']
        final_report['unresolved']+=refinement['unresolved']
        for changes,original in [(final_report['changes'],text),(refinement['actions'],intermediate)]:
            for change in changes:
                change['comparison_verified']=change['before'] in original and change['after'] in candidate
            unverified=sum(not row['comparison_verified'] for row in changes)
            if unverified:final_report['unresolved'].append({'location':'Приклади у звіті редактора',
                'issue':f'{unverified} прикладів не є точними цитатами збережених версій. Перевірте їх за підсвіченим порівнянням.',
                'needs_fact_check':False})
        report.update(editorial_report=final_report,refinement_report=refinement,
            editorial_summary=final_report['summary'],completed_passes=2)
        old,new=paragraphs(text),paragraphs(candidate);rows=[]
        for tag,a,b,c,d in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
            pairs=zip(old[a:b],new[c:d]) if tag=='equal' else [('\n\n'.join(old[a:b]),'\n\n'.join(new[c:d]))]
            for left,right in pairs:rows.append({'id':len(rows)+1,'before':left,'after':right,'changed':left!=right,
                                                'criteria':[],'reason':'','status':'done'})
        report.update(paragraphs=rows,changed_paragraphs=sum(r['changed'] for r in rows),
                      deleted_paragraphs=sum(not r['after'] for r in rows),comparison_unit='fragment')
        _save(folder,report);check_source()
        final_blacklist=word_blacklist.current() if word_blacklist.managed() else blacklist
        report['blacklist_final_check']={'entries':final_blacklist,'changed_during_review':final_blacklist!=blacklist,
            'matches':word_blacklist.matches(candidate,final_blacklist)}
        report['length']={'actual':report['after_words'],'minimum':minimum,'maximum':maximum,
                          'passed':minimum<=report['after_words']<=maximum}
        report.update(status='done',finished_at=time.time())
        return candidate
    except Exception as error:
        report.update(status='cancelled' if isinstance(error,writing_jobs.Cancelled) else 'failed',
                      error=str(error)[:500],finished_at=time.time())
        raise
    finally:_save(folder,report)



def validation_failed(pid, message):
    report=latest(pid)
    if report:
        report.update(status='failed',error=message,finished_at=time.time())
        _save(root(pid)/report['id'],report)


def diff_tokens(old,new):
    left=re.findall(r'\s+|[^\s]+',old);right=re.findall(r'\s+|[^\s]+',new)
    if max(len(left),len(right))>16000:return {'before':[{'text':old,'changed':old!=new}], 'after':[{'text':new,'changed':old!=new}]}
    result={'before':[],'after':[]}
    for tag,a,b,c,d in difflib.SequenceMatcher(None,left,right,autojunk=False).get_opcodes():
        if a!=b:result['before'].append({'text':''.join(left[a:b]),'changed':tag!='equal'})
        if c!=d:result['after'].append({'text':''.join(right[c:d]),'changed':tag!='equal'})
    return result


def view(pid, identity=None):
    base=root(pid)
    if identity is not None and not re.fullmatch(r'[0-9a-f]{32}',identity):
        raise store.StudioError('Редакцію не знайдено',404)
    report=store.read_json(base/identity/'report.json',{}) if identity else latest(pid)
    if not report:
        if identity is not None:raise store.StudioError('Редакцію не знайдено',404)
        return {'available':False}
    if report.get('status')=='running':
        import episode_ideas
        if pid not in episode_ideas.ACTIVE:
            report={**report,'status':'failed','error':'Редактуру перервано. Оригінал збережено; повтор можливий лише за вашою дією.'}
    rows=[]
    for row in report.get('paragraphs',[]):
        tokens=diff_tokens(row['before'],row['after'])
        rows.append({**row,'before_tokens':tokens['before'],'after_tokens':tokens['after']})
    runs=[]
    for file in base.glob('*/report.json'):
        value=store.read_json(file,{}) or {}
        runs.append({k:value.get(k) for k in ('id','started_at','status','provider','cost_basis','cost_usd','known_cost_usd','unknown_request_costs')})
    runs.sort(key=lambda row:row.get('started_at') or 0,reverse=True)
    totals={}
    for run in runs:
        provider=run.get('provider') or 'openrouter'
        amount=run.get('known_cost_usd') if type(run.get('known_cost_usd')) in (int,float) else run.get('cost_usd')
        totals[provider]=totals.get(provider,0)+(amount or 0)
    report={**report,'cost_totals':[{'provider':p,'cost_usd':v} for p,v in totals.items()],'available':True,'paragraphs':rows,'runs':runs,
            'total_cost_usd':sum((row.get('known_cost_usd') if type(row.get('known_cost_usd')) in (int,float) else row.get('cost_usd')) or 0 for row in runs),
            'unknown_charges':sum(row.get('unknown_request_costs') if row.get('unknown_request_costs') is not None else int(row.get('cost_usd') is None) for row in runs)}
    current=(store.load_project(pid).get('voice_script') or {}).get('text','')
    if report.get('mode')=='author_revision_v1':
        import script_drafts
        current=script_drafts.current(pid)['text']
    report['matches_current']=digest(current)==report.get('after_sha256')
    return report
