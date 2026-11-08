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
- {"op": "transitions", "share": 0.7, ...} designs about that share of the seams between frames by the channel rules.
- {"op": "remove", "frame": 12} takes the frame off the timeline with its whole group.
- {"op": "place", "frame": 12, "path": file | "asset_id": id | "text": true, "motion": "zoom_in"} puts a frame of the
  plan on the timeline at the plan frame's time, in its group «Кадр 12»: a picture or a video (a photo gets a slow
  zoom unless "motion": "none"), or with "text" the frame's own spoken words as a full-frame text. The frame agent of
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
from pathlib import Path

from PIL import Image, ImageDraw

import display_text
import joins
import store
import typography
import word_timing

YELLOW, NAVY, INK, WHITE = "#ffd23a", "#0b2f78", "#101418", "#ffffff"
ENTRANCES = ["up", "pop", "blur_up", "fade"]
STYLES = {   # text colour, card colour (None: no card), shadow of the text
    "card": (WHITE, NAVY, {"color": "#000000", "opacity": .25, "blur": 6, "x": 0, "y": 3}),
    "tag": (NAVY, WHITE, {"color": "#000000", "opacity": .25, "blur": 6, "x": 0, "y": 3}),
    "yellow": (YELLOW, None, {"color": "#000000", "opacity": .75, "blur": 14, "x": 0, "y": 3}),
    "white": (WHITE, None, {"color": "#000000", "opacity": .75, "blur": 14, "x": 0, "y": 3}),
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


def _scale_at(points: list[dict], time: float, base: float) -> float:
    have = [(float(p["time"]), float(p["scale"])) for p in points if "scale" in p]
    if not have:
        return base
    if time <= have[0][0]:
        return have[0][1]
    for (t0, s0), (t1, s1) in zip(have, have[1:]):
        if t0 <= time <= t1:
            return s0 + (s1 - s0) * (time - t0) / max(t1 - t0, 1e-6)
    return have[-1][1]


def appear(at: float, duration: float, top: float = 1.0) -> list[dict]:
    at = max(0.05, min(at, duration - 0.4))
    return [{"time": 0.0, "opacity": 0.0}, {"time": round(at - 0.04, 3), "opacity": 0.0}, {"time": round(at + 0.25, 3), "opacity": top}]


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
             duration: float, top: float = 1.0, path=None) -> None:
    """Add a glued accent with its entrance: the glued clip appears when the entrance ends, the entrance clip plays
    from `at` (seconds into the clip) over it."""
    kind = title.split()[-1]
    length = ENTRANCE.get(kind, .6)
    at = max(0.0, min(at, duration - length - .2))
    shown = round(at + length, 3)
    fades = [{"time": 0.0, "opacity": 0.0}, {"time": round(shown - .04, 3), "opacity": 0.0}, {"time": shown, "opacity": top}]
    steady = {**payload, **base, "scale": 1.0, "opacity": top, "keyframes": merge(keys, fades)}
    ctx.add(frame, picture, title, steady)
    ctx.actions.append(_entrance_action(ctx, frame, picture, title, steady, at, length, top, path))


def _entrance_action(ctx, frame, picture, title, steady, at, length, top, path) -> dict:
    kind = title.split()[-1]
    clip = {**steady, "easing": (picture.clip.get("easing", ctx.easing) if picture else ctx.easing)}
    (ox, oy), (dx, dy) = _anchor(ctx, kind, steady, path)
    points, tau = [], 0.0
    span = length + .08          # a little over the glued clip's first visible frame: no gap at the hand-over
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

def draw_arrow(path: Path, tail, head, bend: float, colors=(YELLOW, INK)):
    """A hand-drawn arrow with a dark edge; returns its canvas centre and size in frame pixels."""
    (x0, y0), (x1, y1) = tail, head
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 8:
        raise OpError("Стрілка надто коротка")
    nx, ny = -(y1 - y0) / length, (x1 - x0) / length
    cx, cy = (x0 + x1) / 2 + nx * bend * length, (y0 + y1) / 2 + ny * bend * length
    pts = [((1 - u) ** 2 * x0 + 2 * (1 - u) * u * cx + u * u * x1, (1 - u) ** 2 * y0 + 2 * (1 - u) * u * cy + u * u * y1) for u in [i / 40 for i in range(41)]]
    ang, size = math.atan2(y1 - pts[-4][1], x1 - pts[-4][0]), 34
    tip = [(x1 + math.cos(ang) * 6, y1 + math.sin(ang) * 6), (x1 - math.cos(ang - .5) * size, y1 - math.sin(ang - .5) * size),
           (x1 - math.cos(ang + .5) * size, y1 - math.sin(ang + .5) * size)]
    xs, ys = [p[0] for p in pts + tip], [p[1] for p in pts + tip]
    left, top, right, bottom = min(xs) - 30, min(ys) - 30, max(xs) + 30, max(ys) + 30
    scale = 2
    image = Image.new("RGBA", (int((right - left) * scale), int((bottom - top) * scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    at = lambda p: ((p[0] - left) * scale, (p[1] - top) * scale)
    body = pts[:-3]
    fill, edge = colors
    draw.line([at(p) for p in body], fill=edge, width=17 * scale, joint="curve")
    draw.polygon([at(p) for p in tip], fill=edge, outline=edge, width=8 * scale)
    draw.line([at(p) for p in body], fill=fill, width=9 * scale, joint="curve")
    draw.polygon([at(p) for p in tip], fill=fill)
    image.resize((image.width // scale, image.height // scale), Image.LANCZOS).save(path)
    return ((left + right) / 2, (top + bottom) / 2), (right - left, bottom - top)


def draw_circle(path: Path, radii, colors=(YELLOW, INK)):
    rx, ry = radii
    margin, scale = 24, 2
    image = Image.new("RGBA", (int((2 * rx + 2 * margin) * scale), int((2 * ry + 2 * margin) * scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    box = [margin * scale, margin * scale, (2 * rx + margin) * scale, (2 * ry + margin) * scale]
    fill, edge = colors
    draw.ellipse(box, outline=edge, width=15 * scale)
    draw.ellipse([v + (3 * scale if i < 2 else -3 * scale) for i, v in enumerate(box)], outline=fill, width=8 * scale)
    image.resize((image.width // scale, image.height // scale), Image.LANCZOS).save(path)
    return (2 * rx + 2 * margin, 2 * ry + 2 * margin)


# ---------------------------------------------------------------- the operation context

class Context:
    def __init__(self, project: dict):
        self.project = project
        self.W, self.H = float(project.get("width", 1920)), float(project.get("height", 1080))
        try:
            self.plan = store.load_project_plan(project["id"])
        except (store.StudioError, OSError, ValueError):
            self.plan = None
        self.frames = frame_groups(project, self.plan)
        self._words = None
        self.files: list[Path] = []          # pictures drawn for this request, registered as assets before the batch
        self.actions: list[dict] = []
        self.groups: dict[str, str] = {}     # clip title -> the new frame group it opens (place)
        self.report: list[str] = []
        self.entrance = 0
        self.easing = project.get("settings", {}).get("motion_easing", "ease_in_out")

    def words(self) -> list[dict]:
        if self._words is None:
            import analysis_jobs
            try:
                report = (analysis_jobs.latest(self.project["id"], lambda jid: store.read_json(store.DATA_ROOT / "jobs" / (jid + ".json"))) or {}).get("report") or {}
            except (store.StudioError, OSError, ValueError, KeyError):
                report = {}
            self._words = report.get("aligned_words") or []
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
        """An asset id for a file: an existing asset with the same path, or one registered before the batch."""
        resolved = str(Path(path).resolve())
        for asset in self.project.get("assets", []):
            if asset.get("path") == resolved:
                return asset["id"]
        self.files.append(Path(resolved))
        return store.asset_record(Path(resolved), self.project["id"])["id"]

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


def _moment(ctx: Context, frame: dict, spec: dict, start: float) -> float:
    """When an accent appears, in seconds from its clip start: "appear", or the moment the voice says "word"."""
    if "appear" in spec:
        return float(spec["appear"])
    if spec.get("word"):
        try:
            return word_timing.word_time(ctx.tokens(frame), spec["word"]) - start
        except ValueError as error:
            raise OpError(str(error)) from None
    return 0.3


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
    colors = (spec.get("color", YELLOW), spec.get("edge", INK))
    if kind == "text":
        _accent_text(ctx, frame, picture, spec, start, duration, mid, index)
    elif kind == "arrow":
        tail, head = _point(ctx, picture, spec, "from", mid), _point(ctx, picture, spec, "to", mid)
        path = ctx.drawn_file("arrow", {"tail": tail, "head": head, "bend": spec.get("bend", .15), "colors": colors})
        centre, size = draw_arrow(path, tail, head, float(spec.get("bend", .15)), colors)
        _accent_picture(ctx, frame, picture, f"{index} стрілка", path, centre, size, _moment(ctx, frame, spec, start), duration, mid)
    elif kind == "circle":
        centre = _point(ctx, picture, spec, "at", mid)
        radii = spec.get("radii") or [120, 80]
        path = ctx.drawn_file("circle", {"radii": radii, "colors": colors})
        size = draw_circle(path, radii, colors)
        _accent_picture(ctx, frame, picture, f"{index} коло", path, centre, size, _moment(ctx, frame, spec, start), duration, mid)
    elif kind == "image":
        source = Path(spec["path"]).expanduser() if spec.get("path") else Path(store.resolve_asset(ctx.project, spec["asset_id"])["path"])
        centre = _point(ctx, picture, spec, "at", mid)
        size = spec.get("size") or [300, 300]
        _accent_picture(ctx, frame, picture, f"{index} картинка", source, centre, size, _moment(ctx, frame, spec, start), duration, mid)
    elif kind == "card":
        centre = _point(ctx, picture, spec, "at", mid)
        w, h = spec.get("size") or [400, 120]
        keys, base = _glued(picture, centre, mid, duration, ctx, spec.get("pin", True))
        animated(ctx, frame, picture, f"{index} картка", {"kind": "animation", "content_type": "shape", "color": spec.get("color", NAVY),
                                                          "width": w / ctx.W, "height": h / ctx.H, "mask": "rounded",
                                                          "corner_radius": float(spec.get("radius", min(24, h / 2)))},
                 keys, base, _moment(ctx, frame, spec, start), duration, float(spec.get("opacity", .9)))
    else:
        raise OpError("Невідомий вид акценту: text, arrow, circle, card або image")
    ctx.report.append(f"кадр {frame['number'] or frame['group']['title']}: {kind}")


def _accent_picture(ctx, frame, picture, title, path, centre, size, at, duration, mid):
    keys, base = _glued(picture, centre, mid, duration, ctx)
    animated(ctx, frame, picture, title, {"kind": "image", "asset_id": ctx.asset_for(path), "width": size[0] / ctx.W, "height": size[1] / ctx.H},
             keys, base, at, duration, path=path)


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
    style = spec.get("style", "card")
    if style not in STYLES:
        raise OpError("Стиль підпису: card, tag, yellow або white")
    color, card, shadow = STYLES[style]
    family, weight = spec.get("font_family") or ctx.project.get("font_family") or "Montserrat", int(spec.get("font_weight", 700))
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
    if card or style == "white":
        under = ({"title": "картка", "centre": centre, "size": (right - left + 40, bottom - top + 22), "color": spec.get("card_color", card), "at": first,
                  "top": .9 if style == "card" else .96, "radius": min(24, (bottom - top + 22) / 2)} if card else
                 {"title": "риска", "centre": (centre[0], centre[1] + (bottom - top) / 2 + 8), "size": (right - left, 12), "color": spec.get("card_color", YELLOW),
                  "at": words[-1][1] - start + .2, "top": 1.0, "radius": 4})
        keys, base = _glued(picture, under["centre"], mid, duration, ctx, pin)
        animated(ctx, frame, picture, f"{index} {under['title']}", {"kind": "animation", "content_type": "shape", "color": under["color"],
                                                                     "width": under["size"][0] / ctx.W, "height": under["size"][1] / ctx.H,
                                                                     "mask": "rounded", "corner_radius": under["radius"]},
                 keys, base, max(0.0, under["at"] - (ENTRANCE.get(under["title"], .5) if under["title"] == "картка" else 0)), duration, under["top"])
    keys, base = _glued(picture, (bx, by), mid, duration, ctx, pin)
    entrance = spec.get("entrance") or ENTRANCES[ctx.entrance % len(ENTRANCES)]
    ctx.entrance += 1
    ctx.add(frame, picture, f"{index} текст", {"kind": "text", "text": " ".join(w["text"] for w in placed), **base, "width": box / ctx.W, "height": height / ctx.H,
                                              "font_size": stub["font_size"], "font_family": family, "font_weight": weight, "color": spec.get("text_color", color),
                                              "text_words": placed, "word_entrance": {"type": entrance, "duration": 0.22, "distance": 14}, "shadow": shadow,
                                              "text_role": "label", "keyframes": keys})


def clear_accents(ctx: Context, spec: dict) -> None:
    frame = find_frame(ctx.frames, spec.get("frame"))
    accents = [c for c in frame["clips"] if is_accent(c)]
    if spec.get("kind") == "text":    # only the captions, with the card or underline drawn for each
        index = lambda c: str(c.get("title", "")).split(" акцент ", 1)[-1].split()[0]
        wanted = {index(c) for c in accents if c.get("kind") == "text"}
        accents = [c for c in accents if index(c) in wanted]
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
    asset_id = spec.get("asset_id") or ctx.asset_for(Path(spec["path"]).expanduser())
    ctx.actions.append({"type": "replace_clip_asset", "payload": {"clip_id": clip["id"], "asset_id": asset_id}})
    ctx.actions.append({"type": "update_clip", "payload": {"clip_id": clip["id"], "patch": {"title": clip.get("title", "")}}})
    ctx.report.append(f"кліп «{clip.get('title')}»: новий матеріал")


FRAME_CLIP = "K{:03d} кадр"
MOTIONS = {"zoom_in": (1.0, 1.12), "zoom_out": (1.12, 1.0), "pan_left": (1.22, 1.24), "pan_right": (1.22, 1.24), "none": None}
# Every frame moves from its first moment to its last (user, 5 November 2026: «Якщо нема руху, це є проблема… скучно
# дивитися»): pictures take turns to zoom in, drift sideways and zoom out by about 12%, a vertical photo sits on a blurred
# copy of itself, and a host frame zooms in or out by 12% («якщо диктора ми вибираємо… приближення… або віддалення… 10-15%»).
PICTURE_CYCLE = ["zoom_in", "pan_right", "zoom_out", "pan_left"]
PAN = .07     # the centre travels 14% of the frame's width; a 1.22 scale keeps the picture over the edges


def _aspect(path) -> float | None:
    try:
        with Image.open(path) as image:
            return image.width / image.height
    except (OSError, ZeroDivisionError, TypeError):
        return None


def place(ctx: Context, spec: dict) -> None:
    number = int(spec["frame"])
    planned = next((f for f in (ctx.plan or {}).get("frames", []) if int(f.get("number", 0)) == number), None)
    if planned is None:
        raise OpError(f"Кадру {number} немає в плані", 404)
    have = next((f for f in ctx.frames if f["number"] == number), None)
    if have and (main_picture(ctx.project, have) or _full_frame_text(have) and any(c.get("kind") == "text" for c in have["clips"])):
        raise OpError(f"Кадр {number} уже стоїть на таймлайні: замініть його картинку через replace")
    # both edges on whole video frames by the same rule as the export (AGENTS.md: never round start and length apart,
    # that leaves a one-frame gap or overlap at a seam)
    fps = int(ctx.project.get("fps") or 25)
    first, last = (math.floor(float(planned[key]) * fps + .5 + 1e-8) for key in ("start", "end"))   # render.frame_index
    start, end = first / fps, last / fps
    payload = {"layer_id": ctx.project["tracks"][0]["id"], "start": start, "duration": end - start,
               "title": FRAME_CLIP.format(number)}
    if spec.get("text"):
        words = display_text.clean(" ".join(planned.get("sentences") or []))
        if not words.strip():
            raise OpError(f"У кадрі {number} немає слів для текстового кадру")
        payload.update(kind="text", text=words, text_role="full_frame", source_frame=number, source_text=" ".join(planned.get("sentences") or []))
        _designed_text(ctx, planned, number, payload, start, end, have)
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
        host = planned.get("format") == "host"
        if spec.get("motion"):
            name = spec["motion"]
        elif kind == "image":
            name = ("zoom_in", "zoom_out")[number % 2] if vertical else PICTURE_CYCLE[number % len(PICTURE_CYCLE)]
        elif host:
            name = ("zoom_in", "zoom_out")[number % 2]
        else:
            name = "none"
        motion = MOTIONS.get(name, MOTIONS["zoom_in"])
        if motion:
            first, last = {"time": 0.0, "scale": motion[0] * cover}, {"time": length, "scale": motion[1] * cover}
            if name in ("pan_left", "pan_right"):
                sign = 1 if name == "pan_right" else -1
                first["x"], last["x"] = .5 - sign * PAN, .5 + sign * PAN
                payload["x"] = first["x"]
            payload.update(scale=first["scale"], easing=ctx.easing, keyframes=[first, last])
        if vertical:
            # the black fields beside a vertical photo are its own blurred copy, slowly moving the other way
            title_bg = f"K{number:03d} фон"
            fill = max((ctx.W / ctx.H) / aspect, aspect / (ctx.W / ctx.H)) * 1.06
            ctx.actions.append({"type": "add_clip", "payload": {"layer_id": ctx.project["tracks"][0]["id"], "start": start, "duration": end - start,
                                                                 "title": title_bg, "kind": "image", "asset_id": asset["id"], "blur": 30, "opacity": .9,
                                                                 "scale": fill * 1.08, "easing": ctx.easing,
                                                                 "keyframes": [{"time": 0.0, "scale": fill * 1.08}, {"time": length, "scale": fill}],
                                                                 **({"group_id": have["group"]["id"]} if have else {})}})
            if not have:
                ctx.groups[title_bg] = f"Кадр {number}"
    if have:
        payload["group_id"] = have["group"]["id"]
    else:
        ctx.groups[FRAME_CLIP.format(number)] = f"Кадр {number}"
    ctx.actions.append({"type": "add_clip", "payload": payload})
    ctx.report.append(f"кадр {number}: {'текст' if spec.get('text') else payload['kind']} {start:.2f}–{end:.2f} с")


# A full-frame text frame is designed, not plain words on black (user, 5 November 2026: «фон, блюр… анімацію появлення
# букв… текстові вставки старатися різні робити. З різним блюром, різними картинками на фоні… темнішу або світлішу, текст
# темніший, контрастніший»): a blurred picture of the episode under a dark, navy or light veil, the words appearing with
# the voice, and the look turning from one text frame to the next.
TEXT_LOOKS = [
    {"veil": "#05070c", "veil_opacity": .58, "blur": 22, "color": "#ffffff", "entrance": "blur_up", "zoom": (1.10, 1.0)},
    {"veil": "#f3eee4", "veil_opacity": .66, "blur": 28, "color": "#0e1a33", "entrance": "up", "zoom": (1.0, 1.10)},
    {"veil": "#0b2f78", "veil_opacity": .55, "blur": 18, "color": "#ffffff", "entrance": "pop", "zoom": (1.12, 1.02)},
    {"veil": "#000000", "veil_opacity": .48, "blur": 32, "color": "#ffe9a8", "entrance": "fade", "zoom": (1.02, 1.12)},
    {"veil": "#1d1206", "veil_opacity": .52, "blur": 26, "color": "#fff4e2", "entrance": "blur_up", "zoom": (1.08, 1.0)},
]


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


def _designed_text(ctx: Context, planned: dict, number: int, payload: dict, start: float, end: float, have: dict | None) -> None:
    look = TEXT_LOOKS[number % len(TEXT_LOOKS)]
    duration = end - start
    tokens = _timed_tokens(ctx, planned)
    if tokens and len(tokens) == len(payload["text"].split()):
        family = ctx.project.get("font_family") or "Golos"
        box, stub = _text_layout(ctx, tokens, 1500, 760, 68, family, 700, start)
        if stub["text_words"]:
            stub["text_words"][0]["start"] = min(stub["text_words"][0]["start"], .12)   # the frame opens on its first word
        payload.update(width=box / ctx.W, height=760 / ctx.H, x=.5, y=.5, font_size=stub["font_size"], font_family=family, font_weight=700,
                       text_words=stub["text_words"], word_entrance={"type": look["entrance"], "duration": .26, "distance": 16},
                       color=look["color"], shadow={"color": "#000000" if look["color"] != "#0e1a33" else "#ffffff", "opacity": .45, "blur": 10, "x": 0, "y": 3})
    background = _text_background(ctx, number)
    if background is None:
        return
    group = {"group_id": have["group"]["id"]} if have else {}
    title_bg, title_veil = f"K{number:03d} фон", f"K{number:03d} тінь"
    zoom = look["zoom"]
    try:   # the picture is contained in the frame: a vertical one needs a bigger scale to cover it
        with Image.open(background["path"]) as image:
            aspect, frame_aspect = image.width / image.height, ctx.W / ctx.H
        cover = max(frame_aspect / aspect, aspect / frame_aspect) * 1.04
    except (OSError, KeyError, ZeroDivisionError):
        cover = 1.18
    ctx.actions.append({"type": "add_clip", "payload": {"layer_id": ctx.project["tracks"][0]["id"], "start": start, "duration": duration, "title": title_bg,
                                                         "kind": "image", "asset_id": background["id"], "scale": zoom[0] * cover, "blur": look["blur"], "easing": ctx.easing,
                                                         "keyframes": [{"time": 0.0, "scale": zoom[0] * cover}, {"time": math.floor(duration * 1000) / 1000, "scale": zoom[1] * cover}], **group}})
    ctx.actions.append({"type": "add_clip", "payload": {"layer_id": ctx.project["tracks"][0]["id"], "start": start, "duration": duration, "title": title_veil,
                                                         "kind": "animation", "content_type": "shape", "color": look["veil"], "opacity": look["veil_opacity"],
                                                         "x": .5, "y": .5, "width": 1, "height": 1, **group}})
    if not have:
        ctx.groups[title_bg] = ctx.groups[title_veil] = f"Кадр {number}"


def remove(ctx: Context, spec: dict) -> None:
    """Take a frame off the timeline with everything in its group (picture, accents, text); undo brings it back."""
    frame = find_frame(ctx.frames, spec.get("frame"))
    ctx.actions.append({"type": "delete_group", "payload": {"group_id": frame["group"]["id"]}})
    ctx.report.append(f"кадр {frame['number'] or frame['group']['title']}: прибрано кліпів {len(frame['clips'])}")


def _full_frame_text(frame: dict) -> bool:
    return bool(frame.get("plan") and frame["plan"].get("format") == "text") or any(
        c.get("kind") == "text" and c.get("text_role") == "full_frame" for c in frame["clips"])


def transitions(ctx: Context, spec: dict) -> None:
    """About `share` of all seams between touching frames get a designed transition; the rest are cuts. Into a full-frame
    text frame always a cut; the same transition other than a crossfade never twice in a row; a video going out needs
    source frames for the transition's length. Existing transitions stay unless "replace" is true."""
    share = float(spec.get("share", .7))
    pool = list(spec.get("pool") or DEFAULT_POOL)
    unknown = [t for t in pool if t not in joins.TYPES or t == "cut"]
    if unknown:
        raise OpError("Невідомі переходи: " + ", ".join(sorted(set(unknown))))
    rnd = random.Random(spec.get("seed", 23))
    fps = float(ctx.project.get("fps", 30))
    existing = {(j["from_ref"], j["to_ref"]): j for j in ctx.project.get("join_transitions", [])}
    seams = []
    for a, b in zip(ctx.frames, ctx.frames[1:]):
        if abs(a["end"] - b["start"]) <= 1 / fps + .001:
            seams.append((a, b, "group:" + a["group"]["id"], "group:" + b["group"]["id"]))
    keep = not spec.get("replace")
    designed = sum(1 for _, _, f, t in seams if keep and (f, t) in existing)
    target = round(share * len(seams))
    open_seams = [s for s in seams if not (keep and (s[2], s[3]) in existing)]
    eligible = [s for s in open_seams if not _full_frame_text(s[1])]
    wanted = max(0, min(len(eligible), target - designed))
    chosen = set(id(s) for s in rnd.sample(eligible, wanted)) if wanted else set()
    previous, added, cuts = None, 0, 0
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
        kind = rnd.choice(pool)
        if kind == previous and kind != "crossfade":
            kind = "crossfade"
        duration = float(spec.get("duration", .5 if kind in joins.GRAPHIC_PRESETS else .35))
        duration = min(duration, a["end"] - a["start"], b["end"] - b["start"])
        if not _video_tail(ctx, a, duration):
            kind = None
        if kind is None or duration < .05:
            previous = None
            continue
        ctx.actions.append({"type": "set_join_transition", "payload": {"from_ref": left, "to_ref": right, "type": kind, "duration": round(duration, 3)}})
        previous, added = kind, added + 1
    ctx.report.append(f"стиків {len(seams)}: план {target} переходів ({round(100 * share)}%), було {designed}, додано {added}, прибрано {cuts}, "
                      f"стане {designed + added}; у текстові кадри склейка")


def _video_tail(ctx: Context, frame: dict, duration: float) -> bool:
    """A video going out of a frame keeps playing through the transition: its file must have those frames."""
    for clip in frame["clips"]:
        if clip.get("kind") == "video" and abs(float(clip["start"]) + float(clip["duration"]) - frame["end"]) < .05:
            try:
                available = store.media_duration(Path(store.resolve_asset(ctx.project, clip["asset_id"])["path"]))
            except (store.StudioError, OSError):
                return False
            if available and float(clip.get("trim_start", 0)) + float(clip["duration"]) + duration > available + .04:
                return False
    return True


def motion(ctx: Context, spec: dict) -> None:
    """Give the placed frames the moves `place` gives a new one now: a picture zooms or drifts, a vertical or 4:3 photo
    sits on its blurred copy, a host frame zooms 12%. Frames with accents keep theirs (the accents ride the photo's move)."""
    wanted = set(spec.get("frames") or [])
    plan_frames = {int(f.get("number", 0)): f for f in (ctx.plan or {}).get("frames", [])}
    changed = 0
    # new clips need a layer that stays: the voice's (a picture's own layer goes when the picture is laid again)
    tracks = ctx.project["tracks"]
    anchor = next((tr["id"] for tr in tracks if any(c.get("kind") == "audio" for c in tr["clips"])), tracks[-1]["id"])
    for frame in ctx.frames:
        number = frame.get("number")
        if number is None or (wanted and number not in wanted) or number not in plan_frames:
            continue
        if any(is_accent(c) for c in frame["clips"]) or _full_frame_text(frame):
            continue
        clip = main_picture(ctx.project, frame)
        host = plan_frames[number].get("format") == "host"
        if not clip or not (clip.get("kind") == "image" or host and clip.get("kind") == "video"):
            continue
        asset = next((a for a in ctx.project.get("assets", []) if a.get("id") == clip.get("asset_id")), {})
        aspect = _aspect(asset.get("path")) if clip.get("kind") == "image" else None
        vertical = aspect is not None and aspect < 1.6
        cover = max((ctx.W / ctx.H) / aspect, 1.0) * 1.02 if aspect and not vertical else 1.0
        name = ("zoom_in", "zoom_out")[number % 2] if vertical or host else PICTURE_CYCLE[number % len(PICTURE_CYCLE)]
        a, b = MOTIONS[name]
        length = math.floor(float(clip["duration"]) * 1000) / 1000
        first, last = {"time": 0.0, "scale": a * cover}, {"time": length, "scale": b * cover}
        patch = {"scale": first["scale"], "x": .5, "y": .5}
        if name in ("pan_left", "pan_right"):
            sign = 1 if name == "pan_right" else -1
            first["x"], last["x"] = .5 - sign * PAN, .5 + sign * PAN
            patch["x"] = first["x"]
        patch["keyframes"] = [first, last]
        needs_background = vertical and not any(str(c.get("title", "")).endswith(" фон") for c in frame["clips"])
        if not needs_background:
            ctx.actions.append({"type": "update_clip", "payload": {"clip_id": clip["id"], "patch": patch}})
        if needs_background:
            fill = max((ctx.W / ctx.H) / aspect, aspect / (ctx.W / ctx.H)) * 1.06
            ctx.actions.append({"type": "add_clip", "payload": {"layer_id": anchor, "group_id": frame["group"]["id"],
                                                                 "start": float(clip["start"]), "duration": float(clip["duration"]), "title": f"K{number:03d} фон",
                                                                 "kind": "image", "asset_id": clip["asset_id"], "blur": 30, "opacity": .9, "scale": fill * 1.08,
                                                                 "easing": ctx.easing, "keyframes": [{"time": 0.0, "scale": fill * 1.08}, {"time": length, "scale": fill}]}})
            # a new clip opens the top layer: the photo is laid again after its blurred copy, so it stays above it
            ctx.actions.append({"type": "delete_clip", "payload": {"clip_id": clip["id"]}})
            again = {k: clip[k] for k in ("kind", "asset_id", "start", "duration", "title", "volume", "trim_start", "width", "height", "opacity") if k in clip}
            ctx.actions.append({"type": "add_clip", "payload": {**again, **patch, "layer_id": anchor, "group_id": frame["group"]["id"],
                                                                 "easing": clip.get("easing", ctx.easing)}})
        changed += 1
    ctx.report.append(f"рух оновлено в кадрах: {changed}")


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
            local = mid - (float(accent_clip["start"]) - float(clip["start"]))
            centre = (keyframe_value(accent_clip, "x", local) * ctx.W, keyframe_value(accent_clip, "y", local) * ctx.H)
            text = accent_clip.get("kind") == "text"
            pin = picture.covers(centre[0], centre[1], mid) if text else True
            keys, base = _glued(picture, centre, mid, duration, ctx, pin)
            fades = [{"time": p["time"], "opacity": p["opacity"]} for p in accent_clip.get("keyframes") or [] if "opacity" in p]
            kind = accent_kind(accent_clip)
            if text or kind not in ENTRANCE or not fades:
                ctx.actions.append({"type": "update_clip", "payload": {"clip_id": accent_clip["id"],
                                                                        "patch": {"x": base["x"], "y": base["y"], "scale": 1.0, "keyframes": merge(keys, fades)}}})
                done += 1
                continue
            top = float(fades[-1]["opacity"]) or 1.0
            old = by_title.get(accent_clip["title"])
            shown = next((float(p["time"]) for p in fades if float(p["opacity"]) > 0), .3)
            at = float(old["start"]) - float(accent_clip["start"]) if old else max(0.0, shown - .25)
            length = ENTRANCE[kind]
            at = max(0.0, min(at, duration - length - .2))
            visible = round(at + length, 3)
            fades = [{"time": 0.0, "opacity": 0.0}, {"time": round(visible - .04, 3), "opacity": 0.0}, {"time": visible, "opacity": top}]
            steady = {**accent_clip, **base, "scale": 1.0, "keyframes": merge(keys, fades)}
            ctx.actions.append({"type": "update_clip", "payload": {"clip_id": accent_clip["id"],
                                                                    "patch": {"x": base["x"], "y": base["y"], "scale": 1.0, "keyframes": steady["keyframes"]}}})
            path = store.resolve_asset(ctx.project, accent_clip["asset_id"])["path"] if accent_clip.get("asset_id") else None
            title = accent_clip["title"].split(" акцент ", 1)[-1]
            ctx.actions.append(_entrance_action(ctx, frame, picture, title, steady, at, length, top, path))
            done += 1
            animated_count += 1
    ctx.report.append(f"акцентів приклеєно до фото: {done}, з анімованою появою: {animated_count}")


OPS = {"reglue": reglue, "reanimate": reglue, "animate_accents": reglue, "accent": accent, "clear_accents": clear_accents, "replace": replace, "transitions": transitions, "place": place, "remove": remove, "motion": motion}


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
