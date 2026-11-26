"""CapCut transitions and effects in the export (user, 14 November 2026: «Усе додати»).

The packages were taken from CapCut's cache and rebuilt with numpy (engine/capcut_lib, data in engine/capcut_assets).
The backend (backend/joins.py, backend/capcut.py) puts their clips into the render manifest as animation clips with
`content_type` `capcut_transition` or `capcut_effect`; `expand` turns each into ready movies before the timeline is
planned, so the CPU and GPU renderers only see ordinary graphic clips with a `prepared_source` (ProRes 4444):

- a transition draws both sides of its seam without the channel plate (outgoing side without the incoming clips and the
  other way round), mixes them in the worker and covers the seam with the result, below the plate;
- an overlay effect (noise, stars, glitter, the player) is a short loop with alpha, repeated over the clip's length:
  on one frame or on a row above the timeline it lies over everything below it;
- a content effect (CRT, the sliding card, the glass bracelet) draws what lies below it in its time and changes that.

Only the clips near a seam or an effect are drawn (`_near`), its sides go to the worker as small H.264 videos it decodes
through a pipe, and one worker process a working size stays alive (`_Worker`). Movies and sides are cached by everything
that makes them in backend/data/capcut-cache, so a still, a second export, the GPU preparation or another transition on
the same seam re-use them; an edit elsewhere in the film keeps them.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
APP = ENGINE.parent
CATALOG = json.loads((APP / "frontend" / "capcut-catalog.json").read_text(encoding="utf-8"))
TRANSITIONS = CATALOG["transitions"]
EFFECTS = CATALOG["effects"]
KINDS = {"capcut_transition", "capcut_effect"}
VERSION = "capcut-1"
OVERLAY_LOOP = {"capcut_e01": 17 / 15, "capcut_e02": 3.0, "capcut_e03": 28 / 15, "capcut_e04": 2.0, "capcut_e05": 3.0,
                "capcut_e06": 3.0, "capcut_e09": 3.0, "capcut_e10": 1.0, "capcut_e11": 3.0, "capcut_e13": 2.8}
PREVIEW = False  # set by the preview command: the browser plays H.264 and VP9
# drawn around a seam on each side: the timeline's own fades (a clip's "transition") reach this far at most
MARGIN = 2.0


def data_root() -> Path:
    return Path(os.environ.get("MULTIBOT_STUDIO_DATA", str(APP / "backend" / "data"))).expanduser().resolve()


ASSETS = ENGINE / "capcut_assets"   # the CapCut packages travel with the studio's git, so every Mac has them


def package(kind: str, entry: dict) -> Path:
    group = "transitions" if kind == "capcut_transition" else "effects"
    shipped = ASSETS / group / entry["package"]
    return shipped if shipped.is_dir() else data_root() / "capcut" / group / entry["package"]


def cache_dir() -> Path:
    path = data_root() / "capcut-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def work_size(width: int, height: int) -> tuple[int, int]:
    """numpy drawing size: at most 1280 wide, even, the frame's proportions."""
    scale = min(1.0, 1280 / width)
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)


def _key(*parts) -> str:
    # previews before 25 November 2026 drew their windows at 640 px (captions too big); the export's were right
    version = VERSION + ("-native" if PREVIEW else "")
    return hashlib.sha256(json.dumps([version, *parts], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:24]


def _sources_stamp(layers: list[dict], project_file: Path) -> list:
    stamp = []
    for layer in layers:
        for clip in layer.get("clips", []):
            src = clip.get("source") or clip.get("src") or clip.get("path")
            if not src:
                continue
            path = Path(str(src))
            if not path.is_absolute():
                path = project_file.parent / path
            try:
                st = path.stat()
                stamp.append([str(path), st.st_size, int(st.st_mtime)])
            except OSError:
                stamp.append([str(path), None, None])
    return stamp


class _Worker:
    """One `capcut_worker.py --serve` a working size, started before the sides are drawn so its imports (numpy, scipy,
    the packages: about 2 s a transition) run meanwhile, and kept for the next transition of the same render."""
    _all: dict = {}
    _lock = threading.Lock()

    def __init__(self, pw: int, ph: int):
        env = {**os.environ, "CAPCUT_W": str(pw), "CAPCUT_H": str(ph)}
        self.proc = subprocess.Popen(["nice", "-n", "5", sys.executable, str(ENGINE / "capcut_worker.py"), "--serve"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
        self.busy = threading.Lock()

    @classmethod
    def get(cls, width: int, height: int) -> "_Worker":
        size = work_size(width, height)
        with cls._lock:
            worker = cls._all.get(size)
            if worker is None or worker.proc.poll() is not None:
                worker = cls._all[size] = cls(*size)
            return worker

    def run(self, job: dict) -> None:
        with self.busy:
            try:
                self.proc.stdin.write(json.dumps(job) + "\n")
                self.proc.stdin.flush()
                line = self.proc.stdout.readline()
            except (OSError, ValueError) as error:
                line = json.dumps({"error": f"the worker stopped: {error}"})
            if not line:
                self.proc.kill()
                line = json.dumps({"error": "the worker stopped"})
        answer = json.loads(line)
        if answer.get("error"):
            raise RuntimeError("CapCut: " + answer["error"][-800:])


_QUIET = {"count": 0, "emit": None}
_QUIET_LOCK = threading.Lock()


def _quiet(render, on: bool) -> None:
    """The renderer's progress silenced while a window is drawn: counted, so two windows drawn at once give it back."""
    with _QUIET_LOCK:
        if on:
            if _QUIET["count"] == 0:
                _QUIET["emit"] = render.emit
                render.emit = lambda *a, **k: None
            _QUIET["count"] += 1
        else:
            _QUIET["count"] -= 1
            if _QUIET["count"] == 0:
                render.emit = _QUIET["emit"]


def _near(layers: list[dict], start: float, end: float) -> list[dict]:
    """The layers with only the clips that reach [start - MARGIN, end + MARGIN]: a seam's window planned with the whole
    film's 500 layers probed and planned them all for each side. A film whose clips carry their own fades between
    neighbours (the legacy "transition") stays whole: dropping a neighbour would pair a fade with another clip."""
    def fades(clip):
        kind = clip.get("transition") or "cut"
        kind = kind.get("type") or "cut" if isinstance(kind, dict) else kind
        return str(kind).lower() not in {"cut", "none", "hard", "instant"}
    if any(fades(c) for layer in layers for c in layer.get("clips", [])):
        return layers
    first, last = start - MARGIN, end + MARGIN
    out = []
    for layer in layers:
        clips = [c for c in layer.get("clips", [])
                 if float(c.get("start", 0)) < last and float(c.get("start", 0)) + float(c.get("duration", 0)) > first]
        if clips:
            out.append({**layer, "clips": clips})
    return out


def _side(render, project: dict, project_file: Path, layers: list[dict], start: float, end: float,
          width: int, height: int, fps: int) -> tuple[str | None, int]:
    """[start, end) of `layers` drawn by the FFmpeg renderer as an H.264 video of whole frames (None when nothing is
    there) and its frame count; kept in the cache by everything it is drawn from.

    The window is drawn at the film's own size and scaled down only by the worker: text sizes, strokes and shadows are
    pixels of the film, so the editor's small 640 px preview drawn at 640 made every caption about three times too big
    for the length of the transition (user, 25 November 2026: «коли накладається перехід, різко міняються шрифти і
    розмір»)."""
    width, height = int(project.get("width") or width), int(project.get("height") or height)
    a, b = render.frame_index(start, fps), render.frame_index(end, fps)
    count = max(1, b - a)
    start, end = a / fps, (a + count) / fps   # whole frames, as the plan
    background = project.get("background", "#101114")
    key = _key("s", a, count, width, height, fps, background, layers, _sources_stamp(layers, project_file))
    path = cache_dir() / f"side-{key}.mp4"
    empty = path.with_suffix(".none")
    if empty.exists():
        _used(empty)
        return None, count
    if path.exists() and path.stat().st_size > 0:
        _used(path)
        return str(path), count
    _quiet(render, True)
    try:
        with tempfile.TemporaryDirectory(prefix=".capcut-window-", dir=cache_dir()) as temp:
            work = Path(temp)
            try:
                visual, _, total = render.timeline_plan({**project, "timeline_layers": layers}, project_file, width, height, fps)
            except ValueError as error:
                if "empty" not in str(error).lower():
                    raise
                visual, total = [], 0.0
            parts = []
            for index, (first, last, active) in enumerate(render.timeline_segments(visual, total, fps) if visual else [], 1):
                if min(last, end) - max(first, start) < 1 / fps - 1e-6:
                    continue
                scene = render.timeline_scene(max(first, start), min(last, end), active, work, width, height, background)
                folder = work / f"scene-{index:04d}"
                folder.mkdir()
                part = work / f"part-{index:04d}.mp4"
                render.render_scene(scene, project_file, part, folder, width, height, fps, index)
                parts.append(part)
            if not parts:
                empty.touch()
                return None, count
            listing = work / "parts.txt"
            listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
            tmp = work / "side.mp4"
            subprocess.run([render.FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                            "-c", "copy", str(tmp)], check=True)
            tmp.replace(path)
    finally:
        _quiet(render, False)
    _limit_cache(path)
    return str(path), count


def _strip(layers: list[dict], drop: set[str], top_z: float | None = None) -> list[dict]:
    """Layers without CapCut clips, without the clips in `drop` and (with top_z) without layers from top_z up."""
    out = []
    for index, layer in enumerate(layers):
        z = float(layer.get("z", layer.get("z_index", index)))
        if top_z is not None and z >= top_z - 1e-9:
            continue
        clips = [copy.deepcopy(c) for c in layer.get("clips", [])
                 if c.get("content_type") not in KINDS and c.get("id") not in drop and c.get("type", c.get("kind")) != "audio"]
        if clips:
            out.append({**layer, "z": z, "clips": clips})
    return out


def _used(path: Path) -> None:
    """A reused cache entry is fresh again: storage_tidy drops entries untouched for three days."""
    try:
        os.utime(path, None)
    except OSError:
        pass


# The cache's own limit: every change of a seam, a rule or the engine draws its transitions again in ProRes, and in one
# day of edits they took 27 GB and filled the Mac (25 November 2026). The least recently used go first.
# 1.5 GB: the studio's Mac had a few GB free and a 6 GB cache filled its disk (25 November 2026)
CACHE_LIMIT = int(1.5 * 1024 ** 3)
# what was drawn or used in the last hours stays, whatever the limit: an export drew its 36 seams (1.5 GB of ProRes) and
# the limit removed the first of them before the GPU read them, «scene 38 layer 5 not found» (26 November 2026); the
# studio's tidy (storage_tidy.capcut) trims the cache later
RECENT = 3 * 3600


def _limit_cache(keep: Path) -> None:
    try:
        now = time.time()
        entries = [p for p in cache_dir().iterdir() if p.is_file() and p.suffix in (".mov", ".mp4", ".raw", ".none") and p != keep]   # effect previews (webm) stay
        entries.sort(key=lambda p: p.stat().st_mtime)
        recent = [p for p in entries if now - p.stat().st_mtime < RECENT]
        entries = [p for p in entries if now - p.stat().st_mtime >= RECENT]
        total = sum(p.stat().st_size for p in entries + recent) + (keep.stat().st_size if keep.exists() else 0)
        for item in entries:
            if total <= CACHE_LIMIT:
                break
            size = item.stat().st_size
            item.unlink(missing_ok=True)
            total -= size
    except OSError:
        pass


def _movie(path: Path, job: dict, width: int, height: int) -> Path:
    if path.exists() and path.stat().st_size > 0:
        _used(path)
        return path
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.part{path.suffix}")   # one part per process: two renders of one seam at once
    job = {**job, "out": str(tmp), "out_width": width, "out_height": height}
    try:
        _Worker.get(width, height).run(job)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)   # a failed render leaves no part behind
    _limit_cache(path)
    return path


def _transition(render, project, project_file, clip, width, height, fps) -> str:
    entry = TRANSITIONS[clip["capcut_type"]]
    start, duration = float(clip["start"]), float(clip["duration"])
    end = start + duration
    exclude = set(clip.get("capcut_exclude") or [])
    a_layers = _near(_strip(project["timeline_layers"], exclude | set(clip.get("capcut_a_drop") or [])), start, end)
    b_layers = _near(_strip(project["timeline_layers"], exclude | set(clip.get("capcut_b_drop") or [])), start, end)
    key = _key("t", clip["capcut_type"], start, duration, width, height, fps, project.get("background"), a_layers, b_layers,
               _sources_stamp(a_layers + b_layers, project_file))
    path = cache_dir() / f"transition-direct-capcut-{key}{'.mp4' if PREVIEW else '.mov'}"
    if path.exists():
        _used(path)
        return str(path)
    _Worker.get(width, height)   # its imports run while the sides are drawn
    # both sides at once: each is a separate FFmpeg run of the same length (a transition's preview took about 6 s,
    # half of it these two one after the other; user, 25 November 2026: «таймлайн… дуже сильно висне»)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as pool:
        sides = [pool.submit(_side, render, project, project_file, layers, start, end, width, height, fps)
                 for layers in (a_layers, b_layers)]
        (a_video, n), (b_video, _) = sides[0].result(), sides[1].result()
    return str(_movie(path, {"codec": "mp4" if PREVIEW else "prores", "mode": "transition",
                             "index": int(clip["capcut_type"][-2:]) - 1, "package": str(package("capcut_transition", entry)),
                             "fps": fps, "frames": n, "a_video": a_video, "b_video": b_video,
                             "comp": float(entry.get("default_duration", 1.0))}, width, height))


def _overlay_loop(name: str, fps: int, width: int, height: int, intro: bool = True) -> tuple[str, float]:
    entry = EFFECTS[name]
    loop = OVERLAY_LOOP[name]
    frames = max(1, round(loop * fps))
    key = _key("o", name, fps, width, height, intro)
    path = cache_dir() / f"transition-direct-capcut-{key}.mov"
    index = int(name[-2:]) - 1
    _movie(path, {"mode": "overlay", "index": index, "package": str(package("capcut_effect", entry)), "fps": fps,
                  "frames": frames, "intro": intro, "seconds_offset": 0 if intro else 1.0}, width, height)
    return str(path), frames / fps


def _content(render, project, project_file, clip, layer_z, width, height, fps) -> str:
    entry = EFFECTS[clip["capcut_effect"]]
    start, duration = float(clip["start"]), float(clip["duration"])
    below = _near(_strip(project["timeline_layers"], set(clip.get("capcut_exclude") or []), top_z=layer_z),
                  start, start + duration)
    key = _key("c", clip["capcut_effect"], start, duration, width, height, fps, project.get("background"), below,
               _sources_stamp(below, project_file))
    path = cache_dir() / f"transition-direct-capcut-{key}.mov"
    if path.exists():
        _used(path)
        return str(path)
    _Worker.get(width, height)
    base, n = _side(render, project, project_file, below, start, start + duration, width, height, fps)
    return str(_movie(path, {"mode": "content", "index": int(clip["capcut_effect"][-2:]) - 1,
                             "package": str(package("capcut_effect", entry)), "fps": fps, "frames": n,
                             "base_video": base, "offset": 0}, width, height))


def _as_graphic(clip: dict, source: str, start: float, duration: float, suffix: str = "") -> dict:
    return {"id": str(clip.get("id", "capcut")) + suffix, "type": "animation", "content_type": "graphic_transition",
            "graphic_style": "capcut", "prepared_source": source, "start": start, "duration": duration,
            "trim_start": 0, "x": .5, "y": .5, "width": 1.0, "height": 1.0,
            "opacity": float(clip.get("opacity", 1) if clip.get("opacity") is not None else 1), "volume": 0,
            "easing": "linear"}


def _in_window(start: float, end: float) -> bool:
    window = os.environ.get("STUDIO_CAPCUT_WINDOW")
    if not window:
        return True
    try:
        first, last = (float(x) for x in window.split(","))
    except ValueError:
        return True
    return end > first - 1e-6 and start < last + 1e-6


def expand(project: dict, project_file: Path, width: int, height: int, fps: int, render) -> None:
    """Replaces the CapCut clips of `project["timeline_layers"]` with prepared graphic clips (in place, once)."""
    layers = project.get("timeline_layers")
    if not isinstance(layers, list) or project.get("_capcut_expanded"):
        return
    if not any(c.get("content_type") in KINDS for layer in layers if isinstance(layer, dict)
               for c in layer.get("clips", []) if isinstance(c, dict)):
        return
    dry = bool(getattr(render, "CAPCUT_DRY", False))
    # the film as it was, for the sides of the seams: the loop below only replaces each layer's list of clips
    original = {**project, "timeline_layers": [dict(layer) if isinstance(layer, dict) else layer for layer in layers]}
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        clips = []
        for clip in layer.get("clips", []):
            kind = clip.get("content_type") if isinstance(clip, dict) else None
            if kind not in KINDS:
                clips.append(clip)
                continue
            start, duration = float(clip["start"]), float(clip["duration"])
            if dry or not _in_window(start, start + duration):
                # outside a still's window (STUDIO_CAPCUT_WINDOW) the clip is never seen: it stays an empty placeholder
                # instead of a ProRes drawing (a still drew every transition of the film, up to five minutes)
                clips.append({**_as_graphic(clip, "", start, duration), "content_type": "shape", "color": "#000000",
                              "opacity": 0})
                continue
            if kind == "capcut_transition":
                if clip.get("capcut_type") not in TRANSITIONS:
                    raise ValueError(f"Unknown CapCut transition: {clip.get('capcut_type')}")
                clips.append(_as_graphic(clip, _transition(render, original, project_file, clip, width, height, fps),
                                         start, duration))
                continue
            name = clip.get("capcut_effect")
            if name not in EFFECTS:
                raise ValueError(f"Unknown CapCut effect: {name}")
            if EFFECTS[name]["mode"] == "content":
                clips.append(clip)   # second pass: it draws what lies below it, transitions and overlays included
                continue
            t, part = start, 0
            end = start + duration
            # the effect at its full from the frame's first moment, never building up from nothing at its start
            # or at each loop (user, 25 November 2026: «ефект… має від початку до кінця бути»)
            source, loop = _overlay_loop(name, fps, width, height, intro=False)
            while t < end - 1e-6:
                length = min(loop, end - t)
                frames = render.frame_index(t + length, fps) - render.frame_index(t, fps)
                if frames < 1:
                    break
                clips.append(_as_graphic(clip, source, t, length, f"-{part}"))
                t += length
                part += 1
        layer["clips"] = clips
    order = sorted(range(len(layers)), key=lambda i: float(layers[i].get("z", layers[i].get("z_index", i))) if isinstance(layers[i], dict) else 0)
    for index in order:
        layer = layers[index]
        if not isinstance(layer, dict):
            continue
        z = float(layer.get("z", layer.get("z_index", index)))
        for position, clip in enumerate(layer.get("clips", [])):
            if isinstance(clip, dict) and clip.get("content_type") == "capcut_effect":
                source = _content(render, project, project_file, clip, z, width, height, fps)
                layer["clips"][position] = _as_graphic(clip, source, float(clip["start"]), float(clip["duration"]))
    project["_capcut_expanded"] = True


def effect_preview(name: str, width: int = 640, height: int = 360, fps: int = 25) -> Path:
    """A loop of an effect for the editor as VP9 (the export's own drawing): an overlay with alpha, an effect that changes
    the frame over a sample picture (it had no loop length and answered 500)."""
    entry = EFFECTS[name]
    content = entry.get("mode") == "content"
    loop = 3.0 if content else OVERLAY_LOOP[name]
    path = cache_dir() / f"preview-{_key('p', name, width, height, fps)}.webm"
    job = {"codec": "webm", "mode": entry.get("mode", "overlay"), "index": int(name[-2:]) - 1, "fps": fps,
           "package": str(package("capcut_effect", entry)), "frames": max(1, round(loop * fps))}
    return _movie(path, {**job, "base_video": None, "offset": 0} if content else {**job, "intro": False, "seconds_offset": 1.0},
                  width, height)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="CapCut previews for the editor")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--clip")
    parser.add_argument("--effect")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    args = parser.parse_args()
    global PREVIEW
    PREVIEW = True
    try:
        if args.effect:
            print(json.dumps({"output": str(effect_preview(args.effect, args.width, args.height))}))
            return
        sys.path.insert(0, str(ENGINE))
        import render
        project = json.loads(args.manifest.read_text(encoding="utf-8"))
        fps = int(project.get("fps", 25))
        clip = next(c for layer in project["timeline_layers"] for c in layer.get("clips", []) if c.get("id") == args.clip)
        path = _transition(render, project, args.manifest, clip, args.width, args.height, fps)
        print(json.dumps({"output": path}))
    except (StopIteration, KeyError, ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({"error": str(error)[-1500:]}))
        sys.exit(1)


if __name__ == "__main__":
    main()
