"""The words a frame shows, each with the moment the voice says it.

The plan keeps the spoken sentences of every frame and the analysis keeps the script's words with the recognised time
(`aligned_words`, spoken form: «полтора года»). A frame shows the digit form («1,5 года»), so a label that appears word by
word with the voice needs the digit words joined to the spoken ones: a number that took several spoken words appears
on the first of them. Moved here from the GORBUNOV-23 montage scripts so every agent and the montage operations
(montage_ops.py) share it.
"""
from __future__ import annotations

import re

import display_text
import number_text


def digit_words(sentence_numbers: list[int], words: list[dict], locale: str | None = None) -> list[dict]:
    """Words of the shown (digit) text of these sentences, each {"text", "start"} at the time of its spoken words."""
    out = []
    for number in sentence_numbers:
        spoken = [w for w in words if w.get("sentence") == number]
        text = " ".join(w["text"] for w in spoken)
        spans, cursor = [], 0
        for w in spoken:
            at = text.index(w["text"], cursor)
            spans.append((at, at + len(w["text"])))
            cursor = at + len(w["text"])
        changes = number_text.replacements(text, locale)
        i = 0
        while i < len(spoken):
            a, b = spans[i]
            change = next((c for c in changes if c[0] < b and c[1] > a), None)
            if not change:
                out.append({"text": spoken[i]["text"], "start": float(spoken[i]["start"])})
                i += 1
                continue
            j = i
            while j + 1 < len(spoken) and spans[j + 1][0] < change[1]:
                j += 1
            piece = text[a:change[0]] + change[2] + text[change[1]:spans[j][1]]
            out.extend({"text": token, "start": float(spoken[i]["start"])} for token in piece.split())
            i = j + 1
    return out


def frame_tokens(frame: dict, words: list[dict], locale: str | None = None) -> list[tuple[str, float]]:
    """The shown words of a plan frame with their absolute start times. Raises ValueError when the recognised words do
    not add up to the frame's text (then give the label an explicit moment instead)."""
    tokens = display_text.clean(" ".join(frame.get("sentences", []))).split()
    numbers = [t["number"] for t in frame.get("sentence_timings", [])]
    timed = digit_words(numbers, words, locale or number_text.detect_locale(" ".join(frame.get("sentences", []))))
    if len(timed) != len(tokens):
        raise ValueError(f"Кадр {frame.get('number')}: слова озвучки не зійшлися з текстом кадру ({len(timed)} і {len(tokens)})")
    return [(token, item["start"]) for token, item in zip(tokens, timed)]


def norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower().replace("ё", "е"))


def find_phrase(tokens: list[tuple[str, float]], phrase: str) -> list[tuple[str, float]]:
    """The run of timed words that spells `phrase` (case, punctuation and ё/е aside)."""
    want = [norm(w) for w in phrase.split()]
    for i in range(len(tokens) - len(want) + 1):
        if [norm(t) for t, _ in tokens[i:i + len(want)]] == want:
            return tokens[i:i + len(want)]
    raise ValueError(f"У кадрі немає фрази «{phrase}»")


def word_time(tokens: list[tuple[str, float]], word: str) -> float:
    """When the voice says the first word of the frame that starts with `word`."""
    key = norm(word)
    for token, start in tokens:
        if norm(token).startswith(key):
            return start
    raise ValueError(f"У кадрі немає слова «{word}»")
