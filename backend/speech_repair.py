"""Second look at the places where Whisper swallowed speech.

On a long voice Whisper sometimes skips a sentence and stretches the words around the hole over it: on 30 October 2026
"These are the lucky stories. Studies of adults whose core fell below 28 degrees report that..." came back as
"These are the that...", with "are" lasting 3.5 s. A spoken word lasts well under a second, so a word that long marks a
hole. Each hole is cut out with a little of its neighbours and recognised again on its own, where Whisper hears it fine;
the new words replace the old ones there only when the second pass heard more. The voice and its length never change.
"""
from __future__ import annotations

import shutil, subprocess, tempfile
from pathlib import Path

import speech

LONG_WORD = 1.2      # seconds: longer than any spoken word
CONTEXT = 2          # neighbouring words recognised again together with the hole
PAD = 0.25           # seconds of audio kept around the cut
MAX_HOLES = 60


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


def cut(audio: Path, start: float, end: float, target: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    run = subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                          "-i", str(audio), "-ac", "1", "-ar", "16000", "-y", str(target)], capture_output=True, timeout=120)
    return run.returncode == 0 and target.is_file()


def repair(audio: Path, words: list[dict], language: str | None = None) -> tuple[list[dict], int]:
    """The words with every swallowed hole recognised again; also how many holes gained words."""
    spans = holes(words)
    if not spans:
        return words, 0
    result, fixed, done = [], 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        for n, (a, b) in enumerate(spans):
            start, end = max(0.0, words[a]["start"] - PAD), words[b]["end"] + PAD
            piece = Path(tmp) / f"hole-{n}.wav"
            old = words[a:b + 1]
            new = None
            if cut(audio, start, end, piece):
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
