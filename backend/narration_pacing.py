"""Forecast immutable narration from measured takes. Never rewrite accepted words."""
from __future__ import annotations

import math
from numeric_comparison import comparison_chars as letter_count
from statistics import median

from dubbing_fit import MAX_SPEED, MAX_SHIFT, TEMPO_PERCENT, join_gaps

CALIBRATION = 5
BLOCK = 10
GAP = .05
FORECAST_RESERVE = 1.03


def alignment_check(segments: list[dict], fastest: dict[int, float], total: float) -> dict:
    """An optimistic check of immutable, already-paid audio before buying more.

    Unknown takes occupy no time, and added breath gaps are omitted here. Thus a
    failure cannot be blamed on a character-rate forecast or unknown padding.
    Decoded durations at the allowed maximum tempo are required, never raw/speed.
    The final fitter additionally verifies minimum end times and actual breaths.
    """
    cursor, owner = 0., 0
    issues = []
    for index, length in sorted(fastest.items()):
        if not 0 <= index < len(segments) or not math.isfinite(length) or length <= 0:
            raise ValueError('Invalid measured phrase for alignment')
        source = segments[index]
        earliest = max(0., float(source['start'])-MAX_SHIFT)
        if earliest > cursor:
            cursor, owner = earliest, index
        latest = min(total-length, float(source['start'])+MAX_SHIFT,
                     float(source['end'])+MAX_SHIFT-length)
        if cursor > latest+1e-6:
            issues.append({'index':index, 'first_index':owner, 'excess':round(cursor-latest,3)})
        cursor += length
    # The interval identifies a packed chain, not a request to rewrite every
    # phrase in it. Name the largest actual duration overruns separately.
    for issue in issues:
        candidates = sorted(({'index': i, 'over_by_seconds': round(length -
            (float(segments[i]['end'])-float(segments[i]['start'])), 3)}
            for i, length in fastest.items() if issue['first_index'] <= i <= issue['index']
            and length > float(segments[i]['end'])-float(segments[i]['start'])),
            key=lambda item: item['over_by_seconds'], reverse=True)
        selected, covered = [], 0.
        for candidate in candidates:
            selected.append(candidate)
            covered += candidate['over_by_seconds']
            if covered >= issue['excess']:
                break
        issue['contributors'] = selected
    return {'limit_seconds':MAX_SHIFT, 'measured_phrases':len(fastest),
            'within_limit':not issues, 'issues':issues}


def require_alignment(segments: list[dict], fastest: dict[int,float], total: float) -> dict:
    report = alignment_check(segments,fastest,total)
    if report['issues']:
        issue = max(report['issues'],key=lambda x:x['excess'])
        raise RuntimeError(f"Збережені фрази {issue['first_index']+1}–{issue['index']+1} потребують скорочення "
                           f"мовлення щонайменше на {issue['excess']:.1f} с для зміщення до 7 с. "
                           'Нові платні запити зупинено до виправлення синхронізації. '
                           'Текст і всі готові записи збережені; автоматичної платної перегенерації не буде.')
    return report


def seconds_per_character(texts: list[str], known: dict[int, float]) -> float | None:
    points=[(letter_count(texts[i]),float(length)) for i,length in sorted(known.items())
            if 0<=i<len(texts) and letter_count(texts[i])>=20 and math.isfinite(length) and length>0]
    if len(points)<CALIBRATION or sum(t for _,t in points)<20:return None
    centre=median(t/n for n,t in points)
    stable=[(n,t) for n,t in points if centre*.5<=t/n<=centre*2]
    if len(stable)<CALIBRATION:return None
    overall=sum(t for _,t in stable)/sum(n for n,_ in stable)
    recent=stable[-20:]
    # Smooth changes over a group, with a small reserve. One unusually slow line
    # must not make the following line race or change the selected voice.
    return (.7*overall+.3*sum(t for _,t in recent)/sum(n for n,_ in recent))*FORECAST_RESERVE


def plan(texts: list[str], known: dict[int, float], total: float, offset: int,
         edges: dict[int,dict] | None = None) -> dict:
    # Use the assembler's boundary measurements when present. Reserve a full
    # breath only for joins whose audio has not yet been generated.
    gaps=sum(join_gaps([{'edge_silence':(edges or {}).get(i)} for i in range(len(texts))]))
    measured=sum(known.values())
    # Recorded takes already include their boundary pauses. Extra join padding is
    # a forecast reserve, not a measured impossibility; the assembler measures it.
    minimum=measured/MAX_SPEED
    if not math.isfinite(total) or total <= 0:
        raise ValueError('Invalid source narration duration')
    rate=seconds_per_character(texts,known)
    pending=[i for i in range(offset,len(texts)) if i not in known]
    result={'measured_phrases':len(known),'measured_seconds':round(measured,3),'join_seconds':round(gaps,3),
            'seconds_per_character':rate,'predicted_seconds':None,'predicted_minimum_seconds':None,
            'requires_review':minimum>total+.05, 'measured_excess_seconds':round(max(0.,minimum-total),3),
            'targets':{}}
    if rate is None or not pending:return result
    chars=sum(letter_count(texts[i]) for i in pending)
    # All saved takes can use the same bounded fitting as the remaining takes.
    # The forecasting reserve applies only to unknown audio, not to the film's
    # tempo allowance or the duration of recordings we have already measured.
    budget=max(0,total*MAX_SPEED-measured)
    result['predicted_seconds']=round(measured+rate*chars/FORECAST_RESERVE+gaps,3)
    result['predicted_minimum_seconds']=round((measured+rate*chars)/MAX_SPEED+gaps,3)
    result['expected_minimum_seconds']=round((measured+rate*chars/FORECAST_RESERVE)/MAX_SPEED+gaps,3)
    result['remaining_phrases']=len(pending)
    result['remaining_budget_seconds']=round(budget/MAX_SPEED,3)
    result['requires_review']=result['predicted_minimum_seconds']>total+.05
    # A timing forecast is advisory. Finish the requested single takes and show
    # measured alignment afterwards; never silently rewrite or buy retries.
    return result


def edit_issues(texts: list[str], targets: dict[int,int], replacements: dict[int,str]) -> list[dict]:
    """Check the whole block's budget; dense lines may borrow unused space."""
    issues=[]
    if set(replacements)!=set(targets):
        issues.append({'missing_ids':sorted(set(targets)-set(replacements)),
                       'unexpected_ids':sorted(set(replacements)-set(targets))})
    for i,limit in targets.items():
        value=replacements.get(i)
        minimum=math.ceil(letter_count(texts[i])*.6)
        maximum=max(limit,letter_count(texts[i]))
        if not isinstance(value,str) or '\n' in value or not value.strip() or not minimum<=letter_count(value)<=maximum:
            issues.append({'id':i,'actual_chars':letter_count(value) if isinstance(value,str) else None,
                           'min_chars':minimum,'max_chars':maximum,'target_chars':limit})
    if not issues:
        actual=sum(letter_count(replacements[i]) for i in targets)
        budget=sum(targets.values())
        if actual>budget:issues.append({'block_chars':actual,'block_budget':budget,'reduce_by':actual-budget})
    return issues


def validate_edits(texts: list[str], targets: dict[int,int], replacements: dict[int,str]) -> None:
    if edit_issues(texts,targets,replacements):
        raise RuntimeError('Не вдалося підготувати фрази потрібної довжини до озвучення. Готові записи збережені.')
