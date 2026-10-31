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
- {"op": "place", "frame": 12, "path": file | "asset_id": id | "text": true, "motion": "zoom_in"} puts a frame of the
  plan on the timeline at the plan frame's time, in its group «Кадр 12»: a picture or a video (a photo gets a slow
  zoom unless "motion": "none"), or with "text" the frame's own spoken words as a full-frame text. The frame agent of
  the photo channels (backend/production.py) builds the film with it.

The answer is short (the report lines and the new revision), so an agent does not have to read the whole project back.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

import display_text
import joins
import number_text
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
EASINGS = {"linear", "ease_in", "ease_out", "ease_in_out"}


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


def media_size(path: str) -> tuple[int, int] | None:
    """The picture's display size (a video's frame turned by its rotation)."""
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


def main_picture(project: dict, frame: dict) -> dict | None:
    pictures = [c for c in frame["clips"] if not is_accent(c) and c.get("asset_id") and
                (c.get("kind") in ("image", "video") or c.get("kind") == "animation" and c.get("content_type") == "image")]
    return max(pictures, key=lambda c: float(c.get("width", 1)) * float(c.get("height", 1)), default=None)


def merge(*rows: list[dict]) -> list[dict]:
    by_time = {}
    for row in rows:
        for point in row:
            by_time.setdefault(round(float(point["time"]), 6), {"time": round(float(point["time"]), 6)}).update({k: v for k, v in point.items() if k != "time"})
    return sorted(by_time.values(), key=lambda p: p["time"])


def appear(at: float, duration: float, top: float = 1.0) -> list[dict]:
    at = max(0.05, min(at, duration - 0.4))
    return [{"time": 0.0, "opacity": 0.0}, {"time": round(at - 0.04, 3), "opacity": 0.0}, {"time": round(at + 0.25, 3), "opacity": top}]


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
        folder = store.project_dir(self.project["id"]) / "media" / "accents"
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
    index = sum(1 for c in frame["clips"] if is_accent(c)) + sum(1 for a in ctx.actions if a["type"] == "add_clip" and a["payload"].get("group_id") == frame["group"]["id"])
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
        ctx.add(frame, picture, f"{index} картка", {"kind": "animation", "content_type": "shape", "color": spec.get("color", NAVY), **base,
                                                    "width": w / ctx.W, "height": h / ctx.H, "opacity": 1, "mask": "rounded",
                                                    "corner_radius": float(spec.get("radius", min(24, h / 2))),
                                                    "keyframes": merge(appear(_moment(ctx, frame, spec, start), duration, float(spec.get("opacity", .9))), keys)})
    else:
        raise OpError("Невідомий вид акценту: text, arrow, circle, card або image")
    ctx.report.append(f"кадр {frame['number'] or frame['group']['title']}: {kind}")


def _accent_picture(ctx, frame, picture, title, path, centre, size, at, duration, mid):
    keys, base = _glued(picture, centre, mid, duration, ctx)
    ctx.add(frame, picture, title, {"kind": "image", "asset_id": ctx.asset_for(path), **base, "width": size[0] / ctx.W, "height": size[1] / ctx.H,
                                    "opacity": 1, "keyframes": merge(appear(at, duration), keys)})


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
        ctx.add(frame, picture, f"{index} {under['title']}", {"kind": "animation", "content_type": "shape", "color": under["color"], **base,
                                                            "width": under["size"][0] / ctx.W, "height": under["size"][1] / ctx.H, "opacity": 1,
                                                            "mask": "rounded", "corner_radius": under["radius"], "keyframes": merge(appear(under["at"], duration, under["top"]), keys)})
    keys, base = _glued(picture, (bx, by), mid, duration, ctx, pin)
    entrance = spec.get("entrance") or ENTRANCES[ctx.entrance % len(ENTRANCES)]
    ctx.entrance += 1
    ctx.add(frame, picture, f"{index} текст", {"kind": "text", "text": " ".join(w["text"] for w in placed), **base, "width": box / ctx.W, "height": height / ctx.H,
                                              "font_size": stub["font_size"], "font_family": family, "font_weight": weight, "color": spec.get("text_color", color),
                                              "text_words": placed, "word_entrance": {"type": entrance, "duration": 0.22, "distance": 14}, "shadow": shadow,
                                              "text_role": "label", "keyframes": keys})


def clear_accents(ctx: Context, spec: dict) -> None:
    frame = find_frame(ctx.frames, spec.get("frame"))
    ids = [c["id"] for c in frame["clips"] if is_accent(c)]
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
MOTIONS = {"zoom_in": (1.0, 1.08), "zoom_out": (1.08, 1.0), "none": None}


def place(ctx: Context, spec: dict) -> None:
    number = int(spec["frame"])
    planned = next((f for f in (ctx.plan or {}).get("frames", []) if int(f.get("number", 0)) == number), None)
    if planned is None:
        raise OpError(f"Кадру {number} немає в плані", 404)
    have = next((f for f in ctx.frames if f["number"] == number), None)
    if have and (main_picture(ctx.project, have) or _full_frame_text(have) and any(c.get("kind") == "text" for c in have["clips"])):
        raise OpError(f"Кадр {number} уже стоїть на таймлайні: замініть його картинку через replace")
    start, end = float(planned["start"]), float(planned["end"])
    payload = {"layer_id": ctx.project["tracks"][0]["id"], "start": round(start, 3), "duration": round(end - start, 3),
               "title": FRAME_CLIP.format(number)}
    if spec.get("text"):
        words = display_text.clean(" ".join(planned.get("sentences") or []))
        if not words.strip():
            raise OpError(f"У кадрі {number} немає слів для текстового кадру")
        payload.update(kind="text", text=words, text_role="full_frame", source_frame=number, source_text=" ".join(planned.get("sentences") or []))
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
        motion = MOTIONS.get(spec.get("motion") or ("zoom_in" if kind == "image" else "none"), MOTIONS["zoom_in"])
        if motion:
            payload.update(scale=motion[0], easing=ctx.easing,
                           keyframes=[{"time": 0.0, "scale": motion[0]}, {"time": round(end - start, 3), "scale": motion[1]}])
    if have:
        payload["group_id"] = have["group"]["id"]
    else:
        ctx.groups[FRAME_CLIP.format(number)] = f"Кадр {number}"
    ctx.actions.append({"type": "add_clip", "payload": payload})
    ctx.report.append(f"кадр {number}: {'текст' if spec.get('text') else payload['kind']} {start:.2f}–{end:.2f} с")


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


OPS = {"accent": accent, "clear_accents": clear_accents, "replace": replace, "transitions": transitions, "place": place}


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
                if not (store.under(path, Path(project["episode_path"])) or store.under(path, store.project_dir(pid) / "media")):
                    raise OpError(f"Файл поза випуском: {path}")
            known = {a["id"] for a in project.get("assets", [])}
            project.setdefault("assets", []).extend(record for record in (store.asset_record(path, pid) for path in ctx.files) if record["id"] not in known)
            project["revision"] = project.get("revision", 0) + 1
            store.save_project(project)
        result = store.apply_action(pid, "batch", {"actions": ctx.actions}, project.get("revision", 0))
        if ctx.groups:
            # a frame placed where no group stood yet opens its own «Кадр N» group, as razgon_bridge.py slots does
            grouped = {cid for group in result.get("scene_groups", []) for cid in group.get("clip_ids", [])}
            new = [{"type": "group_clips", "payload": {"clip_ids": [clip["id"]], "title": ctx.groups[clip.get("title")]}}
                   for track in result.get("tracks", []) for clip in track.get("clips", [])
                   if clip.get("title") in ctx.groups and clip["id"] not in grouped]
            if new:
                result = store.apply_action(pid, "batch", {"actions": new}, result.get("revision", 0))
    return {"revision": result.get("revision", 0), "report": ctx.report, "applied": len(ctx.actions)}
