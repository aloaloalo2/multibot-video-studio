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

Movies are cached by everything that makes them in backend/data/capcut-cache, so a still, a second export or the GPU
preparation re-use them.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
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
PLAYER = "capcut_e10"
PREVIEW = False  # set by the preview command: the browser plays H.264 and VP9  # «Плеєр 3»: one second of entrance, then a still loop


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
    return hashlib.sha256(json.dumps([VERSION, *parts], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:24]


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


def _worker(job: dict, width: int, height: int) -> None:
    pw, ph = work_size(width, height)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=cache_dir()) as handle:
        json.dump(job, handle)
        job_path = handle.name
    try:
        env = {**os.environ, "CAPCUT_W": str(pw), "CAPCUT_H": str(ph)}
        result = subprocess.run(["nice", "-n", "5", sys.executable, str(ENGINE / "capcut_worker.py"), job_path],
                                capture_output=True, text=True, env=env, timeout=3600)
        if result.returncode:
            raise RuntimeError("CapCut: " + (result.stderr or result.stdout)[-800:])
    finally:
        Path(job_path).unlink(missing_ok=True)


def _window(render, project: dict, project_file: Path, layers: list[dict], start: float, end: float,
            width: int, height: int, fps: int, out_raw: Path) -> int:
    """Draws [start, end) of `layers` with the FFmpeg renderer and saves the frames as raw RGB at the working size."""
    pw, ph = work_size(width, height)
    sub = {**project, "timeline_layers": layers}
    count = max(1, render.frame_index(end, fps) - render.frame_index(start, fps))
    start, end = render.frame_index(start, fps) / fps, render.frame_index(end, fps) / fps   # whole frames, as the plan
    silent = render.emit
    render.emit = lambda *a, **k: None
    try:
        with tempfile.TemporaryDirectory(prefix=".capcut-window-", dir=cache_dir()) as temp:
            work = Path(temp)
            try:
                visual, _, total = render.timeline_plan(sub, project_file, width, height, fps)
            except ValueError as error:
                if "empty" not in str(error).lower():
                    raise
                visual, total = [], 0.0
            parts = []
            if visual:
                for index, (first, last, active) in enumerate(render.timeline_segments(visual, total, fps), 1):
                    if min(last, end) - max(first, start) < 1 / fps - 1e-6:
                        continue
                    scene = render.timeline_scene(max(first, start), min(last, end), active, work, width, height,
                                                  project.get("background", "#101114"))
                    folder = work / f"scene-{index:04d}"
                    folder.mkdir()
                    part = work / f"part-{index:04d}.mp4"
                    render.render_scene(scene, project_file, part, folder, width, height, fps, index)
                    parts.append(part)
            if parts:
                listing = work / "parts.txt"
                listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
                video = work / "window.mp4"
                subprocess.run([render.FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                                "-c", "copy", str(video)], check=True)
                cmd = [render.FFMPEG, "-v", "error", "-y", "-i", str(video), "-vf",
                       f"scale={pw}:{ph}:flags=area,tpad=stop_mode=clone:stop_duration=2",
                       "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", str(out_raw)]
                subprocess.run(cmd, check=True)
                have = out_raw.stat().st_size // (pw * ph * 3)
                if have < count:
                    with out_raw.open("ab") as handle:
                        last = out_raw.read_bytes()[-(pw * ph * 3):] if have else bytes(pw * ph * 3)
                        handle.write(last * (count - have))
            else:
                out_raw.write_bytes(bytes(pw * ph * 3) * count)
    finally:
        render.emit = silent
    return count


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
            out.append({**layer, "clips": clips})
    return out


def _movie(path: Path, job: dict, width: int, height: int) -> Path:
    if path.exists() and path.stat().st_size > 0:
        return path
    tmp = path.with_name(path.stem + ".part" + path.suffix)
    job = {**job, "out": str(tmp), "out_width": width, "out_height": height}
    _worker(job, width, height)
    tmp.replace(path)
    return path


def _transition(render, project, project_file, clip, width, height, fps) -> str:
    entry = TRANSITIONS[clip["capcut_type"]]
    start, duration = float(clip["start"]), float(clip["duration"])
    end = start + duration
    exclude = set(clip.get("capcut_exclude") or [])
    a_layers = _strip(project["timeline_layers"], exclude | set(clip.get("capcut_a_drop") or []))
    b_layers = _strip(project["timeline_layers"], exclude | set(clip.get("capcut_b_drop") or []))
    key = _key("t", clip["capcut_type"], start, duration, width, height, fps, a_layers, b_layers,
               _sources_stamp(project["timeline_layers"], project_file))
    suffix = ".mp4" if PREVIEW else ".mov"
    path = cache_dir() / f"transition-direct-capcut-{key}{suffix}"
    if path.exists():
        return str(path)
    a_raw, b_raw = cache_dir() / f"{key}-a.raw", cache_dir() / f"{key}-b.raw"
    try:
        n = _window(render, project, project_file, a_layers, start, end, width, height, fps, a_raw)
        _window(render, project, project_file, b_layers, start, end, width, height, fps, b_raw)
        index = int(clip["capcut_type"][-2:]) - 1
        comp = float(entry.get("default_duration", 1.0))
        _movie(path, {"codec": "mp4" if PREVIEW else "prores", "mode": "transition", "index": index, "package": str(package("capcut_transition", entry)),
                      "fps": fps, "frames": n, "a_raw": str(a_raw), "b_raw": str(b_raw), "comp": comp}, width, height)
    finally:
        a_raw.unlink(missing_ok=True)
        b_raw.unlink(missing_ok=True)
    return str(path)


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
    below = _strip(project["timeline_layers"], set(clip.get("capcut_exclude") or []), top_z=layer_z)
    key = _key("c", clip["capcut_effect"], start, duration, width, height, fps, below,
               _sources_stamp(below, project_file))
    path = cache_dir() / f"transition-direct-capcut-{key}.mov"
    if path.exists():
        return str(path)
    raw = cache_dir() / f"{key}-base.raw"
    try:
        n = _window(render, project, project_file, below, start, start + duration, width, height, fps, raw)
        _movie(path, {"mode": "content", "index": int(clip["capcut_effect"][-2:]) - 1,
                      "package": str(package("capcut_effect", entry)), "fps": fps, "frames": n,
                      "base_raw": str(raw), "offset": 0}, width, height)
    finally:
        raw.unlink(missing_ok=True)
    return str(path)


def _as_graphic(clip: dict, source: str, start: float, duration: float, suffix: str = "") -> dict:
    return {"id": str(clip.get("id", "capcut")) + suffix, "type": "animation", "content_type": "graphic_transition",
            "graphic_style": "capcut", "prepared_source": source, "start": start, "duration": duration,
            "trim_start": 0, "x": .5, "y": .5, "width": 1.0, "height": 1.0,
            "opacity": float(clip.get("opacity", 1) if clip.get("opacity") is not None else 1), "volume": 0,
            "easing": "linear"}


def expand(project: dict, project_file: Path, width: int, height: int, fps: int, render) -> None:
    """Replaces the CapCut clips of `project["timeline_layers"]` with prepared graphic clips (in place, once)."""
    layers = project.get("timeline_layers")
    if not isinstance(layers, list) or project.get("_capcut_expanded"):
        return
    if not any(c.get("content_type") in KINDS for layer in layers if isinstance(layer, dict)
               for c in layer.get("clips", []) if isinstance(c, dict)):
        return
    dry = bool(getattr(render, "CAPCUT_DRY", False))
    original = {"timeline_layers": copy.deepcopy(layers), **{k: v for k, v in project.items() if k != "timeline_layers"}}
    for index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            continue
        z = float(layer.get("z", layer.get("z_index", index)))
        clips = []
        for clip in layer.get("clips", []):
            kind = clip.get("content_type") if isinstance(clip, dict) else None
            if kind not in KINDS:
                clips.append(clip)
                continue
            start, duration = float(clip["start"]), float(clip["duration"])
            if dry:
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
            while t < end - 1e-6:
                intro = part == 0
                source, loop = _overlay_loop(name, fps, width, height, intro=intro if name == PLAYER else True)
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
    """A loop of an overlay effect as VP9 with alpha for the editor's preview (the export's own drawing)."""
    entry = EFFECTS[name]
    loop = OVERLAY_LOOP[name]
    path = cache_dir() / f"preview-{_key('p', name, width, height, fps)}.webm"
    return _movie(path, {"codec": "webm", "mode": "overlay", "index": int(name[-2:]) - 1, "fps": fps,
                         "package": str(package("capcut_effect", entry)), "frames": max(1, round(loop * fps)),
                         "intro": False, "seconds_offset": 1.0}, width, height)


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
    except (StopIteration, ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({"error": str(error)[-1500:]}))
        sys.exit(1)


if __name__ == "__main__":
    main()
