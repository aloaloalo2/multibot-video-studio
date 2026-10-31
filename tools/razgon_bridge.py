#!/usr/bin/env python3
"""Bridge between VideoKey Studio plans and Razgon 2D Studio renders.

The Studio owns the episode: script, plan, voiceover timings and the timeline.
Razgon owns the drawing. Razgon renders every picture from the global time of the
video, so its shots, camera moves and transitions run freely across Studio frame
boundaries: each Studio frame is just the [start, end) slice of that one continuous
film, and consecutive clips meet frame-exact. A changed shot re-renders every
Studio frame it passes through (push --shots).

  python3 "VideoKey Studio/tools/razgon_bridge.py" prepare --project-id <studio id>
  python3 "VideoKey Studio/tools/razgon_bridge.py" plan    --razgon "What If/razgon-2d-studio/projects/<slug>" [--dry-run]
  python3 "VideoKey Studio/tools/razgon_bridge.py" check   --razgon "What If/razgon-2d-studio/projects/<slug>"
  python3 "VideoKey Studio/tools/razgon_bridge.py" slots   --razgon "What If/razgon-2d-studio/projects/<slug>" [--frames 3,7]
  python3 "VideoKey Studio/tools/razgon_bridge.py" push    --razgon "What If/razgon-2d-studio/projects/<slug>" [--frames 3,7 | --shots e03s02] [--no-render]
  python3 "VideoKey Studio/tools/razgon_bridge.py" overlay --razgon "What If/razgon-2d-studio/projects/<slug>"
  python3 "VideoKey Studio/tools/razgon_bridge.py" export  --razgon "What If/razgon-2d-studio/projects/<slug>" --spec <studio job.json> --out <file.mp4>
"""
from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import fcntl
import functools
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

YOUTUBE = Path(__file__).resolve().parents[2]
DEFAULT_STUDIO = YOUTUBE / "What If" / "razgon-2d-studio"
STUDIO_BACKEND = Path(__file__).resolve().parents[1] / "backend"
FRAME_TITLE = "Razgon · кадр {:03d}"
BED_TITLE = "Razgon · музика й ефекти"
OVERLAY_TITLE = "Плашка каналу"
RESOLUTIONS = {720: "720p", 1080: "1080p", 1440: "1440p", 2160: "2160p"}
JOBS = max(1, min(8, (os.cpu_count() or 2) // 2))   # at most this many Studio frames render at the same time (render_many)
CHROMIUM_BYTES = 2.2e9   # one render.mjs worker drawing 1920x1080 (06 Fast Food, 31 October 2026)
RAM_LIMIT = float(os.environ.get("RAZGON_RAM_LIMIT", 0.8))   # renders fill the Mac's memory up to this share (user, 31 October 2026)
RAMP = 15.0              # seconds a new Chromium takes to reach its full memory


class BridgeError(Exception):
    pass


# ---------------------------------------------------------------- Studio API
class Studio:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def call(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            with contextlib.suppress(ValueError):
                detail = json.loads(detail).get("error", detail)
            raise BridgeError(f"Студія відповіла {error.code} на {method} {path}: {detail}") from None
        except urllib.error.URLError as error:
            raise BridgeError(f"Студія недоступна за адресою {self.url}: {error.reason}") from None

    def project(self, pid: str) -> dict:
        result = self.call("GET", f"/api/projects/{pid}")
        return result.get("project", result)

    def plan(self, pid: str) -> dict:
        result = self.call("GET", f"/api/projects/{pid}/plan")
        plan = result.get("plan")
        if not plan:
            raise BridgeError("У проєкті немає плану")
        return plan

    def batch(self, project: dict, actions: list[dict]) -> dict:
        if not actions:
            return project
        result = self.call("POST", f"/api/projects/{project['id']}/actions",
                           {"type": "batch", "payload": {"actions": actions}, "expected_revision": project.get("revision")})
        return result["project"]

    def import_file(self, pid: str, path: Path) -> dict:
        return self.call("POST", f"/api/projects/{pid}/assets/pick", {"path": str(path)})["asset"]


# ---------------------------------------------------------------- helpers
def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "episode"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def frame_index(seconds: float, fps: int) -> int:
    return int(round(seconds * fps))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def voice_asset(project: dict, audio: dict, analysis: dict | None = None) -> dict:
    """The narration the plan was timed against: by id, by the speech report, or by its fingerprint."""
    assets = [item for item in project.get("assets", []) if item.get("kind") == "audio"]
    for wanted in (audio.get("asset_id"), (analysis or {}).get("audio", {}).get("asset_id")):
        found = next((item for item in assets if wanted and item.get("id") == wanted), None)
        if found and (not audio.get("sha256") or sha256(Path(found["path"])) == audio["sha256"]):
            return found
    if audio.get("sha256"):
        for item in assets:
            path = Path(item["path"])
            if path.is_file() and sha256(path) == audio["sha256"]:
                return item
    raise BridgeError("Не знайшов у проєкті студії файл озвучки, за яким зроблено таймінги плану")


def all_clips(project: dict):
    for track in project.get("tracks", []):
        for clip in track.get("clips", []):
            yield track, clip


# ---------------------------------------------------------------- prepare
def prepare(args) -> None:
    studio = Studio(args.studio_url)
    project = studio.project(args.project_id)
    plan = studio.plan(args.project_id)
    timing = plan.get("timing", {})
    if timing.get("status") != "audio_synced":
        raise BridgeError("План ще чернетка. Спершу додайте озвучку в студії, щоб з'явився статус «За озвучкою»")
    audio = timing.get("audio") or {}
    duration = float(audio["duration"])
    other = sorted({frame["format"] for frame in plan["frames"] if frame["format"] != "razgon_2d"})
    if other:
        print("Увага: у плані є кадри інших форматів (" + ", ".join(other) + "). Razgon намалює всі кадри.")

    analysis = studio.call("GET", f"/api/projects/{args.project_id}/analysis").get("report") or {}
    voice_record = voice_asset(project, audio, analysis)
    voice = Path(voice_record["path"])
    # Script words with the recogniser's time; raw ASR words only for older reports without them.
    words = analysis.get("aligned_words") or analysis.get("words") or []
    word_source = "script" if analysis.get("aligned_words") else "asr"
    if analysis.get("audio", {}).get("sha256") not in {None, audio.get("sha256")} and audio.get("sha256"):
        words = []

    root = Path(args.studio_dir).resolve()
    if not (root / "render.mjs").is_file():
        raise BridgeError(f"Razgon 2D Studio не встановлено в {root}")
    slug = args.slug or slugify(Path(project["episode_path"]).name)
    target = root / "projects" / slug
    for name in ("input", "timeline", "story", "scenes/sets", "scenes/shots", "build", "out"):
        (target / name).mkdir(parents=True, exist_ok=True)
    voice_dst = target / "input" / ("voiceover" + voice.suffix.lower())
    shutil.copy2(voice, voice_dst)
    (target / "input" / "script.txt").write_text(plan.get("spoken_script") or plan["script"], encoding="utf-8")

    fps = int(project.get("fps") or 30)
    height = int(project.get("height") or 1080)
    width = int(project.get("width") or 1920)
    config_path = target / "config.json"
    # A new film takes the channel's look from the Studio channel settings: style, text style and logo.
    channel = next((c for c in studio.call("GET", "/api/channels").get("channels", []) if c["id"] == project.get("channel_id")), {})
    animation = (channel.get("settings") or {}).get("animation") or {}
    fresh = not config_path.is_file()
    # No letterbox bars: with "bars": None the engine falls back to wide bars on 16:9, and the channel wants the full frame.
    config = read_json(config_path) if not fresh else {
        "title": project["name"], "style": args.style or animation.get("style") or "dusk", "captions": False, "bars": "none",
        "fadeIn": 0.5, "fadeOut": 0.8, "music": {"enabled": True, "gainDb": -17},
        "sfx": {"enabled": True, "gainDb": -6}, "loudness": -14}
    if fresh:
        if animation.get("title_font"):
            config["fonts"] = {"title": animation["title_font"]}
        if animation.get("accent"):
            config["ui"] = {"accent": animation["accent"]}
        # Whether the film uses picture props (library and generated) or draws everything with shapes.
        config["assets"] = animation.get("assets", True) is not False
        # A style the channel copied from a picture is not in engine/styles.js: its whole definition goes into the config.
        if str(config["style"]).startswith("custom-") and channel:
            own = next((s for s in studio.call("GET", f"/api/channels/{channel['id']}/custom-styles").get("styles", []) if s["id"] == config["style"]), None)
            if own:
                config["styleDef"] = own["def"]
            else:
                config["style"] = "dusk"
        # The user chose the style once in the channel settings, so a film that keeps it needs no separate approval.
        if not args.style and animation.get("style") and config["style"] == animation["style"]:
            config["style_approved"] = True
    config.update({"aspect": "9:16" if height > width else "16:9", "resolution": RESOLUTIONS.get(min(width, height), "1080p"),
                   "fps": fps, "voiceover": "input/" + voice_dst.name, "script": "input/script.txt", "duration": round(duration, 3)})
    if not config.get("overlay") and channel:
        logo = target / "input" / "channel_logo.png"
        frame_w, frame_h = (width, height)
        try:
            request = urllib.request.Request(f"{studio.url}/api/channels/{channel['id']}/logo-overlay.png?w={frame_w}&h={frame_h}")
            with urllib.request.urlopen(request, timeout=60) as response:
                logo.write_bytes(response.read())
            config["overlay"] = "input/channel_logo.png"
        except urllib.error.HTTPError:
            pass   # no logo, or switched off for this channel
    write_json(config_path, config)

    sentences = [{"i": i, "start": item["start"], "end": item["end"], "text": item["text"]} for i, item in enumerate(timing["sentences"])]
    write_json(target / "timeline" / "sentences.json", sentences)
    if words:
        write_json(target / "timeline" / "words.json", {"source": "multibot-video-studio", "text": word_source,
                                                         "words": [{"word": w["text"], "start": w["start"], "end": w["end"]} for w in words]})
        (target / "timeline" / "transcript.txt").write_text("\n".join(f"[{s['start']:.2f} -> {s['end']:.2f}] {s['text']}" for s in sentences), encoding="utf-8")
    frames = [{"number": f["number"], "start": f["start"], "end": f["end"], "sentences": f["sentences"], "format": f["format"]} for f in plan["frames"]]
    link = {"studio_url": studio.url, "project_id": project["id"], "episode_path": project["episode_path"], "voice_asset_id": voice_record["id"],
            "script_sha256": plan["script_sha256"], "audio_sha256": audio.get("sha256"), "duration": duration, "fps": fps, "frames": frames}
    write_json(target / "story" / "studio_frames.json", link)
    # tells the Studio where the Razgon project of this episode lives (for its live preview tab)
    write_json(Path(project["episode_path"]) / "razgon.json", {"razgon_root": str(root), "project": str(target)})

    shots_path = target / "story" / "shots.json"
    if not shots_path.is_file():
        shots = [{"id": f"f{f['number']:03d}s01", "start": f["start"], "end": f["end"], "line": " ".join(f["sentences"]),
                  "scene": "", "set": "", "bars": None, "in": {"type": "cut"}, "sfx": [], "amb": None, "notes": "studio frame %d" % f["number"]}
                 for f in frames]
        write_json(shots_path, {"title": project["name"], "duration": duration, "shots": shots, "music": [], "sfx": []})
    print(f"Проєкт Razgon: {target}")
    print(f"Кадрів плану: {len(frames)}, озвучка {duration:.2f} с, {fps} fps, {config['resolution']} {config['aspect']}")
    print("Таймінги слів: " + ("зі студії, Whisper повторно не потрібен" if words else "немає. Запустіть tools/transcribe.py у Razgon"))


# ---------------------------------------------------------------- check
def load_link(razgon: Path) -> tuple[dict, dict, dict]:
    link = read_json(razgon / "story" / "studio_frames.json")
    shots = read_json(razgon / "story" / "shots.json")
    config = read_json(razgon / "config.json")
    return link, shots, config


def check_project(razgon: Path) -> list[str]:
    link, story, config = load_link(razgon)
    fps = int(config["fps"])
    problems = []
    if int(link["fps"]) != fps:
        problems.append(f"fps Razgon ({fps}) не збігається з fps студії ({link['fps']})")
    shots = story["shots"]
    duration = float(link["duration"])
    if abs(float(story.get("duration", 0)) - duration) > 1 / fps:
        problems.append(f"Тривалість shots.json {story.get('duration')} не дорівнює озвучці {duration}")
    if shots and abs(shots[0]["start"]) > 1e-3:
        problems.append("Перший шот має починатися з 0")
    if shots and abs(shots[-1]["end"] - duration) > 1 / fps:
        problems.append("Останній шот має закінчуватися разом з озвучкою")
    for a, b in zip(shots, shots[1:]):
        if abs(a["end"] - b["start"]) > 1e-3:
            problems.append(f"Розрив або перекриття між {a['id']} і {b['id']}")
    return problems


def frames_of_shots(link: dict, story: dict, ids: list[str]) -> set[int]:
    """Studio frames that show any part of these shots, including a transition into the next shot."""
    shots = {shot["id"]: shot for shot in story["shots"]}
    missing = [item for item in ids if item not in shots]
    if missing:
        raise BridgeError("Немає таких шотів: " + ", ".join(missing))
    order = [shot["id"] for shot in story["shots"]]
    result = set()
    for item in ids:
        shot = shots[item]
        end = shot["end"]
        following = order.index(item) + 1
        if following < len(order):
            nxt = shots[order[following]]
            end = max(end, nxt["start"] + float((nxt.get("in") or {}).get("dur", 0.6) or 0))
        result |= {f["number"] for f in link["frames"] if f["start"] < end and f["end"] > shot["start"]}
    return result


def check(args) -> None:
    problems = check_project(Path(args.razgon).resolve())
    if problems:
        raise BridgeError("Проєкт Razgon не готовий:\n- " + "\n- ".join(problems))
    print("Шоти суцільні й покривають усю озвучку.")


# ---------------------------------------------------------------- push
def video_frame_count(path: Path) -> int:
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets",
                             "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return int(result.stdout.strip().strip(",") or 0)


@contextlib.contextmanager
def project_lock(razgon: Path):
    """One render or assembly of a Razgon project at a time: push, final and the Studio export write the same build files."""
    path = razgon / "build" / "studio" / ".bridge.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BridgeError("Цей проєкт Razgon уже рендерить або збирає інший процес (push, final чи експорт студії)") from None
        yield


def frame_clip(razgon: Path, number: int) -> Path:
    return razgon / "build" / "studio" / f"frame_{number:03d}.mp4"


def picture_fingerprint(razgon: Path) -> str:
    """Everything the picture of a frame is drawn from: the project's config, story, word timings, scenes and assets, and
    the Razgon engine. Sound-only settings (music, SFX, ambience, loudness, overlay) are left out."""
    root = razgon.parents[1]
    config = {k: v for k, v in read_json(razgon / "config.json").items() if k not in {"music", "sfx", "loudness", "voiceover", "script", "overlay"}}
    story = read_json(razgon / "story" / "shots.json")
    story = dict(story, music=None, sfx=None, shots=[{k: v for k, v in shot.items() if k not in {"sfx", "amb"}} for shot in story["shots"]])
    digest = hashlib.sha256(json.dumps([config, story], sort_keys=True, ensure_ascii=False).encode())
    for base in (razgon / "scenes", razgon / "assets", razgon / "timeline" / "words.json", root / "engine", root / "player.html", root / "render.mjs"):
        for path in sorted(base.rglob("*")) if base.is_dir() else [base]:
            if path.is_file():
                stat = path.stat()
                digest.update(f"{path}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()


def frame_stamp(fps: int, frame: dict, picture: str) -> dict:
    return {"fps": fps, "first": frame_index(frame["start"], fps), "last": frame_index(frame["end"], fps), "picture": picture}


def fresh_clip(razgon: Path, frame: dict, fps: int, picture: str) -> Path | None:
    """The frame's clip in build/studio, if it was rendered for these frame times from the current picture sources."""
    path = frame_clip(razgon, frame["number"])
    stamp = path.with_suffix(".json")
    if not (path.is_file() and stamp.is_file()):
        return None
    with contextlib.suppress(ValueError, OSError):
        want = frame_stamp(fps, frame, picture)
        if read_json(stamp) == want and video_frame_count(path) == want["last"] - want["first"]:
            return path
    return None


def render_frame(razgon: Path, frame: dict, fps: int, workers: str | None) -> Path:
    path = frame_clip(razgon, frame["number"])
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = path.with_suffix(".json")
    stamp.unlink(missing_ok=True)
    picture = picture_fingerprint(razgon)
    # The Studio slot is [frame_index(start), frame_index(end)). Python rounds .5 to even and render.mjs rounds it up,
    # so the renderer gets times that are already whole frames; otherwise a clip can come out one frame short.
    first, last = frame_index(frame["start"], fps), frame_index(frame["end"], fps)
    want = last - first
    command = ["node", "render.mjs", "--project", str(razgon), "--from", repr(first / fps), "--to", repr(last / fps),
               "--format", "jpeg", "--out", str(path)]
    # on a Mac the frames are drawn on the GPU: 4–7 times faster than Chromium's software drawing, the same picture
    # (PSNR 43–45 dB on 05 Frozen Body, 30 October 2026). render.mjs itself stays as it is: it is part of the picture
    # fingerprint, and a change to it would make every rendered clip stale
    if sys.platform == "darwin":
        command += ["--gl", "gpu"]
    if workers:
        command += ["--workers", workers]
    print(f"Рендер кадру {frame['number']} ({frame['start']:.2f}–{frame['end']:.2f} с)", flush=True)
    for attempt in (1, 2):   # a renderer hiccup can leave a short file: check the length and retry once
        subprocess.run(command, cwd=razgon.parents[1], check=True)
        got = video_frame_count(path)
        if got == want:
            break
        print(f"Кліп {frame['number']} вийшов {got} кадрів замість {want}" + (", рендерю ще раз" if attempt == 1 else ""), flush=True)
    else:
        raise BridgeError(f"Кліп кадру {frame['number']} двічі вийшов неповним")
    # the stamp lets the Studio export reuse this clip while nothing it is drawn from has changed
    write_json(stamp, frame_stamp(fps, frame, picture))
    return path


def describe(error: Exception) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        step = next((Path(str(part)).name for part in error.cmd if str(part).endswith((".mjs", ".py"))), Path(str(error.cmd[0])).name)
        return f"{step} завершився з кодом {error.returncode}"
    return str(error)


def memory() -> tuple[int, int] | None:
    """(bytes in use, total bytes) of the machine's RAM, as Activity Monitor counts it on a Mac; None when unknown."""
    try:
        if sys.platform == "darwin":
            total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True).stdout)
            stat = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True).stdout
            page = int(re.search(r"page size of (\d+) bytes", stat).group(1))
            pages = {k.strip().strip('"'): int(v.strip().rstrip(".")) for k, v in (line.split(":", 1) for line in stat.splitlines()[1:] if ":" in line)}
            # Activity Monitor's «Memory Used»: app memory + wired + compressed. The file cache a render fills while it
            # writes video is given back on demand and stays out, as it does there.
            used = pages["Anonymous pages"] - pages.get("Pages purgeable", 0) + pages["Pages wired down"] + pages["Pages occupied by compressor"]
            return used * page, total
        info = {k: int(v.split()[0]) * 1024 for k, v in (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)}
        return info["MemTotal"] - info["MemAvailable"], info["MemTotal"]
    except (OSError, ValueError, AttributeError, KeyError, subprocess.CalledProcessError):
        return None


def room(chromiums: int) -> bool:
    """True when `chromiums` more render.mjs workers fit under RAM_LIMIT with everything else that runs now."""
    use = memory()
    return use is None or use[0] + chromiums * CHROMIUM_BYTES <= RAM_LIMIT * use[1]


def render_many(razgon: Path, frames: list[dict], fps: int, workers: str | None, jobs: int, done=None) -> None:
    """Render Studio frames side by side, the longest first, at most `jobs` at a time and only as many as the memory
    holds. Each Chromium of render.mjs takes about 2 GB at 1080p; the export ran 6 of them on a 16 GB Mac, the system went
    to disk and no other program would open (31 October 2026). So a frame starts only while the RAM in use stays under
    RAM_LIMIT with it; a render younger than RAMP has not grown yet and is counted in full on top of the reading. The
    first frame always starts. One worker per frame keeps every Chromium busy: several workers on one frame wait idle
    for its slowest chunk."""
    per, jobs = int(workers or 1), max(1, jobs or JOBS)
    queue, running = sorted(frames, key=lambda f: f["start"] - f["end"]), {}
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        while queue or running:
            young = sum(1 for _, at in running.values() if time.monotonic() - at < RAMP)
            if queue and len(running) < jobs and (not running or room(per * (1 + young))):
                frame = queue.pop(0)
                running[pool.submit(render_frame, razgon, frame, fps, str(per))] = (frame, time.monotonic())
                continue
            finished, _ = concurrent.futures.wait(running, timeout=5, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in finished:
                frame, _ = running.pop(future)
                try:
                    future.result()
                except Exception as error:
                    queue.clear()   # the frames already rendering finish, no new one starts
                    raise BridgeError(f"Кадр {frame['number']}: {describe(error)}") from error
                if done:
                    done(frame)


def render_frames(razgon: Path, link: dict, numbers: set[int], workers: str | None, jobs: int = JOBS) -> dict[int, Path]:
    fps = int(link["fps"])
    todo = [frame for frame in link["frames"] if frame["number"] in numbers or not frame_clip(razgon, frame["number"]).is_file()]
    render_many(razgon, todo, fps, workers, jobs)
    return {frame["number"]: frame_clip(razgon, frame["number"]) for frame in link["frames"]}


def render_bed(razgon: Path) -> Path | None:
    """Music, SFX and ambience exactly as Razgon mixes them under the voice, but without the voice."""
    root = razgon.parents[1]
    sys.path[:0] = [str(root / "audio"), str(root / "tools")]
    import numpy as np
    import mix as MIX
    captured = {}
    original_write, original_run = MIX.write_wav, MIX.subprocess.run

    def capture(path, data, *rest, **kw):
        if str(path).endswith("mix_raw.wav"):
            captured["mix"] = np.array(data, copy=True)
        return original_write(path, data, *rest, **kw)

    def skip_master(command, *rest, **kw):
        # mix.py's own loudnorm/mux steps are not needed: the bed is taken pre-master.
        if isinstance(command, list) and any("loudnorm" in str(part) for part in command) or "__no_video__" in str(command):
            return None
        return original_run(command, *rest, **kw)

    MIX.write_wav = capture
    MIX.subprocess.run = skip_master
    argv = sys.argv
    sys.argv = ["mix.py", "--project", str(razgon), "--video", str(razgon / "build" / "__no_video__.mp4")]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            MIX.main()
    finally:
        MIX.write_wav, MIX.subprocess.run, sys.argv = original_write, original_run, argv
    if "mix" not in captured:
        return None
    config = read_json(razgon / "config.json")
    voice = MIX.load_any(str(razgon / config["voiceover"]))
    n = len(captured["mix"])
    voice = np.concatenate([voice, np.zeros((max(0, n - len(voice)), 2), np.float32)])[:n]
    bed = captured["mix"] - (voice - MIX.lp(voice, 25))
    if np.abs(captured["mix"]).max() >= 0.949:
        print("Увага: Razgon м'яко обрізав піки суміші, доріжка музики може містити слабкий слід голосу")
    if np.abs(bed).max() < 1e-5:
        return None
    path = razgon / "build" / "studio" / "music_sfx.wav"
    MIX.write_wav(str(path), bed.astype(np.float32))
    return path


def ensure_overlay(studio: "Studio", razgon: Path, project: dict, duration: float) -> dict:
    """Put the channel plashka (config.json "overlay", a transparent full-frame PNG) on the top layer of the Studio
    timeline for the whole video, as its own "Плашка каналу" frame group, so it is seen in the editor and in exports."""
    config = read_json(razgon / "config.json")
    if not config.get("overlay"):
        return project
    image = (razgon / config["overlay"]).resolve()
    if not image.is_file():
        raise BridgeError(f"Немає файлу плашки: {image}")
    old = next((clip for _, clip in all_clips(project) if clip.get("title") == OVERLAY_TITLE), None)
    if old and abs(old["start"]) < 1e-3 and abs(old["start"] + old["duration"] - duration) < 1e-3:
        # clips added later (frames, sketches) get new layers on top: keep the plashka layer above all of them
        top = len(project["tracks"]) - 1
        layer = next(track for track in project["tracks"] if any(c["id"] == old["id"] for c in track.get("clips", [])))
        if project["tracks"].index(layer) != top:
            project = studio.batch(project, [{"type": "move_layer", "payload": {"layer_id": layer["id"], "to_index": top}}])
        return project
    if old:
        project = studio.batch(project, [{"type": "delete_clip", "payload": {"clip_id": old["id"]}}])
    asset = studio.import_file(project["id"], image)
    project = studio.project(project["id"])   # importing the file bumps the revision
    project = studio.batch(project, [{"type": "add_layer", "payload": {"name": OVERLAY_TITLE, "to_index": len(project["tracks"])}}])
    layer = [track for track in project["tracks"] if track.get("name") == OVERLAY_TITLE and not track.get("clips")][-1]
    project = studio.batch(project, [{"type": "add_clip", "payload": {"layer_id": layer["id"], "kind": "image", "asset_id": asset["id"],
                                                                      "start": 0, "duration": duration, "title": OVERLAY_TITLE}}])
    clip = next(clip for _, clip in all_clips(project) if clip.get("title") == OVERLAY_TITLE)
    return studio.batch(project, [{"type": "group_clips", "payload": {"clip_ids": [clip["id"]], "title": OVERLAY_TITLE, "role": "overlay"}}])


def overlay(args) -> None:
    razgon = Path(args.razgon).resolve()
    link = read_json(razgon / "story" / "studio_frames.json")
    studio = Studio(args.studio_url or link["studio_url"])
    project = ensure_overlay(studio, razgon, studio.project(link["project_id"]), float(link["duration"]))
    print("Плашка каналу на таймлайні: " + ("так" if any(c.get("title") == OVERLAY_TITLE for _, c in all_clips(project)) else "немає overlay у config.json"))


def push(args) -> None:
    razgon = Path(args.razgon).resolve()
    problems = check_project(razgon)
    if problems:
        raise BridgeError("Проєкт Razgon не готовий:\n- " + "\n- ".join(problems))
    link, story, config = load_link(razgon)
    studio = Studio(args.studio_url or link["studio_url"])
    pid = link["project_id"]
    plan = studio.plan(pid)
    if plan["script_sha256"] != link["script_sha256"] or plan.get("timing", {}).get("audio", {}).get("sha256") != link.get("audio_sha256"):
        raise BridgeError("План у студії змінився після prepare. Запустіть prepare ще раз і перевірте шоти")
    if args.frames and args.shots:
        raise BridgeError("Передайте --frames або --shots")
    if args.shots:
        wanted = frames_of_shots(link, story, [item.strip() for item in args.shots.split(",") if item.strip()])
        print("Кадри студії для цих шотів: " + ", ".join(map(str, sorted(wanted))))
    else:
        wanted = {int(item) for item in args.frames.split(",")} if args.frames else {f["number"] for f in link["frames"]}
    clips = render_frames(razgon, link, set() if args.no_render else wanted, args.workers, args.jobs)
    bed = None if args.no_audio else render_bed(razgon)

    project = studio.project(pid)
    existing = {clip.get("title"): clip for _, clip in all_clips(project)}
    fps = int(link["fps"])
    actions, removals, imported = [], [], 0
    base_layer = project["tracks"][0]["id"]
    for frame in link["frames"]:
        if frame["number"] not in wanted:
            continue
        asset = studio.import_file(pid, clips[frame["number"]])
        imported += 1
        title = FRAME_TITLE.format(frame["number"])
        start = frame_index(frame["start"], fps) / fps
        duration = (frame_index(frame["end"], fps) - frame_index(frame["start"], fps)) / fps
        old = existing.get(title)
        if old and old.get("kind") != "video":   # the frame block put by slots: swap it for the rendered clip
            removals.append({"type": "delete_clip", "payload": {"clip_id": old["id"]}}); old = None
        if old and abs(old["start"] - start) < 1e-3 and abs(old["duration"] - duration) < 1e-3:
            actions.append({"type": "replace_clip_asset", "payload": {"clip_id": old["id"], "asset_id": asset["id"]}})
            actions.append({"type": "update_clip", "payload": {"clip_id": old["id"], "patch": {"title": title}}})
            continue
        if old:
            removals.append({"type": "delete_clip", "payload": {"clip_id": old["id"]}})
        actions.append({"type": "add_clip", "payload": {"layer_id": base_layer, "kind": "video", "asset_id": asset["id"],
                                                        "start": start, "duration": duration, "title": title, "volume": 0}})
    if bed:
        asset = studio.import_file(pid, bed)
        old = existing.get(BED_TITLE)
        if old:
            removals.append({"type": "delete_clip", "payload": {"clip_id": old["id"]}})
        actions.append({"type": "add_clip", "payload": {"layer_id": base_layer, "kind": "audio", "asset_id": asset["id"],
                                                        "start": 0, "duration": float(link["duration"]), "title": BED_TITLE, "volume": 1}})
    voice_id = link.get("voice_asset_id")
    if voice_id and not any(clip.get("kind") == "audio" and clip.get("asset_id") == voice_id for _, clip in all_clips(project)):
        actions.append({"type": "add_clip", "payload": {"layer_id": base_layer, "kind": "audio", "asset_id": voice_id,
                                                        "start": 0, "duration": float(link["duration"]), "title": "Озвучка", "volume": 1}})
    # Removals go last: in item-layer mode deleting a clip also deletes its layer,
    # and the additions above refer to an existing layer.
    actions += removals
    if actions:
        project = studio.project(pid)
        project = studio.batch(project, actions)

    grouped = {cid for group in project.get("scene_groups", []) for cid in group["clip_ids"]}
    groups = []
    for _, clip in all_clips(project):
        match = re.fullmatch(r"Razgon · кадр (\d{3})", clip.get("title", ""))
        if match and clip["id"] not in grouped:
            groups.append({"type": "group_clips", "payload": {"clip_ids": [clip["id"]], "title": f"Кадр {int(match.group(1))}"}})
    if groups:
        project = studio.batch(project, groups)
    project = ensure_overlay(studio, razgon, project, float(link["duration"]))
    print(f"У студію передано кліпів: {imported}" + (", музика й ефекти окремою доріжкою" if bed else ""))
    print(f"Проєкт: {studio.url}/channels/{project['channel_id']}/projects/{pid}")
    # Replaced clips and render leftovers are removed by the Studio in the background; an older Studio without it is fine.
    with contextlib.suppress(BridgeError):
        studio.call("POST", f"/api/projects/{pid}/tidy", {})


# ---------------------------------------------------------------- plan
# ---------------------------------------------------------------- frames for review without a render
def ensure_frame_slots(studio: "Studio", razgon: Path, link: dict, project: dict, reset: frozenset = frozenset()) -> dict:
    """Put every Studio frame on the timeline as a numbered "Кадр N" block before any render. The block is a Studio code
    clip (an invisible shape, no media file): live mode, which only keeps overlay and audio clips, draws the Razgon film
    over it; the Studio export renders the blocks. The frames in `reset` go back from a rendered clip to a block, so a
    changed scene is drawn live and rendered again by the export (a clip it rendered before stays in build/studio and
    is reused while the scene is unchanged)."""
    pid, fps = link["project_id"], int(link["fps"])
    # the blocks follow the plan: a block whose frame is gone (the director joined takes) or whose frame moved is removed
    # and put back at the frame's place below
    want = {FRAME_TITLE.format(f["number"]): (frame_index(f["start"], fps), frame_index(f["end"], fps)) for f in link["frames"]}
    stale = [clip for _, clip in all_clips(project) if re.fullmatch(r"Razgon · кадр \d{3}", clip.get("title", ""))
             and (clip["title"] not in want or (round(clip["start"] * fps), round((clip["start"] + clip["duration"]) * fps)) != want[clip["title"]]
                  or (int(clip["title"][-3:]) in reset and clip.get("kind") != "animation"))]
    if stale:
        project = studio.batch(project, [{"type": "delete_clip", "payload": {"clip_id": clip["id"]}} for clip in stale])
    have = {clip.get("title") for _, clip in all_clips(project)}
    frames = [f for f in link["frames"] if FRAME_TITLE.format(f["number"]) not in have]
    if not frames:
        return project
    base_layer = project["tracks"][0]["id"]
    actions = []
    for f in frames:
        first, last = frame_index(f["start"], fps), frame_index(f["end"], fps)
        actions.append({"type": "add_clip", "payload": {"layer_id": base_layer, "kind": "animation", "content_type": "shape", "start": first / fps,
                                                        "duration": (last - first) / fps, "title": FRAME_TITLE.format(f["number"]), "opacity": 0, "color": "#101114"}})
    project = studio.batch(project, actions)
    grouped = {cid for group in project.get("scene_groups", []) for cid in group["clip_ids"]}
    groups = [{"type": "group_clips", "payload": {"clip_ids": [clip["id"]], "title": f"Кадр {int(m.group(1))}"}}
              for _, clip in all_clips(project) for m in [re.fullmatch(r"Razgon · кадр (\d{3})", clip.get("title", ""))] if m and clip["id"] not in grouped]
    if groups:
        project = studio.batch(project, groups)
    return ensure_overlay(studio, razgon, project, float(link["duration"]))


def slots(args) -> None:
    razgon = Path(args.razgon).resolve()
    link = read_json(razgon / "story" / "studio_frames.json")
    studio = Studio(args.studio_url or link["studio_url"])
    project = studio.project(link["project_id"])
    voice_id = link.get("voice_asset_id")
    if voice_id and not any(c.get("kind") == "audio" and c.get("asset_id") == voice_id for _, c in all_clips(project)):
        project = studio.batch(project, [{"type": "add_clip", "payload": {"layer_id": project["tracks"][0]["id"], "kind": "audio", "asset_id": voice_id,
                                                                          "start": 0, "duration": float(link["duration"]), "title": "Озвучка", "volume": 1}}])
    reset = frozenset(int(item) for item in args.frames.split(",") if item.strip()) if args.frames else frozenset()
    project = ensure_frame_slots(studio, razgon, link, project, reset)
    n = sum(1 for _, c in all_clips(project) if re.fullmatch(r"Razgon · кадр \d{3}", c.get("title", "")))
    print(f"Кадри на таймлайні: {n} (блоки-код без медіа, наживо малює Razgon)")


def plan_from_direction(args) -> None:
    """Rewrite the Studio frame plan from the Razgon direction.

    A Studio frame is a whole number of sentences (the Studio's rule) and the Studio computes its times from the
    voiceover. A frame boundary is placed at every sentence boundary where the film really cuts (a shot starts within
    0.45 s of it) and always where an episode starts, so the clips in the Studio follow the film's own scenes.
    """
    razgon = Path(args.razgon).resolve()
    link, story, config = load_link(razgon)
    studio = Studio(args.studio_url or link["studio_url"])
    pid = link["project_id"]
    plan = studio.plan(pid)
    if plan.get("timing", {}).get("status") != "audio_synced":
        raise BridgeError("План у студії ще чернетка")
    if plan["script_sha256"] != link["script_sha256"]:
        raise BridgeError("Сценарій у студії змінився після prepare. Запустіть prepare ще раз")
    sys.path.insert(0, str(STUDIO_BACKEND))
    import planner
    sentences = [text for frame in plan["frames"] for text in frame["sentences"]]
    timings = [item for frame in plan["frames"] for item in frame["sentence_timings"]]
    duration = float(plan["timing"]["audio"]["duration"])
    shots = story["shots"]
    episode_starts = [s["start"] for i, s in enumerate(shots) if i and s.get("episode") != shots[i - 1].get("episode")]
    cut_times = [s["start"] for s in shots[1:]]
    cuts, unaligned = set(), []
    beats_path = razgon / "story" / "beats.json"
    if beats_path.is_file():
        # the director's meaning beats decide the frames; shot cuts don't matter then
        beats = read_json(beats_path)["beats"]
        cuts = {int(b["first_sentence"]) for b in beats if int(b["first_sentence"]) > 0}
        if max(cuts, default=0) >= len(timings):
            raise BridgeError("beats.json посилається на речення, яких немає в плані")
        print(f"Кадри за смисловими блоками режисера: {len(beats)}")
        timings_range = range(0)
    else:
        timings_range = range(1, len(timings))
    for j in timings_range:
        gap_from, gap_to = timings[j - 1]["end"], timings[j]["start"]
        if any(gap_from - 0.45 <= c <= gap_to + 0.45 for c in cut_times):
            cuts.add(j)
    for e in ([] if beats_path.is_file() else episode_starts):
        j = min(range(1, len(timings)), key=lambda j: abs(timings[j]["start"] - e))
        if abs(timings[j]["start"] - e) > 0.6:
            unaligned.append(round(e, 2))
        cuts.add(j)
    groups, current = [], []
    for j, text in enumerate(sentences):
        if j in cuts and current:
            groups.append(current); current = []
        current.append(text)
    groups.append(current)
    times = planner.aligned_times(groups, timings, duration, None)
    shot_at = lambda t: next((s for s in shots if s["start"] <= t < s["end"]), shots[-1])
    frames, offset = [], 0
    for n, (group, (a, b)) in enumerate(zip(groups, times), 1):
        first = shot_at((a + b) / 2 if len(group) == 1 else timings[offset]["start"] + 0.01)
        frames.append({"number": n, "start": round(a, 3), "end": round(b, 3), "sentences": group, "format": "razgon_2d",
                       "sentence_timings": timings[offset:offset + len(group)], "episode": first.get("episode"), "scene": first.get("scene", "")})
        offset += len(group)
    new_plan = dict(plan, frames=frames, frame_source="razgon-direction")
    # the frames come from the direction, not from the channel's planner settings: bind the plan to the settings saved
    # now, so the Studio doesn't flag it as stale after an unrelated settings change
    channel = next((c for c in studio.call("GET", "/api/channels")["channels"] if c["id"] == plan.get("channel_id")), None)
    if channel:
        snapshot = planner.effective_settings(channel["settings"])
        new_plan.update(settings_snapshot=snapshot, settings_signature=planner.settings_signature(snapshot))
    new_plan["report"] = dict(plan.get("report", {}), frames=len(frames), format_seconds={"razgon_2d": round(times[-1][1], 3)})
    lengths = [f["end"] - f["start"] for f in frames]
    print(f"Кадрів студії: {len(plan['frames'])} → {len(frames)}; тривалість кадру від {min(lengths):.1f} до {max(lengths):.1f} с")
    if unaligned:
        print("Увага: початок епізоду не на межі речення (кадр студії почнеться на найближчій межі): " + ", ".join(map(str, unaligned)))
    if args.dry_run:
        for f in frames[:12]:
            print(f"  {f['number']:3d} {f['start']:7.2f}-{f['end']:7.2f} {f.get('episode') or '':4} {' '.join(f['sentences'])[:70]}")
        return
    studio.call("POST", f"/api/projects/{pid}/plan", {"plan": new_plan})
    check = studio.call("GET", f"/api/projects/{pid}")
    production = check.get("production") or check.get("project", {}).get("production") or {}
    if not production.get("plan_ready"):
        raise BridgeError("Студія не прийняла план: " + str(production.get("reason")))
    link["frames"] = [{k: f[k] for k in ("number", "start", "end", "sentences", "format")} for f in frames]
    write_json(razgon / "story" / "studio_frames.json", link)
    for old in (razgon / "build" / "studio").glob("frame_*.mp4"):
        old.unlink()
    print("План записано в студію, кадри Razgon оновлено. Старі кліпи видалено, наступний push відрендерить нові.")
    slots(argparse.Namespace(razgon=str(razgon), studio_url=args.studio_url, frames=None))


# ---------------------------------------------------------------- the glued final MP4
def final(args) -> None:
    """The finished video for the channel: the rendered Studio frames back to back, the channel plashka on top for the
    whole film, and Razgon's own mix of the original voiceover with music and SFX, loudness-normalised (config.loudness,
    −14 LUFS). Nothing is re-rendered: run push first."""
    razgon = Path(args.razgon).resolve()
    link, story, config = load_link(razgon)
    clips = [frame_clip(razgon, f["number"]) for f in link["frames"]]
    missing = [c.name for c in clips if not c.is_file()]
    if missing:
        raise BridgeError("Немає відрендерених кадрів (спершу push): " + ", ".join(missing[:10]))
    out = Path(args.out).resolve()
    glue(razgon, link, config, clips, (razgon / config["overlay"]) if config.get("overlay") else None, out)
    print(f"Фінал: {out}")


@functools.lru_cache(maxsize=1)
def video_encoder() -> tuple[str, ...]:
    """Apple's hardware H.264 encoder when this ffmpeg has it, x264 otherwise. Gluing the whole film with the plate on top
    re-encodes every frame: on a Mac busy with renders VideoToolbox did 89 fps against x264's 25 fps, at the same look
    (SSIM 0.989 against the source for both, 29 October 2026). 14 Mbit/s is well above YouTube's 8 Mbit/s for 1080p."""
    found = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if re.search(r"\bh264_videotoolbox\b", found):
        return ("-c:v", "h264_videotoolbox", "-b:v", "14M", "-maxrate", "20M", "-bufsize", "28M", "-profile:v", "high")
    return ("-c:v", "libx264", "-preset", "faster", "-crf", "18")


def glue(razgon: Path, link: dict, config: dict, clips: list[Path], overlay: Path | None, out: Path, progress=None) -> None:
    """The frame clips back to back with the plashka on top, encoded once, then Razgon's mix of the voice with music and
    SFX at config.loudness muxed in without touching the picture. progress(phase, 0..1) hears about both steps."""
    fps = int(link["fps"])
    want = sum(frame_index(f["end"], fps) - frame_index(f["start"], fps) for f in link["frames"])
    got = sum(video_frame_count(c) for c in clips)
    if got != want:
        raise BridgeError(f"Кадри разом дають {got} кадрів замість {want}")
    listing = razgon / "build" / "final_concat.txt"
    listing.write_text("".join("file '{}'\n".format(str(c).replace("'", "'\\''")) for c in clips))
    silent = razgon / "build" / "video_silent.mp4"
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
    if overlay and overlay.is_file():
        command += ["-i", str(overlay), "-filter_complex", "[1:v]scale={w}:{h}[o];[0:v][o]overlay=0:0:format=auto".format(w=RESOLUTION_W(config), h=RESOLUTION_H(config))]
    command += ["-r", str(fps), *video_encoder(), "-pix_fmt", "yuv420p", "-an", str(silent)]
    print(f"Склеюю {len(clips)} кадрів ({got} кадрів відео)" + (" з плашкою каналу" if overlay else ""), flush=True)
    if progress is None:
        subprocess.run(command, check=True)
    else:
        encoder = subprocess.Popen(command[:-1] + ["-progress", "pipe:1", "-nostats", str(silent)], stdout=subprocess.PIPE, text=True)
        for line in encoder.stdout:
            if line.startswith("frame="):
                with contextlib.suppress(ValueError):
                    progress("composing", min(1.0, int(line[6:]) / max(1, want)))
        if encoder.wait():
            raise BridgeError(f"ffmpeg не склеїв кадри (код {encoder.returncode})")
        progress("razgon_sound", 0.0)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "audio/mix.py", "--project", str(razgon), "--video", str(silent), "--out", str(out)], cwd=razgon.parents[1], check=True)


# ---------------------------------------------------------------- the Studio's «Експорт MP4»
def studio_export(args) -> None:
    """The Studio's own export of a Razgon episode, the same film as push + final. The spec (written by the Studio's
    backend/razgon_export.py) gives, per frame, the rendered clip the Studio timeline holds, or null for a frame that is
    still a code block. Those frames are rendered here, unless build/studio already has them rendered for the same times
    from the same picture sources. Progress goes to stdout as JSON lines for the Studio export job."""
    def report(**event):
        print(json.dumps(event, ensure_ascii=False), flush=True)
    try:
        razgon = Path(args.razgon).resolve()
        spec = read_json(Path(args.spec))
        problems = check_project(razgon)
        if problems:
            raise BridgeError("Проєкт Razgon не готовий: " + "; ".join(problems))
        link, story, config = load_link(razgon)
        fps = int(link["fps"])
        sources = {int(number): Path(path) for number, path in (spec.get("clips") or {}).items() if path}
        picture = picture_fingerprint(razgon)
        todo = [f for f in link["frames"] if f["number"] not in sources and not fresh_clip(razgon, f, fps, picture)]
        length = lambda f: frame_index(f["end"], fps) - frame_index(f["start"], fps)
        # rough weights from the 1080p renders: Razgon draws ~1.4 s per second of film, gluing and mixing take ~0.2 s
        film_frames = sum(length(f) for f in link["frames"])
        render_share = 1.4 / (1.4 + 0.2)
        glue_progress = lambda phase, p: report(stage="razgon", phase=phase, progress=round(render_share + (1 - render_share) * (0.8 * p if phase == "composing" else 0.8 + 0.2 * p), 4))
        # the count and the share are of the whole film: frames already rendered from the same code read as done from the
        # start, so a restarted export goes on from where the last one stopped instead of from 0%
        total, ready = len(link["frames"]), len(link["frames"]) - len(todo)
        ready_frames = film_frames - sum(length(f) for f in todo)
        report(stage="razgon", phase="razgon_frames", progress=round(render_share * ready_frames / film_frames, 4), completed=ready, total=total)
        finished = []
        def rendered(frame):
            finished.append(frame)
            report(stage="razgon", phase="razgon_frames", progress=round(render_share * (ready_frames + sum(map(length, finished))) / film_frames, 4),
                   completed=ready + len(finished), total=total)
        render_many(razgon, todo, fps, args.workers, args.jobs, rendered)
        clips = [sources.get(f["number"]) or frame_clip(razgon, f["number"]) for f in link["frames"]]
        glue(razgon, link, config, clips, Path(spec["overlay"]) if spec.get("overlay") else None, Path(args.out).resolve(), glue_progress)
        glue_progress("razgon_sound", 1.0)
    except (BridgeError, subprocess.CalledProcessError, OSError, ValueError, KeyError) as error:
        report(stage="error", message=describe(error))
        raise SystemExit(1)


MIXED_TAIL = 0.5   # seconds of held last picture after a mixed episode's frame: the Studio's transition out fades over it


def studio_frames(args) -> None:
    """The Studio's export of a mixed episode: photos, stock, text frames and some Razgon frames (Alexey Gorbunov's
    channel, 31 October 2026). Only the listed frames are Razgon code blocks. They are rendered here, or taken from
    build/studio while nothing they are drawn from has changed, and each gets a copy with MIXED_TAIL seconds of its last
    picture held, so a Studio transition out of the frame has pictures to fade. The Studio engine then exports the whole
    timeline. Progress goes to stdout as JSON lines; the last one lists the clips by frame number."""
    def report(**event):
        print(json.dumps(event, ensure_ascii=False), flush=True)
    try:
        razgon = Path(args.razgon).resolve()
        problems = check_project(razgon)
        if problems:
            raise BridgeError("Проєкт Razgon не готовий: " + "; ".join(problems))
        link, _, _ = load_link(razgon)
        fps = int(link["fps"])
        numbers = {int(item) for item in args.numbers.split(",") if item.strip()}
        frames = [f for f in link["frames"] if f["number"] in numbers]
        missing = sorted(numbers - {f["number"] for f in frames})
        if missing:
            raise BridgeError("У плані Razgon немає кадрів " + ", ".join(map(str, missing)))
        picture = picture_fingerprint(razgon)
        todo = [f for f in frames if not fresh_clip(razgon, f, fps, picture)]
        length = lambda f: frame_index(f["end"], fps) - frame_index(f["start"], fps)
        whole, finished = sum(map(length, frames)), []
        def progress(frame=None):
            if frame:
                finished.append(frame)
            ready = whole - sum(map(length, todo)) + sum(map(length, finished))
            report(stage="razgon", phase="razgon_frames", progress=round(ready / whole, 4), completed=len(frames) - len(todo) + len(finished), total=len(frames))
        progress()
        render_many(razgon, todo, fps, args.workers, args.jobs, progress)
        clips = {}
        for f in frames:
            clip = frame_clip(razgon, f["number"])
            held = clip.with_name(f"{clip.stem}_tail.mp4")
            if not held.is_file() or held.stat().st_mtime < clip.stat().st_mtime:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf", f"tpad=stop_mode=clone:stop_duration={MIXED_TAIL}",
                                *video_encoder(), "-pix_fmt", "yuv420p", "-an", str(held)], check=True)
            clips[str(f["number"])] = str(held)
        report(stage="razgon_frames_done", clips=clips)
    except (BridgeError, subprocess.CalledProcessError, OSError, ValueError, KeyError) as error:
        report(stage="error", message=describe(error))
        raise SystemExit(1)


def RESOLUTION_W(config: dict) -> int:
    short = int(str(config.get("resolution", "1080p")).rstrip("p"))
    return short * 16 // 9 if config.get("aspect", "16:9") == "16:9" else short


def RESOLUTION_H(config: dict) -> int:
    short = int(str(config.get("resolution", "1080p")).rstrip("p"))
    return short if config.get("aspect", "16:9") == "16:9" else short * 16 // 9


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="створити проєкт Razgon з плану студії")
    p.add_argument("--project-id", required=True)
    p.add_argument("--studio-url", default="http://127.0.0.1:8770")
    p.add_argument("--studio-dir", default=str(DEFAULT_STUDIO))
    p.add_argument("--slug")
    p.add_argument("--style", help="стиль Razgon; без нього береться стиль каналу зі студії, інакше dusk")
    p.set_defaults(run=prepare)
    pl = sub.add_parser("plan", help="записати в студію план кадрів за режисурою Razgon")
    pl.add_argument("--razgon", required=True)
    pl.add_argument("--studio-url")
    pl.add_argument("--dry-run", action="store_true")
    pl.set_defaults(run=plan_from_direction)
    c = sub.add_parser("check", help="перевірити, що шоти суцільні й покривають озвучку")
    c.add_argument("--razgon", required=True)
    c.set_defaults(run=check)
    u = sub.add_parser("push", help="відрендерити кадри й покласти їх на таймлайн студії")
    u.add_argument("--razgon", required=True)
    u.add_argument("--studio-url")
    u.add_argument("--frames", help="номери кадрів через кому; без них оновлюються всі")
    u.add_argument("--shots", help="id змінених шотів Razgon через кому; оновлюються всі кадри, через які вони проходять")
    u.add_argument("--no-render", action="store_true", help="не рендерити, взяти вже готові кліпи")
    u.add_argument("--no-audio", action="store_true", help="не передавати музику й ефекти")
    u.add_argument("--workers", help="воркерів Chromium на один кадр (типово 1)")
    u.add_argument("--jobs", type=int, default=JOBS, help=f"найбільше кадрів одночасно, поки вистачає пам'яті (типово {JOBS})")
    u.set_defaults(run=push)
    k = sub.add_parser("slots", help="покласти кадри «Кадр N» на таймлайн без рендеру (для перегляду наживо)")
    k.add_argument("--razgon", required=True)
    k.add_argument("--studio-url")
    k.add_argument("--frames", help="номери кадрів через кому, які з відрендереного кліпу знову стають блоком-кодом")
    k.set_defaults(run=slots)
    f = sub.add_parser("final", help="склеїти фінальний MP4: кадри підряд, плашка, озвучка + музика й ефекти, −14 LUFS")
    f.add_argument("--razgon", required=True)
    f.add_argument("--out", required=True)
    f.set_defaults(run=final)
    o = sub.add_parser("overlay", help="покласти плашку каналу (config.json overlay) верхнім шаром на весь ролик")
    o.add_argument("--razgon", required=True)
    o.add_argument("--studio-url")
    o.set_defaults(run=overlay)
    e = sub.add_parser("export", help="«Експорт MP4» студії: дорендерити кадри-блоки й склеїти фільм, як push + final")
    e.add_argument("--razgon", required=True)
    e.add_argument("--spec", required=True, help="JSON студії: кліпи кадрів з таймлайну й плашка")
    e.add_argument("--out", required=True)
    e.add_argument("--workers", help="воркерів Chromium на один кадр (типово 1)")
    e.add_argument("--jobs", type=int, default=JOBS, help=f"найбільше кадрів одночасно, поки вистачає пам'яті (типово {JOBS})")
    e.set_defaults(run=studio_export)
    m = sub.add_parser("frames", help="«Експорт MP4» змішаного ролика: дорендерити лише кадри-блоки Razgon, решту збирає студія")
    m.add_argument("--razgon", required=True)
    m.add_argument("--numbers", required=True, help="номери кадрів студії через кому")
    m.add_argument("--workers", help="воркерів Chromium на один кадр (типово 1)")
    m.add_argument("--jobs", type=int, default=JOBS, help=f"найбільше кадрів одночасно, поки вистачає пам'яті (типово {JOBS})")
    m.set_defaults(run=studio_frames)
    args = parser.parse_args()
    # an agent the Studio started draws frames as code blocks: the frames are rendered by the Studio's «Експорт MP4» only
    if args.command in {"push", "final"} and os.environ.get("MULTIBOT_RENDER_ON_EXPORT"):
        sys.exit("Кадри рендерить тільки «Експорт MP4» студії, коли автор його натисне. "
                 "Поклади кадри на таймлайн блоками-кодом: python3 'VideoKey Studio/tools/razgon_bridge.py' slots --razgon <проєкт> --frames <номери>")
    try:
        with project_lock(Path(args.razgon).resolve()) if args.command in {"push", "final", "export", "frames"} else contextlib.nullcontext():
            args.run(args)
    except BridgeError as error:
        if args.command in {"export", "frames"}:
            print(json.dumps({"stage": "error", "message": str(error)}, ensure_ascii=False), flush=True)
        sys.exit(str(error))


if __name__ == "__main__":
    main()
