"""Second look at the places where Whisper swallowed speech.

On a long voice Whisper sometimes skips a sentence and stretches the words around the hole over it: on 30 October 2026
"These are the lucky stories. Studies of adults whose core fell below 28 degrees report that..." came back as
"These are the that...", with "are" lasting 3.5 s. A spoken word lasts well under a second, so a word that long marks a
hole. Each hole is cut out with a little of its neighbours and recognised again on its own, where Whisper hears it fine;
the new words replace the old ones there only when the second pass heard more. The voice and its length never change.
"""
from __future__ import annotations

import job_timing
from pathlib import Path

import speech

LONG_WORD = 1.2      # seconds: longer than any spoken word
CONTEXT = 2          # neighbouring words recognised again together with the hole
PAD = 0.25           # seconds of audio kept around the cut
MAX_HOLES = 60
MAX_SCRIPT_PHRASES = 8
MAX_SCRIPT_SECONDS = 60


def holes(words: list[dict]) -> list[tuple[int, int]]:
    """Word index ranges [a, b] around every stretched word, merged where they touch."""
    spans = []
    for i, word in enumerate(words):
        if word["end"] - word["start"] > LONG_WORD:
            a, b = max(0, i - CONTEXT), min(len(words) - 1, i + CONTEXT)
            if spans and a <= spans[-1][1] + 1:
                spans[-1] = (spans[-1][0], b)
            else:
                spans.append((a, b))
    return spans[:MAX_HOLES]


def voice(audio) -> speech.Voice:
    return audio if isinstance(audio, speech.Voice) else speech.Voice(audio)


def cut(audio: speech.Voice, start: float, end: float):
    """The piece of the voice between two moments, decoded once for all pieces; None when it cannot be read."""
    try:
        return audio.piece(start, end)
    except (RuntimeError, OSError, ValueError):
        return None


@job_timing.measure('recognition')
def repair(audio: Path | speech.Voice, words: list[dict], language: str | None = None) -> tuple[list[dict], int]:
    """The words with every swallowed hole recognised again; also how many holes gained words."""
    spans = holes(words)
    if not spans:
        return words, 0
    audio, result, fixed, done = voice(audio), [], 0, 0
    for a, b in spans:
        start, end = max(0.0, words[a]["start"] - PAD), words[b]["end"] + PAD
        old = words[a:b + 1]
        new = None
        piece = cut(audio, start, end)
        if piece:
            try:
                heard, _ = speech.transcribe(piece, end - start, lambda *args, **kwargs: None, language)
                # the padding may reach into the neighbours: the new words stay between them
                lo = words[a - 1]["end"] if a else 0.0
                hi = words[b + 1]["start"] if b + 1 < len(words) else end
                new = []
                for w in heard:
                    s0 = round(min(max(w["start"] + start, lo), hi), 3)
                    new.append({**w, "start": s0, "end": round(min(max(w["end"] + start, s0), hi), 3)})
            except RuntimeError:
                new = None
        result += words[done:a]
        if new and len(new) > len(old):
            result += new
            fixed += 1
        else:
            result += old
        done = b + 1
    return result + words[done:], fixed


@job_timing.measure('recognition')
def repair_script(audio: Path | speech.Voice, script: str, words: list[dict], language=None, *, duration=None, sequence_verified=False, order_only=False) -> tuple[list[dict], int]:
    """Rehear blocked phrases locally, preserving neighbours and the acceptance gate."""
    if not script or not words:
        return words, 0
    duration = duration or max(word['end'] for word in words)
    def compare(value):
        return speech.compare_script(script, value, duration, sequence_verified=sequence_verified, order_only=order_only)
    try:
        report = compare(words)
    except ValueError:
        # Rehearing is an optional repair: a check that cannot run leaves the recognised words as they are, and the
        # main comparison afterwards reports the real state (20 November 2026: one phrase failed the whole recognition).
        return words, 0
    if report['status'] == 'matched':
        return words, 0
    blocking = speech.blocking_issues(sequence_verified, order_only=order_only)
    targets = [row['number'] for row in report['phrases']
               if blocking.intersection(row['issues'])][:MAX_SCRIPT_PHRASES]
    fixed = 0

    def score(value):
        issues = blocking | {'repeated_speech', 'out_of_order'}
        blocked = {row['number'] for row in value['phrases'] if issues.intersection(row['issues'])}
        return blocked, value['matched_words']

    audio = voice(audio)
    for number in targets:
        row = report['phrases'][number - 1]
        if not blocking.intersection(row['issues']):
            continue
        # A completely swallowed opening/ending can have no boundary.
        # Use the nearest heard phrases and the measured audio duration.
        left = row['start']
        right = row['end']
        if left is None:
            left = next((p['end'] for p in reversed(report['phrases'][:number - 1]) if p['end'] is not None), 0)
        if right is None:
            right = next((p['start'] for p in report['phrases'][number:] if p['start'] is not None), duration)
        lo, hi = max(0, left - 1), min(duration, right + 1)
        span = [i for i, word in enumerate(words) if word['end'] > lo and word['start'] < hi]
        if not span:
            continue
        a, b = span[0], span[-1]
        start = lo if a == 0 else words[a]['start']
        end = hi if b == len(words) - 1 else words[b]['end']
        if end <= start or end - start > MAX_SCRIPT_SECONDS:
            continue
        piece = cut(audio, start, end)
        if not piece:
            continue
        try:
            heard, _ = speech.transcribe(piece, end - start, lambda *args, **kwargs: None, language)
        except RuntimeError:
            continue
        heard = [{**word, 'start': round(max(start, min(end, word['start'] + start)), 3),
                  'end': round(max(start, min(end, word['end'] + start)), 3)} for word in heard]
        heard = [word for word in heard if word['end'] > word['start']]
        candidate = words[:a] + heard + words[b + 1:]
        try:
            reviewed = compare(candidate)
        except ValueError:
            continue
        old_bad, old_hits = score(report)
        new_bad, new_hits = score(reviewed)
        if new_bad <= old_bad and new_hits >= old_hits and (len(new_bad) < len(old_bad) or new_hits > old_hits):
            words, report = candidate, reviewed
            fixed += 1
    return words, fixed
