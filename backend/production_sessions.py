"""Bound the context of long frame runs; never retry a failed or uncertain session."""
import copy
import threading

SESSION_FRAMES = 15  # fewer sessions re-reading the same brief: about a third cheaper (user, 16 November 2026: «15 кадрів зроби краще в 1 сесії»)


def add_usage(total, value):
    for key, number in (value or {}).items():
        if isinstance(number, dict):add_usage(total.setdefault(key, {}), number)
        elif isinstance(number, (int, float)) and not isinstance(number, bool):total[key] = total.get(key, 0) + number


REVIEW_NOTE = ('\nПотрібен лише актуальний візуальний огляд цих кадрів. Збережи готові сцени, зображення й таймлайн. '
               'Зроби аркуші змінених кадрів, переглянь і зафіксуй результат. Виправляй композицію лише за виявленим дефектом.')
# Every chunk of ten frames gets its own session at once, and a session that is done takes the next chunk left (user,
# 14 November 2026: «65 кадрів… створити 6 сесій… як тільки звільниться одна сесія, наступна може брати… щоб швидко
# було»). Each session starts from an empty context anyway, so the limits spent stay the same and only come faster;
# the timeline and Razgon's shared files are locked per change, and the Chromiums of their stills wait for one of a
# few slots (kit tools/chromium_gate.py). PARALLEL caps one episode at 8, STUDIO_SESSIONS all episodes together at 30
# (user, 14 November 2026: «на ролик 8 сесій… для студії… 40», then «нехай 30»; a Claude CLI
# session took about 130 MB, at most 440 MB, that day).
PARALLEL = 8
STUDIO_SESSIONS = threading.BoundedSemaphore(30)
STAGGER = .5   # seconds between the starts of an episode's sessions


def run(targets, launch, verify, checkpoint, cancelled, stop, *, previous=None, pending_review=None, parallel=None):
    from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
    targets = sorted(set(targets))
    previous = previous or {}
    completed = set(previous.get('completed_frames') or []) & set(targets)
    totals = {'summary': str(previous.get('summary') or '')[-1200:], 'cost': 0, 'duration': 0, 'turns': 0}
    usage, models = {}, {}
    answer = {'result': totals['summary'], 'session_id': previous.get('session_id')}
    lock = threading.Lock()
    failure = []
    chunks = [(index, targets[start:start + SESSION_FRAMES]) for index, start in enumerate(range(0, len(targets), SESSION_FRAMES), 1)]
    numbered = len(targets) > SESSION_FRAMES
    side_by_side = max(1, int(parallel or PARALLEL)) > 1 and len(chunks) > 1

    def account(raw):
        nonlocal answer
        with lock:
            answer = copy.deepcopy(raw)
            totals['cost'] += float(raw.get('total_cost_usd') or 0)
            add_usage(usage, raw.get('usage'))
            add_usage(models, raw.get('modelUsage'))
            totals['duration'] += raw.get('duration_ms') or 0
            totals['turns'] += raw.get('num_turns') or 0
            answer.update(total_cost_usd=totals['cost'], usage=copy.deepcopy(usage), modelUsage=copy.deepcopy(models),
                          duration_ms=totals['duration'], num_turns=totals['turns'])
            return copy.deepcopy(answer)

    def session(index, frames):
        """One chunk of ten frames: None when it is done, else (code, answer) that stops the run."""
        if cancelled():raise InterruptedError('Створення кадрів зупинено')
        with lock:
            saved = [n for n in frames if n in completed]
        if saved and not verify(saved):
            # A changed neighbour must not replay the other approved frames in this scope. A frame that is drawn and
            # only waits for a fresh look stays made: the one final review after all sessions looks at it.
            stale = set(pending_review() or []) if pending_review else set()
            with lock:
                completed.difference_update(n for n in saved if n not in stale and not verify([n]))
        with lock:
            frames = [n for n in frames if n not in completed]
            summary = totals['summary']
        if not frames:
            return None
        if previous and pending_review and not verify(frames) and set(frames) <= set(pending_review() or []):
            # A continuation after a pause or a limit found this chunk already drawn; its frames only need a fresh look.
            # Opening a working session for that cost 5-15 turns per chunk (user, 15 November 2026: «ліміти витрачаються
            # швидко»); the final review looks at all such frames together instead.
            with lock:
                completed.update(frames)
            return None
        with STUDIO_SESSIONS:
            code, raw = launch(frames, summary, index if numbered else 0)
        result = account(raw)
        if cancelled():raise InterruptedError('Створення кадрів зупинено')
        if code or raw.get('is_error') or stop(raw):return code or 1, result
        valid = verify(frames)
        pending = sorted(set(pending_review() or [])) if not valid and pending_review else []
        if pending and set(pending) <= set(frames) and DEFERRED_REVIEW:
            # Drawn frames that only wait for a look count as made: one low-effort review looks at the whole film at
            # the end instead of a look inside every session (user, 15 November 2026: «роби все що здешевить перевірки
            # … і головне пришвидшить»)
            valid = True
            pending = []
        if pending and set(pending) <= set(frames):
            if cancelled():raise InterruptedError('Створення кадрів зупинено')
            with STUDIO_SESSIONS:
                code, raw = launch(pending, summary + REVIEW_NOTE, 1000 + index)
            result = account(raw)
            if cancelled():raise InterruptedError('Створення кадрів зупинено')
            if code or raw.get('is_error') or stop(raw):return code or 1, result
            valid = verify(frames)
        if not valid and side_by_side and pending_review and set(pending_review() or []) & set(frames):
            # Drawn and reviewed, but the session next door changed a shared scene file or added PNGs meanwhile, so the
            # verdicts look stale (user, 14 November 2026: both Космос episodes stopped this way). The frames count as
            # made; the one final review after all sessions looks at them again instead of stopping the episode.
            valid = True
        if not valid:
            result.update(is_error=True, result='Поточний пакет кадрів не завершений або не пройшов перевірку. Готові результати збережено.')
            return 1, result
        with lock:
            completed.update(frames)
            totals['summary'] = str(raw.get('result') or '')[-1200:]
            checkpoint({'completed_frames': sorted(completed), 'remaining_frames': sorted(set(targets) - completed),
                        'summary': totals['summary'], 'session': index, 'session_id': raw.get('session_id')})
        return None

    width = min(max(1, int(parallel or PARALLEL)), len(chunks) or 1)
    if width == 1 or len(chunks) == 1:
        for index, frames in chunks:
            stopped = session(index, frames)
            if stopped:return stopped
        return 0, answer
    queue = list(chunks)
    errors = []
    with ThreadPoolExecutor(max_workers=width) as pool:
        running = set()
        while queue or running:
            while queue and len(running) < width and not failure and not errors:
                index, frames = queue.pop(0)
                running.add(pool.submit(session, index, frames))
                if len(running) < width and queue:
                    import time
                    time.sleep(STAGGER)   # the sessions do not start in the same instant
            if not running:break
            done, running = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                try:
                    stopped = future.result()
                except BaseException as error:   # a stop or a crash: let the other session finish, then raise
                    errors.append(error)
                    continue
                if stopped and not failure:failure.append(stopped)
    if errors:raise errors[0]
    if failure:return failure[0]
    return 0, answer


def merge_answers(previous, current):
    """Keep original paid-work receipts when a final scoped review is needed."""
    result=copy.deepcopy(current)
    for key in ('total_cost_usd','duration_ms','num_turns'):
        result[key]=(previous.get(key) or 0)+(current.get(key) or 0)
    for key in ('usage','modelUsage'):
        value=copy.deepcopy(previous.get(key) or {})
        add_usage(value,current.get(key))
        result[key]=value
    return result


# Sessions draw and run the free automatic checks; the look at the pictures is one review session at the end.
DEFERRED_REVIEW = True


def finish_review(numbers, launch, verify, cancelled, stop):
    """One bounded pass for stale final receipts, including earlier frame batches."""
    summary=('Потрібен лише актуальний візуальний огляд перелічених готових кадрів. '
             'Збережи сцени, матеріали й таймлайн. Онови кешовані стоп-кадри. '
             'Якщо пікселі не змінилися, збережи попередні схвалення. '
             'Переглянь лише кадри, які справді змінилися, і зафіксуй результат. '
             'Не перебудовуй готові сцени; виправляй лише підтверджені візуальні дефекти.')
    return run(numbers,lambda ns,_,index:launch(ns,summary,2000+index),verify,
               lambda receipt:None,cancelled,stop)
