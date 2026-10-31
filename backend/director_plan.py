"""The frame plan a director writes for a photo or video channel (user, 31 October 2026: «план завжди робить клод-код,
тобто режисер… на основі тих пропорцій, які були вказані в каналі»).

Once the voice is recognised the plan follows it sentence by sentence. The director (Claude Opus 5.5, backend/director.py)
reads those sentences and the channel's format shares (`sentences`), groups whole sentences into frames by meaning,
gives each frame a format and a short idea of its picture, and hands the frames back (`apply`). The Studio checks them
before it saves: every sentence once and in order, no more sentences in a frame than the channel allows, only formats
the channel uses, the channel's opening format, at most five frames of one format in a row (Razgon scenes excepted)
and each format's share of the film within SHARE_TOLERANCE of the channel's. The times come from the voice, as for
every synced plan, and the frames keep their groups through later recognitions (planner.keep_director_frames).
"""
from __future__ import annotations

import planner
import store

SHARE_TOLERANCE = 5.0   # percentage points between a format's share of the film and the channel's share
RUN_LIMIT = 5
# what each format shows, for the director choosing one for a line of the voice
HINTS = {"stock_video": "реальне відео зі стоків: люди, побут, природа, рух",
         "stock_photo": "реальне фото зі стоків",
         "generated_photo": "картинка, яку згенерують саме під цю репліку, коли стоку не знайти",
         "generated_video": "відео, яке згенерують під репліку",
         "razgon_2d": "процес чи механізм у русі, намальований кодом",
         "animation": "анімована схема чи інфографіка",
         "text": "коротка важлива теза текстом на весь кадр",
         "host": "кадр із ведучим"}


def synced_plan(pid: str) -> dict:
    plan = store.load_project_plan(pid)
    if not plan or plan.get("timing", {}).get("status") != "audio_synced":
        raise store.StudioError("Спершу додайте озвучку: план кадрів робиться за нею")
    return plan


def channel_settings(project: dict) -> dict:
    channel = next((c for c in store.list_channels() if c["id"] == project.get("channel_id")), None)
    if not channel:
        raise store.StudioError("Канал проєкту не знайдено", 404)
    return planner.effective_settings(channel.get("settings") or {})


def shares(settings: dict) -> dict[str, float]:
    """The channel's formats with their share of the film in percent."""
    weights = {key: float(value) for key, value in settings["weights"].items() if float(value or 0) > 0}
    total = sum(weights.values())
    if not total:
        raise store.StudioError("У налаштуваннях каналу немає жодного формату з часткою")
    return {key: round(100 * value / total, 1) for key, value in weights.items()}


def opening(settings: dict) -> tuple[str | None, int]:
    """The format the channel's first frames must have, if it names one, and how many frames."""
    chosen = settings.get("first_clip_format", "auto")
    if chosen == "video":
        weights = settings["weights"]
        chosen = max(("stock_video", "generated_video"), key=lambda key: (float(weights.get(key, 0)), key == "stock_video"))
    return (None if chosen == "auto" else chosen), int(settings.get("first_clip_count", 1))


def voice(plan: dict) -> tuple[list[str], list[dict]]:
    return ([text for frame in plan["frames"] for text in frame["sentences"]],
            [item for frame in plan["frames"] for item in frame["sentence_timings"]])


def sentences(pid: str) -> dict:
    """What the director needs: the voice's sentences with their times and the channel's formats."""
    project = store.load_project(pid)
    plan, settings = synced_plan(pid), channel_settings(project)
    texts, timings = voice(plan)
    first, count = opening(settings)
    targets = shares(settings)
    return {"sentences": [{"number": number, "text": text, "start": timing["start"], "end": timing["end"]}
                          for number, (text, timing) in enumerate(zip(texts, timings), 1)],
            "duration": float(plan["timing"]["audio"]["duration"]), "shares": targets,
            "labels": {key: planner.LABELS.get(key, key) for key in targets}, "hints": {key: HINTS.get(key, "") for key in targets},
            "max_sentences": int(settings["max_sentences_per_scene"]), "tolerance": SHARE_TOLERANCE,
            "opening": {"format": first, "count": count} if first else None}


def apply(pid: str, frames, dry_run: bool = False) -> dict:
    """Check the director's frames and, unless dry_run, save them as the plan. Returns {"ok", "problems", "shares", ...}."""
    project = store.load_project(pid)
    plan, settings = synced_plan(pid), channel_settings(project)
    texts, timings = voice(plan)
    targets, limit = shares(settings), int(settings["max_sentences_per_scene"])
    labels = {key: planner.LABELS.get(key, key) for key in targets}
    if not isinstance(frames, list) or not frames:
        raise store.StudioError("Передайте кадри: список frames")
    problems, groups, kinds, ideas, expected = [], [], [], [], 1
    for index, frame in enumerate(frames, 1):
        numbers = frame.get("sentences") if isinstance(frame, dict) else None
        if not isinstance(numbers, list) or not numbers or not all(isinstance(n, int) and not isinstance(n, bool) for n in numbers):
            problems.append(f"Кадр {index}: sentences має бути списком номерів речень")
            continue
        if numbers != list(range(expected, expected + len(numbers))):
            problems.append(f"Кадр {index}: речення мають іти підряд від {expected}, а тут {numbers}")
        if len(numbers) > limit:
            problems.append(f"Кадр {index}: {len(numbers)} речень, а в кадрі каналу можна до {limit}")
        kind = frame.get("format")
        if kind not in targets:
            problems.append(f"Кадр {index}: формату «{kind}» канал не використовує; можна: " + ", ".join(targets))
        expected = numbers[-1] + 1
        groups.append(numbers)
        kinds.append(kind)
        ideas.append(str(frame.get("idea") or frame.get("visual") or "").strip())
    if not problems and expected - 1 != len(texts):
        problems.append(f"Кадри покривають речення 1–{expected - 1}, а в озвучці їх {len(texts)}")
    if problems:
        return {"ok": False, "problems": problems}
    first, count = opening(settings)
    if first and any(kind != first for kind in kinds[:count]):
        problems.append(f"Перші {count} кадр(и) за налаштуваннями каналу мають бути «{labels.get(first, first)}»")
    run = 1
    for index in range(1, len(kinds)):
        run = run + 1 if kinds[index] == kinds[index - 1] else 1
        if run > RUN_LIMIT and kinds[index] not in planner.UNLIMITED_RUN_FORMATS:
            problems.append(f"Кадри {index + 2 - run}–{index + 1}: понад {RUN_LIMIT} кадрів «{labels[kinds[index]]}» поспіль")
            run = 1
    duration = float(plan["timing"]["audio"]["duration"])
    try:
        times = planner.aligned_times([[texts[n - 1] for n in group] for group in groups], timings, duration, None)
    except ValueError as error:
        raise store.StudioError(str(error)) from None
    seconds = {key: 0.0 for key in targets}
    for kind, (start, end) in zip(kinds, times):
        seconds[kind] += end - start
    covered = sum(seconds.values()) or 1
    actual = {key: round(100 * value / covered, 1) for key, value in seconds.items()}
    for key, target in targets.items():
        if abs(actual[key] - target) > SHARE_TOLERANCE:
            problems.append(f"«{labels[key]}»: {actual[key]:.1f}% тривалості замість {target:.1f}% (допуск ±{SHARE_TOLERANCE:g})")
    result = {"ok": not problems, "problems": problems, "frames": len(groups), "shares": actual, "targets": targets}
    if problems or dry_run:
        return result
    made = []
    for number, (group, kind, idea, (start, end)) in enumerate(zip(groups, kinds, ideas, times), 1):
        frame = {"number": number, "start": round(start, 3), "end": round(end, 3), "sentences": [texts[n - 1] for n in group],
                 "sentence_timings": [dict(timings[n - 1]) for n in group], "format": kind}
        if idea:
            frame["visual"] = idea
        made.append(frame)
    new_plan = dict(plan, frames=made, frame_source=planner.DIRECTOR_FRAME_SOURCE, opening_clip_split=False,
                    settings_snapshot=settings, settings_signature=planner.settings_signature(settings), settings_scope="channel")
    new_plan.pop("director_stale", None)
    new_plan["report"] = dict(plan.get("report", {}), frames=len(made), format_seconds={key: round(value, 3) for key, value in seconds.items()})
    try:
        planner.validate_synced_plan(new_plan, duration)
    except ValueError as error:
        raise store.StudioError(str(error)) from None
    store.attach_plan(pid, new_plan)
    return result
