"""Local speech recognition and conservative script-to-word alignment."""
from __future__ import annotations

import difflib
import math
import threading
import unicodedata
import re
import bisect

import planner
import number_text

MODEL_NAME = "small"
_MODEL = None
MODEL_LOCK = threading.Lock()


def tokens(text, locale=None):
    return number_text.comparison_tokens(text, locale)


def compare_script(script, words, duration):
    """Use only real ASR word boundaries; missing boundaries are never interpolated."""
    sentences = planner.split_sentences(script)
    locale = number_text.detect_locale(script)
    reference, ranges = [], []
    for sentence in sentences:
        start = len(reference)
        reference.extend(tokens(sentence, locale))
        ranges.append((start, len(reference)))
    heard_text = " ".join(word["text"] for word in words)
    starts, ends, offset = [], [], 0
    for word in words:
        starts.append(offset); offset += len(word["text"]); ends.append(offset); offset += 1
    heard, source_indexes, source_end_indexes = [], [], []
    for token, start, end in number_text.word_spans(heard_text, locale):
        heard.append(token)
        source_indexes.append(max(0, bisect.bisect_right(starts, start) - 1))
        source_end_indexes.append(min(len(words) - 1, bisect.bisect_left(ends, end)))
    matcher = difflib.SequenceMatcher(None, reference, heard, autojunk=False)
    mapping, differences, affected = {}, [], set()
    for kind, a0, a1, b0, b1 in matcher.get_opcodes():
        if kind == "equal":
            mapping.update({a: b for a, b in zip(range(a0, a1), range(b0, b1))})
            continue
        related = [index for index, (start, end) in enumerate(ranges) if a0 < end and a1 > start]
        if not related and ranges:
            related = [next((index for index, (_, end) in enumerate(ranges) if a0 < end), len(ranges) - 1)]
        affected.update(related)
        differences.append({"kind": kind, "sentences": [index + 1 for index in related],
                            "expected": " ".join(reference[a0:a1]), "recognized": " ".join(heard[b0:b1])})
    phrases, previous_end = [], 0.0
    for index, (sentence, (start, end)) in enumerate(zip(sentences, ranges)):
        matched = [mapping[position] for position in range(start, end) if position in mapping]
        issues = []
        if index in affected or len(matched) != end - start:
            issues.append("text_difference")
        first = words[source_indexes[mapping[start]]] if start in mapping else None
        last = words[source_end_indexes[mapping[end - 1]]] if end - 1 in mapping else None
        begin, finish = first["start"] if first else None, last["end"] if last else None
        if begin is None or finish is None:
            issues.append("missing_boundary")
        elif not all(type(value) in (int, float) and math.isfinite(value) for value in (begin, finish)) or begin < previous_end or finish <= begin or finish > duration + .001:
            issues.append("uncertain_boundary")
        if first and last:
            indexes = sorted({index for position in matched for index in range(source_indexes[position], source_end_indexes[position] + 1)})
            probabilities = [float(words[position].get("probability", 0)) for position in indexes]
            confidence = sum(probabilities) / len(probabilities) if probabilities else 0
            if probabilities and min(probabilities) < .5:
                issues.append("low_recognition_confidence")
            recognized = number_text.to_digits(" ".join(word["text"] for word in words[source_indexes[min(matched)]:source_end_indexes[max(matched)] + 1]), locale) if matched else ""
        else:
            confidence, recognized = 0, ""
        if finish is not None and math.isfinite(finish):
            previous_end = max(previous_end, finish)
        phrases.append({"number": index + 1, "text": number_text.to_digits(sentence, locale), "spoken_text": sentence, "recognized": recognized,
                        "start": begin, "end": finish, "matched_words": len(matched), "words": end - start,
                        "recognition_confidence": round(confidence, 4), "issues": issues})
    ready = bool(phrases) and not differences and all(not phrase["issues"] for phrase in phrases)
    timings = {"duration": duration, "sentences": [{"text": phrase["text"], "start": phrase["start"], "end": phrase["end"]} for phrase in phrases]} if ready else None
    if timings:
        planner.validate_sentence_timings(script, timings["sentences"], duration)
    return {"status": "matched" if ready else "needs_review", "matched_words": len(mapping),
            "script_words": len(reference), "recognized_words": len(heard),
            "word_match_percent": round(len(mapping) / len(reference) * 100, 1) if reference else 0,
            "matched_phrases": sum(not phrase["issues"] for phrase in phrases), "phrase_count": len(phrases),
            "phrases": phrases, "differences": differences, "timings": timings}


def transcribe(path, duration, progress, language=None):
    global _MODEL
    try:
        from faster_whisper import WhisperModel
        with MODEL_LOCK:
            if _MODEL is None:
                _MODEL = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        raise RuntimeError("Локальний Whisper або його модель недоступні. Перевірте встановлення моделі small") from error
    segments, info = _MODEL.transcribe(str(path), language=language, word_timestamps=True, vad_filter=True,
                                       beam_size=5, condition_on_previous_text=False)
    words = []
    for segment in segments:
        for word in segment.words or []:
            words.append({"text": word.word.strip(), "start": round(float(word.start), 3), "end": round(float(word.end), 3), "probability": round(float(word.probability), 4)})
        progress(int(min(85, 20 + round(segment.end / max(duration, .001) * 65))))
    if not words:
        raise RuntimeError("У файлі не вдалося розпізнати мовлення")
    return words, {"engine": "faster-whisper", "model": MODEL_NAME, "language": info.language,
                   "language_probability": round(float(info.language_probability), 4), "local": True}
