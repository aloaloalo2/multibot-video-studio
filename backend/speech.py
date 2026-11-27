"""Local speech recognition and conservative script-to-word alignment."""
from __future__ import annotations

import job_timing
import copy
import difflib
import math
import os
import platform
import shutil
import subprocess
import sys
import threading
import types
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
MIN_MATCH_PERCENT = 90.0
# Under the order policy the whole voice still has to be heard well: a voice where only some three words in four were
# recognised has something wrong with it, and the episode stops before the automatic montage (user, 27 November 2026:
# «якщо порядок пропущений… або взагалі якогось речення нема… або тільки 75% типу слів розпізнано… Тоді ми
# зупиняємося… автомонтаж»). Normal voices come out at 97–98%.
MIN_ORDER_MATCH_PERCENT = 85.0
ORDER_MATCH_MIN_WORDS = 100   # the share is checked on voices of at least this many script words
MIN_PHRASE_MATCH_PERCENT = 80
MAX_UNHEARD_RUN = 3
BLOCKING_ISSUES = {"missing_boundary", "uncertain_boundary", "missing_speech", "low_phrase_match", "number_difference"}


def blocking_issues(sequence_verified=False, *, order_only=False):
    return BLOCKING_ISSUES - {'low_phrase_match', 'number_difference'} if sequence_verified or order_only else BLOCKING_ISSUES


def transcript_script(words):
    """The recognised voice as a script: Whisper's own words and punctuation, one clean line of text."""
    text = re.sub(r"\s+", " ", " ".join(word["text"] for word in words)).strip()
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    if text and text[-1] not in ".!?…":
        text += "."
    if not text:
        raise RuntimeError("У файлі не вдалося розпізнати мовлення")
    return text


def _compare_in_order(script, words, duration, sequence_verified=False, *, order_only=False):
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

    range_ends = [end for _, end in ranges]
    matcher = difflib.SequenceMatcher(None, reference, heard, autojunk=False)
    mapping, differences, affected, numeric_differences = {}, [], set(), set()
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
        # sentences whose tokens overlap [a0, a1); ranges are consecutive, so the first one ending after a0 leads them
        first = min(bisect.bisect_right(range_ends, a0), len(ranges) - 1) if ranges else 0
        related = []
        for index in range(first, len(ranges)):
            if ranges[index][0] >= a1:
                break
            if a0 < ranges[index][1] and a1 > ranges[index][0]:
                related.append(index)
        if not related and ranges:
            related = [first]
        affected.update(related)
        expected_numbers = [token for token in reference[a0:a1] if re.search(r'\d', token)]
        heard_numbers = [token for token in heard[b0:b1] if re.search(r'\d', token)]
        if expected_numbers != heard_numbers:
            numeric_differences.update(related)
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
            # The voice always comes in whole sentences: a sentence heard in part was said whole and only Whisper
            # missed words (user, 27 November 2026: «Озвучка завжди іде мінімум як речення… ніяке слово пропущене не
            # може бути… головне послідовність речень»). Under the order policy only a sentence heard not at all is
            # missing; a partly heard one keeps its words' estimated times as a note.
            issues.append("missing_speech" if not order_only or not matched else "unheard_words")
        if len(matched) * 100 < (end - start) * MIN_PHRASE_MATCH_PERCENT:
            issues.append("low_phrase_match")
        if index in numeric_differences:
            issues.append("number_difference")
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
                        "word_match_percent": round(len(matched) / (end - start) * 100, 1) if end > start else 0,
                        "recognition_confidence": round(confidence, 4), "issues": issues})
    # Each written word takes the time of the tokens it holds (one token per word, several for «2025-го» and the like).
    tokens_of = [[] for _ in chunks]
    for a, owners in enumerate(token_chunks):
        for k in owners:
            tokens_of[k].append(a)
    script_words = []
    for k, chunk in enumerate(chunks):
        owned = [times[a] for a in tokens_of[k] if times[a]]
        if owned:
            script_words.append({"text": chunk["text"], "sentence": chunk["sentence"], "start": round(min(t[0] for t in owned), 3),
                                 "end": round(max(t[1] for t in owned), 3),
                                 "word_index": k,
                                 "estimated": any(estimated[a] for a in tokens_of[k])})
    percent = round(len(mapping) / len(reference) * 100, 1) if reference else 0
    blocking = blocking_issues(sequence_verified, order_only=order_only)
    # Original narration needs evidence that each sentence is present in order.
    # ASR spelling/numerals remain diagnostics; they are not an assembly proof.
    # a share means something over a whole voice; on a few sentences two Whisper slips already make 66%
    floor = (MIN_ORDER_MATCH_PERCENT if len(reference) >= ORDER_MATCH_MIN_WORDS else 0) if sequence_verified or order_only else MIN_MATCH_PERCENT
    ready = bool(phrases) and percent >= floor and all(not blocking.intersection(phrase["issues"]) for phrase in phrases)
    timings = {"duration": duration, "sentences": [{"text": phrase["text"], "start": phrase["start"], "end": phrase["end"]} for phrase in phrases]} if ready else None
    if timings:
        planner.validate_sentence_timings(script, timings["sentences"], duration)
    return {"status": "matched" if ready else "needs_review", "matched_words": len(mapping),
            **({'recognition_policy': 'sentence_order'} if order_only else {}),
            "script_words": len(reference), "recognized_words": len(heard),
            "word_match_percent": percent, "minimum_phrase_match_percent": MIN_PHRASE_MATCH_PERCENT,
            "corrected_words": len(reference) - len(mapping),
            "matched_phrases": sum(not blocking.intersection(phrase["issues"]) for phrase in phrases), "phrase_count": len(phrases),
            "phrases": phrases, "differences": differences, "timings": timings, "aligned_words": script_words}


_MLX_PATHS = {}
SAMPLE_RATE = 16000


def mlx_model_path(model=MODEL_NAME):
    """Local MLX snapshot for Apple Silicon, or None to use the CPU engine. Looked up once per model: the repairs ask
    for it before every short piece."""
    if model in _MLX_PATHS:
        return _MLX_PATHS[model]
    if sys.platform != "darwin" or platform.machine() != "arm64" or model not in MLX_REPOS:
        return None
    try:
        import mlx_whisper  # noqa: F401
        from huggingface_hub import snapshot_download
        _MLX_PATHS[model] = snapshot_download(MLX_REPOS[model], local_files_only=True)
    except Exception:
        return None
    return _MLX_PATHS[model]


class Voice:
    """An audio file decoded once to 16 kHz mono, the input both engines read; pieces are slices of it, so the repairs
    recognise them again without another FFmpeg run each."""

    def __init__(self, path, samples=None, offset=0.0):
        self.path, self._samples, self.offset = path, samples, offset

    @property
    def samples(self):
        if self._samples is None:
            import numpy as np
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise RuntimeError("Для розпізнавання потрібен FFmpeg")
            run = subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "0", "-i", str(self.path),
                                  "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE), "-"],
                                 capture_output=True, timeout=1800)
            if run.returncode:
                raise RuntimeError("Не вдалося прочитати аудіо для розпізнавання")
            self._samples = np.frombuffer(run.stdout, np.int16).flatten().astype(np.float32) / 32768.0
        return self._samples

    def piece(self, start, end):
        """The audio between two moments of this voice, or None when it holds nothing."""
        a, b = max(0, int(round(start * SAMPLE_RATE))), int(round(end * SAMPLE_RATE))
        part = self.samples[a:b]
        return Voice(self.path, part, start) if len(part) else None


def _input(audio):
    return audio.samples if isinstance(audio, Voice) else str(audio)


def transcribe_mlx(model_path, audio, duration, progress, language=None):
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
            result = mlx_whisper.transcribe(_input(audio), path_or_hf_repo=model_path, language=language, verbose=None,
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


@job_timing.measure('recognition')
def transcribe(audio, duration, progress, language=None):
    """Words of a file path or a decoded Voice (or a piece of one), with their times in that audio."""
    global _MODEL
    model_path = mlx_model_path()
    if model_path:
        return transcribe_mlx(model_path, audio, duration, progress, language)
    try:
        from faster_whisper import WhisperModel
        with MODEL_LOCK:
            if _MODEL is None:
                _MODEL = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8", cpu_threads=CPU_THREADS, local_files_only=True)
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        raise RuntimeError("Локальний Whisper або його модель недоступні. Перевірте встановлення моделі small") from error
    segments, info = _MODEL.transcribe(_input(audio), language=language, word_timestamps=True, vad_filter=True,
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
_LAST_COMPARISON = [None, None]   # key, report: the worker compares the words the repairs settled on once more
_COMPARISON_LOCK = threading.Lock()


@job_timing.measure('verification')
def compare_script(script, words, duration, sequence_verified=False, *, order_only=False):
    key = (script, duration, bool(sequence_verified), bool(order_only),
           tuple((w.get("text"), w.get("start"), w.get("end"), w.get("probability")) for w in words))
    with _COMPARISON_LOCK:
        if _LAST_COMPARISON[0] == key:
            return copy.deepcopy(_LAST_COMPARISON[1])
    report = speech_order.mark(script, words,
                               _compare_in_order(script, words, duration, sequence_verified, order_only=order_only),
                               blocking_issues(sequence_verified, order_only=order_only))
    with _COMPARISON_LOCK:
        _LAST_COMPARISON[:] = [key, copy.deepcopy(report)]
    return report
