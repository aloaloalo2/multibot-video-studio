"""Forecast immutable narration from measured takes. Never rewrite accepted words."""
from __future__ import annotations

import math
from statistics import median

from dubbing_fit import MAX_SPEED

CALIBRATION = 5
BLOCK = 10
GAP = .05


def seconds_per_character(texts: list[str], known: dict[int, float]) -> float | None:
    points=[(len(texts[i]),float(length)) for i,length in sorted(known.items())
            if 0<=i<len(texts) and len(texts[i])>=20 and math.isfinite(length) and length>0]
    if len(points)<CALIBRATION or sum(t for _,t in points)<20:return None
    centre=median(t/n for n,t in points)
    stable=[(n,t) for n,t in points if centre*.5<=t/n<=centre*2]
    if len(stable)<CALIBRATION:return None
    overall=sum(t for _,t in stable)/sum(n for n,_ in stable)
    recent=stable[-20:]
    # Smooth changes over a group, with a small reserve. One unusually slow line
    # must not make the following line race or change the selected voice.
    return (.7*overall+.3*sum(t for _,t in recent)/sum(n for n,_ in recent))*1.03


def plan(texts: list[str], known: dict[int, float], total: float, offset: int) -> dict:
    gaps=GAP*max(0,len(texts)-1)
    measured=sum(known.values())
    minimum=measured/MAX_SPEED+gaps
    if minimum>total+.05:
        raise RuntimeError(f'Збережені фрази вже перевищують тривалість ролика щонайменше на {minimum-total:.1f} с '
                           'при прискоренні до 7%. Нові платні запити зупинено. Усі записи збережені.')
    rate=seconds_per_character(texts,known)
    pending=[i for i in range(offset,len(texts)) if i not in known]
    result={'measured_phrases':len(known),'measured_seconds':round(measured,3),
            'seconds_per_character':rate,'predicted_seconds':None,'predicted_minimum_seconds':None,
            'requires_review':False,'targets':{}}
    if rate is None or not pending:return result
    chars=sum(len(texts[i]) for i in pending)
    # Smooth the forecast separately from the hard 7% limit on actual audio.
    budget=max(0,(total-gaps-min(5,total*.005))*1.03-measured)
    result['predicted_seconds']=round((measured+rate*chars)/1.03+gaps,3)
    result['predicted_minimum_seconds']=round((measured+rate*chars)/MAX_SPEED+gaps,3)
    result['requires_review']=result['predicted_minimum_seconds']>total+.05
    factor=min(1.,budget/(rate*chars)) if chars else 1.
    if factor>=.97:return result
    if factor<.65:
        raise RuntimeError('За виміряним темпом прогнозована озвучка значно довша за ролик навіть із прискоренням до 7%. '
                           'Озвучення зупинено до нових витрат. Текст не змінено, готові записи збережені; '
                           'потрібно перевірити прогноз і монтаж.')
    return result


def edit_issues(texts: list[str], targets: dict[int,int], replacements: dict[int,str]) -> list[dict]:
    """Check the whole block's budget; dense lines may borrow unused space."""
    issues=[]
    if set(replacements)!=set(targets):
        issues.append({'missing_ids':sorted(set(targets)-set(replacements)),
                       'unexpected_ids':sorted(set(replacements)-set(targets))})
    for i,limit in targets.items():
        value=replacements.get(i)
        minimum=math.ceil(len(texts[i])*.6)
        maximum=max(limit,len(texts[i]))
        if not isinstance(value,str) or '\n' in value or not value.strip() or not minimum<=len(value)<=maximum:
            issues.append({'id':i,'actual_chars':len(value) if isinstance(value,str) else None,
                           'min_chars':minimum,'max_chars':maximum,'target_chars':limit})
    if not issues:
        actual=sum(len(replacements[i]) for i in targets)
        budget=sum(targets.values())
        if actual>budget:issues.append({'block_chars':actual,'block_budget':budget,'reduce_by':actual-budget})
    return issues


def validate_edits(texts: list[str], targets: dict[int,int], replacements: dict[int,str]) -> None:
    if edit_issues(texts,targets,replacements):
        raise RuntimeError('Не вдалося підготувати фрази потрібної довжини до озвучення. Готові записи збережені.')
