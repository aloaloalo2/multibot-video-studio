"""Informational translation counts and legacy explicit character-budget utilities.

The automatic translation pipeline uses assessment(), never the legacy fitter.
Raw character counts do not measure spoken duration or translation quality.
This module never synthesizes audio or publishes text.
"""
from __future__ import annotations

import math
import re
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



def assessment(source_text: str, translated_text: str) -> dict:
    """Informational counts only: spelling out source digits can lengthen speech text.

    Character differences are neither a fidelity verdict nor a duration estimate.
    Source and target grammar, number words and units can differ in length; the
    semantic audit checks their meaning and measured audio governs pacing.
    """
    source_chars, translated_chars = count(source_text), count(translated_text)
    numeric = re.compile(r"\d+(?:[.,:/-]\d+)*")
    source_numbers = len(numeric.findall(source_text))
    target_numbers = len(numeric.findall(translated_text))
    return {'source_chars': source_chars, 'translated_chars': translated_chars,
            'difference_chars': translated_chars-source_chars,
            'difference_percent': round(100*(translated_chars-source_chars)/source_chars, 3) if source_chars else None,
            'advisory_only': True, 'duration_estimate': False,
            'source_numeric_tokens': source_numbers, 'translated_numeric_tokens': target_numbers,
            'numeric_forms_differ': source_numbers != target_numbers,
            'comparison_basis': 'raw_characters_with_spaces'}


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


def refinement_plan(source_text: str, lines: list[str], source_units=None,
                    tolerance: float = TOLERANCE) -> dict:
    """Choose a measured subset for one useful length pass, preserving every ID.

    Work toward the nearest accepted boundary with half a percent of source
    length left for later meaning repairs. A phrase's twelve-percent allowance
    is a selection/weighting hint, not permission to remove its facts. Length
    expansion relative to the source is only a ranking heuristic; spoken numbers
    can make a dense translation longer legitimately. Callers enforce the batch
    total and audit meaning independently.
    """
    values = _ordered(lines, len(lines)) if lines else []
    state = report(source_text, join_lines(values), tolerance)
    if source_units is not None and (len(source_units) != len(values)
                                    or any(not isinstance(x, str) for x in source_units)):
        raise ValueError('Source units must match every translation phrase.')
    if state['within_budget']:
        return {'direction': 'none', 'target_chars': state['translated_chars'],
                'required_change': 0, 'ids': [], 'line_targets': {}}
    if not values or not state['source_chars']:
        raise ValueError('Cannot refine an empty source or translation.')
    shorten = state['over_by'] > 0
    reserve = min(math.ceil(state['source_chars']*.005),
                  (state['max_chars']-state['min_chars'])//2)
    target = state['max_chars']-reserve if shorten else state['min_chars']+reserve
    wanted = abs(state['translated_chars']-target)
    lengths = [len(x) for x in values]
    capacities = [min(n-1, max(1, math.floor(n*.12))) if shorten else max(1, math.floor(n*.12))
                  for n in lengths]
    def score(index):
        difference = lengths[index]-count(source_units[index]) if source_units is not None else 0
        return (-(difference if shorten else -difference), -lengths[index], index)
    chosen, capacity = [], 0
    for index in sorted(range(len(values)), key=score):
        if capacities[index]:
            chosen.append(index)
            capacity += capacities[index]
            if capacity >= wanted:
                break
    if not capacity:
        raise ValueError('Budget cannot retain every nonempty phrase.')
    change = min(wanted, capacity)
    adjustments = {i: change*capacities[i]//capacity for i in chosen}
    spare = change-sum(adjustments.values())
    for index in sorted(chosen, key=lambda i: (-(change*capacities[i] % capacity), i))[:spare]:
        adjustments[index] += 1
    ids = sorted(i for i in chosen if adjustments[i])
    targets = {i: lengths[i]+(-adjustments[i] if shorten else adjustments[i]) for i in ids}
    return {'direction': 'shorten' if shorten else 'expand', 'target_chars': target,
            'required_change': change, 'ids': ids, 'line_targets': targets}


class BudgetError(RuntimeError):
    """A recoverable text-only pause, retaining the best complete draft."""
    def __init__(self, message, lines, state, passes, *, reason="review", resumable=True):
        super().__init__(message)
        self.lines = list(lines)
        self.report = dict(state)
        self.passes = passes
        self.reason = reason
        self.resumable = resumable


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


def _merge_update(value, current):
    """Merge unambiguous valid IDs; omitted or malformed units keep their text."""
    if not isinstance(value, Mapping):
        candidate = _ordered(value, len(current))
        return candidate, list(range(len(current))), []
    updates, invalid, issues = {}, set(), []
    for key, text in value.items():
        if type(key) is int:
            index = key
        elif isinstance(key, str) and key.isdecimal():
            index = int(key)
        else:
            issues.append('Invalid phrase id.')
            continue
        if index not in range(len(current)):
            issues.append('Unknown phrase id.')
            continue
        if index in updates or index in invalid:
            updates.pop(index, None)
            invalid.add(index)
            issues.append('Duplicate phrase id.')
            continue
        try:
            updates[index] = _ordered([text], 1)[0]
        except ValueError as error:
            invalid.add(index)
            issues.append(str(error))
    if not updates:
        raise ValueError(' '.join(issues) or 'Every original phrase update is missing.')
    candidate = list(current)
    for index, text in updates.items():
        candidate[index] = text
    pending = sorted(set(range(len(current)))-set(updates))
    if pending:
        issues.append('Partial response: retained existing text for missing or invalid phrase ids: '
                      + ', '.join(map(str, pending)) + '.')
    return candidate, sorted(updates), issues


def fit(source_text: str, lines: list[str], rewrite, *, validate=None,
        max_passes: int | None = None, max_stalled_passes: int = 3,
        on_checkpoint=None, tolerance: float = TOLERANCE) -> dict:
    """Keep improving a complete draft until its length and meaning are valid.

    rewrite(current_lines, feedback) returns ordered lines or partial id->text
    updates. Only progress toward the inclusive whole-text budget replaces the
    best draft. Unchanged, malformed or regressing replies pause resumably after
    max_stalled_passes consecutive attempts; improving work has no fixed cap.
    An explicit max_passes can impose a caller's text-only request budget.

    validate(lines) rejects with False/an exception, or returns corrected complete
    lines, or {"lines": corrected_lines, "issue_count": count_found_by_audit}.
    Decreasing issue counts allow continued semantic repairs; an unchanged count
    eventually pauses for review. Corrections are measured and validated again,
    including another length refinement when needed. on_checkpoint(lines, report, passes, issue) receives
    detached copies of useful drafts and the final pause state. Nothing here is
    published, synthesized, truncated, or filled to meet a numerical target.
    """
    if max_passes is not None and (type(max_passes) is not int or max_passes < 0):
        raise ValueError('max_passes must be a nonnegative integer or None.')
    if type(max_stalled_passes) is not int or max_stalled_passes < 1:
        raise ValueError('max_stalled_passes must be a positive integer.')
    current = _ordered(lines, len(lines)) if lines else []
    state = report(source_text, join_lines(current), tolerance)
    passes = stalled = semantic_stalled = 0
    last_semantic_count = None
    seen = {join_lines(current)}
    audited = set()
    issue = None
    pending_ids = []

    def checkpoint():
        if on_checkpoint is not None:
            on_checkpoint(list(current), dict(state), passes, issue)

    def pause(message, reason):
        nonlocal issue
        issue = message
        checkpoint()
        raise BudgetError(message, current, state, passes, reason=reason)

    checkpoint()
    while True:
        if state['within_budget']:
            encoded = join_lines(current)
            if encoded in audited:
                pause('Meaning corrections returned to a previously audited draft. Saved for review.',
                      'validation_cycle')
            audited.add(encoded)
            checked = validate(list(current)) if validate is not None else None
            if checked is False:
                pause('Translation failed language or meaning validation.', 'validation')
            issue_count = None
            if isinstance(checked, Mapping) and 'lines' in checked:
                issue_count = checked.get('issue_count')
                if type(issue_count) is not int or issue_count < 0:
                    pause('Meaning audit returned an invalid issue count.', 'validation')
                checked = checked['lines']
            if isinstance(checked, (list, tuple, Mapping)):
                try:
                    corrected = _ordered(checked, len(current))
                except ValueError as error:
                    pause('Invalid meaning correction: ' + str(error), 'validation')
                if corrected != current:
                    current = corrected
                    state = report(source_text, join_lines(current), tolerance)
                    semantic_progress = (issue_count is not None and
                                         (last_semantic_count is None or issue_count < last_semantic_count))
                    previous_stalls = semantic_stalled
                    semantic_stalled = 0 if semantic_progress else semantic_stalled+1
                    if issue_count is not None:
                        last_semantic_count = issue_count
                    issue = 'Meaning corrections were retained; checking their length and meaning again.'
                    checkpoint()
                    if previous_stalls >= max_stalled_passes and not semantic_progress:
                        pause('Meaning corrections have not converged. Saved the corrected draft for review.',
                              'validation_stalled')
                    stalled = 0
                    seen = {join_lines(current)}
                    continue
                if issue_count:
                    pause('Meaning audit still reports unresolved issues. The draft is saved for review.',
                          'validation_stalled')
            checkpoint()
            return {'lines': list(current), 'report': dict(state), 'passes': passes}

        if not current or not state['source_chars']:
            pause('Cannot change an empty source or remove every phrase.', 'invalid_budget')
        try:
            target_hints = allocate_targets(current, state['source_chars'])
        except ValueError as error:
            pause(str(error), 'invalid_budget')
        if max_passes is not None and passes >= max_passes:
            pause('Text refinement request limit reached. The best draft is saved and can be resumed.',
                  'pass_limit')
        feedback = {**state, 'attempt': passes+1, 'max_passes': max_passes,
                    'target_chars': state['source_chars'], 'line_targets': target_hints,
                    'ids': list(range(len(current))), 'last_issue': issue,
                    'pending_ids': list(pending_ids), 'stalled_passes': stalled}
        draft = rewrite(list(current), feedback)
        passes += 1
        try:
            candidate, updated_ids, issues = _merge_update(draft, current)
        except ValueError as error:
            issue = str(error)
            stalled += 1
        else:
            encoded = join_lines(candidate)
            next_state = report(source_text, encoded, tolerance)
            distance = state['over_by']+state['under_by']
            next_distance = next_state['over_by']+next_state['under_by']
            if next_distance < distance:
                current, state = candidate, next_state
                pending_ids = sorted(set(range(len(current)))-set(updated_ids))
                stalled = 0
                issue = ' '.join(issues) or 'The best draft is retained; continue toward the whole-text budget.'
                checkpoint()
            else:
                stalled += 1
                issue = ('The response repeated an unchanged or previously rejected draft. '
                         if encoded in seen else
                         'The response did not improve the whole-text character budget. ') + (
                         'The best draft is retained. Use different natural wording without losing facts.')
            seen.add(encoded)
        if stalled >= max_stalled_passes:
            pause('Text refinement made no progress for ' + str(stalled)
                  + ' consecutive attempts. The best draft is saved and can be resumed. ' + (issue or ''),
                  'stalled')
