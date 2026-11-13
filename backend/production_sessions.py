"""Bound the context of long frame runs; never retry a failed or uncertain session."""
import copy

SESSION_FRAMES = 10  # Two batches of five; discard images/tool history before it dominates the next batch.


def add_usage(total, value):
    for key, number in (value or {}).items():
        if isinstance(number, dict):add_usage(total.setdefault(key, {}), number)
        elif isinstance(number, (int, float)) and not isinstance(number, bool):total[key] = total.get(key, 0) + number


def run(targets, launch, verify, checkpoint, cancelled, stop, *, previous=None, pending_review=None):
    targets = sorted(set(targets))
    previous = previous or {}
    completed = set(previous.get('completed_frames') or []) & set(targets)
    summary = str(previous.get('summary') or '')[-1200:]
    cost = 0
    usage, models = {}, {}
    duration = turns = 0
    answer = {'result':summary,'session_id':previous.get('session_id')}
    for index, start in enumerate(range(0, len(targets), SESSION_FRAMES), 1):
        if cancelled():raise InterruptedError('Створення кадрів зупинено')
        frames = targets[start:start + SESSION_FRAMES]
        saved = [n for n in frames if n in completed]
        if saved and not verify(saved):
            # A changed neighbour must not replay the other approved frames in this scope.
            completed.difference_update(n for n in saved if not verify([n]))
        frames = [n for n in frames if n not in completed]
        if not frames:
            continue
        code, raw = launch(frames, summary, index if len(targets) > SESSION_FRAMES else 0)
        answer = copy.deepcopy(raw)
        cost += float(raw.get('total_cost_usd') or 0)
        add_usage(usage, raw.get('usage'))
        add_usage(models, raw.get('modelUsage'))
        duration += raw.get('duration_ms') or 0
        turns += raw.get('num_turns') or 0
        answer.update(total_cost_usd=cost, usage=usage.copy(), modelUsage=copy.deepcopy(models), duration_ms=duration, num_turns=turns)
        if cancelled():raise InterruptedError('Створення кадрів зупинено')
        if code or raw.get('is_error') or stop(raw):return code or 1, answer
        valid=verify(frames)
        pending=sorted(set(pending_review() or [])) if not valid and pending_review else []
        if pending and set(pending)<=set(frames):
            if cancelled():raise InterruptedError('Створення кадрів зупинено')
            code,raw=launch(pending,summary+'\nПотрібен лише актуальний візуальний огляд цих кадрів. Збережи готові сцени, зображення й таймлайн. Зроби аркуші змінених кадрів, переглянь і зафіксуй результат. Виправляй композицію лише за виявленим дефектом.',1000+index)
            answer=copy.deepcopy(raw)
            cost+=float(raw.get('total_cost_usd') or 0)
            add_usage(usage,raw.get('usage'));add_usage(models,raw.get('modelUsage'))
            duration+=raw.get('duration_ms') or 0;turns+=raw.get('num_turns') or 0
            answer.update(total_cost_usd=cost,usage=copy.deepcopy(usage),modelUsage=copy.deepcopy(models),duration_ms=duration,num_turns=turns)
            if cancelled():raise InterruptedError('Створення кадрів зупинено')
            if code or raw.get('is_error') or stop(raw):return code or 1,answer
            valid=verify(frames)
        if not valid:
            answer.update(is_error=True, result='Поточний пакет кадрів не завершений або не пройшов перевірку. Готові результати збережено.')
            return 1, answer
        completed.update(frames)
        summary = str(raw.get('result') or '')[-1200:]
        checkpoint({'completed_frames':sorted(completed),'remaining_frames':sorted(set(targets)-completed),
                    'summary':summary,'session':index,'session_id':raw.get('session_id')})
    return 0, answer
