"""Explicit author wishes, resumed in the saved author session into a working draft."""
import copy
import json
import time
import uuid

import script_drafts
import store
import word_blacklist
import writing_jobs

MAX_WISHES = 12000


def valid_session(value):
    try:
        uuid.UUID(value['session_id'])
        if not isinstance(value['model'], str) or not value['model'].startswith('claude-opus-'):
            return None
        if value['effort'] not in {'low', 'medium', 'high', 'xhigh', 'max'}:
            return None
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    return copy.deepcopy(value)


def author_session(pid, data):
    """Recover only recorded author identity; a receipt must match saved script text."""
    found = valid_session(data.get('author_session') or {})
    if found:
        return found
    root = store.project_dir(pid)
    editorial = store.read_json(root / 'script-editing/latest.json', {}) or {}
    if editorial.get('project_id') == pid and editorial.get('provider') == 'claude_code' and editorial.get('mode') in {'author_self_review_v1', 'author_revision_v1'}:
        found = valid_session({'session_id': editorial.get('session_id'), 'model': editorial.get('model'),
            'effort': editorial.get('reasoning_effort'), 'api_cost_usd': editorial.get('session_cumulative_api_cost_usd')})
        if found:
            return found
    draft = store.read_json(root / 'script-draft.json', {}) or {}
    text = draft.get('script')
    texts = {text.strip()} if isinstance(text, str) else set()
    first = root / 'script-first-draft.txt'
    if first.is_file():
        texts.add(first.read_text().strip())
    texts.discard('')
    for path in sorted(root.glob('script-*-receipt.json'), reverse=True):
        receipt = store.read_json(path, {}) or {}
        try:
            from episode_ideas import unpack
            result = unpack(receipt.get('result'))
        except (ValueError, TypeError, AttributeError):
            continue
        if not isinstance(result, dict) or not isinstance(result.get('script'), str) or result['script'].strip() not in texts:
            continue
        usage = receipt.get('modelUsage')
        if not isinstance(usage, dict) or not all(isinstance(row, dict) for row in usage.values()):
            continue
        models = {row.get('canonicalModel') or name for name, row in usage.items()}
        if len(models) != 1:
            continue
        found = valid_session({'session_id': receipt.get('session_id'), 'model': models.pop(),
            'effort': data.get('effort'), 'api_cost_usd': receipt.get('total_cost_usd')})
        if found:
            return found
    return None


def availability(pid):
    data = store.read_json(store.project_dir(pid) / 'episode-draft.json', {}) or {}
    session = author_session(pid, data)
    return {'author_revision_supported': True, 'can_revise': bool(session),
            'revision_wishes': data.get('revision_wishes', ''),
            'revision_reason': '' if session else 'Сесію автора цього сценарію не збережено. Продовжити її через Opus неможливо.'}


def prepare(project, data, body):
    wishes = body.get('wishes')
    if not isinstance(wishes, str) or not wishes.strip() or len(wishes) > MAX_WISHES:
        raise store.StudioError('Напишіть побажання до правок, до 12 000 символів')
    session = author_session(project['id'], data)
    if not session:
        raise store.StudioError('Немає збереженої сесії автора. Нову сесію замість неї не запускаємо.', 409)
    from episode_ideas import ACTIVE
    if any(job.get('project_id') != project['id'] and (job.get('author_session') or {}).get('session_id') == session['session_id'] for job in ACTIVE.values()):
        raise store.StudioError('Ця сесія Opus уже працює над іншим запитом. Дочекайтеся завершення.', 409)
    with store.LOCK:
        current = script_drafts.current(project['id'])
        if not current['text'].strip():
            raise store.StudioError('Спершу додайте сценарій')
        if any(body.get(key) != current[field] for key, field in
               (('expected_version', 'version'), ('base_sha256', 'base_sha256'), ('epoch', 'epoch'), ('sha256', 'sha256'))):
            raise store.StudioError('Сценарій змінився. Збережіть правки й відкрийте вікно ще раз.', 409)
        identity = uuid.uuid4().hex
        folder = store.project_dir(project['id']) / 'script-editing' / identity
        store.atomic_text(folder / 'before.txt', current['text'])
        base = {key: current[key] for key in ('version', 'base_sha256', 'epoch', 'sha256')}
        data.update(author_session=session, manual_revision=True, revision_wishes=wishes.strip(),
                    revision_id=identity, revision_base=base, completed=False,
                    script_saved=True, editing_status='running')


def run(project, data, ctx, ask, receipt_file):
    import script_editing
    pid = project['id']
    folder = store.project_dir(pid) / 'script-editing' / data['revision_id']
    before = (folder / 'before.txt').read_text()
    session = data['author_session']
    report = {'id': data['revision_id'], 'project_id': pid, 'mode': 'author_revision_v1',
              'provider': 'claude_code', 'cost_basis': 'api_equivalent', 'status': 'running',
              'started_at': time.time(), 'session_id': session['session_id'],
              'model': session['model'], 'reasoning_effort': session['effort'],
              'wishes': data['revision_wishes'], 'before': before, 'before_words': script_editing.word_count(before)}
    script_editing._save(folder, report)
    try:
        requirements = {key: ctx[key] for key in ('channel_agent_rules', 'script_wishes', 'author_writing_rules', 'youtube_script_rules', 'channel_script_rules', 'claude_memory_notes') if ctx.get(key)}
        requirements['word_blacklist'] = word_blacklist.current()
        requirements['selected_title'] = project['name']
        prompt = ('Revise this complete script in the SAME author session according to the new author wishes. '
                  'Keep its language, supported facts, names, numbers and unrequested content. '
                  'Apply the wishes substantively. Preserve approximate length unless the wishes request a change. '
                  'Review your changes for natural spoken phrasing and meaning before returning them. '
                  'Do not use antithesis or em dashes. '
                  'Return only JSON {"script":"the COMPLETE revised script","summary":"a short Ukrainian summary of the changes"}.\n'
                  'AUTHOR WISHES:\n' + data['revision_wishes'] + '\nCURRENT CHANNEL REQUIREMENTS:\n' +
                  json.dumps(requirements, ensure_ascii=False) + '\nCURRENT COMPLETE SCRIPT:\n' + before)
        store.atomic_text(folder / 'prompt.txt', prompt)
        result = ask(prompt)
        store.atomic_json(folder / 'response.json', result)
        after = result.get('script') if isinstance(result, dict) else None
        if not isinstance(after, str) or not after.strip() or len(after) > script_drafts.MAX_TEXT:
            raise ValueError('Opus не повернув повний сценарій. Попередній текст збережено.')
        after = after.strip()
        store.atomic_text(folder / 'after.txt', after)
        report.update(after=after, after_sha256=script_editing.digest(after), after_words=script_editing.word_count(after))
        report.update(checks_advisory=True, blacklist_final_check={'matches': word_blacklist.matches(after, word_blacklist.current())})
        from episode_ideas import LOCK
        with LOCK, store.LOCK:
            writing_jobs.check()
            current = script_drafts.current(pid)
            if any(current[key] != value for key, value in data['revision_base'].items()):
                raise ValueError('Сценарій змінено під час роботи Opus. Його результат збережено окремо.')
            saved = script_drafts.save(pid, {'text': after, 'expected_version': current['version'],
                'base_sha256': current['base_sha256'], 'epoch': current['epoch']})
        report.update(status='done', after=after, after_sha256=script_editing.digest(after), after_words=script_editing.word_count(after),
                      editorial_summary=str(result.get('summary') or '')[:2000], finished_at=time.time())
        old, new = script_editing.paragraphs(before), script_editing.paragraphs(after)
        report['paragraphs'] = [{'id': index + 1, 'before': old[index] if index < len(old) else '',
            'after': new[index] if index < len(new) else '', 'status': 'done',
            'changed': (old[index] if index < len(old) else '') != (new[index] if index < len(new) else '')} for index in range(max(len(old), len(new)))]
        report.update(changed_paragraphs=sum(row['changed'] for row in report['paragraphs']),
                      deleted_paragraphs=sum(not row['after'] for row in report['paragraphs']))
        data.update(revision_draft_version=saved['version'], editing_status='done', completed=True, review_required=False,
                    status='done', actual_words=report['after_words'], finished_at=time.time())
    except Exception as error:
        report.update(status='cancelled' if isinstance(error, writing_jobs.Cancelled) else 'failed', error=str(error), finished_at=time.time())
        data['editing_status'] = report['status']
        raise
    finally:
        receipt = store.read_json(receipt_file, {}) or {}
        if receipt:
            store.atomic_json(folder / 'author-receipt.json', receipt)
        report.update(request_id=receipt.get('identity'), receipt_session_id=receipt.get('session_id'),
                      cost_usd=receipt.get('incremental_cost_usd'), usage=receipt.get('usage'),
                      session_cumulative_api_cost_usd=receipt.get('total_cost_usd'))
        script_editing._save(folder, report)
