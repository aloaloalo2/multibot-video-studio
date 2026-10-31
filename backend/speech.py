"""Local speech recognition and conservative script-to-word alignment."""
from __future__ import annotations

import difflib
import math
import os
import platform
import sys
import threading
import types
import unicodedata
import re
import bisect

import planner
import speech_order
import number_text

MODEL_NAME = "small"
# Apple Silicon: the same model runs on the GPU through MLX when it is installed and cached locally.
MLX_REPOS = {"small": "mlx-community/whisper-small-mlx", "large-v3-turbo": "mlx-community/whisper-large-v3-turbo"}
CPU_THREADS = os.cpu_count() or 4
_MODEL = None
MODEL_LOCK = threading.Lock()
GPU_LOCK = threading.Lock()


def tokens(text, locale=None):
    return number_text.comparison_tokens(text, locale)


# Script text is the truth and the recogniser only supplies time. Small recognition slips («souls» for
# «soles», «coroid» for «choroid») are corrected to the script automatically; a real gap in the voice,
# an overlapping or missing boundary, or a weak overall match still go to review.
MIN_MATCH_PERCENT = 95.0
MAX_UNHEARD_RUN = 3
BLOCKING_ISSUES = {"missing_boundary", "uncertain_boundary", "missing_speech"}


def transcript_script(words):
    """The recognised voice as a script: Whisper's own words and punctuation, one clean line of text."""
    text = re.sub(r"\s+", " ", " ".join(word["text"] for word in words)).strip()
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    if text and text[-1] not in ".!?…":
        text += "."
    if not text:
        raise RuntimeError("У файлі не вдалося розпізнати мовлення")
    return text


def compare_script(script, words, duration):
    sentences = planner.split_sentences(script)
    locale = number_text.detect_locale(script)
    reference, ranges, chunks, token_chunks = [], [], [], []
    for index, sentence in enumerate(sentences):
        start = len(reference)
        pieces = [(match.start(), match.end()) for match in re.finditer(r"\S+", sentence)]
        base = len(chunks)
        chunks.extend({"text": sentence[a:b], "sentence": index + 1} for a, b in pieces)
        for token, a, b in number_text.word_spans(sentence, locale):
            reference.append(token)
            token_chunks.append([base + k for k, (c, d) in enumerate(pieces) if c < b and d > a])
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

    def heard_span(b0, b1):
        return float(words[source_indexes[b0]]["start"]), float(words[source_end_indexes[b1 - 1]]["end"])

    matcher = difflib.SequenceMatcher(None, reference, heard, autojunk=False)
    mapping, differences, affected = {}, [], set()
    times, estimated = [None] * len(reference), [False] * len(reference)
    for kind, a0, a1, b0, b1 in matcher.get_opcodes():
        if kind in {"equal", "replace"} and a1 - a0 == b1 - b0:
            for a, b in zip(range(a0, a1), range(b0, b1)):
                times[a] = heard_span(b, b + 1)
        elif kind == "replace":
            # The script words were said inside this heard span; share it out by order.
            begin, finish = heard_span(b0, b1)
            for k, a in enumerate(range(a0, a1)):
                times[a] = (begin + (finish - begin) * k / (a1 - a0), begin + (finish - begin) * (k + 1) / (a1 - a0))
                estimated[a] = True
        if kind == "equal":
            mapping.update({a: b for a, b in zip(range(a0, a1), range(b0, b1))})
            continue
        related = [index for index, (start, end) in enumerate(ranges) if a0 < end and a1 > start]
        if not related and ranges:
            related = [next((index for index, (_, end) in enumerate(ranges) if a0 < end), len(ranges) - 1)]
        affected.update(related)
        differences.append({"kind": kind, "sentences": [index + 1 for index in related],
                            "expected": " ".join(reference[a0:a1]), "recognized": " ".join(heard[b0:b1])})
    # Script words the recogniser did not hear at all sit between their heard neighbours.
    unheard = set()
    position = 0
    while position < len(reference):
        if times[position] is not None:
            position += 1; continue
        run_end = position
        while run_end < len(reference) and times[run_end] is None:
            run_end += 1
        left = times[position - 1][1] if position else None
        right = times[run_end][0] if run_end < len(reference) else None
        if run_end - position > MAX_UNHEARD_RUN:
            unheard.update(range(position, run_end))
        if left is not None and right is not None and right >= left:
            for k, a in enumerate(range(position, run_end)):
                times[a] = (left + (right - left) * k / (run_end - position), left + (right - left) * (k + 1) / (run_end - position))
                estimated[a] = True
        position = run_end

    phrases, previous_end = [], 0.0
    for index, (sentence, (start, end)) in enumerate(zip(sentences, ranges)):
        matched = [mapping[position] for position in range(start, end) if position in mapping]
        issues = []
        if index in affected or len(matched) != end - start:
            issues.append("text_difference")
        if any(estimated[start:end]):
            issues.append("estimated_words")
        if any(position in unheard for position in range(start, end)) or len(matched) * 2 < end - start:
            issues.append("missing_speech")
        begin = times[start][0] if end > start and times[start] else None
        finish = times[end - 1][1] if end > start and times[end - 1] else None
        if begin is None or finish is None:
            issues.append("missing_boundary")
        elif not all(math.isfinite(value) for value in (begin, finish)) or begin < previous_end - .001 or finish <= begin or finish > duration + .001:
            issues.append("uncertain_boundary")
        if matched:
            indexes = sorted({index for position in matched for index in range(source_indexes[position], source_end_indexes[position] + 1)})
            probabilities = [float(words[position].get("probability", 0)) for position in indexes]
            confidence = sum(probabilities) / len(probabilities) if probabilities else 0
            if probabilities and min(probabilities) < .5:
                issues.append("low_recognition_confidence")
            recognized = number_text.to_digits(" ".join(word["text"] for word in words[min(indexes):max(indexes) + 1]), locale)
        else:
            confidence, recognized = 0, ""
        if finish is not None and math.isfinite(finish):
            previous_end = max(previous_end, finish)
        phrases.append({"number": index + 1, "text": number_text.to_digits(sentence, locale), "spoken_text": sentence, "recognized": recognized,
                        "start": None if begin is None else round(begin, 3), "end": None if finish is None else round(finish, 3),
                        "matched_words": len(matched), "words": end - start,
                        "recognition_confidence": round(confidence, 4), "issues": issues})
    script_words = []
    for k, chunk in enumerate(chunks):
        owned = [times[a] for a, owners in enumerate(token_chunks) if k in owners and times[a]]
        if owned:
            script_words.append({"text": chunk["text"], "sentence": chunk["sentence"], "start": round(min(t[0] for t in owned), 3),
                                 "end": round(max(t[1] for t in owned), 3),
                                 "estimated": any(estimated[a] for a, owners in enumerate(token_chunks) if k in owners)})
    percent = round(len(mapping) / len(reference) * 100, 1) if reference else 0
    ready = bool(phrases) and percent >= MIN_MATCH_PERCENT and all(not BLOCKING_ISSUES.intersection(phrase["issues"]) for phrase in phrases)
    timings = {"duration": duration, "sentences": [{"text": phrase["text"], "start": phrase["start"], "end": phrase["end"]} for phrase in phrases]} if ready else None
    if timings:
        planner.validate_sentence_timings(script, timings["sentences"], duration)
    return {"status": "matched" if ready else "needs_review", "matched_words": len(mapping),
            "script_words": len(reference), "recognized_words": len(heard),
            "word_match_percent": percent, "corrected_words": len(reference) - len(mapping),
            "matched_phrases": sum(not BLOCKING_ISSUES.intersection(phrase["issues"]) for phrase in phrases), "phrase_count": len(phrases),
            "phrases": phrases, "differences": differences, "timings": timings, "aligned_words": script_words}


def mlx_model_path(model=MODEL_NAME):
    """Local MLX snapshot for Apple Silicon, or None to use the CPU engine."""
    if sys.platform != "darwin" or platform.machine() != "arm64" or model not in MLX_REPOS:
        return None
    try:
        import mlx_whisper  # noqa: F401
        from huggingface_hub import snapshot_download
        return snapshot_download(MLX_REPOS[model], local_files_only=True)
    except Exception:
        return None


def transcribe_mlx(model_path, path, duration, progress, language=None):
    import mlx_whisper
    module = sys.modules["mlx_whisper.transcribe"]  # the package re-exports a function under the same name

    class Progress:
        def __init__(self, total=None, **_):
            self.total, self.done = max(total or 1, 1), 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def update(self, count):
            self.done += count
            progress(int(min(85, 20 + round(self.done / self.total * 65))))

    with GPU_LOCK:
        original = module.tqdm
        module.tqdm = types.SimpleNamespace(tqdm=Progress)
        try:
            result = mlx_whisper.transcribe(str(path), path_or_hf_repo=model_path, language=language, verbose=None,
                                            word_timestamps=True, condition_on_previous_text=False)
        finally:
            module.tqdm = original
    words = [{"text": word["word"].strip(), "start": round(float(word["start"]), 3), "end": round(float(word["end"]), 3),
              "probability": round(float(word.get("probability", 0)), 4)}
             for segment in result.get("segments", []) for word in segment.get("words") or [] if word["word"].strip()]
    if not words:
        raise RuntimeError("У файлі не вдалося розпізнати мовлення")
    return words, {"engine": "mlx-whisper", "model": MODEL_NAME, "device": "gpu", "language": result.get("language"),
                   "language_probability": None, "local": True}


def transcribe(path, duration, progress, language=None):
    global _MODEL
    model_path = mlx_model_path()
    if model_path:
        return transcribe_mlx(model_path, path, duration, progress, language)
    try:
        from faster_whisper import WhisperModel
        with MODEL_LOCK:
            if _MODEL is None:
                _MODEL = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8", cpu_threads=CPU_THREADS, local_files_only=True)
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
    return words, {"engine": "faster-whisper", "model": MODEL_NAME, "device": "cpu", "language": info.language,
                   "language_probability": round(float(info.language_probability), 4), "local": True}


# A voice said out of order or with a piece said twice goes to review with a note of where (speech_order.py); the
# comparison above walks script and voice side by side and cannot see either on its own. Nothing is cut or moved.
_compare_in_order = compare_script


def compare_script(script, words, duration):
    return speech_order.mark(script, words, _compare_in_order(script, words, duration), BLOCKING_ISSUES)
