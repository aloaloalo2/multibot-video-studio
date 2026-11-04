"""Offline language preflight. No translator, speech calls or audio mutation here.

Script checks catch foreign blocks even in very short phrases. The local langid
model also checks sufficiently long same-script phrases and short-line windows.
Its score is a classifier score, never a guarantee or translation quality grade.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from functools import lru_cache

VERSION = 4
_lock = threading.RLock()
_identifier = None
LATIN = set('en de es fr pt it pl tr nl id cs ro'.split())
EXPECTED = {**{code: {'LATIN'} for code in LATIN},
            **{code: {'CYRILLIC'} for code in ('ru', 'uk', 'kk')},
            'hi': {'DEVANAGARI'}, 'ar': {'ARABIC'}, 'ja': {'CJK', 'HIRAGANA', 'KATAKANA'},
            'ko': {'HANGUL', 'CJK'}, 'zh': {'CJK'}}


def identify(text: str) -> tuple[str, float]:
    global _identifier
    # One immutable model for all targets. Never set_languages on shared state:
    # parallel Spanish/Polish jobs must not change one another's classifier.
    with _lock:
        if _identifier is None:
            from langid.langid import LanguageIdentifier, model
            _identifier = LanguageIdentifier.from_modelstring(model, norm_probs=True)
        code, score = _identifier.classify(text)
    return code, float(score)


def script_problem(code: str, text: str, minimum: int = 12) -> bool:
    scripts = {}
    for char in text:
        if not char.isalpha():
            continue
        name = unicodedata.name(char, '').split(' ', 1)[0]
        scripts[name] = scripts.get(name, 0) + 1
    letters = sum(scripts.values())
    # Names/acronyms can be foreign. A substantial foreign run is unsafe.
    foreign = sum(n for script, n in scripts.items() if script not in EXPECTED.get(code, set()))
    # One or two quoted names/terms inside otherwise correct speech are not
    # evidence of a foreign sentence. Require a predominantly foreign passage.
    words=re.findall(r'[^\W\d_]+',text,flags=re.UNICODE)
    foreign_words=sum(any(unicodedata.name(c,'').split(' ',1)[0] not in EXPECTED.get(code,set())
                          for c in word) for word in words)
    return foreign >= minimum and foreign / max(1, letters) >= .6 and foreign_words>=3


RU_MARKERS=set('что чтобы когда который которая которые это этот эта эти только очень потому где ещё всё также деньги чувствовали много как свою своей своих этого этом будет если уже меня для'.split())
UK_MARKERS=set('що щоб коли який яка які це цей ця ці тільки лише дуже тому де ще також гроші відчували багато як свою своїх цього цьому буде якщо вже мене для'.split())

def reliable_mismatch(target, detected, text):
    """Nearby Cyrillic languages need evidence beyond an overconfident classifier."""
    if {target,detected}=={'ru','uk'}:
        words=re.findall(r'[^\W\d_]+',text.lower(),flags=re.UNICODE)
        markers={'ru':RU_MARKERS,'uk':UK_MARKERS}
        own=sum(word in markers[target]-markers[detected] for word in words)
        other=sum(word in markers[detected]-markers[target] for word in words)
        exclusive={'ru':set('ыэёъ'),'uk':set('іїєґ')}
        own+=sum(c in exclusive[target] for c in text.lower())
        other+=sum(c in exclusive[detected] for c in text.lower())
        if own>=2 and own>other:
            return False
    return detected in EXPECTED and detected!=target


@lru_cache(maxsize=96)
def _check(code: str, lines: tuple[str, ...]) -> dict:
    issues = {}
    unavailable = False

    def inspect(text, indexes, structural=False):
        nonlocal unavailable
        letters = sum(c.isalpha() for c in text)
        if not structural and (letters < 35 or len(text.split()) < 6):
            return
        try:
            detected, score = identify(text)
        except (ImportError, OSError, ValueError):
            unavailable = True
            detected, score = None, 0.0
        if structural or (reliable_mismatch(code,detected,text) and score >= .99999):
            for index in indexes:
                issues.setdefault(index, {'index': index, 'detected': detected,
                    'reason': 'script' if structural else 'language', 'text': lines[index]})

    for index, line in enumerate(lines):
        # Scan within a paragraph too, so a short foreign passage in a long
        # otherwise correct paragraph is not hidden by majority voting.
        units = re.split(r'(?<=[.!?。！？])\s+', line)
        for unit in units:
            inspect(unit, [index], script_problem(code, unit))
    # A short foreign sentence surrounded by a detected foreign block belongs
    # to that block too, e.g. the three-word Russian sentence in the incident.
    strong = set(issues)
    for index, line in enumerate(lines):
        if index not in strong and ({index-1, index+1} & strong) and script_problem(code, line, 4):
            inspect(line, [index], True)
    # Short adjacent phrases jointly provide enough context for language ID.
    start = 0
    while start < len(lines):
        end = start + 1
        while end < len(lines) and sum(c.isalpha() for c in ' '.join(lines[start:end])) < 160 and end-start < 5:
            end += 1
        # A mixed-script window must not implicate its correct neighbours.
        # Those foreign phrases already have precise script issues above.
        window = lines[start:end]
        if not any(script_problem(code, text) for text in window):
            joined = ' '.join(window)
            if sum(c.isalpha() for c in joined) >= 80:
                try:
                    detected, score = identify(joined)
                    if reliable_mismatch(code,detected,joined) and score >= .99999:
                        for index in range(start, end):
                            own, confidence = identify(lines[index])
                            if own == detected and confidence >= .95 and reliable_mismatch(code,own,lines[index]):
                                issues.setdefault(index, {'index': index, 'detected': detected,
                                    'reason': 'language', 'text': lines[index]})
                except (ImportError, OSError, ValueError):
                    unavailable = True
        start = end
    # Probe even short documents so a missing dependency cannot enable TTS.
    if lines and not issues:
        try:
            identify(' '.join(lines)[:1000])
        except (ImportError, OSError, ValueError):
            unavailable = True
    return {'version': VERSION, 'target': code, 'state': 'blocked' if issues else 'unavailable' if unavailable else 'ok',
            'issues': list(sorted(issues.values(), key=lambda item: item['index'])),
            'checked_lines': len(lines), 'method': 'unicode-script+langid'}


def check(code: str, texts, segments=None) -> dict:
    if isinstance(texts, str):
        texts = [line.strip() for line in texts.splitlines() if line.strip()]
    report = _check(code, tuple(texts))
    return {**report, 'issues': [{**item, **({'start': segments[item['index']].get('start'),
        'end': segments[item['index']].get('end')} if segments and item['index'] < len(segments) else {})}
        for item in report['issues']]}


def message(report: dict) -> str:
    if report['state'] == 'unavailable':
        return 'Перевірка мови недоступна. Озвучення заблоковано до відновлення локального визначника мови.'
    numbers = ', '.join(str(item['index']+1) for item in report['issues'][:8])
    more = '…' if len(report['issues']) > 8 else ''
    return f'У перекладі знайдено іншу мову. Фрази: {numbers}{more}. Виправте текст перед озвученням.'


def require(code: str, texts) -> dict:
    report = check(code, texts)
    if report['state'] != 'ok':
        import store
        raise store.StudioError(message(report), 409)
    return report
