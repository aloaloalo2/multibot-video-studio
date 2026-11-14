"""Bound the context of long frame runs; never retry a failed or uncertain session."""
import copy

SESSION_FRAMES = 10  # Two batches of five; discard images/tool history before it dominates the next batch.


def add_usage(total, value):
    for key, number in (value or {}).items():
        if isinstance(number, dict):add_usage(total.setdefault(key, {}), number)
        elif isinstance(number, (int, float)) and not isinstance(number, bool):total[key] = total.get(key, 0) + number


REVIEW_NOTE = ('\nПотрібен лише актуальний візуальний огляд цих кадрів. Збережи готові сцени, зображення й таймлайн. '
               'Зроби аркуші змінених кадрів, переглянь і зафіксуй результат. Виправляй композицію лише за виявленим дефектом.')
# Two sessions of ten frames run side by side (user, 14 November 2026: «чому не запустити ще одну сесію, яка буде також
# працювати над 10 кадрами?»). Each session starts from an empty context anyway, so the limits spent stay the same and
# the episode is ready about twice as fast; the timeline and Razgon's shared files are locked per change.
PARALLEL = 2


def run(targets, launch, verify, checkpoint, cancelled, stop, *, previous=None, pending_review=None, parallel=None):
    import threading
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
            # A changed neighbour must not replay the other approved frames in this scope.
            with lock:
                completed.difference_update(n for n in saved if not verify([n]))
        with lock:
            frames = [n for n in frames if n not in completed]
            summary = totals['summary']
        if not frames:
            return None
        code, raw = launch(frames, summary, index if numbered else 0)
        result = account(raw)
        if cancelled():raise InterruptedError('Створення кадрів зупинено')
        if code or raw.get('is_error') or stop(raw):return code or 1, result
        valid = verify(frames)
        pending = sorted(set(pending_review() or [])) if not valid and pending_review else []
        if pending and set(pending) <= set(frames):
            if cancelled():raise InterruptedError('Створення кадрів зупинено')
            code, raw = launch(pending, summary + REVIEW_NOTE, 1000 + index)
            result = account(raw)
            if cancelled():raise InterruptedError('Створення кадрів зупинено')
            if code or raw.get('is_error') or stop(raw):return code or 1, result
            valid = verify(frames)
        if not valid:
            result.update(is_error=True, result='Поточний пакет кадрів не завершений або не пройшов перевірку. Готові результати збережено.')
            return 1, result
        with lock:
            completed.update(frames)
            totals['summary'] = str(raw.get('result') or '')[-1200:]
            checkpoint({'completed_frames': sorted(completed), 'remaining_frames': sorted(set(targets) - completed),
                        'summary': totals['summary'], 'session': index, 'session_id': raw.get('session_id')})
        return None

    width = max(1, int(parallel or PARALLEL))
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
                    time.sleep(.5)   # the two sessions do not start in the same instant
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


def finish_review(numbers, launch, verify, cancelled, stop):
    """One bounded pass for stale final receipts, including earlier frame batches."""
    summary=('Потрібен лише актуальний візуальний огляд перелічених готових кадрів. '
             'Збережи сцени, матеріали й таймлайн. Онови кешовані стоп-кадри. '
             'Якщо пікселі не змінилися, збережи попередні схвалення. '
             'Переглянь лише кадри, які справді змінилися, і зафіксуй результат. '
             'Не перебудовуй готові сцени; виправляй лише підтверджені візуальні дефекти.')
    return run(numbers,lambda ns,_,index:launch(ns,summary,2000+index),verify,
               lambda receipt:None,cancelled,stop)
