"""Plan unvoiced wording from measured takes. Never pay for a timing retake."""
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
            'seconds_per_character':rate,'predicted_seconds':None,'targets':{}}
    if rate is None or not pending:return result
    chars=sum(len(texts[i]) for i in pending)
    # Use 3% for planning and retain the rest of the 7% bound for model variation.
    budget=max(0,(total-gaps-min(5,total*.005))*1.03-measured)
    result['predicted_seconds']=round((measured+rate*chars)/1.03+gaps,3)
    factor=min(1.,budget/(rate*chars)) if chars else 1.
    if factor>=.97:return result
    if factor<.65:
        raise RuntimeError('Виміряний темп потребує надто сильного скорочення решти тексту. '
                           'Озвучення зупинено до нових витрат. Готові фрази збережені; потрібна перевірка тексту.')
    for i in range(offset,min(len(texts),offset+BLOCK)):
        if i not in known:
            result['targets'][i]=max(8,math.floor(len(texts[i])*factor))
    return result


def validate_edits(texts: list[str], targets: dict[int,int], replacements: dict[int,str]) -> None:
    if set(replacements)!=set(targets):
        raise RuntimeError('Не вдалося підготувати всі фрази до озвучення. Нових платних запитів не зроблено.')
    for i,limit in targets.items():
        value=replacements[i]
        if not isinstance(value,str) or '\n' in value or not value.strip() or not len(texts[i])*.6<=len(value)<=limit:
            raise RuntimeError(f'Фраза {i+1} потребує перевірки довжини перед озвученням. Готові записи збережені.')
