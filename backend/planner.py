"""Scene planning owned and executed by MultiBot Video Studio."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
import number_text

SETTING_DEFAULTS = {
    "short_sentence_words": 5, "max_sentences_per_scene": 4,
    "words_per_minute": 145, "first_clip_seconds": 0,
    "motion_easing": "ease_in_out",
}


def effective_settings(settings: dict) -> dict:
    # Retired opening fields must never influence a new plan.
    return {**{key: settings.get(key, value) for key, value in SETTING_DEFAULTS.items()},
            "weights": copy.deepcopy(settings.get("weights", {}))}


def settings_signature(settings: dict) -> str:
    raw = json.dumps(effective_settings(settings), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()

LABELS = {
    "generated_video": "Створене відео",
    "stock_video": "Стокове відео",
    "generated_photo": "Створене фото",
    "stock_photo": "Стокове фото",
    "animation": "Анімація / схема",
    "text": "Текстова сцена",
    "host": "Ведучий",
}
def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    # Preserve ordinary abbreviations and decimal points before splitting.
    placeholders = {"т.д.": "т¤д¤", "т.п.": "т¤п¤", "н.е.": "н¤е¤", "Dr.": "Dr¤", "Mr.": "Mr¤"}
    for old, new in placeholders.items():
        text = text.replace(old, new)
    parts = re.split(r"(?<=[.!?…])\s+(?=[«„“\"(\w])", text)
    return [p.replace("¤", ".").strip() for p in parts if p.strip()]


def word_count(sentence: str) -> int:
    return len(re.findall(r"[\wÀ-ÿА-Яа-яЁёІіЇїЄєҐґ]+(?:['’][\wА-Яа-яІіЇїЄєҐґ]+)?", sentence))


def group_sentences(sentences: list[str], short_limit: int, max_per_scene: int) -> list[list[str]]:
    scenes: list[list[str]] = []
    carry: list[str] = []
    for sentence in sentences:
        if word_count(sentence) <= short_limit and len(carry) < max_per_scene - 1:
            carry.append(sentence)
            continue
        scenes.append(carry + [sentence])
        carry = []
    if carry:
        if scenes and len(scenes[-1]) + len(carry) <= max_per_scene:
            scenes[-1].extend(carry)
        else:
            scenes.append(carry)
    return scenes


def estimate_times(groups: list[list[str]], words_per_minute: float, duration: float | None, first_clip_seconds: float = 0) -> list[tuple[float, float]]:
    weights = [max(1, sum(word_count(s) for s in group)) for group in groups]
    total = sum(weights)
    full = duration if duration is not None else total * 60 / words_per_minute
    if first_clip_seconds and len(groups) == 1:
        return [(0.0, duration if duration is not None else first_clip_seconds)]
    if first_clip_seconds and full <= first_clip_seconds:
        raise ValueError("Тривалість першого кліпу перевищує тривалість ролика")
    if first_clip_seconds and len(groups) > 1 and full > first_clip_seconds:
        remaining_weight = sum(weights[1:])
        boundaries = [0.0, first_clip_seconds]
        elapsed = first_clip_seconds
        for weight in weights[1:-1]:
            elapsed += (full - first_clip_seconds) * weight / remaining_weight
            boundaries.append(elapsed)
        boundaries.append(full)
        return list(zip(boundaries[:-1], boundaries[1:]))
    boundaries = [0.0]
    elapsed = 0.0
    for weight in weights[:-1]:
        elapsed += full * weight / total
        boundaries.append(elapsed)
    boundaries.append(full)
    return list(zip(boundaries[:-1], boundaries[1:]))


def assign_formats(times: list[tuple[float, float]], config: dict, hints: dict[int, str] | None = None, groups: list[list[str]] | None = None) -> list[str]:
    formats: list[str | None] = [None] * len(times)
    opening = [0] if times else []
    video_format = "generated_video" if float(config.get("first_clip_seconds", 0)) > 0 or config["weights"].get("generated_video", 0) > 0 else "stock_video" if config["weights"].get("stock_video", 0) > 0 else "generated_video"
    types = [video_format]
    if not types or any(item not in LABELS for item in types):
        raise ValueError("opening_clip_types містить невідомий формат")
    for j, index in enumerate(opening):
        formats[index] = types[min(j, len(types) - 1)]
    weights = {key: float(value) for key, value in config["weights"].items() if value > 0}
    if not weights:
        raise ValueError("Для автоматичного плану потрібен хоча б один формат")
    total_weight = sum(weights.values())
    used = defaultdict(float)
    scene_hints = {}
    if hints and groups:
        sentence_number = 0
        for scene_index, group in enumerate(groups):
            for _ in group:
                sentence_number += 1
                if sentence_number in hints and scene_index not in opening:
                    scene_hints.setdefault(scene_index, hints[sentence_number])
    scheduled = 0.0
    previous, run = None, 0
    for i, (start, end) in enumerate(times):
        duration = end - start
        scheduled += duration
        fixed = formats[i] or scene_hints.get(i)
        if fixed:
            if fixed == previous and run >= 5:
                raise ValueError("Змістова розмітка задає понад п’ять однакових форматів поспіль. Змініть формат одного з кадрів")
            pick = fixed
        else:
            eligible = [key for key in weights if key != previous or run < 5]
            if not eligible:
                raise ValueError("Для чергування кадрів додайте частку ще одного формату. Дозволено до п’яти однакових поспіль")
            pick = max(eligible, key=lambda key: (scheduled * weights[key] / total_weight - used[key], key))
        formats[i] = pick
        used[pick] += duration
        run = run + 1 if pick == previous else 1
        previous = pick
    result = [str(item) for item in formats]
    return result


def speech_text(text, locale=None):
    return number_text.comparison_tokens(text, locale)


def validate_sentence_timings(script, timings, duration):
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Для таймінгів потрібна виміряна тривалість аудіо")
    sentences = split_sentences(script)
    locale = number_text.detect_locale(script)
    if not isinstance(timings, list) or len(timings) != len(sentences):
        raise ValueError("Потрібні таймінги кожної фрази сценарію з готової озвучки")
    result, previous = [], 0.0
    for number, (text, item) in enumerate(zip(sentences, timings), 1):
        if not isinstance(item, dict) or speech_text(item.get("text", ""), locale) != speech_text(text, locale):
            raise ValueError(f"Текст фрази {number} не відповідає сценарію. Звірте розшифровку озвучки")
        start, end = item.get("start"), item.get("end")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (start, end)) or start < previous or end <= start or end > duration + .001:
            raise ValueError(f"Невірний час фрази {number} у готовій озвучці")
        result.append({"number": number, "text": text, "start": start, "end": end})
        previous = end
    return result


def aligned_times(groups, timings, duration):
    boundaries, offset = [0.0], 0
    for group in groups[:-1]:
        offset += len(group)
        boundaries.append(timings[offset]["start"])
    boundaries.append(duration)
    if any(end <= start for start, end in zip(boundaries, boundaries[1:])):
        raise ValueError("Межі кадрів не узгоджуються з озвучкою")
    return list(zip(boundaries[:-1], boundaries[1:]))


def validate_synced_plan(plan, duration):
    timing = plan.get("timing", {})
    if timing.get("status") != "audio_synced":
        raise ValueError("Це чернетка плану. Додайте готову озвучку та таймінги фраз")
    if not plan.get("frames") or plan["frames"][0].get("format") not in {"stock_video", "generated_video"}:
        raise ValueError("Перший кадр має бути відео. Перегенеруйте план")
    script = plan.get("script", "")
    if not script or hashlib.sha256(script.encode("utf-8")).hexdigest() != plan.get("script_sha256"):
        raise ValueError("Сценарій змінився. Оновіть прив’язку до озвучки")
    spoken_script = plan.get("spoken_script", script)
    locale = number_text.detect_locale(spoken_script)
    if plan.get("spoken_script_sha256") and hashlib.sha256(spoken_script.encode("utf-8")).hexdigest() != plan["spoken_script_sha256"]:
        raise ValueError("Озвучений оригінал сценарію змінився")
    if plan.get("number_format") == "digits_after_whisper" and number_text.to_digits(spoken_script) != script:
        raise ValueError("Числовий текст не відповідає озвученому сценарію")
    timings = validate_sentence_timings(spoken_script, timing.get("sentences"), duration)
    if plan.get("number_format") == "digits_after_whisper":
        timings = [{**item, "text": number_text.to_digits(item["text"], locale)} for item in timings]
    groups = [frame.get("sentences", []) for frame in plan["frames"]]
    expected_sentences = split_sentences(spoken_script)
    if plan.get("number_format") == "digits_after_whisper":
        expected_sentences = [number_text.to_digits(text, locale) for text in expected_sentences]
    if [text for group in groups for text in group] != expected_sentences:
        raise ValueError("Кадри не покривають усі фрази сценарію")
    expected = aligned_times(groups, timings, duration)
    offset = 0
    for frame, group, (start, end) in zip(plan["frames"], groups, expected):
        if abs(float(frame["start"]) - start) > .0011 or abs(float(frame["end"]) - end) > .0011 or frame.get("sentence_timings") != timings[offset:offset + len(group)]:
            raise ValueError("Таймінги кадрів змінилися. Оновіть план за озвучкою")
        offset += len(group)


def upgrade_legacy_number_format(plan):
    """Read older number formatting using the unchanged spoken source.

    Only migrate a plan that exactly matches the previous formatter and whose
    stored script, sentence timings and frame contents still agree. This does
    not alter the saved plan, frame boundaries, formats or the montage.
    """
    if plan.get('number_format') != 'digits_after_whisper' or plan.get('timing', {}).get('status') != 'audio_synced':
        return plan
    spoken = plan.get('spoken_script', '')
    script = plan.get('script', '')
    if not spoken or not script or number_text.to_digits(spoken) == script:
        return plan
    if hashlib.sha256(spoken.encode('utf-8')).hexdigest() != plan.get('spoken_script_sha256') or hashlib.sha256(script.encode('utf-8')).hexdigest() != plan.get('script_sha256'):
        return plan
    import legacy_number_text
    if legacy_number_text.to_digits(spoken) != script:
        return plan
    old_sentences = split_sentences(script)
    spoken_sentences = split_sentences(spoken)
    timing = plan.get('timing', {}).get('sentences', [])
    frames = plan.get('frames', [])
    if (len(old_sentences) != len(spoken_sentences) or len(timing) != len(old_sentences)
        or [entry.get('text') for entry in timing] != old_sentences
        or [text for frame in frames for text in frame.get('sentences', [])] != old_sentences
        or [entry for frame in frames for entry in frame.get('sentence_timings', [])] != timing):
        return plan
    updated = copy.deepcopy(plan)
    locale = number_text.detect_locale(spoken)
    formatted = [number_text.to_digits(sentence, locale) for sentence in spoken_sentences]
    updated['script'] = number_text.to_digits(spoken)
    updated['script_sha256'] = hashlib.sha256(updated['script'].encode('utf-8')).hexdigest()
    for item, text in zip(updated['timing']['sentences'], formatted):
        item['text'] = text
    offset = 0
    for frame in updated['frames']:
        count = len(frame['sentences'])
        frame['sentences'] = formatted[offset:offset+count]
        frame['sentence_timings'] = copy.deepcopy(updated['timing']['sentences'][offset:offset+count])
        offset += count
    try:
        validate_synced_plan(updated, updated['timing']['audio']['duration'])
    except (ValueError, TypeError, KeyError):
        return plan
    return updated


def digitize_synced_plan(plan):
    """Format actual post-ASR text while retaining the immutable spoken source."""
    if plan.get("timing", {}).get("status") != "audio_synced":
        return plan
    plan = copy.deepcopy(plan)
    source = plan["script"]
    locale = number_text.detect_locale(source)
    plan["spoken_script"] = source
    plan["spoken_script_sha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    plan["number_format"] = "digits_after_whisper"
    plan["script"] = number_text.to_digits(source)
    plan["script_sha256"] = hashlib.sha256(plan["script"].encode("utf-8")).hexdigest()
    for item in plan["timing"]["sentences"]:
        item["text"] = number_text.to_digits(item["text"], locale)
    for frame in plan["frames"]:
        frame["sentences"] = [number_text.to_digits(text, locale) for text in frame["sentences"]]
        frame["sentence_timings"] = [{**item, "text": number_text.to_digits(item["text"], locale)} for item in frame["sentence_timings"]]
    return plan


def build_plan(script: str, settings: dict, channel_name: str, duration=None, hints=None, alignment=None) -> dict:
    config = effective_settings(settings)
    if not isinstance(script, str) or not script.strip():
        raise ValueError("Додайте текст сценарію")
    if duration is not None and (type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0):
        raise ValueError("Тривалість має бути додатним числом")
    sentences = split_sentences(script)
    normalized_hints = {}
    if hints is not None:
        if not isinstance(hints, dict):
            raise ValueError("Підказки мають бути об'єктом JSON")
        for key, value in hints.items():
            number = int(key)
            if str(number) != str(key) or not 1 <= number <= len(sentences) or value not in LABELS:
                raise ValueError("Невірна підказка для речення")
            normalized_hints[number] = value
    groups = group_sentences(sentences, int(config["short_sentence_words"]), int(config["max_sentences_per_scene"]))
    timings = validate_sentence_timings(script, alignment, duration) if alignment is not None else None
    times = aligned_times(groups, timings, duration) if timings else estimate_times(groups, float(config["words_per_minute"]), duration, float(config["first_clip_seconds"]))
    formats = assign_formats(times, config, normalized_hints, groups)
    frames = [{"number": i, "start": round(start, 3), "end": round(end, 3), "sentences": group, "format": fmt}
              for i, (group, (start, end), fmt) in enumerate(zip(groups, times, formats), 1)]
    if timings:
        offset = 0
        for frame, group in zip(frames, groups):
            frame["sentence_timings"] = timings[offset:offset + len(group)]
            offset += len(group)
    amounts = defaultdict(float)
    for frame in frames:
        amounts[frame["format"]] += frame["end"] - frame["start"]
    return {
        "generator": "multibot-video-studio", "planner_version": 2,
        "timing": {"status": "audio_synced" if timings else "draft", "basis": "audio_alignment" if timings else "duration_estimate" if duration is not None else "script_estimate", "sentences": timings or []},
        "settings_snapshot": config, "settings_signature": settings_signature(config),
        "script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        "hints": normalized_hints, "script": script, "frames": frames,
        "report": {"channel": channel_name, "frames": len(frames),
                   "duration_seconds": round(times[-1][1], 2),
                   "format_seconds": {key: round(value, 3) for key, value in amounts.items()},
                   "timing_basis": "audio_alignment" if timings else "duration_estimate" if duration is not None else "script"},
    }


