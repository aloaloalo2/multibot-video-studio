"""Voice at 100%: the narration of every project plays and exports at one standard level.

The user, 31 October 2026: the voice the author drops in is 100%, the slider makes it louder or quieter from there, and
100% is set automatically so that the voice never goes over the top. Voices come from different services at different
levels (HeyGen gave GORBUNOV-23 −15.1 LUFS with peaks at 0 dBFS), so the Studio measures each voice file once
(EBU R128 loudness and true peak) and plays and exports its clip with a gain that brings it to TARGET_LUFS, lowered
further if its peaks would pass PEAK_DBTP. The clip's own volume stays the author's: 100% is that level.

The voice is the recording the plan's timings were made from: an audio clip with the timed file's asset id or the same
bytes (store.plan_readiness counts the voice the same way). Music and effects keep their own levels.
"""
from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path

import store

TARGET_LUFS = -16.0   # spoken video under quiet music: clear and well below YouTube's −14 LUFS playback level
PEAK_DBTP = -1.5      # the loudest moment of the voice at 100% stays this far under full scale
CACHE = store.DATA_ROOT / "audio_levels.json"
_LOCK = threading.Lock()


def _key(path: Path) -> str:
    stat = path.stat()
    return f"{path.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}"


def measure(path: Path) -> dict | None:
    """{"lufs", "peak"} of an audio file (integrated loudness and true peak), measured once per file version."""
    path = Path(path)
    try:
        key = _key(path)
    except OSError:
        return None
    with _LOCK:
        cache = store.read_json(CACHE, {}) or {}
        if key in cache:
            return cache[key]
    log = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summary = log.rsplit("Summary:", 1)[-1]
    lufs, peak = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary), re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not lufs or not peak or "inf" in lufs.group(1):
        return None
    result = {"lufs": float(lufs.group(1)), "peak": float(peak.group(1)) if "inf" not in peak.group(1) else -99.0}
    with _LOCK:
        cache = store.read_json(CACHE, {}) or {}
        cache[key] = result
        store.atomic_json(CACHE, cache)
    return result


def gain(level: dict) -> float:
    """The linear gain that brings a voice to TARGET_LUFS without its peaks passing PEAK_DBTP."""
    db = min(TARGET_LUFS - level["lufs"], PEAK_DBTP - level["peak"])
    return round(max(0.1, min(4.0, 10 ** (db / 20))), 4)


def voice_gains(project: dict, plan: dict | None = None) -> dict:
    """{asset id: gain} for the audio clips that carry the project's timed voice; {} when the voice is unknown."""
    if plan is None:
        try:
            plan = store.load_project_plan(project["id"])
        except (store.StudioError, OSError, ValueError):
            return {}
    audio = ((plan or {}).get("timing") or {}).get("audio") or {}
    if not audio.get("asset_id") and not audio.get("sha256"):
        return {}
    result = {}
    for track in project.get("tracks", []):
        for clip in track.get("clips", []):
            aid = clip.get("asset_id")
            if clip.get("kind") != "audio" or not aid or aid in result:
                continue
            try:
                path = Path(store.resolve_asset(project, aid)["path"])
                same = aid == audio.get("asset_id") or audio.get("sha256") and store.audio_fingerprint(path) == audio["sha256"]
            except (store.StudioError, OSError):
                continue
            level = measure(path) if same else None
            if level:
                result[aid] = gain(level)
    return result
