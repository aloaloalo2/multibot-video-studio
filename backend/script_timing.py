"""The director starts from the script while the voice is still being made.

User, 16 November 2026: «план кадрів ж можна зробити зі сценарію… А потім, коли ми отримаємо від віспера… час, тоді
ми вже можемо план кадрів зробити точніший… Ну, я дозволяю так робити», and «якщо є сценарій, то робимо так. Якщо
сценарія нема, лише озвучка є… тоді по черзі… не тільки для анімаційних проєктів, а й для всіх проєктів».

When a narration starts on a channel that hands the voice on to the montage by itself (auto_montage), the Studio
estimates when every sentence and word of the script will sound (the channel's measured pace from its earlier voiced
episodes, else its words per minute) and attaches a plan with timing status ESTIMATE. The director (backend/director.py)
groups those sentences into frames as usual. Nothing that needs the real voice runs on it: production, montage and export
still ask for «audio_synced». Once Whisper has timed the real voice, the plan is rebuilt from it and keeps the director's
groups of sentences (planner.keep_director_frames); an animated film's shots, sound cues and music are recompiled onto the
real times without a new run of the director (tools/direction.py retime). If the voice says other sentences than the
script, the plan is marked director_stale and the director runs again, as before.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata

import planner
import store

ESTIMATE = "script_estimate"
GAP = 0.06            # share of a sentence's span left as a pause before the next one
HISTORY = 8           # the channel's latest voiced episodes that set its pace
LOCK = threading.Lock()
_THREAD = threading.Thread   # its own reference: the director's start stays apart from the narration's worker


def letters(text: str) -> int:
    return sum(ch.isalpha() for ch in text)


def estimated(plan: dict | None) -> bool:
    return bool(plan) and (plan.get("timing") or {}).get("status") == ESTIMATE


def channel_pace(project: dict, settings: dict) -> float:
    """Seconds of voice per letter of the script, from the channel's latest voiced episodes (pauses included)."""
    seconds = count = 0.0
    used = 0
    found = []
    for path in (store.DATA_ROOT / "projects").glob("*/project.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if item.get("channel_id") == project.get("channel_id") and item.get("id") != project.get("id") and not item.get("deleted_at"):
            found.append(item)
    for item in sorted(found, key=lambda p: p.get("plan_updated_at") or 0, reverse=True):
        if used >= HISTORY:
            break
        try:
            plan = store.load_project_plan(item["id"])
        except (store.StudioError, OSError, ValueError, TypeError, KeyError):
            continue
        timing = (plan or {}).get("timing") or {}
        duration = (timing.get("audio") or {}).get("duration")
        text = (plan or {}).get("spoken_script") or (plan or {}).get("script") or ""
        if timing.get("status") != "audio_synced" or not duration or letters(text) < 200:
            continue
        seconds += float(duration)
        count += letters(text)
        used += 1
    if count >= 200:
        return seconds / count
    words_per_minute = float(planner.effective_settings(settings).get("words_per_minute") or 150)
    return 60 / words_per_minute / 5.5   # about 5.5 letters a word


def estimate(script: str, pace: float) -> dict:
    """Sentences and words of the script laid on a clock at the channel's pace."""
    sentences = planner.split_sentences(script)
    if not sentences:
        raise store.StudioError("У сценарії немає речень")
    rows, words, clock = [], [], 0.0
    for text in sentences:
        span = max(letters(text), 1) * pace
        start, end = clock, clock + span * (1 - GAP)
        rows.append({"text": text, "start": round(start, 3), "end": round(end, 3)})
        tokens = [t for t in re.split(r"\s+", text.strip()) if t]
        weights = [max(letters(t), 1) for t in tokens]
        total, at = sum(weights) or 1, start
        for token, weight in zip(tokens, weights):
            step = (end - start) * weight / total
            words.append({"text": token, "start": round(at, 3), "end": round(at + step, 3)})
            at += step
        clock += span
    return {"duration": round(clock, 3), "sentences": rows, "words": words}


def build(project: dict, script: str) -> dict:
    """An estimated plan of the script with the channel's settings and the episode's own format shares."""
    channel = store.get_channel_folder(project["channel_id"], include_disabled=True)
    settings = store.validate_settings(store.read_channel_settings(channel, {}))
    if project.get("plan_weights") is not None:
        settings = store.validate_settings({**settings, "weights": project["plan_weights"]})
    timed = estimate(script, channel_pace(project, settings))
    try:
        plan = planner.build_plan(script, settings, unicodedata.normalize("NFC", channel.name), timed["duration"], None, timed["sentences"])
    except (ValueError, TypeError) as error:
        raise store.StudioError(str(error)) from None
    plan["timing"].update(status=ESTIMATE, basis=ESTIMATE, words=timed["words"],
                          audio={"duration": timed["duration"], "estimated": True})
    plan["spoken_script"] = script
    plan["spoken_script_sha256"] = hashlib.sha256(script.encode("utf-8")).hexdigest()
    plan.update(settings_scope="project" if project.get("plan_weights") is not None else "channel",
                channel_id=project["channel_id"], generated_at=time.time())
    return plan


def wanted(project: dict) -> str | None:
    """The script to direct before the voice, or None when this episode goes the usual way."""
    if store.project_plan_mode(project) == "direct" or not project.get("episode_path"):
        return None
    channel = store.get_channel_folder(project["channel_id"], include_disabled=True)
    if (store.read_channel_settings(channel, {}) or {}).get("auto_montage") is not True:
        return None   # the director runs only when the voice would hand the episode on to it anyway
    script = str((project.get("voice_script") or {}).get("text") or "").strip()
    if not script:
        return None   # a voice without a script: recognition first, then the director (user: «тоді по черзі»)
    plan = store.load_project_plan(project["id"])
    timing = (plan or {}).get("timing") or {}
    if timing.get("status") == "audio_synced":
        return None   # the voice is already timed: the usual way is as quick
    if plan and plan.get("frame_source") == planner.DIRECTOR_FRAME_SOURCE and plan.get("script") == script:
        return None   # this script is directed already
    return script


def start_soon(pid: str) -> None:
    _THREAD(target=start, args=(pid,), daemon=True).start()


def start(pid: str) -> bool:
    """Called when a narration starts: attach the estimated plan and start the director on it. Never raises."""
    try:
        import director
        import episode_pause
        import production
        if episode_pause.paused(pid):
            return False
        with LOCK:
            project = store.load_project(pid)
            script = wanted(project)
            if script is None or pid in director.ACTIVE or pid in production.ACTIVE:
                return False
            store.attach_plan(pid, build(project, script))
        director.start(pid, "script")
        return True
    except Exception:
        import traceback
        traceback.print_exc()
        return False
