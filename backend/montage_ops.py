"""Montage operations for agents: a few high-level requests become one batch of ordinary timeline actions.

POST /api/projects/<id>/ops {"ops": [...], "expected_revision": n, "dry_run": false} applies them as one undo step:

- {"op": "accent", "frame": 12, "kind": "text" | "arrow" | "circle" | "card" | "image", ...} puts a caption, an
  arrow, a ring, a card or a picture into the frame's group, glued to the frame's photo: its keyframes repeat the
  photo's pan and zoom, so it never slides off the thing it marks. Points and sizes are pixels of the project frame as
  it looks at the frame's middle moment (the still from GET .../still shows exactly that), or with "space": "photo"
  fractions of the picture itself. A caption takes its words' times from the voice ("phrase", or "text" that the voice
  says in the frame) or appears at "appear" seconds into the frame; arrows and rings appear on "word" or at "appear".
- {"op": "clear_accents", "frame": 12} removes the accents a frame got from "accent" (titles «K012 акцент …»).
- {"op": "replace", "clip": id, "path": file | "asset_id": id} swaps a clip's picture and keeps its title, box and motion.
- {"op": "transitions", ...} designs the seams between frames by the channel rules; "share": 0.7 sets a share instead.
- {"op": "remove", "frame": 12} takes the frame off the timeline with its whole group.
- {"op": "place", "frame": 12, "path": file | "asset_id": id | "text": true, "motion": "zoom_in"} puts a frame of the
  plan on the timeline at the plan frame's time, in its group «Кадр 12»: a picture or a video, still unless the director
  explicitly names its "motion" (zoom_in, zoom_out, pan_left, pan_right), or with "text" the frame's own spoken words as a full-frame text. The frame agent of
  the photo channels (backend/production.py) builds the film with it.

The answer is short (the report lines and the new revision), so an agent does not have to read the whole project back.
"""
from __future__ import annotations

import hashlib
import json
import os
import math
import random
import re
import subprocess
import uuid
from functools import cached_property
from pathlib import Path

from PIL import Image, ImageDraw

import display_text
import native_animation
import soundtrack
import joins
import store
import channel_design
import style_lab
import typography
import word_timing

YELLOW, NAVY, INK, WHITE = "#ffd23a", "#0b2f78", "#101418", "#ffffff"
STYLES = {   # text colour, card colour (None: no card), shadow of the text
    "plain": (WHITE, None, None),
    "card": (WHITE, NAVY, None),
    "tag": (NAVY, WHITE, None),
    "yellow": (YELLOW, None, None),
    "white": (WHITE, None, None),
}
# The channel rule (AGENTS.md, 28 October 2026): about 70% of the seams between frames get a designed transition, varied
# but calm; a full-frame text frame starts with a cut, its first word must show at once.
DEFAULT_POOL = ["crossfade"] * 10 + ["slide_left", "slide_right", "zoom_in", "zoom_out", "cin_pearl_mist", "cin_blue_moon", "cin_arctic_mist"]


class OpError(store.StudioError):
    pass


# ---------------------------------------------------------------- keyframes, as the preview and the export read them

def eased(p: float, mode: str) -> float:
    p = max(0.0, min(1.0, p))
    return p ** 3 if mode == "ease_in" else 1 - (1 - p) ** 3 if mode == "ease_out" else p * p * (3 - 2 * p) if mode == "ease_in_out" else p


def keyframe_value(clip: dict, prop: str, local: float) -> float:
    """engine/render.py scalar_value after timeline_plan: a first keyframe later than 0 starts from the clip's value."""
    base = float(clip.get(prop, .5 if prop in ("x", "y") else 1.0))
    known = sorted((float(p["time"]), float(p[prop])) for p in clip.get("keyframes") or [] if prop in p)
    if not known:
        return base
    if known[0][0] > 1e-9:
        known.insert(0, (0.0, base))
    if local <= known[0][0]:
        return known[0][1]
    for (t0, a), (t1, b) in zip(known, known[1:]):
        if local < t1:
            return a + (b - a) * eased((local - t0) / (t1 - t0), clip.get("easing", "linear"))
    return known[-1][1]


def end_time(duration: float) -> float:
    """The last keyframe moment, never past the clip's end."""
    return math.floor(duration * 1000) / 1000


# ---------------------------------------------------------------- frames and their photos

def frame_groups(project: dict, plan: dict | None = None) -> list[dict]:
    """The frame groups in time order: {"group", "number", "start", "end", "clips", "plan"}."""
    clips = {c["id"]: c for t in project.get("tracks", []) for c in t.get("clips", [])}
    by_number = {f["number"]: f for f in (plan or {}).get("frames", [])}
    result = []
    for group in project.get("scene_groups", []):
        if group.get("role") == "overlay":
            continue
        members = [clips[cid] for cid in group.get("clip_ids", []) if cid in clips]
        if not members:
            continue
        match = re.fullmatch(r"Кадр (\d+)", str(group.get("title", "")).strip())
        number = int(match.group(1)) if match else None
        result.append({"group": group, "number": number, "start": min(float(c["start"]) for c in members),
                       "end": max(float(c["start"]) + float(c["duration"]) for c in members), "clips": members, "plan": by_number.get(number)})
    result.sort(key=lambda f: (f["start"], f["end"]))
    return result


def find_frame(frames: list[dict], ref) -> dict:
    for frame in frames:
        if ref == frame["number"] or ref == frame["group"]["id"] or isinstance(ref, str) and ref.strip() == str(frame["group"].get("title", "")).strip():
            return frame
    if isinstance(ref, str) and ref.isdigit():
        return find_frame(frames, int(ref))
    raise OpError(f"Кадр {ref} не знайдено", 404)


def is_accent(clip: dict) -> bool:
    return bool(re.search(r"(^|\s)акцент(\s|$)", str(clip.get("title", ""))))


_SIZES: dict[tuple, tuple[int, int] | None] = {}


def media_size(path: str) -> tuple[int, int] | None:
    """The picture's display size (a video's frame turned by its rotation), measured once per file version: the summary
    and every placing operation ask it for each video, and ffprobe takes a moment each time."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _SIZES:
        _SIZES[key] = _measure_size(path)
    return _SIZES[key]


def _measure_size(path: str) -> tuple[int, int] | None:
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, ValueError):
        pass
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
                              "-of", "json", path], capture_output=True, text=True, timeout=30).stdout
        stream = json.loads(out)["streams"][0]
        rotation = stream.get("tags", {}).get("rotate") or next((d.get("rotation") for d in stream.get("side_data_list", []) if "rotation" in d), 0)
        size = (int(stream["width"]), int(stream["height"]))
        return size[::-1] if round(abs(float(rotation))) % 180 == 90 else size
    except (OSError, ValueError, KeyError, IndexError, TypeError, subprocess.TimeoutExpired):
        return None


class Picture:
    """A frame's main photo or video as the export draws it: contained in its box, moved by its keyframes."""

    def __init__(self, project: dict, clip: dict):
        self.clip, self.W, self.H = clip, float(project.get("width", 1920)), float(project.get("height", 1080))
        box_w, box_h = float(clip.get("width", 1)) * self.W, float(clip.get("height", 1)) * self.H
        asset = store.resolve_asset(project, clip["asset_id"])
        size = media_size(asset["path"]) if clip.get("mask") != "circle" else None
        self.portrait = bool(size and size[0] < size[1])
        if size and size[0] and size[1] and abs(size[0] / size[1] - box_w / box_h) > 1e-3:
            aspect = size[0] / size[1]
            box_w, box_h = (box_w, box_w / aspect) if aspect > box_w / box_h else (box_h * aspect, box_h)
        self.cw, self.ch = box_w, box_h
        self.duration = float(clip["duration"])

    def state(self, local: float) -> tuple[float, float, float]:
        return tuple(keyframe_value(self.clip, prop, local) for prop in ("x", "y", "scale"))

    def to_frame(self, u: float, v: float, local: float) -> tuple[float, float]:
        x, y, s = self.state(local)
        return x * self.W + (u - .5) * self.cw * s, y * self.H + (v - .5) * self.ch * s

    def to_photo(self, px: float, py: float, local: float) -> tuple[float, float]:
        x, y, s = self.state(local)
        return .5 + (px - x * self.W) / (self.cw * s), .5 + (py - y * self.H) / (self.ch * s)

    def covers(self, px: float, py: float, local: float) -> bool:
        u, v = self.to_photo(px, py, local)
        return 0 <= u <= 1 and 0 <= v <= 1

    def times(self, duration: float) -> list[float]:
        """Moments at which a glued clip needs a keyframe: the photo's own ones, or a dense row where its properties
        change at different moments under a curved easing (then no single keyframe row follows it exactly)."""
        rows = {prop: {float(p["time"]) for p in self.clip.get("keyframes") or [] if prop in p} for prop in ("x", "y", "scale")}
        moments = {0.0, end_time(duration)} | set().union(*rows.values())
        filled = [row for row in rows.values() if row]
        if self.clip.get("easing", "linear") != "linear" and any(row != filled[0] for row in filled):
            moments |= {k / 10 for k in range(int(duration * 10) + 1)}
        return sorted(t for t in moments if 0 <= t <= end_time(duration))


def is_background(clip: dict) -> bool:
    """The blurred copy under a vertical photo or a text frame («K012 фон»): it moves its own way, nothing glues to it."""
    return str(clip.get("title", "")).endswith(" фон")


def main_picture(project: dict, frame: dict) -> dict | None:
    pictures = [c for c in frame["clips"] if not is_accent(c) and not is_background(c) and c.get("asset_id") and
                (c.get("kind") in ("image", "video") or c.get("kind") == "animation" and c.get("content_type") == "image")]
    return max(pictures, key=lambda c: float(c.get("width", 1)) * float(c.get("height", 1)), default=None)


def merge(*rows: list[dict]) -> list[dict]:
    by_time = {}
    for row in rows:
        for point in row:
            by_time.setdefault(round(float(point["time"]), 6), {"time": round(float(point["time"]), 6)}).update({k: v for k, v in point.items() if k != "time"})
    return sorted(by_time.values(), key=lambda p: p["time"])


# ---------------------------------------------------------------- how an accent comes in
# The user, 6 November 2026: «активной анимации… красивое появление, типа стрелочки… которая указывает на то место,
# куда нужно. Кружочек, который появляется». The engine moves a clip by x, y, scale and opacity under one easing, so a
# glued accent keeps its photo's slow curve, and its entrance plays in a second, short clip on top (title «… поява …»,
# linear, a keyframe each 0.04 s): an arrow grows out of its tail towards the point and jabs at it twice, a ring closes
# in on its target from 1.7× and pulses, a card springs open, an underline is drawn from its left end. The glued clip
# stays invisible until the entrance ends.

ENTRANCE = {"стрілка": 1.5, "коло": 1.4, "картка": .5, "риска": .5, "картинка": .6}
STEP = .04


def _back_out(p: float) -> float:
    p = max(0.0, min(1.0, p)) - 1
    return 1 + 2.70158 * p ** 3 + 1.70158 * p ** 2


def _entrance_state(kind: str, tau: float, top: float) -> tuple[float, float, float]:
    """(grow, jab in px along the arrow, opacity) at `tau` seconds into the entrance."""
    if kind == "стрілка":
        grow = .15 + .85 * _back_out(tau / .32)
        jab = 16 * abs(math.sin(math.pi * (tau - .75) / .3)) if .75 <= tau <= 1.35 else 0.0
        return grow, jab, top * min(1.0, tau / .1)
    if kind == "коло":
        grow = 1.7 - .7 * _back_out(tau / .38)
        if .85 <= tau <= 1.25:
            grow *= 1 + .08 * math.sin(math.pi * (tau - .85) / .4)
        return grow, 0.0, top * min(1.0, tau / .15)
    if kind == "риска":
        return .04 + .96 * (1 - (1 - min(1.0, tau / .35)) ** 3), 0.0, top * min(1.0, tau / .08)
    return .6 + .4 * _back_out(tau / .3), 0.0, top * min(1.0, tau / .12)


def accent_kind(clip: dict) -> str:
    return str(clip.get("title", "")).split()[-1]


def accent_index(clip: dict) -> str:
    """The number an accent has in its frame («K012 акцент 2 текст» → "2"): a caption and its card or underline share it."""
    return (str(clip.get("title", "")).split(" акцент ", 1)[-1].split() or [""])[0]


def is_entrance(clip: dict) -> bool:
    return " поява " in f" {clip.get('title', '')} "


def _arrow_ends(path) -> tuple[tuple[float, float], tuple[float, float]]:
    """Tail and head of a drawn arrow, in pixels from the picture's centre: the two ends farthest apart, the head the
    one with more ink around it (its triangle)."""
    image = Image.open(path).getchannel("A")
    k = max(1, max(image.size) // 160)
    small = image.resize((max(1, image.width // k), max(1, image.height // k)))
    ink = [(x * k, y * k) for y in range(small.height) for x in range(small.width) if small.getpixel((x, y)) > 128]
    if len(ink) < 2:
        return (-image.width / 4, 0.0), (image.width / 4, 0.0)
    cx, cy = sum(x for x, _ in ink) / len(ink), sum(y for _, y in ink) / len(ink)
    a = max(ink, key=lambda q: (q[0] - cx) ** 2 + (q[1] - cy) ** 2)
    b = max(ink, key=lambda q: (q[0] - a[0]) ** 2 + (q[1] - a[1]) ** 2)
    def width(end, other):     # the ink across the arrow a little way in from this end: the head's triangle is wider
        dx, dy = other[0] - end[0], other[1] - end[1]
        norm = math.hypot(dx, dy) or 1.0
        dx, dy = dx / norm, dy / norm
        cx, cy = end[0] + dx * 20, end[1] + dy * 20
        hits = 0
        for step in range(-40, 41):
            x, y = int(cx - dy * step), int(cy + dx * step)
            if 0 <= x < image.width and 0 <= y < image.height and image.getpixel((x, y)) > 128:
                hits += 1
        return hits
    tail, head = (a, b) if width(b, a) >= width(a, b) else (b, a)
    centre = (image.width / 2, image.height / 2)
    return (tail[0] - centre[0], tail[1] - centre[1]), (head[0] - centre[0], head[1] - centre[1])


def _anchor(ctx: Context, kind: str, payload: dict, path=None):
    """The point an accent grows from (px from its centre at scale 1) and the unit direction it jabs in."""
    if kind == "стрілка" and path:
        tail, head = _arrow_ends(path)
        length = math.hypot(head[0] - tail[0], head[1] - tail[1]) or 1.0
        return tail, ((head[0] - tail[0]) / length, (head[1] - tail[1]) / length)
    if kind == "риска":
        return (-float(payload["width"]) * ctx.W / 2, 0.0), (1.0, 0.0)
    return (0.0, 0.0), (0.0, 0.0)


def animated(ctx: Context, frame: dict, picture, title: str, payload: dict, keys: list[dict], base: dict, at: float,
             duration: float, top: float = 1.0, path=None, motion: str = "animated") -> None:
    """Add a glued accent with its entrance: the glued clip appears when the entrance ends, the entrance clip plays
    from `at` (seconds into the clip) over it."""
    kind = title.split()[-1]
    length = ENTRANCE.get(kind, .6)
    if motion == "animated" and max(at, 0) + length + .08 > duration:
        motion = "fade"
    if motion in {"still", "fade"}:
        at = max(0.0, min(at, duration))
        end = min(duration, at + (.22 if motion == "fade" else 0))
        fades = [{"time": 0, "opacity": 0}, {"time": max(0, at - (.001 if motion == "still" else 0)), "opacity": 0},
                 {"time": end, "opacity": top}]
        ctx.add(frame, picture, title, {**payload, **base, "opacity": top, "keyframes": merge(keys, fades), "accent_motion": motion})
        return
    if motion != "animated":
        raise OpError("Невідомий рух акценту")
    at = max(0.0, at)
    shown = round(at + length, 3)
    fades = [{"time": 0.0, "opacity": 0.0}, {"time": round(shown - .001, 3), "opacity": 0.0}, {"time": shown, "opacity": top}]
    steady = {**payload, **base, "scale": 1.0, "opacity": top, "keyframes": merge(keys, fades)}
    ctx.add(frame, picture, title, steady)
    ctx.actions.append(_entrance_action(ctx, frame, picture, title, steady, at, length, top, path))


def _entrance_action(ctx, frame, picture, title, steady, at, length, top, path) -> dict:
    kind = title.split()[-1]
    clip = {**steady, "easing": (picture.clip.get("easing", ctx.easing) if picture else ctx.easing)}
    (ox, oy), (dx, dy) = _anchor(ctx, kind, steady, path)
    points, tau = [], 0.0
    span = length if top < 1 else length + .08  # translucent layers would darken if both were visible
    while tau <= span + 1e-9:
        t = at + tau
        px, py, s = keyframe_value(clip, "x", t) * ctx.W, keyframe_value(clip, "y", t) * ctx.H, keyframe_value(clip, "scale", t)
        grow, jab, opacity = _entrance_state(kind, min(tau, length), top)
        cx, cy = px - (grow - 1) * s * ox + dx * jab * s, py - (grow - 1) * s * oy + dy * jab * s
        points.append({"time": round(tau, 3), "x": round(cx / ctx.W, 5), "y": round(cy / ctx.H, 5),
                       "scale": round(max(.05, s * grow), 5), "opacity": round(opacity, 4)})
        tau = round(tau + STEP, 6)
    start = float(picture.clip["start"]) if picture else frame["start"]
    words = title.split()
    named = " ".join(words[:-1] + ["поява", words[-1]])
    keep = ("kind", "asset_id", "content_type", "color", "width", "height", "mask", "corner_radius", "shadow")
    return {"type": "add_clip", "payload": {"layer_id": ctx.project["tracks"][0]["id"], "group_id": frame["group"]["id"],
                                            "start": round(start + at, 3), "duration": round(span, 3), "easing": "linear",
                                            "title": f"{ctx.prefix(frame)} акцент {named}", "x": points[0]["x"], "y": points[0]["y"],
                                            "scale": 1.0, "opacity": top, "keyframes": points, **{k: steady[k] for k in keep if k in steady}}}


# ---------------------------------------------------------------- drawn accents

def draw_arrow(path: Path, tail, head, bend: float, colors, style: dict | None = None):
    """A hand-drawn arrow with a dark edge, in the channel's own style (channel_design: stroke, edge, head shape and
    size); returns its canvas centre and size in frame pixels."""
    style = style or {}
    stroke, rim = int(style.get("stroke", 9)), int(style.get("edge_width", 4))
    shape, factor = style.get("head", "filled"), float(style.get("head_size", 3.8))
    (x0, y0), (x1, y1) = tail, head
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 8:
        raise OpError("Стрілка надто коротка")
    nx, ny = -(y1 - y0) / length, (x1 - x0) / length
    cx, cy = (x0 + x1) / 2 + nx * bend * length, (y0 + y1) / 2 + ny * bend * length
    pts = [((1 - u) ** 2 * x0 + 2 * (1 - u) * u * cx + u * u * x1, (1 - u) ** 2 * y0 + 2 * (1 - u) * u * cy + u * u * y1) for u in [i / 40 for i in range(41)]]
    ang, size = math.atan2(y1 - pts[-4][1], x1 - pts[-4][0]), max(18, stroke * factor)
    spread = .5 if shape != "barb" else .38
    tip = [(x1 + math.cos(ang) * 6, y1 + math.sin(ang) * 6), (x1 - math.cos(ang - spread) * size, y1 - math.sin(ang - spread) * size),
           (x1 - math.cos(ang + spread) * size, y1 - math.sin(ang + spread) * size)]
    xs, ys = [p[0] for p in pts + tip], [p[1] for p in pts + tip]
    left, top, right, bottom = min(xs) - 30, min(ys) - 30, max(xs) + 30, max(ys) + 30
    scale = 2
    image = Image.new("RGBA", (int((right - left) * scale), int((bottom - top) * scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    at = lambda p: ((p[0] - left) * scale, (p[1] - top) * scale)
    body = pts[:-3]
    fill, edge = colors
    draw.line([at(p) for p in body], fill=edge, width=(stroke + 2 * rim) * scale, joint="curve")
    if shape == "open":   # two strokes, no filled head
        for wing in tip[1:]:
            draw.line([at(tip[0]), at(wing)], fill=edge, width=(stroke + 2 * rim) * scale)
        for wing in tip[1:]:
            draw.line([at(tip[0]), at(wing)], fill=fill, width=stroke * scale)
    else:
        draw.polygon([at(p) for p in tip], fill=edge, outline=edge, width=2 * rim * scale)
    draw.line([at(p) for p in body], fill=fill, width=stroke * scale, joint="curve")
    if shape != "open":
        draw.polygon([at(p) for p in tip], fill=fill)
    image.resize((image.width // scale, image.height // scale), Image.LANCZOS).save(path)
    return ((left + right) / 2, (top + bottom) / 2), (right - left, bottom - top)


def draw_circle(path: Path, radii, colors, line="solid", style: dict | None = None):
    style = style or {}
    ring, rim = int(style.get("ring_width", 8)), int(style.get("edge_width", 4))
    rx, ry = radii
    margin, scale = 24, 2
    image = Image.new("RGBA", (int((2 * rx + 2 * margin) * scale), int((2 * ry + 2 * margin) * scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    box = [margin * scale, margin * scale, (2 * rx + margin) * scale, (2 * ry + margin) * scale]
    fill, edge = colors
    inset = min(3 * scale, int(min(rx, ry) * scale / 2))
    inner = [v + (inset if i < 2 else -inset) for i, v in enumerate(box)]
    if line == "dashed":
        count = max(6, round(math.pi * (rx + ry) / 35))
        for i in range(count):
            start, end = 360 * i / count, 360 * (i + .62) / count
            draw.arc(box, start, end, fill=edge, width=(ring + 2 * rim) * scale)
            draw.arc(inner, start, end, fill=fill, width=ring * scale)
    else:
        draw.ellipse(box, outline=edge, width=(ring + 2 * rim) * scale)
        draw.ellipse(inner, outline=fill, width=ring * scale)
    image.resize((image.width // scale, image.height // scale), Image.LANCZOS).save(path)
    return (2 * rx + 2 * margin, 2 * ry + 2 * margin)


# ---------------------------------------------------------------- the operation context

def project_plan(project: dict) -> dict | None:
    """The plan of a project already in hand. store.load_project_plan reads the project again first (0.3–0.6 s on a long
    episode, the half of every operation's time on Andromeda); a project without a plan file of its own still asks it."""
    try:
        if project.get("plan_source"):
            path = store.project_plan_file(project)
            return store.cached_plan(path)[0] if path else None
        return store.load_project_plan(project["id"])
    except (store.StudioError, OSError, ValueError):
        return None


def channel_settings(project: dict) -> dict:
    """The saved settings of the project's channel; empty without a channel."""
    if not project.get("channel_id"):
        return {}
    try:
        return store.read_channel_settings(store.get_channel_folder(project["channel_id"], include_disabled=True), {}) or {}
    except (store.StudioError, OSError, ValueError):
        return {}


_WORDS: dict[str, tuple[tuple, list]] = {}


def aligned_words(pid: str) -> list[dict]:
    """The voice's words with their time from the latest recognition (analysis_jobs.latest without its third read of the
    project), kept per version of the report file: every text frame and caption asks them."""
    try:
        pointer = store.read_json(store.project_dir(pid) / "analysis-state.json", {}) or {}
        if not pointer.get("job_id"):
            return []
        job = store.read_json(store.DATA_ROOT / "jobs" / (pointer["job_id"] + ".json")) or {}
        if job.get("project_id") != pid or job.get("type") != "speech":
            return []
        path = store.project_dir(pid) / "analysis" / job["id"] / "result.json"
        stat = path.stat()
        key = (stat.st_size, stat.st_mtime_ns)
        cached = _WORDS.get(str(path))
        if not cached or cached[0] != key:
            cached = (key, (store.read_json(path) or {}).get("aligned_words") or [])
            _WORDS[str(path)] = cached
        return cached[1]
    except (store.StudioError, OSError, ValueError, KeyError, TypeError):
        return []


class Context:
    text_look = "varied"   # the channel's look of text frames; a context made without __init__ (tests) keeps the default

    def __init__(self, project: dict):
        self.project = project
        self.W, self.H = float(project.get("width", 1920)), float(project.get("height", 1080))
        self.plan = project_plan(project)
        self.frames = frame_groups(project, self.plan)
        self._words = None
        self.files: list[Path] = []          # pictures drawn for this request, registered as assets before the batch
        self.actions: list[dict] = []
        self.groups: dict[str, str] = {}     # clip title -> the new frame group it opens (place)
        self.report: list[str] = []
        self.easing = project.get("settings", {}).get("motion_easing", "ease_in_out")
        # per-channel looks (saved channel settings): the project snapshot first, the channel's current file else, so a
        # project made before the setting still follows it
        self.channel = channel = channel_settings(project)
        self.text_look = project.get("settings", {}).get("text_look") or channel.get("text_look", "varied")
        self.animation_style = channel.get("animation") or project.get("settings", {}).get("animation") or {}
        # the channel's montage fonts (settings «Шрифти монтажу»): text frames take the main one, captions and accents the
        # accent one (user, 16 November 2026: «перевір, чи воно дійсно його використовує»). A font set on the project
        # itself still wins, as before.
        fonts = channel.get("typography") or {}
        self.unified_font = fonts.get("unified") is True
        self.text_font = project.get("font_family") or fonts.get("font_family") or "Golos"
        self.accent_font = project.get("font_family") or fonts.get("accent_font_family") or fonts.get("font_family") or "Montserrat"

    @cached_property
    def accent_look(self) -> dict:
        """The channel's arrows and rings (channel_design.accent_style reads the channel's settings and kit each time)."""
        return channel_design.accent_style(self.project)

    @cached_property
    def accent_color(self):
        # the channel's own colour from its style, else its design kit's (never one colour shared by every channel)
        # the style this film was made in: the director picks one of the styles the author starred (26 November 2026)
        style = dict(self.animation_style)
        try:
            link = store.razgon_link(self.project)
            used = json.loads((Path(link["project"]) / "config.json").read_text(encoding="utf-8")).get("style") if link else None
            if isinstance(used, str) and used:
                style["style"] = used
        except (OSError, ValueError, KeyError, TypeError, store.StudioError):
            pass
        return style_lab.accent_color(self.project.get("channel_id"), style) or channel_design.for_project(self.project)["palette"]["accent"]

    def words(self) -> list[dict]:
        if self._words is None:
            self._words = aligned_words(self.project["id"])
        return self._words

    def tokens(self, frame: dict) -> list[tuple[str, float]]:
        if not frame.get("plan"):
            raise OpError(f"Кадр {frame['number']} без кадру плану: задайте час появи (appear)")
        if not self.words():
            raise OpError("Немає слів озвучки з часом: спершу розпізнавання, або задайте час появи (appear)")
        try:
            return word_timing.frame_tokens(frame["plan"], self.words())
        except ValueError as error:
            raise OpError(str(error)) from None

    def asset_for(self, path: Path) -> str:
        """An asset id for a file: an existing asset with the same path, or one registered before the batch. A file from
        the episode folder or the studio's own project folder is copied into the studio's media first (adopted)."""
        resolved = Path(path).resolve()
        for candidate in dict.fromkeys([resolved, self.adopted(resolved)]):
            for asset in self.project.get("assets", []):
                if asset.get("path") == str(candidate):
                    return asset["id"]
        resolved = self.adopted(resolved)
        if resolved not in self.files:
            self.files.append(resolved)
        return store.asset_record(resolved, self.project["id"])["id"]

    def adopted(self, path: Path) -> Path:
        """The studio's own copy of a picture an agent left in the episode folder or in the project's work folder: the
        episode folder is the author's, for scripts, sources, previews and the finished video only (user, 25 November
        2026: «папка кадри… це типу сміття технічне, мені взагалі тут в таких папках не потрібно»). The copy is named by
        its content, so the same file placed again reuses it; the original is left where it is."""
        media = store.media_dir(self.project)
        if not path.is_file() or store.under(path, media):
            return path
        episode = self.project.get("episode_path")
        if not ((episode and store.under(path, Path(episode))) or store.under(path, store.project_dir(self.project["id"]))):
            return path   # the batch refuses it as a file outside the episode
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        folder = media / "adopted"
        folder.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^\w. -]", "_", path.stem).strip(". ")[:60] or "asset"
        target = folder / f"{stem}-{digest.hexdigest()[:12]}{path.suffix.lower()}"
        if not target.is_file():
            temporary = folder / (".adopt-" + uuid.uuid4().hex)
            try:
                store.clone_or_copy(path, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return target.resolve()

    def drawn_file(self, kind: str, spec: dict) -> Path:
        folder = store.media_dir(self.project) / "accents"
        folder.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(json.dumps([kind, spec], sort_keys=True, default=str).encode()).hexdigest()[:16]
        return folder / f"{kind}-{digest}.png"

    def prefix(self, frame: dict) -> str:
        return f"K{frame['number']:03d}" if frame["number"] is not None else str(frame["group"].get("title") or frame["group"]["id"])[:40]

    def add(self, frame: dict, picture: Picture | None, title: str, payload: dict) -> None:
        clip = picture.clip if picture else None
        start = float(clip["start"]) if clip else frame["start"]
        duration = float(clip["duration"]) if clip else frame["end"] - frame["start"]
        self.actions.append({"type": "add_clip", "payload": {"layer_id": self.project["tracks"][0]["id"], "group_id": frame["group"]["id"],
                                                             "start": round(start, 3), "duration": round(duration, 3), "easing": clip.get("easing", self.easing) if clip else self.easing,
                                                             "title": f"{self.prefix(frame)} акцент {title}", **payload}})


# ---------------------------------------------------------------- operations

def _point(ctx: Context, picture: Picture | None, spec: dict, key: str, mid: float) -> tuple[float, float]:
    """A point of the request in frame pixels at the frame's middle moment."""
    value = spec.get(key)
    if not (isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)):
        raise OpError(f"Потрібна точка «{key}»: [x, y]")
    if spec.get("space") == "photo":
        if picture is None:
            raise OpError("У кадрі немає фото, до якого прив'язати точку")
        return picture.to_frame(float(value[0]), float(value[1]), mid)
    return float(value[0]), float(value[1])


def _glued(picture: Picture | None, centre: tuple[float, float], mid: float, duration: float, ctx: Context, pin: bool = True) -> tuple[list[dict], dict]:
    """Keyframes that keep a clip centred on `centre` (frame px at the middle moment) glued to the moving photo, and
    the clip's own x and y at its start."""
    if picture is None or not pin:
        return [], {"x": centre[0] / ctx.W, "y": centre[1] / ctx.H}
    u, v = picture.to_photo(centre[0], centre[1], mid)
    reference = picture.state(mid)[2]
    points = []
    for moment in picture.times(duration):
        px, py = picture.to_frame(u, v, moment)
        points.append({"time": round(moment, 3), "x": round(px / ctx.W, 5), "y": round(py / ctx.H, 5), "scale": round(picture.state(moment)[2] / reference, 5)})
    return points, {"x": points[0]["x"], "y": points[0]["y"]}


LAST_QUIET = 1.0   # seconds at a frame's end in which nothing new comes on screen


def _quiet_end(frame: dict, start: float, at: float) -> float:
    """`at` (seconds from the clip start) moved out of the frame's last second: something that came in there was gone at
    once with the transition (user, 25 November 2026: «за секунду до кінця кадра нічого не може появлятися, це
    заборонено»)."""
    return max(0.0, min(at, float(frame["end"]) - start - LAST_QUIET))


def _moment(ctx: Context, frame: dict, spec: dict, start: float) -> float:
    """When an accent appears, in seconds from its clip start: "appear", or the moment the voice says "word"; never in
    the frame's last second."""
    if "appear" in spec:
        return _quiet_end(frame, start, float(spec["appear"]))
    if spec.get("word"):
        try:
            return _quiet_end(frame, start, word_timing.word_time(ctx.tokens(frame), spec["word"]) - start)
        except ValueError as error:
            raise OpError(str(error)) from None
    return _quiet_end(frame, start, 0.3)


def _text_layout(ctx: Context, words: list[tuple[str, float]], width: float, height: float, size: int, family: str, weight: int, clip_start: float):
    def lay(box):
        stub = {"width": box / ctx.W, "height": height / ctx.H, "font_size": size, "font_weight": weight,
                "text_words": [{"text": t, "start": round(max(0.0, s - clip_start), 3), "x": .5, "y": .5, "width": .1, "height": .1} for t, s in words]}
        typography.reflow({"width": ctx.W, "height": ctx.H}, stub, family)
        return stub, len({w["y"] for w in stub["text_words"]})
    # `width` is the longest row; reflow fills 76% of its box. The box then narrows while the text keeps its rows and
    # size, so a two-row label breaks in the middle instead of leaving one word below
    box = width / 0.76
    stub, rows = lay(box)
    while box > 200:
        trial, count = lay(box - 12)
        inside = all(0 <= w["x"] - w["width"] / 2 and w["x"] + w["width"] / 2 <= 1 for w in trial["text_words"])
        if count != rows or trial["font_size"] != stub["font_size"] or not inside:
            break
        box, stub = box - 12, trial
    return box, stub


def accent(ctx: Context, spec: dict) -> None:
    frame = find_frame(ctx.frames, spec.get("frame"))
    clip = main_picture(ctx.project, frame)
    picture = Picture(ctx.project, clip) if clip else None
    duration = picture.duration if picture else frame["end"] - frame["start"]
    start = float(clip["start"]) if clip else frame["start"]
    mid = duration / 2
    kind = spec.get("kind")
    index = (sum(1 for c in frame["clips"] if is_accent(c) and not is_entrance(c)) +
             sum(1 for a in ctx.actions if a["type"] == "add_clip" and a["payload"].get("group_id") == frame["group"]["id"] and not is_entrance(a["payload"])))
    motion = spec.get("motion", "animated")
    if kind in {"arrow", "circle"}:
        colors = (spec.get("color") or ctx.accent_color, spec.get("edge") or ctx.accent_look.get("edge", INK))
    if kind == "text":
        _accent_text(ctx, frame, picture, spec, start, duration, mid, index)
    elif kind == "arrow":
        tail, head = _point(ctx, picture, spec, "from", mid), _point(ctx, picture, spec, "to", mid)
        look = ctx.accent_look
        bend = float(spec.get("bend", look.get("bend", .15)))
        path = ctx.drawn_file("arrow", {"tail": tail, "head": head, "bend": bend, "colors": colors, "style": look})
        centre, size = draw_arrow(path, tail, head, bend, colors, look)
        _accent_picture(ctx, frame, picture, f"{index} стрілка", path, centre, size, _moment(ctx, frame, spec, start), duration, mid, motion)
    elif kind == "circle":
        centre = _point(ctx, picture, spec, "at", mid)
        radii = spec.get("radii") or [120, 80]
        if not isinstance(radii, (list, tuple)) or len(radii) != 2:
            raise OpError("Потрібні два радіуси контуру")
        radii = [store.finite_float(r, 1, limit, "Радіус поза межами кадру") for r, limit in zip(radii, (ctx.W, ctx.H))]
        look = ctx.accent_look
        line = spec.get("line", look.get("ring", "solid"))
        if line not in ("solid", "dashed"):
            raise OpError("Тип контуру має бути solid або dashed")
        path = ctx.drawn_file("circle", {"radii": radii, "colors": colors, "line": line, "style": look})
        size = draw_circle(path, radii, colors, line, look)
        _accent_picture(ctx, frame, picture, f"{index} коло", path, centre, size, _moment(ctx, frame, spec, start), duration, mid, motion)
    elif kind == "image":
        source = Path(spec["path"]).expanduser() if spec.get("path") else Path(store.resolve_asset(ctx.project, spec["asset_id"])["path"])
        centre = _point(ctx, picture, spec, "at", mid)
        size = spec.get("size") or [300, 300]
        _accent_picture(ctx, frame, picture, f"{index} картинка", source, centre, size, _moment(ctx, frame, spec, start), duration, mid, motion, spec)
    elif kind == "card":
        centre = _point(ctx, picture, spec, "at", mid)
        w, h = spec.get("size") or [400, 120]
        keys, base = _glued(picture, centre, mid, duration, ctx, spec.get("pin", True))
        animated(ctx, frame, picture, f"{index} картка", {"kind": "animation", "content_type": "shape", "color": spec.get("color", NAVY),
                                                          "width": w / ctx.W, "height": h / ctx.H, "mask": "rounded",
                                                          "corner_radius": float(spec.get("radius", min(24, h / 2)))},
                 keys, base, _moment(ctx, frame, spec, start), duration, float(spec.get("opacity", .9)), motion=motion)
    else:
        raise OpError("Невідомий вид акценту: text, arrow, circle, card або image")
    ctx.report.append(f"кадр {frame['number'] or frame['group']['title']}: {kind}")


def _accent_picture(ctx, frame, picture, title, path, centre, size, at, duration, mid, motion, spec=None):
    if title.endswith(" картинка") and motion == "animated":   # a PNG prop: the channel's living motion (asset_motion)
        import asset_motion
        return asset_motion.accent(ctx, frame, picture, title, {"kind": "image", "asset_id": ctx.asset_for(path)}, centre, size, at, duration, spec)
    keys, base = _glued(picture, centre, mid, duration, ctx)
    animated(ctx, frame, picture, title, {"kind": "image", "asset_id": ctx.asset_for(path), "width": size[0] / ctx.W, "height": size[1] / ctx.H},
             keys, base, at, duration, path=path, motion=motion)


def _accent_text(ctx: Context, frame, picture, spec, start, duration, mid, index):
    phrase = spec.get("phrase") or spec.get("text")
    if not phrase or not str(phrase).strip():
        raise OpError("Підпису потрібен текст (text або phrase)")
    words = None
    if "appear" not in spec:
        try:
            words = word_timing.find_phrase(ctx.tokens(frame), phrase)
        except (ValueError, store.StudioError) as error:
            if spec.get("phrase"):
                raise OpError(str(error)) from None
    if words is None:   # not said in this frame: the words appear one after another from "appear"
        at = start + float(spec.get("appear", 0.3))
        words = [(token, at + .12 * k) for k, token in enumerate(str(phrase).split())]
    words[-1] = (words[-1][0].rstrip(".,!?:;"), words[-1][1])
    # a caption's words come in no later than a second before the frame ends
    latest = float(frame["end"]) - LAST_QUIET
    words = [(token, min(at, latest)) for token, at in words]
    style = spec.get("style", "card" if ctx.text_look == "dim" or spec.get("card_color") else "plain")
    if style not in STYLES:
        raise OpError("Стиль підпису: plain, card, tag, yellow або white")
    color, card, shadow = STYLES[style]
    requested_font = None if getattr(ctx, "unified_font", False) else spec.get("font_family")
    family = requested_font or getattr(ctx, "accent_font", None) or ctx.project.get("font_family") or "Montserrat"
    weight = int(spec.get("font_weight", 700))
    centre = _point(ctx, picture, spec, "at", mid)
    width, height, size = float(spec.get("width", 520)), float(spec.get("height", 320)), int(spec.get("font_size", 44))
    box, stub = _text_layout(ctx, words, width, height, size, family, weight, start)
    placed = stub["text_words"]
    left = min(w["x"] - w["width"] / 2 for w in placed) * box
    right = max(w["x"] + w["width"] / 2 for w in placed) * box
    top = min(w["y"] - w["height"] / 2 for w in placed) * height
    bottom = max(w["y"] + w["height"] / 2 for w in placed) * height
    # the text box is placed so that its rows are centred on `centre`
    bx, by = centre[0] - ((left + right) / 2 - box / 2), centre[1] - ((top + bottom) / 2 - height / 2)
    # a label over the picture rides with it; one in the black field beside a vertical photo stands still
    pin = spec.get("pin", picture is not None and picture.covers(centre[0], centre[1], mid))
    first = words[0][1] - start
    # «dim» (Григорий Антропов, user 8 November 2026: «плашка… чорною… трошки прозорою… з рівними кутами»): a black,
    # slightly see-through card with square corners and a little more room round the words
    dim = ctx.text_look == "dim" and style == "card" and "card_color" not in spec
    if card or style == "white":
        under = ({"title": "картка", "centre": centre, "size": (right - left + (72 if dim else 40), bottom - top + (34 if dim else 22)),
                  "color": "#000000" if dim else spec.get("card_color", card), "at": first,
                  "top": .72 if dim else .9 if style == "card" else .96, "radius": float(spec.get("radius", 0 if dim else min(24, (bottom - top + 22) / 2)))} if card else
                 {"title": "риска", "centre": (centre[0], centre[1] + (bottom - top) / 2 + 8), "size": (right - left, 12), "color": spec.get("card_color") or ctx.accent_color,
                  "at": words[-1][1] - start + .2, "top": 1.0, "radius": 4})
        keys, base = _glued(picture, under["centre"], mid, duration, ctx, pin)
        animated(ctx, frame, picture, f"{index} {under['title']}", {"kind": "animation", "content_type": "shape", "color": under["color"],
                                                                     "width": under["size"][0] / ctx.W, "height": under["size"][1] / ctx.H,
                                                                     "mask": "rounded" if under["radius"] else "none", "corner_radius": under["radius"]},
                 keys, base, max(0.0, under["at"] - (ENTRANCE["картка"] if under["title"] == "картка" and spec.get("motion", "animated") == "animated" else 0)),
                 duration, float(spec.get("card_opacity", under["top"])), motion=spec.get("motion", "animated"))
    keys, base = _glued(picture, (bx, by), mid, duration, ctx, pin)
    entrance = spec.get("entrance") or "fade"
    ctx.add(frame, picture, f"{index} текст", {"kind": "text", "text": " ".join(w["text"] for w in placed), **base, "width": box / ctx.W, "height": height / ctx.H,
                                              "font_size": stub["font_size"], "font_family": family, "font_weight": weight, "color": spec.get("text_color") or spec.get("color") or color,
                                              "text_words": placed, "word_entrance": {"type": entrance, "duration": 0.22, "distance": 14}, "shadow": shadow,
                                              "text_role": "label", "keyframes": keys})


def clear_accents(ctx: Context, spec: dict) -> None:
    frame = find_frame(ctx.frames, spec.get("frame"))
    accents = [c for c in frame["clips"] if is_accent(c)]
    if spec.get("kind") == "text":    # only the captions, with the card or underline drawn for each
        wanted = {accent_index(c) for c in accents if c.get("kind") == "text"}
        accents = [c for c in accents if accent_index(c) in wanted]
    ids = [c["id"] for c in accents]
    ctx.actions += [{"type": "delete_clip", "payload": {"clip_id": cid}} for cid in ids]
    ctx.report.append(f"кадр {frame['number'] or frame['group']['title']}: прибрано акцентів {len(ids)}")


def replace(ctx: Context, spec: dict) -> None:
    clips = {c["id"]: c for t in ctx.project["tracks"] for c in t["clips"]}
    clip = clips.get(spec.get("clip"))
    if clip is None:
        frame = find_frame(ctx.frames, spec.get("frame"))
        clip = main_picture(ctx.project, frame)
        if clip is None:
            raise OpError("У кадрі немає фото чи відео для заміни")
    owner = next((f for f in ctx.frames if any(c.get('id') == clip['id'] for c in f['clips'])), None)
    if owner and (owner.get('plan') or {}).get('format') == 'animation':
        raise OpError('Правки анімації внесіть шарами через op: animation, replace: true. Відео кадру не рендериться.', 400)
    asset_id = spec.get("asset_id") or ctx.asset_for(Path(spec["path"]).expanduser())
    ctx.actions.append({"type": "replace_clip_asset", "payload": {"clip_id": clip["id"], "asset_id": asset_id}})
    ctx.actions.append({"type": "update_clip", "payload": {"clip_id": clip["id"], "patch": {"title": clip.get("title", "")}}})
    ctx.report.append(f"кліп «{clip.get('title')}»: новий матеріал")


FRAME_CLIP = "K{:03d} кадр"
FULL = {"x": .5, "y": .5, "width": 1, "height": 1}   # a layer over the whole frame
MOTIONS = {"zoom_in": (1.0, 1.12), "zoom_out": (1.12, 1.0), "pan_left": (1.22, 1.24), "pan_right": (1.22, 1.24), "none": None}
PAN = .07     # the centre travels 14% of the frame's width; a 1.22 scale keeps the picture over the edges
# The studio moves nothing by itself (user, 8 November 2026: «це має робити не студія, а… режисер… прибери в студії
# взагалі можливість самій змінювати рух… всю постановку відео має робити» режисер, after automatic pans cropped the text
# of infographics and moved animation frames he had not asked to move). `place` puts a picture still unless the agent
# names its move (`motion`: zoom_in, zoom_out, pan_left, pan_right, or its own keyframes through the actions API);
# a vertical photo still gets its blurred copy behind it, standing still.


def _aspect(path) -> float | None:
    """A picture's width over its height, measured once per file version (media_size)."""
    size = media_size(str(path)) if path else None
    return size[0] / size[1] if size and size[1] else None


def place(ctx: Context, spec: dict) -> None:
    number = int(spec["frame"])
    planned = next((f for f in (ctx.plan or {}).get("frames", []) if int(f.get("number", 0)) == number), None)
    if planned is None:
        raise OpError(f"Кадру {number} немає в плані", 404)
    if planned.get('format') == 'animation':
        raise OpError('Кодову анімацію додайте шарами через op: animation. Відео рендериться лише під час експорту.', 400)
    if FRAME_CLIP.format(number) in ctx.groups:
        raise OpError(f"Кадр {number} повторюється в одному запиті")
    have = next((f for f in ctx.frames if f["number"] == number), None)
    if have and (main_picture(ctx.project, have) or _full_frame_text(have) and any(c.get("kind") == "text" for c in have["clips"])):
        raise OpError(f"Кадр {number} уже стоїть на таймлайні: замініть його картинку через replace")
    # both edges on whole video frames by the same rule as the export (AGENTS.md: never round start and length apart,
    # that leaves a one-frame gap or overlap at a seam)
    fps = int(ctx.project.get("fps") or 25)
    first, last = (math.floor(float(planned[key]) * fps + .5 + 1e-8) for key in ("start", "end"))   # render.frame_index
    start, end = first / fps, last / fps
    first_action = len(ctx.actions)
    payload = {"layer_id": ctx.project["tracks"][0]["id"], "start": start, "duration": end - start,
               "title": FRAME_CLIP.format(number)}
    if spec.get("text"):
        # the words to read on screen (user, 25 November 2026: «вставки текстові мають бути вже адаптовані… числа або
        # англійські букви»): the frame agent's own text when it gives one, else the voice's words
        words = display_text.clean(str(spec["display"]) if isinstance(spec.get("display"), str) and spec["display"].strip()
                                   else " ".join(planned.get("sentences") or []))
        if not words.strip():
            raise OpError(f"У кадрі {number} немає слів для текстового кадру")
        payload.update(kind="text", text=words, text_role="full_frame", source_frame=number, source_text=" ".join(planned.get("sentences") or []))
        if isinstance(spec.get("display"), str) and spec["display"].strip():
            payload["adapted"] = True
        _designed_text(ctx, planned, number, payload, start, end, have, spec)
    else:
        if spec.get("asset_id"):
            asset = next((a for a in ctx.project.get("assets", []) if a.get("id") == spec["asset_id"]), None)
            if asset is None:
                raise OpError("Матеріал не знайдено в проєкті", 404)
            kind = asset.get("kind")
        else:
            path = Path(spec["path"]).expanduser()
            kind = store.media_kind(path)
            asset = {"id": ctx.asset_for(path)}
        if kind not in {"image", "video"}:
            raise OpError("Кадр приймає картинку або відео")
        payload.update(kind=kind, asset_id=asset["id"])
        if kind == "video":
            payload["volume"] = 0
            # a stock video shorter than its frame would leave the end of the frame empty: say so now, not in a later summary
            source = Path(asset["path"]) if asset.get("path") else Path(spec["path"]).expanduser()
            length = store.media_duration(source) if source.is_file() else None
            trim = float(spec.get("trim_start") or 0)
            if length and length - trim < end - start - 1 / fps:
                raise OpError(f"Відео кадру {number} триває {length - trim:.1f} с, а кадр {end - start:.1f} с: візьміть довше відео")
            if trim:
                payload["trim_start"] = trim
        length = math.floor((end - start) * 1000) / 1000
        aspect = _aspect(asset.get("path") or spec.get("path")) if kind == "image" else None
        vertical = aspect is not None and aspect < 1.6      # 3:4 and 4:3 sit in the frame with fields beside them
        cover = max((ctx.W / ctx.H) / aspect, 1.0) * 1.02 if aspect and not vertical else 1.0   # a wide photo fills the frame before it drifts
        name = spec.get("motion") or "none"
        if name not in MOTIONS:
            raise OpError("Рух: zoom_in, zoom_out, pan_left, pan_right або none")
        motion = MOTIONS[name]
        if motion and name in ("zoom_in", "zoom_out") and spec.get("zoom_percent") is not None:
            amount = 1 + max(0.0, min(30.0, float(spec["zoom_percent"]))) / 100
            motion = (1.0, amount) if name == "zoom_in" else (amount, 1.0)
        if motion:
            first, last = {"time": 0.0, "scale": motion[0] * cover}, {"time": length, "scale": motion[1] * cover}
            if name in ("pan_left", "pan_right"):
                sign = 1 if name == "pan_right" else -1
                first["x"], last["x"] = .5 - sign * PAN, .5 + sign * PAN
                payload["x"] = first["x"]
            payload.update(scale=first["scale"], easing=ctx.easing, keyframes=[first, last])
        elif cover != 1.0:
            payload["scale"] = cover
        if vertical:
            # the black fields beside a vertical photo are its own blurred copy, standing still
            title_bg = f"K{number:03d} фон"
            fill = max((ctx.W / ctx.H) / aspect, aspect / (ctx.W / ctx.H)) * 1.06
            ctx.actions.append({"type": "add_clip", "payload": {"layer_id": ctx.project["tracks"][0]["id"], "start": start, "duration": end - start,
                                                                 "title": title_bg, "kind": "image", "asset_id": asset["id"], "blur": 30, "opacity": .9,
                                                                 "scale": fill,
                                                                 **({"group_id": have["group"]["id"]} if have else {})}})
            if not have:
                ctx.groups[title_bg] = f"Кадр {number}"
    if have:
        payload["group_id"] = have["group"]["id"]
    else:
        backdrop = store.frame_background(payload["layer_id"], start, end, title=f"K{number:03d} чорний фон")
        ctx.actions.insert(first_action, {"type": "add_clip", "payload": backdrop})
        ctx.groups[backdrop["title"]] = f"Кадр {number}"
        ctx.groups[FRAME_CLIP.format(number)] = f"Кадр {number}"
    ctx.actions.append({"type": "add_clip", "payload": payload})
    ctx.report.append(f"кадр {number}: {'текст' if spec.get('text') else payload['kind']} {start:.2f}–{end:.2f} с")


def _text_background(ctx: Context, number: int) -> dict | None:
    """A picture of the episode for the text frame's background: a neighbouring frame's picture first, any picture else."""
    by_number = {f["number"]: f for f in ctx.frames if f.get("number") is not None}
    order = [number - 1, number + 1, number - 2, number + 2] if number % 2 else [number + 1, number - 1, number + 2, number - 2]
    for near in order:
        frame = by_number.get(near)
        clip = main_picture(ctx.project, frame) if frame else None
        asset = next((a for a in ctx.project.get("assets", []) if clip and a.get("id") == clip.get("asset_id")), None)
        if asset and asset.get("kind") == "image":
            return asset
    images = [a for a in ctx.project.get("assets", []) if a.get("kind") == "image" and "accents" not in str(a.get("path", ""))]
    return images[number % len(images)] if images else None


def _timed_tokens(ctx: Context, planned: dict) -> list[tuple[str, float]]:
    """The shown words of a frame with the voice's times; when the recognised words do not add up (a number written by
    hand, say), each sentence's words are spread over its own spoken time."""
    try:
        return word_timing.frame_tokens(planned, ctx.words())
    except (ValueError, KeyError, TypeError):
        out = []
        for text, timing in zip(planned.get("sentences") or [], planned.get("sentence_timings") or []):
            tokens = display_text.clean(text).split()
            a, b = float(timing["start"]), float(timing["end"])
            step = max(.12, (b - a) * .85 / max(1, len(tokens)))
            out.extend((token, a + i * step) for i, token in enumerate(tokens))
        return out


# The backdrops of a full-frame text (user, 21 November 2026: «для текстових вставок не має бути шаблонності… текстова
# вставка має бути підібрана під конкретну ситуацію»): the host's own video under a black veil, a blurred picture of the
# episode under a contrasting veil, or a black field with a grey grid. The director or the
# frame agent picks one for the moment (spec "backdrop"); without a pick the studio takes one the previous text frame
# did not have, among those the episode can give.
TEXT_BACKDROPS = ("host", "blur", "grid")
TEXT_ENTRANCES = ("letters_fade", "blur_up", "up", "pop", "letters_up", "grow", "left", "blur", "letters_blur", "down", "fade", "shrink", "right")


def _text_history(ctx: Context, number: int) -> tuple[str | None, str | None]:
    """The backdrop and the word entrance of the nearest text frame before this one (placed earlier or in this batch)."""
    chosen = getattr(ctx, "text_choices", {})
    before = sorted([n for n in chosen if n < number] + [f["number"] for f in ctx.frames
                     if f.get("number") is not None and f["number"] < number and _full_frame_text(f)])
    if not before:
        return None, None
    last = before[-1]
    if last in chosen:
        return chosen[last]
    frame = next(f for f in ctx.frames if f.get("number") == last)
    titles = " ".join(c.get("title", "") for c in frame["clips"])
    backdrop = "host" if "відео ведучого" in titles else "grid" if "сітка" in titles else "blur"
    entrance = next(((c.get("word_entrance") or {}).get("type") for c in frame["clips"] if c.get("kind") == "text"), None)
    return backdrop, entrance


def _grid_picture(ctx: Context) -> Path:
    """The channel's own background pattern for text frames (channel_design.pattern: grid, fine grid, dots, crosses,
    diagonals or rings in its colours, a little changed in this film), darker at the edges; made once a film and size."""
    W, H = int(ctx.W), int(ctx.H)
    spec = channel_design.pattern(ctx.project)
    key = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:10]
    folder = store.media_dir(ctx.project) / "text-backdrops"
    path = folder / f"pattern-{spec['kind']}-{key}-{W}x{H}.png"
    if path.is_file():
        return path
    folder.mkdir(parents=True, exist_ok=True)
    rgb = lambda c: tuple(int(c.lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))
    field, line, major = rgb(spec["field"]), rgb(spec["line"]), rgb(spec["line2"])
    image = Image.new("RGB", (W, H), field)
    draw = ImageDraw.Draw(image)
    step, every, width, kind = max(16, round(H * spec["step"])), int(spec["major"]), int(spec.get("width", 1)), spec["kind"]
    xs = list(range(W // 2 % step, W, step))
    ys = list(range(H // 2 % step, H, step))
    tone = lambda n: major if n % every == 0 else line
    if kind in ("grid", "fine-grid"):
        for x in xs:
            draw.line([(x, 0), (x, H)], fill=tone((x - W // 2) // step), width=width)
        for y in ys:
            draw.line([(0, y), (W, y)], fill=tone((y - H // 2) // step), width=width)
        if kind == "fine-grid":
            half = step // 2
            for x in range(W // 2 % half, W, half):
                draw.line([(x, 0), (x, H)], fill=tuple((a + b) // 2 for a, b in zip(field, line)), width=1)
    elif kind == "dots":
        for x in xs:
            for y in ys:
                r = 2 if ((x - W // 2) // step + (y - H // 2) // step) % every else 3
                draw.ellipse([x - r, y - r, x + r, y + r], fill=tone((x - W // 2) // step * ((y - H // 2) // step)))
    elif kind == "cross":
        arm = max(3, step // 6)
        for x in xs:
            for y in ys:
                c = tone((x - W // 2) // step + (y - H // 2) // step)
                draw.line([(x - arm, y), (x + arm, y)], fill=c, width=width)
                draw.line([(x, y - arm), (x, y + arm)], fill=c, width=width)
    elif kind == "diagonal":
        for n, x in enumerate(range(-H, W + H, step)):
            draw.line([(x, 0), (x + H, H)], fill=tone(n), width=width)
    elif kind == "rings":
        cx, cy = W // 2, H // 2
        for n, r in enumerate(range(step, int(math.hypot(W, H) / 2) + step, step)):
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=tone(n), width=width)
    shade = Image.radial_gradient("L").resize((W, H))
    dark = tuple(max(0, v // 3) for v in field)
    image = Image.composite(Image.new("RGB", image.size, dark), image, shade.point(lambda v: min(255, int(v * spec["vignette"]))))
    image.save(path)
    return path


def _text_choice(ctx: Context, number: int, start: float, end: float, spec: dict) -> tuple[str, str, dict | None]:
    """The backdrop and the entrance of this text frame, and the host video when the backdrop is the host."""
    if "_host_video" not in vars(ctx):   # the host video and its length, read once a request (it looks into the analysis)
        import host_from_voice
        found = host_from_voice.voice_video(ctx.project, getattr(ctx, "plan", None))
        ctx._host_video = (found, store.media_duration(Path(found["path"])) or 0) if found else (None, 0)
    host, length = ctx._host_video
    if host and length and length < end - 1 / int(ctx.project.get("fps") or 25):
        host = None
    can = [b for b in TEXT_BACKDROPS if b != "host" or host]
    if _text_background(ctx, number) is None:
        can = [b for b in can if b != "blur"]
    wanted = spec.get("backdrop")
    if wanted not in (None, "auto") and wanted not in TEXT_BACKDROPS:
        raise OpError("Фон тексту: host, blur, grid або auto")
    previous, last_entrance = _text_history(ctx, number)
    if wanted in can or wanted == "blur":   # blur with no picture yet holds a plain dark field
        backdrop = wanted
    else:
        fresh = [b for b in can if b != previous] or can
        backdrop = fresh[number % len(fresh)]
    entrance = spec.get("entrance")
    if entrance not in (None, "auto") and entrance not in TEXT_ENTRANCES:
        raise OpError("Поява слів: " + ", ".join(TEXT_ENTRANCES))
    if entrance in (None, "auto"):
        # white words typed over the host (the author's example); any other entrance changes from text frame to text frame
        pool = [e for e in TEXT_ENTRANCES if e != last_entrance]
        entrance = "letters_fade" if backdrop == "host" and last_entrance != "letters_fade" else pool[(number * 7) % len(pool)]
    ctx.text_choices = {**getattr(ctx, "text_choices", {}), number: (backdrop, entrance)}
    return backdrop, entrance, host if backdrop == "host" else None


def _designed_text(ctx: Context, planned: dict, number: int, payload: dict, start: float, end: float, have: dict | None, spec: dict | None = None) -> None:
    spec = spec or {}
    # a channel with the dim look (Antropov) keeps it unless the director asks for a backdrop
    dim = ctx.text_look == "dim" and spec.get("backdrop") in (None, "auto")
    # the channel's own looks, a little changed in this film (channel_design), never the studio's shared ones
    look = channel_design.text_look(ctx.project, number, dim)
    duration = end - start
    tokens = _timed_tokens(ctx, planned)
    shown = payload["text"].split()
    if tokens and shown and len(tokens) != len(shown):
        # a text adapted for reading has other words than the voice: each takes the time of the spoken word at the same
        # place in the sentence, so the words still come with the voice
        spoken = len(tokens)
        tokens = [(word, tokens[min(spoken - 1, int(index * spoken / len(shown)))][1]) for index, word in enumerate(shown)]
    background = _text_background(ctx, number)
    backdrop, entrance, host = ("blur", look["entrance"], None) if dim else _text_choice(ctx, number, start, end, spec)
    color = look["color"] if backdrop == "blur" else "#ffffff"
    if tokens and len(tokens) == len(payload["text"].split()):
        family = getattr(ctx, "text_font", None) or ctx.project.get("font_family") or "Golos"
        fps = int(ctx.project.get("fps") or 25)
        # Keep the background on the plan boundary. Anchor the text layer to the video
        # frame containing its first word, with word timings relative to that layer.
        onset = max(start, min(math.floor(tokens[0][1] * fps) / fps, end - 1 / fps))
        payload.update(start=onset, duration=end-onset)
        box, stub = _text_layout(ctx, tokens, 1500, 760, 68, family, 700, onset)
        # every word, the first too, waits for its own moment in the voice (AGENTS.md, 20 October 2026; user 8 November
        # 2026: «текст вже появився, хоча про нього ми ще не говорили»): no pulling the first word to the frame's start
        payload.update(width=box / ctx.W, height=760 / ctx.H, x=.5, y=.5, font_size=stub["font_size"], font_family=family, font_weight=700,
                       text_words=stub["text_words"], word_entrance={"type": entrance, "duration": .05 if entrance.startswith("letters_") else .26, "distance": 16},
                       color=color, shadow={"color": look["glow"], "opacity": .55, "blur": 22, "x": 0, "y": 0} if dim else
                       None)
    group = {"group_id": have["group"]["id"]} if have else {}

    def layer(title: str, **fields) -> None:
        """A layer of the whole text frame; a frame not on the timeline yet opens its group «Кадр N» with it."""
        ctx.actions.append({"type": "add_clip", "payload": {"layer_id": ctx.project["tracks"][0]["id"], "start": start, "duration": duration,
                                                             "title": title, **fields, **group}})
        if not have:
            ctx.groups[title] = f"Кадр {number}"

    zoom = lambda a, b: [{"time": 0.0, "scale": a}, {"time": end_time(duration), "scale": b}]
    if backdrop == "host":
        # the host speaking these very words, from the frame's own second, under black at 59% (the author's example)
        layer(f"K{number:03d} відео ведучого", kind="video", asset_id=host["id"], trim_start=start, volume=0, scale=1.0, easing=ctx.easing,
              keyframes=zoom(1.0, 1.08))
        layer(f"K{number:03d} тінь", kind="animation", content_type="shape", color="#000000", opacity=.59, **FULL)
        return
    if backdrop == "grid":
        # a black field with a grey grid drifting closer; no CapCut noise over it (user, 25 November 2026: «шуми… дуже
        # агресивні… воно не потрібно»)
        layer(f"K{number:03d} сітка", kind="image", asset_id=ctx.asset_for(_grid_picture(ctx)), scale=1.0, easing=ctx.easing,
              keyframes=zoom(1.0, 1.07))
        return
    if background is None:
        # Text frames are placed before the pictures are made, so the episode may have none yet. The words wait for the
        # voice, so without a background the frame was empty from its boundary to the first word, a hole on the ruler
        # and in the export (user, 15 November 2026: «чому інколи виникають пусті місця»). A plain dark field holds it.
        if have:
            layer(f"K{number:03d} фон", kind="animation", content_type="shape", color="#000000", **FULL)
        return
    # the picture is contained in the frame: a vertical one needs a bigger scale to cover it
    aspect, frame_aspect = _aspect(background.get("path")), ctx.W / ctx.H
    cover = max(frame_aspect / aspect, aspect / frame_aspect) * 1.04 if aspect else 1.18
    near, far = look["zoom"]
    layer(f"K{number:03d} фон", kind="image", asset_id=background["id"], scale=near * cover, blur=look["blur"], easing=ctx.easing,
          **({"visual_effect": "monochrome"} if dim else {}), keyframes=zoom(near * cover, far * cover))
    layer(f"K{number:03d} тінь", kind="animation", content_type="shape", color=look["veil"], opacity=look["veil_opacity"], **FULL)
    if dim:
        layer(f"K{number:03d} переливання", kind="animation", content_type="gradient", opacity=.42,
              gradient={"colors": look["flow"], "speed": .09, "amplitude": .3, "softness": .14}, **FULL)


# effects the author never wants (user, 25 November 2026: «Рожевий всесвіт»… «більш ніколи не додавай взагалі ні в які проекти»)
BANNED_EFFECTS = {"capcut_e11"}
# effects that light only a band or a corner of the frame at a time: «Зоряний круїз» is a diagonal stream of stars, 17% of
# the frame a moment, 6% of its left side (user, 25 November 2026: «ефект чомусь не на всьому кадрі той що на фоні»)
BAND_EFFECTS = {"capcut_e09"}


def effect(ctx: Context, spec: dict) -> None:
    """{"op": "effect", "frame": N, "effect": "capcut_e04", "strength": .3, "on": "frame" | "background"}: a CapCut effect
    inside the frame's own group at the given strength (0.05–1; light textures 0.2–0.4), over the whole frame or only its
    background under the words and graphics; it replaces the frame's own effect, "effect": null takes it off."""
    frame = find_frame(ctx.frames, spec.get("frame"))
    group = frame["group"]
    start, end = float(frame["start"]), float(frame["end"])
    for layer in ctx.project.get("tracks", []):
        for clip in layer.get("clips", []):
            if clip.get("content_type") == "capcut_effect" and (clip["id"] in group.get("clip_ids", []) or
                    abs(float(clip["start"]) - start) < .06 and abs(float(clip["start"]) + float(clip["duration"]) - end) < .06):
                ctx.actions.append({"type": "delete_clip", "payload": {"clip_id": clip["id"]}})
    name = spec.get("effect")
    if name in BANNED_EFFECTS:
        raise OpError("Цей ефект автор не використовує в жодному проєкті")
    if name in BAND_EFFECTS:
        raise OpError("Цей ефект вкриває лише смугу кадру, а не весь кадр: для тла візьми рівномірний (шум, пил, зерно)")
    where = spec.get("on") or "frame"
    if where not in ("frame", "background"):
        raise OpError("Ефект на frame або background")
    if name:
        strength = float(spec.get("strength", .3))
        if not .05 <= strength <= 1:
            raise OpError("Сила ефекту від 0.05 до 1")
        payload = {"effect": name, "group_id": group["id"], "opacity": round(strength, 3)}
        if where == "background":
            pictures = [c for c in frame["clips"] if c.get("kind") in ("image", "video") and c.get("content_type") != "capcut_effect"]
            if not pictures:
                raise OpError("У кадрі немає фону для ефекту")
            order = {c["id"]: i for i, t in enumerate(ctx.project["tracks"]) for c in t["clips"]}
            payload["above_clip"] = min(pictures, key=lambda c: order.get(c["id"], 0))["id"]
        ctx.actions.append({"type": "add_capcut_effect", "payload": payload})
    ctx.report.append(f"кадр {frame['number']}: ефект {name or 'прибрано'}" + (f" на {'фоні' if where == 'background' else 'кадрі'}, сила {round(100 * float(spec.get('strength', .3)))}%" if name else ""))


def remove(ctx: Context, spec: dict) -> None:
    """Take a frame off the timeline with everything in its group (picture, accents, text); undo brings it back."""
    frame = find_frame(ctx.frames, spec.get("frame"))
    ctx.actions.append({"type": "delete_group", "payload": {"group_id": frame["group"]["id"]}})
    ctx.report.append(f"кадр {frame['number'] or frame['group']['title']}: прибрано кліпів {len(frame['clips'])}")


def _full_frame_text(frame: dict) -> bool:
    return bool(frame.get("plan") and frame["plan"].get("format") == "text") or any(
        c.get("kind") == "text" and c.get("text_role") == "full_frame" for c in frame["clips"])


def _text_extent(clip: dict) -> tuple[float, float, float]:
    """(top, bottom, row) of a text clip's letters in frame fractions: its words' rows, else its box."""
    cy, h = float(clip.get("y", .5)), float(clip.get("height", .1)) * float(clip.get("scale", 1) or 1)
    words = clip.get("text_words") or []
    if words:
        top = min(float(w["y"]) - float(w.get("height", .1)) / 2 for w in words)
        bottom = max(float(w["y"]) + float(w.get("height", .1)) / 2 for w in words)
        row = max(float(w.get("height", .1)) for w in words) * h
        return cy + (top - .5) * h, cy + (bottom - .5) * h, row
    return cy - h / 2, cy + h / 2, h


def _letters_span(clip: dict) -> tuple[float, float]:
    """(left, right) of a text clip's letters across, in frame fractions: a box widened after its words were laid keeps
    them off its own middle (Andromeda 40: the box at 38% of the frame, its words at 43% of the box)."""
    cx, w = float(clip.get("x", .5)), float(clip.get("width", .5)) * float(clip.get("scale", 1) or 1)
    words = clip.get("text_words") or []
    if not words:
        return cx - w / 2, cx + w / 2
    left = min(float(v["x"]) - float(v.get("width", 0)) / 2 for v in words)
    right = max(float(v["x"]) + float(v.get("width", 0)) / 2 for v in words)
    return cx + (left - .5) * w, cx + (right - .5) * w


def _letters_centre(clip: dict) -> float:
    left, right = _letters_span(clip)
    return (left + right) / 2


TEXT_GAP = .3   # the space between the parts of one text frame, in rows of its largest letters


def _composable(frame: dict) -> list[dict] | None:
    """The text clips of a full-frame text frame whose layout the studio may set: nothing but full-frame backgrounds,
    veils and effects stand beside them (a photo, a picture or a motion-code layer next to the words is the director's
    own composition and stays)."""
    if not _full_frame_text(frame):
        return None
    texts = []
    for clip in frame["clips"]:
        if clip.get("kind") == "text":
            texts.append(clip)
        elif clip.get("content_type") == "code":
            return None
        elif clip.get("kind") in ("image", "video", "animation") and clip.get("content_type") != "capcut_effect":
            size = float(clip.get("scale", 1) or 1)
            if float(clip.get("width", 1)) * size < .98 or float(clip.get("height", 1)) * size < .98:
                return None
    return texts or None


def text_layout_changes(frame: dict, size: tuple[int, int] = (1920, 1080)) -> list[tuple[dict, dict]]:
    """The changes that make a full-frame text frame's parts one block in the middle of the frame: every part centred
    across, the block centred down, and a part that goes on the sentence in another colour (Andromeda 40: «…пятна
    оказались / отдельными галактиками») written at the main text's size as its next line, at its own line spacing
    (user, 25 November 2026: «тут чому так? і розмір шрифта різний»). A coloured phrase laid over its own words moves
    with them. Empty when the frame stands so already or is not the studio's to lay out (see _composable)."""
    import copy
    texts = _composable(frame)
    if not texts:
        return []
    W, H = size
    # the main text is the part with the most words; the others take its size, with their words laid out again
    main = max(texts, key=lambda c: len(c.get("text_words") or []))
    font = int(main.get("font_size") or 0)
    resized = {}
    for clip in texts:
        if clip is main or not font or int(clip.get("font_size") or 0) == font or not clip.get("text_words"):
            continue
        overlaid = _text_extent(clip)[0] < _text_extent(main)[1] - .01 and _text_extent(clip)[1] > _text_extent(main)[0] + .01
        if overlaid:   # a highlight over the main words keeps the size it was laid with
            continue
        trial = copy.deepcopy(clip)
        trial["font_size"] = font
        typography.reflow({"width": W, "height": H}, trial, clip.get("font_family") or main.get("font_family") or "Golos")
        resized[clip["id"]] = trial
    view = lambda c: resized.get(c["id"], c)
    units: list[list[dict]] = []
    for clip in sorted(texts, key=lambda c: _text_extent(view(c))[0]):
        top, bottom, _ = _text_extent(view(clip))
        if units:
            utop, ubottom = min(_text_extent(view(c))[0] for c in units[-1]), max(_text_extent(view(c))[1] for c in units[-1])
            if top < ubottom - .01 and bottom > utop + .01:
                units[-1].append(clip)
                continue
        units.append([clip])
    spans = [(min(_text_extent(view(c))[0] for c in u), max(_text_extent(view(c))[1] for c in u)) for u in units]
    # the parts stand line under line: the main text's own spacing (typography: rows 1.45 of the size apart, 1.4 high)
    gap = font * .05 / H if font else TEXT_GAP * max(_text_extent(c)[2] for c in texts)
    cursor = .5 - (sum(b - t for t, b in spans) + gap * (len(units) - 1)) / 2
    moves = []
    for unit, (top, bottom) in zip(units, spans):
        dy = cursor - top
        cursor += bottom - top + gap
        # a unit moves as one: a highlight laid over some of its words keeps standing on them
        dx = .5 - (min(_letters_span(view(c))[0] for c in unit) + max(_letters_span(view(c))[1] for c in unit)) / 2
        for clip in unit:
            shown = view(clip)
            if abs(dx) < .004 and abs(dy) < .004 and shown is clip:
                continue
            changes = {"x": round(float(clip.get("x", .5)) + dx, 5), "y": round(float(clip.get("y", .5)) + dy, 5)}
            if shown is not clip:
                changes.update(font_size=shown["font_size"], text_words=shown["text_words"])
            if any("x" in k or "y" in k for k in clip.get("keyframes") or []):
                changes["keyframes"] = [{**k, **({"x": round(float(k["x"]) + dx, 5)} if "x" in k else {}),
                                         **({"y": round(float(k["y"]) + dy, 5)} if "y" in k else {})} for k in clip["keyframes"]]
            moves.append((clip, changes))
    return moves


LEAD_SIZE, KEY_SIZE = 54, 112   # px at 1080 lines: the lead-in reads quietly, the key phrase is the frame's headline


def _layout(clip: dict, font: int, weight: int, box: float, W: int, H: int) -> dict:
    """The clip with its words laid out again at `font` in a box `box` of the frame's width."""
    import copy
    out = copy.deepcopy(clip)
    out.update(font_size=font, font_weight=weight, width=box, height=min(.9, max(.12, font * 1.45 * 6 / H)))
    typography.reflow({"width": W, "height": H}, out, clip.get("font_family") or "Golos")
    return out


def text_design_changes(frame: dict, accent: str, size: tuple[int, int] = (1920, 1080)) -> list[dict]:
    """A text frame with a lead-in and a key phrase (two text parts, the second going on the sentence in another colour)
    designed as a headline: the lead-in small and quiet in two or three lines, the key phrase large in the accent colour
    with a soft glow, a line growing from its middle under it when the voice says it, the whole stack in the middle of
    the frame (user, 25 November 2026: «такі текстові вставки мають бути по дизайну в 100 раз крутіші бо зараз халтура»).
    Returns batch actions; empty for a frame of another shape."""
    texts = _composable(frame)
    if not texts or len(texts) != 2:
        return []
    lead, key = sorted(texts, key=lambda c: _text_extent(c)[0])
    if len(key.get("text_words") or []) > 5 or len(lead.get("text_words") or []) < len(key.get("text_words") or []):
        return []
    overlaid = _text_extent(key)[0] < _text_extent(lead)[1] - .01
    if overlaid or any(str(c.get("title", "")).endswith(" лінія") for c in frame["clips"]):
        return []
    W, H = size
    scale = H / 1080
    lead_new = _layout(lead, round(LEAD_SIZE * scale), 600, .62, W, H)
    color = key.get("color") if str(key.get("color") or "").startswith("#") and key.get("color") != "#ffffff" else accent
    font = round(KEY_SIZE * scale)
    while True:   # the key phrase on one line, as large as fits in 86% of the width
        key_new = _layout(key, font, 800, .92, W, H)
        if len({w["y"] for w in key_new["text_words"]}) == 1 or font <= 60 * scale:
            break
        font -= 4
    lt, lb, _ = _text_extent({**lead_new, "y": .5})
    kt, kb, _ = _text_extent({**key_new, "y": .5})
    line_h, gap, under = .006, font * .32 / H, font * .2 / H
    total = (lb - lt) + gap + (kb - kt) + under + line_h
    top = .5 - total / 2
    lead_y = .5 + (top - lt)
    key_y = .5 + (top + (lb - lt) + gap - kt)
    line_y = top + (lb - lt) + gap + (kb - kt) + under + line_h / 2
    left, right = _letters_span({**key_new, "x": .5})
    lead_x = .5 - (sum(_letters_span({**lead_new, "x": .5})) / 2 - .5)
    key_x = .5 - ((left + right) / 2 - .5)
    actions = [
        {"type": "update_clip", "payload": {"clip_id": lead["id"], "changes": {
            "x": round(lead_x, 5), "y": round(lead_y, 5), "width": lead_new["width"], "height": lead_new["height"],
            "font_size": lead_new["font_size"], "font_weight": 600, "text_words": lead_new["text_words"], "opacity": .86,
            "shadow": {"color": "#000000", "opacity": .55, "blur": 18, "x": 0, "y": 2}}}},
        {"type": "update_clip", "payload": {"clip_id": key["id"], "changes": {
            "x": round(key_x, 5), "y": round(key_y, 5), "width": key_new["width"], "height": key_new["height"],
            "font_size": key_new["font_size"], "font_weight": 800, "text_words": key_new["text_words"], "color": color,
            "shadow": {"color": color, "opacity": .5, "blur": 30, "x": 0, "y": 0}}}},
    ]
    said = float(key["start"]) + min(float(w.get("start", 0)) for w in key["text_words"])
    start, end = float(frame["start"]), float(frame["end"])
    at = max(0.0, min(said + .15, end - LAST_QUIET) - start)
    # a clip is at least 1% of the frame high and scales from 5%: the line is drawn at 0.6 of a box 1% high (6 px at
    # 1080) and grows from a dot in its middle to its whole width
    full = .6
    width = (right - left) * .82 / full
    actions.append({"type": "add_clip", "payload": {
        "layer_id": None, "kind": "animation", "content_type": "shape", "title": f"K{frame['number']:03d} лінія",
        "color": color, "start": start, "duration": end - start, "x": .5, "y": round(line_y, 5),
        "width": round(width, 5), "height": .01, "scale": full, "mask": "rounded", "corner_radius": 3,
        "group_id": frame["group"]["id"], "easing": "ease_out",
        "keyframes": [{"time": round(at, 3), "scale": .05, "opacity": 0.0}, {"time": round(at + .45, 3), "scale": full, "opacity": 1.0}]}})
    return actions


def design_text(ctx: Context, spec: dict) -> None:
    """{"op": "design_text", "frames": [..] | absent for all}: text frames with a lead-in and a key phrase made into a
    designed headline (text_design_changes)."""
    wanted = spec.get("frames")
    frames = [find_frame(ctx.frames, ref) for ref in wanted] if wanted else ctx.frames
    accent = ctx.accent_color
    for frame in frames:
        actions = text_design_changes(frame, accent, (ctx.W, ctx.H))
        for action in actions:
            if action["type"] == "add_clip":
                action["payload"]["layer_id"] = ctx.project["tracks"][-1]["id"]
        ctx.actions.extend(actions)
        if actions:
            ctx.report.append(f"кадр {frame['number']}: заголовок — підводка, ключова фраза, лінія")


def compose_text(ctx: Context, spec: dict) -> None:
    """{"op": "compose_text", "frames": [..] | absent for all}: every full-frame text frame laid out as one centred block
    (user, 25 November 2026, frame 40 of Andromeda: «текстові вставки мають бути побудовані з розумом… виглядає дуже
    дивно розкидано»: the words stood left of the middle and the coloured end line apart from them)."""
    wanted = spec.get("frames")
    frames = [find_frame(ctx.frames, ref) for ref in wanted] if wanted else ctx.frames
    for frame in frames:
        moves = text_layout_changes(frame, (ctx.W, ctx.H))
        for clip, changes in moves:
            ctx.actions.append({"type": "update_clip", "payload": {"clip_id": clip["id"], "changes": changes}})
        if moves:
            ctx.report.append(f"кадр {frame['number'] or frame['group']['title']}: текст зібрано по центру")


HOST_IN = "crossfade"   # the one way into the host frame: a plain dissolve (26 November 2026)
OUT_ONLY = {"capcut_t30"}   # «Розрізання й панорама»: the host's way out or a seam between other frames only


def _host_or_text(frame: dict) -> bool:
    """A host frame or a full-frame text: it always comes in and goes out with a transition (user, 21 November 2026:
    «якщо це був диктор або ж текстова вставка, то у нас обох боків обов'язково має бути з переходами»)."""
    return _full_frame_text(frame) or _format(frame) == "host"


def _format(frame: dict) -> str:
    return str((frame.get("plan") or {}).get("format") or "")


def channel_transitions(project: dict) -> dict:
    """The channel's «Переходи» setting: {allowed, share}; empty when the channel chose nothing."""
    return dict(channel_settings(project).get("transitions") or {})


HOST_OUT = .6      # seconds of the quick transition out of the host
MAX_SQUEEZE = 1.8  # a transition may run at most this much faster than its own animation


def transitions(ctx: Context, spec: dict) -> None:
    """The studio picks the seams between touching frames that get a designed transition (a change of format, every other
    seam of one format; an explicit `share` sets a share instead); the rest are cuts. Both seams of a
    host frame and of a full-frame text frame always get one, beyond the share if need be; the same transition other than a crossfade never twice in a row; a video going out needs
    source frames for the transition's length. Existing transitions stay unless "replace" is true."""
    chosen = dict(ctx.channel.get("transitions") or {}) if hasattr(ctx, "channel") else channel_transitions(ctx.project)
    # the studio decides itself where a seam takes a transition, with no share to keep (user, 25 November 2026: «як часто
    # ставити перехід, 70%… прибери… студія… сама рішати, коли їй треба ставити, коли ні… обмежень не буде»); an
    # explicit "share" of the op still sets one
    share = float(spec["share"]) if spec.get("share") is not None else None
    pool = list(spec.get("pool") or (chosen["allowed"] if "allowed" in chosen else DEFAULT_POOL))
    if not pool:
        share, pool = 0.0, ["crossfade"]   # the channel allowed no transition: every seam stays a cut
    unknown = [t for t in pool if t not in joins.CHOICES]
    if unknown:
        raise OpError("Невідомі переходи: " + ", ".join(sorted(set(unknown))))
    rnd = random.Random(spec.get("seed", 23))
    fps = float(ctx.project.get("fps", 30))
    existing = {(j["from_ref"], j["to_ref"]): j for j in ctx.project.get("join_transitions", [])}
    seams = []
    for a, b in zip(ctx.frames, ctx.frames[1:]):
        if abs(a["end"] - b["start"]) <= 1 / fps + .001:
            seams.append((a, b, "group:" + a["group"]["id"], "group:" + b["group"]["id"]))
    scope = spec.get("frames")
    if scope is not None:
        if not isinstance(scope,list) or not scope or any(type(n) is not int or n < 1 for n in scope):
            raise OpError("Вкажіть номери кадрів для переходів.")
        if set(scope) - {f["number"] for f in ctx.frames}:
            raise OpError("Спершу поставте вибрані кадри на таймлайн.")
        # a seam into a host or full-frame text frame belongs to the frame before it too: the host's frames are made by the
        # studio, never in an agent's batch, so the transition into the host was never set (user, 25 November 2026:
        # «якщо хайген аватар, то in переход має бути обов'язковий. Просто що без озвучки»)
        seams = [seam for seam in seams if seam[1]["number"] in scope or (seam[0]["number"] in scope and _host_or_text(seam[1]))]
    keep = not spec.get("replace")
    designed = sum(1 for _, _, f, t in seams if keep and (f, t) in existing)
    open_seams = [s for s in seams if not (keep and (s[2], s[3]) in existing)]
    must = [s for s in open_seams if _host_or_text(s[0]) or _host_or_text(s[1])]
    eligible = [s for s in open_seams if s not in must]
    if share is None:
        # automatic: a change of format is a change of scene and takes a transition; frames of one format in a row take
        # one every other seam, so a run of photos breathes without a transition on each cut
        picked, run = [], 0
        for seam in eligible:
            if _format(seam[0]) != _format(seam[1]):
                picked.append(seam); run = 0
            else:
                run += 1
                if run % 2:
                    picked.append(seam)
        chosen = set(id(s) for s in must) | set(id(s) for s in picked)
        target = designed + len(chosen)
    else:
        target = round(share * len(seams))
        wanted = max(0, min(len(eligible), target - designed - len(must)))
        chosen = set(id(s) for s in must) | (set(id(s) for s in rnd.sample(eligible, wanted)) if wanted else set())
    # where the host goes out: short, driving transitions, one to three of them taking turns through the film, chosen for
    # this film (user, 25 November 2026: «коли аватар закінчується… не може бути длінний перехід… швидкий… драйвовий…
    # для кожного ролика свій… один, два, три переходи, які чергуються»)
    import sound_settings
    # soft by what a transition shows (sound_settings.TRANSITION_CHARACTER): a dissolve, a wash, a gentle film
    kinds = list(dict.fromkeys(pool))   # the pool without its repeats (crossfade stands there ten times by default)
    soft = {"crossfade"} | {t for t in kinds if t.startswith("cin_") or sound_settings.transition_character(t) == "soft"}
    # a transition keeps its own shape: squeezed far below its own length it was a blink of its middle (user, 25 November
    # 2026, «Кадри з монтажу» of 1.4 s in 0.45 s out of the host: «він якийсь недопилений»); out of the host only the
    # transitions that keep their shape at HOST_OUT seconds
    def natural(kind):
        return joins.capcut_duration(kind) if kind in joins.CAPCUT else .5 if kind in joins.GRAPHIC_PRESETS else .35
    def keeps_shape(kind, room):
        return natural(kind) <= room * MAX_SQUEEZE
    lively = [t for t in kinds if t not in soft and keeps_shape(t, HOST_OUT)] or [t for t in kinds if t not in soft] or list(kinds)
    film = random.Random(str(ctx.project.get("id")) + "host-out")
    drive = film.sample(lively, min(len(lively), film.choice([2, 3]) if len(lively) > 2 else len(lively)))
    host_outs = 0
    # elsewhere more variety: a soft dissolve at most about one seam in five, never the same transition twice running
    softs = [t for t in kinds if t in soft]
    previous, added, cuts = None, 0, 0
    every = bool(spec.get("every"))
    unused = list(kinds)
    if every:
        rnd.shuffle(unused)
        if keep:
            used = {j["type"] for j in ctx.project.get("join_transitions", [])}
            unused = [t for t in unused if t not in used]
    for seam in seams:
        a, b, left, right = seam
        if keep and (left, right) in existing:
            previous = existing[(left, right)]["type"]
            continue
        if id(seam) not in chosen:
            if (left, right) in existing:
                ctx.actions.append({"type": "set_join_transition", "payload": {"from_ref": left, "to_ref": right, "type": "cut"}})
                cuts += 1
            previous = None
            continue
        host_out = _format(a) == "host"
        # into the host gently, out of him with drive (user, 25 November 2026: «in для ведучого… не має бути такий
        # драйвовий… частіше… м'якші переходи, а out… драйвовіші»)
        into_host = _format(b) == "host"
        host_in = not host_out and into_host
        # "every": each transition the channel ticked goes in at least once, to check them all on one film (user,
        # 25 November 2026: «використав кожен перехід, який я виділив галочкою… перевірити… наскільки якісно»)
        room = HOST_OUT if host_out else min(a["end"] - a["start"], b["end"] - b["start"])
        # a flash washes the picture white and drops into the next one in a few frames: into or out of a dark text frame
        # that drop is a blink (user, 25 November 2026, Antropov 13 → 14, «Яскраве стирання»: «спочатку приливається, а
        # потім блимає»); such a seam takes any other transition
        dark = any(_full_frame_text(side) or _format(side) == "text" for side in (a, b))
        # transitions that only belong where the host goes out or between other frames: never into the host, never on
        # either side of a text frame (user, 25 November 2026, «Розрізання й панорама» out of a text frame: «ніколи не
        # використовуй такий перехід… для показа диктора і… текстових вставок. Це більше як out»)
        bright = lambda t: (dark and sound_settings.transition_character(t) == "flash") or ((dark or into_host) and t in OUT_ONLY)
        # into the host only a plain dissolve: every CapCut «soft» one still swirls, melts or tints his face (user, 26
        # November 2026, Andromeda 83→84, «Пиловий вихор», then «Райдужний фільтр»: «знову драйвовий»)
        fresh = [t for t in unused if t != previous and (not host_out or t not in soft) and not host_in
                 and keeps_shape(t, room) and not bright(t)] if every else []
        if fresh:
            kind = fresh[0]
            unused.remove(kind)
            host_outs += host_out
        elif host_out:
            kind = drive[host_outs % len(drive)]
            if kind == previous and len(drive) > 1 and previous != "crossfade":   # never the same twice in a row
                host_outs += 1
                kind = drive[host_outs % len(drive)]
            host_outs += 1
            if bright(kind):
                kind = next((t for t in drive + lively if not bright(t) and t != previous), kind)
        else:
            options = [t for t in kinds if t != previous and keeps_shape(t, room) and not bright(t)] or \
                      [t for t in kinds if t != previous and not bright(t)] or [t for t in kinds if not bright(t)] or \
                      [t for t in kinds if t != previous] or list(kinds)
            hard = [t for t in options if t not in soft]
            calm = [t for t in softs if (t != previous or t == "crossfade") and keeps_shape(t, room)]
            kind = HOST_IN if host_in else rnd.choice(calm) if calm and (not hard or rnd.random() < .2) else rnd.choice(hard or options)
        duration = float(spec.get("duration", natural(kind)))
        if host_out:
            duration = min(duration, HOST_OUT)   # quick, with drive
        duration = min(duration, a["end"] - a["start"], b["end"] - b["start"])
        # a video going out with no frames left for the transition holds its last picture through it (joins.held_source)
        if kind is None or duration < .05:
            previous = None
            continue
        ctx.actions.append({"type": "set_join_transition", "payload": {"from_ref": left, "to_ref": right, "type": kind, "duration": round(duration, 3)}})
        previous, added = kind, added + 1
    soundtrack.transitions(ctx, spec)
    soundtrack.typing(ctx, spec)
    soundtrack.drawing(ctx, spec)
    ctx.report.append(f"стиків {len(seams)}: план {target} переходів ({'автоматично' if share is None else str(round(100 * share)) + '%'}), було {designed}, додано {added}, прибрано {cuts}, "
                      f"стане {designed + added}; кадри ведучого й текстові з переходами з обох боків")


def reglue(ctx: Context, spec: dict) -> None:
    """Glue the accents of a frame to its photo again, where they stand at the frame's middle moment (an accent glued to
    the blurred background copy drifted against the photo; user, 6 November 2026: «акцент двигается не синхронно»),
    and give arrows, rings, cards and underlines their entrance clip (made again, so it can run any number of times)."""
    wanted = set(spec.get("frames") or [])
    done = animated_count = 0
    for frame in ctx.frames:
        if wanted and frame.get("number") not in wanted:
            continue
        clip = main_picture(ctx.project, frame)
        if not clip or clip.get("kind") not in ("image", "video"):
            continue
        by_title = {c["title"].replace(" поява ", " "): c for c in frame["clips"] if is_accent(c) and is_entrance(c)}
        ctx.actions += [{"type": "delete_clip", "payload": {"clip_id": c["id"]}} for c in by_title.values()]
        picture = Picture(ctx.project, clip)
        duration, mid = picture.duration, picture.duration / 2
        for accent_clip in [c for c in frame["clips"] if is_accent(c) and not is_entrance(c)]:
            import asset_motion
            if asset_motion.is_living(accent_clip) and accent_clip["title"] not in by_title:   # a PNG prop with its own motion
                ctx.actions.append({"type": "update_clip", "payload": {"clip_id": accent_clip["id"], "patch": asset_motion.reglued(ctx, frame, picture, accent_clip)}})
                done += 1
                continue
            local = mid - (float(accent_clip["start"]) - float(clip["start"]))
            centre = (keyframe_value(accent_clip, "x", local) * ctx.W, keyframe_value(accent_clip, "y", local) * ctx.H)
            text = accent_clip.get("kind") == "text"
            # A caption in the side field and its underline/card share one coordinate system.
            # Pinning only the underline to the moving photo makes its entrance drift away from the words.
            caption = next((c for c in frame["clips"] if c.get("kind") == "text" and accent_index(c) == accent_index(accent_clip)), None)
            label = caption if accent_kind(accent_clip) in {"риска", "картка"} else accent_clip if text else None
            if label:
                label_local = mid - (float(label["start"]) - float(clip["start"]))
                pin = picture.covers(keyframe_value(label, "x", label_local) * ctx.W,
                                     keyframe_value(label, "y", label_local) * ctx.H, mid)
            else:
                pin = True
            keys, base = _glued(picture, centre, mid, duration, ctx, pin)
            fades = [{"time": p["time"], "opacity": p["opacity"]} for p in accent_clip.get("keyframes") or [] if "opacity" in p]
            kind = accent_kind(accent_clip)
            if text or accent_clip.get("accent_motion") in ("fade", "still") or kind not in ENTRANCE or not fades:
                ctx.actions.append({"type": "update_clip", "payload": {"clip_id": accent_clip["id"],
                                                                        "patch": {"x": base["x"], "y": base["y"], "scale": 1.0, "keyframes": merge(keys, fades)}}})
                done += 1
                continue
            top = float(fades[-1]["opacity"])
            old = by_title.get(accent_clip["title"])
            shown = next((float(p["time"]) for p in fades if float(p["opacity"]) > 0), .3)
            at = float(old["start"]) - float(accent_clip["start"]) if old else max(0.0, shown - .25)
            length = ENTRANCE[kind]
            at = max(0.0, min(at, duration - length - (.08 if top >= 1 else 0)))
            visible = round(at + length, 3)
            fades = [{"time": 0.0, "opacity": 0.0}, {"time": round(visible - .001, 3), "opacity": 0.0}, {"time": visible, "opacity": top}]
            steady = {**accent_clip, **base, "scale": 1.0, "keyframes": merge(keys, fades)}
            ctx.actions.append({"type": "update_clip", "payload": {"clip_id": accent_clip["id"],
                                                                    "patch": {"x": base["x"], "y": base["y"], "scale": 1.0, "keyframes": steady["keyframes"]}}})
            path = store.resolve_asset(ctx.project, accent_clip["asset_id"])["path"] if accent_clip.get("asset_id") else None
            title = accent_clip["title"].split(" акцент ", 1)[-1]
            ctx.actions.append(_entrance_action(ctx, frame, picture, title, steady, at, length, top, path))
            done += 1
            animated_count += 1
    ctx.report.append(f"акцентів приклеєно до фото: {done}, з анімованою появою: {animated_count}")


def motion_code_op(ctx: Context, spec: dict) -> None:
    """Motion design written as code over a frame (motion_code.py): {"op": "motion_code", "frame": N, "code": source of
    function draw(ctx, t, info), "start": seconds from the frame's start, "duration": seconds (to the frame's end by
    default), "title", "assets": {name: file or asset id}, "replace": title of the frame's motion clip to swap}. The clip
    lies over the frame's picture in its group; info.words holds the voice's words of its time."""
    import motion_code
    frame = find_frame(ctx.frames, spec.get("frame"))
    code = motion_code.validate(spec.get("code"))
    offset = store.finite_float(spec.get("start", 0), 0, 36000, "Невірний початок моушн-коду")
    start = frame["start"] + offset
    duration = store.finite_float(spec.get("duration") or (frame["end"] - start), .1, 36000, "Невірна тривалість моушн-коду")
    if start + duration > frame["end"] + 1e-3:
        raise OpError(f"Моушн-код виходить за кадр {frame['number']}: кадр до {frame['end']:.2f} с")
    assets = {}
    for name, source in (spec.get("assets") or {}).items():
        path = Path(str(source)).expanduser()
        assets[name] = ctx.asset_for(path) if path.is_file() else str(source)
    words = [{"text": w["text"], "start": round(float(w["start"]) - start, 3), "end": round(float(w["end"]) - start, 3)}
             for w in ctx.words() if float(w.get("end", 0)) > start and float(w.get("start", 0)) < start + duration]
    label = str(spec.get("title") or "графіка").strip()[:60]
    title = f"K{frame['number']:03d} моушн {label}" if frame["number"] is not None else f"моушн {label}"
    if spec.get("replace"):
        old = [c for c in frame["clips"] if c.get("content_type") == "code" and c.get("title") in {spec["replace"], title}]
        if not old:
            raise OpError(f"У кадрі {frame['number']} немає моушн-коду «{spec['replace']}»")
        for clip in old:
            ctx.actions.append({"type": "delete_clip", "payload": {"clip_id": clip["id"]}})
    # a code that paints the whole frame is the frame's background: it goes under the frame's words (or when asked)
    fills = bool(re.search(r"fillRect\(\s*0\s*,\s*0\s*,\s*(?:W|info\.w|w)\s*,\s*(?:H|info\.h|h)\s*\)", code))
    under = spec.get("under_text") if isinstance(spec.get("under_text"), bool) else fills
    ctx.actions.append({"type": "add_clip", "payload": {"layer_id": ctx.project["tracks"][0]["id"], "group_id": frame["group"]["id"],
                                                        "under_text": under,
                                                        "kind": "animation", "content_type": "code", "code": code, "code_assets": assets,
                                                        "code_words": words, "start": round(start, 3), "duration": round(duration, 3),
                                                        "title": title, "x": .5, "y": .5, "width": 1, "height": 1}})
    ctx.report.append(f"кадр {frame['number']}: моушн-код «{label}» {start:.2f}–{start + duration:.2f} с")


OPS = {"effect": effect, "transition_sounds": soundtrack.transitions, "typing_sounds": soundtrack.typing, "drawing_sounds": soundtrack.drawing, "appear_sounds": soundtrack.appear, "soundtrack": soundtrack.place, "animation": native_animation.place, "reglue": reglue, "reanimate": reglue, "animate_accents": reglue, "accent": accent, "clear_accents": clear_accents, "replace": replace, "transitions": transitions, "place": place, "remove": remove, "motion_code": motion_code_op, "compose_text": compose_text, "design_text": design_text}


def run(pid: str, ops: list, expected_revision=None, dry_run: bool = False) -> dict:
    """Turn the requests into actions and apply them as one batch (one undo step). Returns the report, the number of
    actions and the new revision; with dry_run only what would be done."""
    if not isinstance(ops, list) or not 1 <= len(ops) <= 500:
        raise OpError("Передайте від 1 до 500 операцій")
    with store.LOCK:
        project = store.load_project(pid)
        if expected_revision is not None and expected_revision != project.get("revision", 0):
            raise store.StudioError("Проєкт змінився. Прочитайте його ще раз перед правкою", 409)
        ctx = Context(project)
        ctx.dry_run = dry_run
        for spec in ops:
            if not isinstance(spec, dict) or spec.get("op") not in OPS:
                raise OpError("Невідома операція: " + str(spec.get("op") if isinstance(spec, dict) else spec))
            try:
                OPS[spec["op"]](ctx, spec)
            except (KeyError, TypeError, ValueError) as error:
                raise OpError(f"{spec['op']}: {error}") from None
        if any(a["type"] == "add_clip" for a in ctx.actions):
            plate = next((g for g in project.get("scene_groups", []) if g.get("role") == "overlay"), None)
            if plate:   # the channel plate stays the top of the picture
                ctx.actions.append({"type": "reorder_stack", "payload": {"source": "group:" + plate["id"], "target": "scenes", "above": True}})
        if dry_run or not ctx.actions:
            return {"revision": project.get("revision", 0), "report": ctx.report, "actions": ctx.actions if dry_run else [], "applied": 0}
        if len(ctx.actions) > 1800:
            raise OpError("Забагато дій за раз (понад 1800): розділіть операції")
        if ctx.files:
            for path in ctx.files:
                if not path.is_file() or not store.media_kind(path):
                    raise OpError(f"Файл недоступний: {path.name}")
                if not (store.under(path, Path(project["episode_path"])) or any(store.under(path, root) for root in store.media_roots(project))):
                    raise OpError(f"Файл поза випуском: {path}")
            known = {a["id"] for a in project.get("assets", [])}
            project.setdefault("assets", []).extend(record for record in (store.asset_record(path, pid) for path in ctx.files) if record["id"] not in known)
            # the media list is not an edit (as prune_razgon_renders): the revision moves only with the batch below, so a
            # batch that fails leaves no phantom change for an open editor
            store.save_project(project)
        # a frame placed where no group stood yet opens its own «Кадр N» group in the same batch: one undo step
        by_frame: dict[str, list[str]] = {}
        for title, frame in ctx.groups.items():
            by_frame.setdefault(frame, []).append(title)
        groups = [{"type": "group_clips", "payload": {"clip_titles": titles, "title": frame}} for frame, titles in by_frame.items()]
        result = store.apply_action(pid, "batch", {"actions": ctx.actions + groups}, project.get("revision", 0))
    return {"revision": result.get("revision", 0), "report": ctx.report, "applied": len(ctx.actions)}
