"""Whole-translation character budgets, including spaces and stored line separators.

This module never synthesizes audio or publishes text. The caller supplies a text
rewrite callback and checks language and meaning before accepting the result.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

TOLERANCE = .03


def count(text: str) -> int:
    """Match the displayed script count: retain internal spaces, trim only its edges."""
    return len(text.strip())


def join_lines(lines: list[str]) -> str:
    """Explicit stored representation; each phrase keeps its own line and identity."""
    return '\n'.join(line.strip() for line in lines)


def report(source_text: str, translated_text: str, tolerance: float = TOLERANCE) -> dict:
    if not math.isfinite(tolerance) or not 0 <= tolerance < 1:
        raise ValueError('Tolerance must be finite and between zero and one.')
    source_chars, translated_chars = count(source_text), count(translated_text)
    margin = Decimal(str(tolerance))
    lower = int((Decimal(source_chars) * (1-margin)).to_integral_value(rounding=ROUND_CEILING))
    upper = int((Decimal(source_chars) * (1+margin)).to_integral_value(rounding=ROUND_FLOOR))
    difference = translated_chars-source_chars
    return {'source_chars': source_chars, 'translated_chars': translated_chars,
            'min_chars': lower, 'max_chars': upper,
            'within_budget': lower <= translated_chars <= upper,
            'difference_chars': difference,
            'difference_percent': round(100*difference/source_chars, 3) if source_chars else None,
            'over_by': max(0, translated_chars-upper), 'under_by': max(0, lower-translated_chars)}


def allocate_targets(lines: list[str], target_chars: int) -> dict[int, int]:
    """Proportional hints whose sum plus line separators equals the whole budget.

    These are not per-phrase constraints: dense phrases may borrow from shorter
    ones. Every existing phrase keeps at least one character and its same id.
    """
    if not lines:
        if target_chars:
            raise ValueError('A nonempty budget needs source lines.')
        return {}
    available = target_chars-(len(lines)-1)
    if available < len(lines):
        raise ValueError('Budget cannot retain every nonempty phrase.')
    weights = [max(1, count(line)) for line in lines]
    total = sum(weights)
    remaining = available-len(lines)
    targets = [1+remaining*w//total for w in weights]
    spare = available-sum(targets)
    order = sorted(range(len(lines)), key=lambda i: (-(remaining*weights[i] % total), i))
    for index in order[:spare]:
        targets[index] += 1
    return dict(enumerate(targets))


class BudgetError(RuntimeError):
    """A recoverable text-only failure, retaining the latest complete draft."""
    def __init__(self, message, lines, state, passes):
        super().__init__(message)
        self.lines = list(lines)
        self.report = dict(state)
        self.passes = passes


def _ordered(value, size):
    if isinstance(value, Mapping):
        mapped = {}
        for key, text in value.items():
            if type(key) is int:
                index = key
            elif isinstance(key, str) and key.isdecimal():
                index = int(key)
            else:
                raise ValueError('Invalid phrase id.')
            if index in mapped:
                raise ValueError('Duplicate phrase id.')
            mapped[index] = text
        if set(mapped) != set(range(size)):
            raise ValueError('Every original phrase id is required exactly once.')
        value = [mapped[index] for index in range(size)]
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError('Every original phrase must remain in order.')
    if any(not isinstance(line, str) or not line.strip() or '\n' in line.strip() or '\r' in line.strip()
           for line in value):
        raise ValueError('Every phrase must contain one nonempty line.')
    return [line.strip() for line in value]


def fit(source_text: str, lines: list[str], rewrite, *, validate=None,
        max_passes: int = 3, tolerance: float = TOLERANCE) -> dict:
    """Refine text at most three times, without paid TTS or changing input data.

    rewrite(current_lines, feedback) returns a complete ordered list or id->text
    mapping. feedback contains whole-text counts/bounds, proportional line hints
    and the prior issue. validate(final_lines) must reject wrong language or lost
    meaning by raising or returning False. Only the returned result is accepted;
    unfinished drafts stay in BudgetError for review and must not be published.
    """
    if type(max_passes) is not int or not 0 <= max_passes <= 3:
        raise ValueError('Use at most three text-only refinement passes.')
    current = _ordered(lines, len(lines)) if lines else []
    state = report(source_text, join_lines(current), tolerance)
    seen = {join_lines(current)}
    repeated = 0
    issue = None

    def accepted(passes):
        if validate is not None and validate(list(current)) is False:
            raise BudgetError('Translation failed language or meaning validation.', current, state, passes)
        return {'lines': list(current), 'report': dict(state), 'passes': passes}

    if state['within_budget']:
        return accepted(0)
    if not current or not state['source_chars']:
        raise BudgetError('Cannot change an empty source or remove every phrase.', current, state, 0)
    try:
        target_hints = allocate_targets(current, state['source_chars'])
    except ValueError as error:
        raise BudgetError(str(error), current, state, 0) from error
    for attempt in range(1, max_passes+1):
        feedback = {**state, 'attempt': attempt, 'max_passes': max_passes,
                    'target_chars': state['source_chars'], 'line_targets': target_hints,
                    'ids': list(range(len(current))), 'last_issue': issue}
        draft = rewrite(list(current), feedback)
        try:
            candidate = _ordered(draft, len(current))
        except ValueError as error:
            issue = str(error)
            continue
        encoded = join_lines(candidate)
        next_state = report(source_text, encoded, tolerance)
        if next_state['within_budget']:
            current, state = candidate, next_state
            return accepted(attempt)
        if encoded in seen:
            repeated += 1
            issue = 'The response repeated an unchanged or previously rejected draft. Use different natural wording.'
            if repeated >= 2:
                raise BudgetError('Repeated translation drafts still exceed the whole-text budget.',
                                  current, state, attempt)
            continue
        seen.add(encoded)
        current, state = candidate, next_state
        issue = 'The complete draft is still outside the whole-text character budget.'
        target_hints = allocate_targets(current, state['source_chars'])
    raise BudgetError('Translation needs review to fit within the whole-text character budget.',
                      current, state, max_passes)
