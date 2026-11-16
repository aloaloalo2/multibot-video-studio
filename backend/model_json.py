"""One forgiving reader for JSON that language models write (DeepSeek, MiniMax, Opus, Codex).

Models wrap the same answer in different ways: ```json fences (any tag, any case, one end only), a word before it
(«JSON\\n{…}» stopped a Polish translation on 16 November 2026), a sentence after it. The content checks of each
caller stay as strict as before; only the wrapping is forgiven here, so a correct answer is never thrown away and
bought again.
"""
from __future__ import annotations

import json
import re

FENCE_OPEN = re.compile(r"^\s*```[A-Za-z0-9_-]*[ \t]*\n?")
FENCE_CLOSE = re.compile(r"\n?[ \t]*```\s*$")


def strip_fences(text: str) -> str:
    """The text without a Markdown fence at its start and/or its end."""
    text = str(text or "").strip()
    text = FENCE_OPEN.sub("", text, count=1)
    return FENCE_CLOSE.sub("", text, count=1).strip()


def loads(text: str, *, object_pairs_hook=None, kinds=(dict, list)):
    """The JSON value of a model answer. The whole (unfenced) text is tried first; then the first `{` or `[` from which
    a complete JSON value of one of `kinds` decodes, ignoring words before and after it. Raises ValueError when the
    answer holds no such value."""
    body = strip_fences(text)
    decoder = json.JSONDecoder(object_pairs_hook=object_pairs_hook)
    # Only a syntax error moves the search on; a value the hook refuses (a duplicate key) stays refused, so an inner
    # object of a refused answer is never taken instead.
    try:
        value = decoder.decode(body)
        if isinstance(value, kinds):
            return value
    except json.JSONDecodeError:
        pass
    for start, char in enumerate(body):
        if char not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(body, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, kinds):
            return value
    raise ValueError("The answer holds no JSON value")


def documents(text: str, *, object_pairs_hook=None) -> list:
    """Every JSON value of an answer written one after another (JSONL, or several objects), words before the first
    and after the last forgiven. Raises ValueError when none decodes."""
    body = strip_fences(text)
    decoder = json.JSONDecoder(object_pairs_hook=object_pairs_hook)

    def run(part):
        found, rest = [], part.strip()
        while rest:
            value, end = decoder.raw_decode(rest)
            found.append(value)
            rest = rest[end:].strip()
        return found
    try:
        found = run(body)
        if found:
            return found
    except json.JSONDecodeError:
        pass
    # words between the values too («{draft}\n\nWait, fix:\n{final}», «{...}\nNote: see [1].»): every value that
    # decodes, in order, the text around and between them skipped (a refused duplicate key still raises)
    found, at = [], 0
    while at < len(body):
        starts = [i for i in (body.find("{", at), body.find("[", at)) if i >= 0]
        if not starts:
            break
        start = min(starts)
        try:
            value, end = decoder.raw_decode(body, start)
        except json.JSONDecodeError:
            at = start + 1
            continue
        found.append(value)
        at = end
    if found:
        return found
    raise ValueError("The answer holds no JSON value")
