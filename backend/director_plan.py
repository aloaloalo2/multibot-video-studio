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

import re

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
         "animation": "вільна кодова анімація: схеми, діаграми, рухомі фігури, підписи й асети; окремий формат від Razgon",
         "text": "коротка важлива теза текстом на весь кадр",
         "host": "кадр із ведучим"}


def synced_plan(pid: str) -> dict:
    plan = store.load_project_plan(pid)
    if not plan or plan.get("timing", {}).get("status") not in {"audio_synced", "script_estimate"}:
        raise store.StudioError("Спершу додайте озвучку: план кадрів робиться за нею")
    return plan


def channel_settings(project: dict) -> dict:
    """The channel's saved settings with the episode's own format shares when it has them (as plan_settings_match
    reads them), so a director's plan is held to the shares the episode asks for and is not shown as stale."""
    channel = next((c for c in store.list_channels() if c["id"] == project.get("channel_id")), None)
    if not channel:
        raise store.StudioError("Канал проєкту не знайдено", 404)
    settings = dict(channel.get("settings") or {})
    if project.get("plan_weights") is not None:
        settings["weights"] = project["plan_weights"]
        settings.pop('weights_auto', None)
    result = planner.effective_settings(settings)
    # a host frame on any channel (user, 5 November 2026): first and last frame, never two in a row, spread evenly
    if float((result.get("weights") or {}).get("host", 0) or 0) > 0 or 'host' in result.get('weights_auto', []):
        result["host_even_distribution"] = True
    return result


def shares(settings: dict) -> dict[str, float]:
    """The channel's formats with their share of the film in percent."""
    weights = {key: float(value) for key, value in settings["weights"].items() if float(value or 0) > 0}
    for key in settings.get('weights_auto', []):
        weights.setdefault(key, 0.0)
    total = sum(weights.values())
    if not total:
        raise store.StudioError("У налаштуваннях каналу немає жодного формату з часткою")
    return {key: round(100 * value / total, 1) for key, value in weights.items()}


OPENING_FRAMES = 3
CONTINUES = re.compile(r"(?i)^\s*(та сама|той самий|те саме|ті самі|та ж|той же|те ж|продовж|далі та сама|та же|тот же|то же|те же|продолж)")


def _video(settings: dict, chosen: str) -> str:
    if chosen != "video":
        return chosen
    weights = settings["weights"]
    return max(("stock_video", "generated_video"), key=lambda key: (float(weights.get(key, 0)), key == "stock_video"))


def opening(settings: dict) -> list:
    """The format each of the film's first frames must have, in order; None leaves that frame to the director.
    «Початок ролика» names up to three frames (user, 25 November 2026: «перший кадр, там анімація, другий кадр, там
    такий-то»); a channel that names none keeps its older single format and count. A host channel opens with the host
    unless the sequence names the first frame itself."""
    sequence = settings.get("opening_sequence")
    if isinstance(sequence, list) and any(item != "auto" for item in sequence):
        result = [None if item == "auto" else _video(settings, item) for item in sequence[:OPENING_FRAMES]]
    else:
        chosen = _video(settings, settings.get("first_clip_format", "auto"))
        result = [] if chosen == "auto" else [chosen] * int(settings.get("first_clip_count", 1))
    if settings.get("host_even_distribution") and not (result and result[0]):
        result = ["host"] + result[1:]
    while result and result[-1] is None:
        result.pop()
    return result


def voice(plan: dict) -> tuple[list[str], list[dict]]:
    return ([text for frame in plan["frames"] for text in frame["sentences"]],
            [item for frame in plan["frames"] for item in frame["sentence_timings"]])


def sentences(pid: str) -> dict:
    """What the director needs: the voice's sentences with their times and the channel's formats."""
    project = store.load_project(pid)
    plan, settings = synced_plan(pid), channel_settings(project)
    texts, timings = voice(plan)
    rules = opening(settings)
    targets = shares(settings)
    return {"sentences": [{"number": number, "text": text, "start": timing["start"], "end": timing["end"]}
                          for number, (text, timing) in enumerate(zip(texts, timings), 1)],
            "duration": float(plan["timing"]["audio"]["duration"]), "shares": targets,
            # times estimated from the script while the voice is made; Whisper's times replace them, frames stay
            "estimated": plan["timing"].get("status") == "script_estimate",
            "labels": {key: planner.LABELS.get(key, key) for key in targets}, "hints": {key: HINTS.get(key, "") for key in targets},
            "generated_image_style": settings.get("generated_image_style", ""),
            "tolerance": SHARE_TOLERANCE,
            "auto_formats": settings.get('weights_auto', []),
            "opening": [{"number": number, "format": kind} for number, kind in enumerate(rules, 1) if kind] or None,
            "host_rules": {"first_frame": bool(rules) and rules[0] == "host", "last_frame": True, "no_consecutive": True,
                           "even_distribution": True} if settings.get("host_even_distribution") else None}


def apply(pid: str, frames, dry_run: bool = False) -> dict:
    """Check the director's frames and, unless dry_run, save them as the plan. Returns {"ok", "problems", "shares", ...}."""
    project = store.load_project(pid)
    plan, settings = synced_plan(pid), channel_settings(project)
    texts, timings = voice(plan)
    # no limit of sentences a frame (user, 21 November 2026: «це обмеження ми прибираємо взагалі»): a limit cut one
    # continuous scene of the Jupiter film into two frames that jumped against each other
    targets = shares(settings)
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
    # one continuous scene is one frame (user, 25 November 2026: «та сама сцена, але розбита на 4 кадри»): an idea that
    # says it goes on from the frame before, in the same format, belongs to that frame
    for index in range(1, len(kinds)):
        if kinds[index] == kinds[index - 1] and CONTINUES.match(ideas[index] or ""):
            problems.append(f"Кадр {index + 1} продовжує сцену кадру {index} («{ideas[index][:60]}…»): безперервна сцена має бути одним "
                            f"кадром, об'єднай їхні речення в один кадр")
    for number, (wanted, kind) in enumerate(zip(opening(settings), kinds), 1):
        if wanted and kind != wanted:
            problems.append(f"Кадр {number} за початком ролика в налаштуваннях каналу має бути «{labels.get(wanted, wanted)}»")
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
    if settings.get("host_even_distribution") and "host" in targets:
        hosts = [i for i, kind in enumerate(kinds) if kind == "host"]
        if any(b == a + 1 for a, b in zip(hosts, hosts[1:])):
            problems.append("Ведучий не може бути у двох кадрах поспіль")
        if kinds and kinds[-1] != "host":
            problems.append("Останній кадр ролику має бути з ведучим")
        if hosts:
            starts = [times[i][0] for i in hosts]
            ideal = duration / len(hosts)
            gaps = [b - a for a, b in zip(starts, starts[1:] + [duration])]
            if max(gaps) > ideal * 2:
                problems.append("Розподіліть ведучого рівномірно по всьому ролику: завелика перерва між появами")
    covered = sum(seconds.values()) or 1
    actual = {key: round(100 * value / covered, 1) for key, value in seconds.items()}
    for key, target in targets.items():
        if key not in settings.get('weights_auto', []) and abs(actual[key] - target) > SHARE_TOLERANCE:
            problems.append(f"«{labels[key]}»: {actual[key]:.1f}% тривалості замість {target:.1f}% (допуск ±{SHARE_TOLERANCE:g})")
    result = {"ok": not problems, "problems": problems, "frames": len(groups), "shares": actual, "targets": targets,
              "auto_formats": settings.get('weights_auto', [])}
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
                    settings_snapshot=settings, settings_signature=planner.settings_signature(settings),
                    settings_scope="project" if project.get("plan_weights") is not None else "channel")
    new_plan.pop("director_stale", None)
    new_plan["report"] = dict(plan.get("report", {}), frames=len(made), format_seconds={key: round(value, 3) for key, value in seconds.items()})
    try:
        planner.validate_synced_plan(new_plan, duration)
    except ValueError as error:
        raise store.StudioError(str(error)) from None
    store.attach_plan(pid, new_plan)
    return result
