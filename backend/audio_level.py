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

import hashlib
import re
import subprocess
import threading
from pathlib import Path

import store

TARGET_LUFS = -16.0   # spoken video under quiet music: clear and well below YouTube's −14 LUFS playback level
PEAK_DBTP = -1.5      # the loudest moment of the voice at 100% stays this far under full scale
# The sound standard of every episode (user, 5 November 2026: «one script that sets everything the same from episode to
# episode … calm, not loud, and the music is heard»). The original voice and every translation play at TARGET_LUFS; the
# music and effects under them are set against the voice at that level, not against the file the service delivered
# (episode 08: HeyGen gave −26.6 LUFS, so the bed made against it came out at −48.8 LUFS and was lost under the
# voice the Studio had brought up by 10.6 dB). MUSIC_DB is the music's loudness against the voice (it is ducked a
# further 9 dB while the narrator speaks), SFX_DB the effects' level against it: the levels agreed for What If 06.
MUSIC_DB = -13.0
SFX_DB = -6.0
LEVELED: Path | None = None   # where leveled voice copies go; None: store.DATA_ROOT / "leveled" (read when used, so a
                              # test that moves DATA_ROOT keeps its copies out of the real data)


def leveled_dir() -> Path:
    return LEVELED or store.DATA_ROOT / "leveled"
CACHE = store.DATA_ROOT / "audio_levels.json"
_LOCK = threading.Lock()
_MEASURING: dict[str, threading.Lock] = {}   # a lock per file being measured now
_FAILED: set[str] = set()                    # file versions ffmpeg could not measure, until the next start


_READ: tuple = (None, None, {})   # (cache file, its stat, its measures): read again only when the file changed


def _levels() -> dict:
    """The measures on disk (call under _LOCK). The file holds every voice and sound the studio measured (1 235 of them,
    244 KB); every measure() parsed it whole, about 5 ms a call and several calls a request (25 November 2026)."""
    global _READ
    try:
        stat = CACHE.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        stamp = None
    if _READ[0] != CACHE or _READ[1] != stamp or stamp is None:
        _READ = (CACHE, stamp, store.read_json(CACHE, {}) or {})
    return _READ[2]


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
        cache = _levels()
        if key in cache:
            return cache[key]
        if key in _FAILED:
            return None
        gate = _MEASURING.setdefault(key, threading.Lock())
    # one measure a file at a time: a second request waits for the first one's answer instead of decoding it again
    with gate:
        with _LOCK:
            cache = _levels()
            if key in cache or key in _FAILED:
                return cache.get(key)
        try:
            log = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                                 capture_output=True, text=True, timeout=600).stderr
        except (OSError, subprocess.TimeoutExpired):
            log = ""
        summary = log.rsplit("Summary:", 1)[-1]
        lufs, peak = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary), re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
        if not lufs or not peak or "inf" in lufs.group(1):
            with _LOCK:
                _FAILED.add(key)   # a file that cannot be measured is not decoded again on every read of the project
                _MEASURING.pop(key, None)
            return None
        return _store(key, lufs, peak)


def _store(key, lufs, peak) -> dict:
    result = {"lufs": float(lufs.group(1)), "peak": float(peak.group(1)) if "inf" not in peak.group(1) else -99.0}
    with _LOCK:
        cache = dict(_levels())
        cache[key] = result
        store.atomic_json(CACHE, cache)
        _MEASURING.pop(key, None)
    return result


def gain(level: dict) -> float:
    """The linear gain that brings a voice to TARGET_LUFS without its peaks passing PEAK_DBTP."""
    db = min(TARGET_LUFS - level["lufs"], PEAK_DBTP - level["peak"])
    return round(max(0.1, min(4.0, 10 ** (db / 20))), 4)


def standard_db(level: dict) -> float:
    """The gain in dB that brings a voice to TARGET_LUFS; its peaks are held by the limiter of leveled()."""
    return max(-20.0, min(20.0, TARGET_LUFS - level["lufs"]))


_VOICE_PATHS: dict = {}


def _narration_key(project: dict):
    """What _voice_paths reads, by version: the project's revision and the plan and source-timing files."""
    try:
        plan = store.project_plan_file(project)
        plan_key = store.plan_file_key(plan) if plan else None
    except (store.StudioError, OSError):
        return None
    try:
        source = store.project_dir(project["id"]) / "source-timing.json"
        source_key = store.plan_file_key(source) if source.is_file() else None
    except (store.StudioError, OSError, KeyError):
        return None
    return (project.get("id"), project.get("revision"), plan_key, source_key)


def _voice_paths(project: dict, plan: dict | None = None) -> dict:
    """{asset id: path} of the audio clips that carry the project's timed voice; {} when the voice is unknown. Kept per
    version of the project and its plan: every sound file the player asks for passed here, 0.15–0.6 s each, and an
    episode with 150 effects queued its music and sounds for seconds (user, 25 November 2026: «музика пропадає… дуже
    довго підгружається»)."""
    if plan is None:
        key = _narration_key(project)
        hit = _VOICE_PATHS.get(project.get("id")) if key else None
        if hit and hit[0] == key:
            return dict(hit[1])
        result = _voice_paths_read(project)
        if key:
            _VOICE_PATHS[project.get("id")] = (key, result)
        return dict(result)
    return _voice_paths_read(project, plan)


def _voice_paths_read(project: dict, plan: dict | None = None) -> dict:
    if plan is None:
        try:
            plan = store.load_project_narration(project["id"])
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
            if same:
                result[aid] = path
    return result


def voice_gains(project: dict, plan: dict | None = None) -> dict:
    """{asset id: gain} for the audio clips that carry the project's timed voice; {} when the voice is unknown. A voice
    whose leveled copy is made plays that copy (voice_file) at gain 1; until then the old gain, capped by its peaks."""
    return voice_state(project, plan)[0]


def voice_state(project: dict, plan: dict | None = None) -> tuple[dict, dict]:
    """({asset id: gain}, {asset id: file token}) decided together. The token names the very file the gain belongs to
    («l<key>» the leveled copy, «o<key>» the recording itself) and goes into the player's address, so one address
    always serves the same bytes: the copy used to appear (or be tidied away) behind an unchanged address while a
    player was reading it, and a seek then read the other file and the voice went silent (user, 25 November 2026:
    «коли перемотую… нажимаю плей, звука нема»)."""
    gains, tokens = {}, {}
    for aid, path in _voice_paths(project, plan).items():
        level = measure(path)
        if not level:
            continue
        key = hashlib.sha1(_key(path).encode()).hexdigest()[:20]
        copy = not _at_standard(level) and leveled(path, wait=False, level=level) != path
        gains[aid] = 1.0 if copy or _at_standard(level) else gain(level)
        tokens[aid] = ("l" if copy else "o") + key
    return gains, tokens


def token_file(path: Path, token: str) -> Path:
    """The file a token from voice_state names: the recording for «o…», the leveled copy for «l…» (made now when it
    was tidied away meanwhile, so the address keeps its bytes); a token of an older version of the file plays the file."""
    if token.startswith("l"):
        return leveled(path, wait=True)
    return path


def voice_file(project: dict, aid: str, path: Path, wait: bool = False) -> Path:
    """The file a player or the export plays for this asset: the voice's leveled copy when it carries the timed voice
    (made now with wait=True, as the export does; else started in the background), any other file as it is."""
    # Image/animation requests must not reload the narration and compare audio
    # fingerprints. A long live montage can request dozens of these per second.
    if not any(clip.get('kind') == 'audio' and clip.get('asset_id') == aid
               for track in project.get('tracks', []) for clip in track.get('clips', [])):
        return path
    return leveled(path, wait=wait) if aid in _voice_paths(project) else path


def _at_standard(level: dict) -> bool:
    return abs(level["lufs"] - TARGET_LUFS) < 0.5 and level["peak"] <= PEAK_DBTP + 0.3


_BUILDING: set[str] = set()


def leveled(path: Path, wait: bool = True, level: dict | None = None) -> Path:
    """The voice file at the standard level: brought to TARGET_LUFS by a plain gain, its peaks held under PEAK_DBTP by a
    limiter (no levelling of its own). A quiet HeyGen voice (08: −26.6 LUFS, peaks −5.1 dB) could reach only −23 LUFS with
    a gain capped by its peaks, while its translations stood at −16, so the original sounded quieter (user, 5 November
    2026). FLAC keeps every sample in place (timings stay exact); made once per file version, in about 30 s of CPU. With
    wait=False the copy is started in the background and the file itself is returned until it is there. A file already
    at the standard, or one that cannot be measured, is returned as it is (level: its measure, when already read)."""
    level = level or measure(path)
    if not level or _at_standard(level):
        return path
    key = hashlib.sha1(_key(path).encode()).hexdigest()[:20]
    out = leveled_dir() / (key + ".flac")
    if out.is_file():
        return out
    if not wait:
        with _LOCK:
            if key in _BUILDING:
                return path
            _BUILDING.add(key)
        try:
            threading.Thread(target=_build, args=(path, out, level, key), daemon=True).start()
        except Exception:
            with _LOCK:
                _BUILDING.discard(key)
            return path
        return path
    _build(path, out, level, key)
    return out if out.is_file() else path


def _build(path: Path, out: Path, level: dict, key: str) -> None:
    lock = _MEASURING.setdefault("leveled:" + key, threading.Lock())
    with lock:
        try:
            if out.is_file():
                return
            out.parent.mkdir(parents=True, exist_ok=True)
            part = out.with_name(out.stem + ".part.flac")
            limit = 10 ** ((PEAK_DBTP - 1.0) / 20)   # a dB of room for the true peak between samples
            db = standard_db(level)
            for _ in range(4):   # the limiter takes some loudness off the peaks: give it back (08 needed +0.6 dB once)
                subprocess.run(["nice", "-n", "10", "ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(path), "-vn", "-af",
                                f"volume={db:.2f}dB,alimiter=limit={limit:.4f}:attack=5:release=50:level=false",
                                # 16 bits are plenty for a voice at −16 LUFS and half the size of 24 (700 MB a film before)
                                "-c:a", "flac", "-sample_fmt", "s16", "-compression_level", "8", str(part)], check=True, timeout=1800)
                got = measure(part)
                short = TARGET_LUFS - got["lufs"] if got else 0.0
                if short < 0.4 or db >= 20:
                    break
                db = min(20.0, db + short)
            part.replace(out)
            # which voice the copy is of, by path and size: the tidy keeps it while that voice is in a project, even after
            # its file time changed (a time rounded by a copy once made every copy look unused, and 37 went; 25 November 2026)
            try:
                store.atomic_json(out.with_suffix(".json"), {"source": str(Path(path).resolve()), "size": Path(path).stat().st_size})
            except OSError:
                pass
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            with _LOCK:
                _BUILDING.discard(key)
