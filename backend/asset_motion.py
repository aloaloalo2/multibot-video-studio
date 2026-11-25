"""Motion of transparent PNG props: how a picture comes into a frame, lives in it and holds to the seam.

Agents put pictures on transparent backgrounds over photos and text frames: accent pictures (`accent kind=image`),
`animation` layers with `content_type: image` and the PNG layers of native animation frames. Before this module most
of them faded in over 0.35 s and then stood still for the rest of the frame (fennel episode, 25 November 2026: 191 of
423 PNG layers had no motion at all, 101 stopped moving more than a second before their end, 30 came in during the
frame's last second), all under linear easing, so every entrance started and stopped with a jolt.

A recipe is three parts:

- the entrance: "slide" (comes in from a side and overshoots a little), "rise" (surfaces with a scale from below 1),
  "drop" (falls in from above and bounces), "pop" (springs open), "fade" (a soft fade with a small scale);
- the life: "float" (a slow drift around its place), "drift" (a slow travel in one direction, parallax), "pulse"
  (a gentle breath of scale with a small float), "still" only when asked;
- the end: "hold" (keeps living to the seam; the transition takes it with the frame) or "out" (leaves before the
  clip ends, only for a clip that ends before its frame).

Everything is sampled into keyframes of x, y, scale and opacity under linear easing (the engine and the preview read
them the same way), on fractions of a pixel. The entrance starts on the word the voice says (word_timing) or at an
explicit moment, never inside the frame's last second (montage_ops.LAST_QUIET), and the picture moves until its last
keyframe at the clip's end. Each channel moves its own way: amplitudes, speeds, overshoot, the entrances it prefers and
the side things come from are drawn from the channel's design kit (channel_design.for_project) and shifted a little in
every film, so two channels never share one motion template.
"""
from __future__ import annotations

import hashlib
import math
import random

import channel_design

VERSION = 1
ENTERS = ("slide", "rise", "drop", "pop", "fade")
LIVES = ("float", "drift", "pulse")
EXITS = ("hold", "out")
QUIET = 1.0          # the frame's last second: nothing new comes in (montage_ops.LAST_QUIET)
STEP = .04           # entrance sampling (a keyframe each video frame at 25 fps)
MAX_POINTS = 64      # one clip's keyframes stay well under the FFmpeg expression limit (~100)
SIDES = ("left", "right", "below", "above")


# ---------------------------------------------------------------- the channel's own way of moving

def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16))


def style(project: dict) -> dict:
    """The channel's motion style, drawn from its design kit's seed (made on this computer for this channel only) and
    shifted a little in this film."""
    seed = channel_design.for_project(project).get("seed") or f"none:{project.get('id')}"
    rng = _rng(seed, "asset-motion", VERSION)
    enters = rng.sample(list(ENTERS), 3)
    lives = rng.sample(list(LIVES), 2)
    base = {
        "enters": enters,                                     # the three entrances the channel uses, in its order
        "lives": lives,                                       # its two ways of living in a frame
        "enter_length": rng.uniform(.5, .8),                  # seconds
        "overshoot": rng.uniform(.8, 1.9),                    # back-out strength of slide, rise and pop
        "bounce": rng.uniform(.25, .55),                      # height of the drop's first bounce, of the fall
        "distance": rng.uniform(.05, .11),                    # a slide's way in, a fraction of the frame width
        "side": rng.choice(SIDES),                            # where things come from first
        "float_px": rng.uniform(4.0, 9.0),                    # float amplitude in px of a 1080p frame
        "float_period": rng.uniform(4.0, 7.5),                # seconds
        "drift_px_s": rng.uniform(3.0, 7.0),                  # drift speed in px a second of a 1080p frame
        "drift_angle": rng.uniform(0, 2 * math.pi),
        "breath": rng.uniform(.012, .028),                    # pulse: scale amplitude
        "breath_period": rng.uniform(2.6, 4.4),
        "stagger": rng.uniform(.09, .2),                      # seconds between items of one group
        "parallax": rng.uniform(.04, .12),                    # how much more than its photo a glued prop moves
    }
    film = _rng(seed, project.get("id"), "film-motion")
    for key, spread in (("enter_length", .08), ("float_px", 1.0), ("float_period", .6), ("drift_px_s", .8),
                        ("breath", .003), ("stagger", .02), ("distance", .01), ("overshoot", .2)):
        base[key] = round(base[key] + film.uniform(-spread, spread), 4)
    base["drift_angle"] = round(base["drift_angle"] + film.uniform(-.5, .5), 4)
    return base


def recipe(project: dict, frame: int | None, index: int = 0, spec: dict | str | None = None) -> dict:
    """The recipe of prop `index` in frame `frame`: the channel's entrance for this frame (one per frame, so a group
    comes in together, one after another), its life (alternating within the frame) and "hold". `spec` overrides any
    part: {"enter": "drop", "life": "pulse", "exit": "out", "side": "left", "delay": .2} or just the entrance name."""
    look = style(project)
    pick = _rng(project.get("id"), frame, "recipe")
    enter = look["enters"][pick.randrange(len(look["enters"]))]
    life = look["lives"][(index + pick.randrange(2)) % len(look["lives"])]
    sides = list(SIDES)
    side = sides[(sides.index(look["side"]) + pick.randrange(4) + index % 2) % 4] if enter == "slide" else look["side"]
    made = {"enter": enter, "life": life, "exit": "hold", "side": side, "delay": round(index * look["stagger"], 3),
            "phase": round(_rng(project.get("id"), frame, index, "phase").uniform(0, 2 * math.pi), 4)}
    if isinstance(spec, str):
        spec = {"enter": spec}
    for key, value in (spec or {}).items():
        if key in made and value is not None:
            made[key] = value
    if made["enter"] not in ENTERS + ("none",):
        raise ValueError(f"Невідома поява картинки: {made['enter']} ({', '.join(ENTERS)})")
    if made["life"] not in LIVES + ("still",):
        raise ValueError(f"Невідомий рух картинки в кадрі: {made['life']} ({', '.join(LIVES)})")
    if made["exit"] not in EXITS:
        raise ValueError(f"Невідомий кінець руху картинки: {made['exit']} (hold, out)")
    if made["side"] not in SIDES:
        raise ValueError(f"Невідомий бік появи: {made['side']} ({', '.join(SIDES)})")
    return made


# ---------------------------------------------------------------- curves

def _back_out(p: float, k: float) -> float:
    p = max(0.0, min(1.0, p)) - 1
    return 1 + (k + 1) * p ** 3 + k * p ** 2


def _bounce_out(p: float, height: float) -> float:
    """1 at the end; a fall with one bounce of `height` (fraction of the fall) and a small second one."""
    p = max(0.0, min(1.0, p))
    a, b = .62, .86
    if p < a:
        return (p / a) ** 2
    if p < b:
        q = (p - a) / (b - a)
        return 1 - height * 4 * q * (1 - q)
    q = (p - b) / (1 - b)
    return 1 - height * .3 * 4 * q * (1 - q)


def _smooth(p: float) -> float:
    p = max(0.0, min(1.0, p))
    return p * p * (3 - 2 * p)


def entrance(enter: str, tau: float, length: float, look: dict, side: str, W: float, H: float, w: float, h: float):
    """(dx px, dy px, scale factor, opacity factor) at `tau` seconds into the entrance."""
    p = tau / length if length > 0 else 1.0
    if enter in ("none",) or p >= 1:
        return 0.0, 0.0, 1.0, 1.0
    if enter == "slide":
        d = look["distance"] * W
        far = 1 - _back_out(p, look["overshoot"])
        vec = {"left": (-1, 0), "right": (1, 0), "below": (0, 1), "above": (0, -1)}[side]
        if side in ("below", "above"):
            d = max(d * H / W, h * .35)
        return vec[0] * d * far, vec[1] * d * far, 1.0, min(1.0, p / .35)
    if enter == "rise":
        s = .82 + .18 * _back_out(p, look["overshoot"] * .7)
        return 0.0, (1 - _smooth(p)) * .015 * H, s, min(1.0, p / .5)
    if enter == "drop":
        fall = max(.07 * H, h * .45)
        return 0.0, -(1 - _bounce_out(p, look["bounce"])) * fall, 1.0, min(1.0, p / .18)
    if enter == "pop":
        return 0.0, 0.0, .45 + .55 * _back_out(p, look["overshoot"] * 1.2), min(1.0, p / .2)
    return 0.0, 0.0, .94 + .06 * _smooth(p), _smooth(p / .8)   # fade


def life(kind: str, t: float, look: dict, phase: float, H: float, room: tuple[float, float]) -> tuple[float, float, float]:
    """(dx px, dy px, scale factor) `t` seconds into the life; `room` keeps the travel inside the frame (px, x and y)."""
    k = H / 1080
    if kind == "still":
        return 0.0, 0.0, 1.0
    amp_x, amp_y = min(look["float_px"] * k, room[0]), min(look["float_px"] * k, room[1])
    w = 2 * math.pi / look["float_period"]
    fx, fy = amp_x * .6 * math.sin(w * .63 * t + phase * 1.7), amp_y * math.sin(w * t + phase)
    if kind == "float":
        return fx, fy, 1.0
    if kind == "drift":
        speed = look["drift_px_s"] * k
        ux, uy = math.cos(look["drift_angle"]), math.sin(look["drift_angle"])
        return ux * speed * t * .999 + fx * .35, uy * speed * t * .999 + fy * .35, 1.0
    breath = 1 + look["breath"] * math.sin(2 * math.pi * t / look["breath_period"] + phase)
    return fx * .5, fy * .5, breath   # pulse


# ---------------------------------------------------------------- keyframes

def keyframes(project: dict, made: dict, *, duration: float, at: float, x: float, y: float, width: float, height: float,
              scale: float = 1.0, opacity: float = 1.0, base=None, latest: float | None = None) -> list[dict]:
    """Keyframes of one picture by `made` (recipe()): `at` seconds into the clip it starts its entrance, `latest` the
    last moment it may start (the frame's quiet second); x, y, width and height are fractions of the frame at scale 1.
    `base(t)` gives (x, y, scale) of a picture glued to a moving photo; the prop then moves with it and a little more
    (parallax). The clip that carries them must use "easing": "linear"."""
    W, H = float(project.get("width", 1920)), float(project.get("height", 1080))
    look = style(project)
    length = min(float(look["enter_length"]) * (1.15 if made["enter"] == "drop" else 1.0), max(.2, duration * .5))
    at = max(0.0, float(at) + float(made.get("delay", 0)))
    if latest is not None:
        at = min(at, max(0.0, latest))
    at = min(at, max(0.0, duration - .3))
    length = max(.2, min(length, duration - at - .04)) if duration - at > .3 else max(.04, duration - at)
    end = math.floor(duration * 1000) / 1000
    mid = duration / 2
    ref = base(mid) if base else (x, y, scale)

    def anchor(t):
        if not base:
            return x, y, scale
        bx, by, bs = base(t)
        p = float(look["parallax"])
        return bx + (bx - ref[0]) * p, by + (by - ref[1]) * p, bs * (1 + (bs / ref[2] - 1) * p)

    # room to move: the distance from the picture's box to the frame's edges, never pushing it further out
    half_w, half_h = width * W * scale / 2, height * H * scale / 2
    cx, cy = ref[0] * W, ref[1] * H
    room_x = max(0.0, min(cx - half_w, W - cx - half_w))
    room_y = max(0.0, min(cy - half_h, H - cy - half_h))
    span = max(0.0, end - at - length)
    if made["life"] == "drift":       # a drift's whole travel fits the room it has
        speed = look["drift_px_s"] * H / 1080
        travel = speed * span
        limit = max(0.0, min(room_x / max(abs(math.cos(look["drift_angle"])), 1e-3),
                             room_y / max(abs(math.sin(look["drift_angle"])), 1e-3)))
        if travel > limit:
            look = {**look, "drift_px_s": limit / max(span, 1e-3) * 1080 / H}
    room = (room_x * .8, room_y * .8)

    def at_time(t):
        bx, by, bs = anchor(t)
        if t < at:
            dx, dy, sf, of = entrance(made["enter"], 0.0, length, look, made["side"], W, H, width * W, height * H)
            return bx * W + dx * bs / scale, by * H + dy * bs / scale, bs * sf, 0.0
        tau = t - at
        dx, dy, sf, of = entrance(made["enter"], tau, length, look, made["side"], W, H, width * W, height * H)
        lt = max(0.0, tau - length)
        lx, ly, ls = life(made["life"], lt, look, float(made.get("phase", 0)), H, room)
        envelope = _smooth(lt / .8)          # the life fades in after the entrance: no jolt of speed
        lx, ly, ls = lx * envelope, ly * envelope, 1 + (ls - 1) * envelope
        o = of
        if made["exit"] == "out" and duration - t < .4:
            q = _smooth((duration - t) / .4)
            o *= q
            sf *= .9 + .1 * q
        return bx * W + dx + lx, by * H + dy + ly, bs * sf * ls, o

    moments = {0.0, end}
    if at > 0:
        moments.add(max(0.0, round(at - .001, 3)))
    k = 0
    while at + k * STEP < at + length + 1e-9:
        moments.add(round(at + k * STEP, 3))
        k += 1
    moments.add(round(min(end, at + length), 3))
    entering = len(moments)
    if span > 0:
        period = min(look["float_period"], look["breath_period"]) if made["life"] == "pulse" else look["float_period"]
        step = max(period / 12, span / max(1, MAX_POINTS - entering - 2), .12)
        count = max(1, math.ceil(span / step))
        for i in range(1, count + 1):
            moments.add(round(min(end, at + length + span * i / count), 3))
    points = []
    for t in sorted(m for m in moments if 0 <= m <= end):
        px, py, s, o = at_time(t)
        points.append({"time": t, "x": round(px / W, 5), "y": round(py / H, 5), "scale": round(max(.05, s), 5),
                       "opacity": round(max(0.0, min(1.0, o * opacity)), 4)})
    return points


# ---------------------------------------------------------------- PNG layers placed by agents (native animation)

def _moving(part: dict) -> list[float]:
    return sorted(float(k["time"]) for k in part.get("keyframes") or [] if {"x", "y", "scale"} & set(k))


def value(part: dict, prop: str, t: float) -> float:
    """A property of a layer at `t` under its own easing (as montage_ops.keyframe_value and the engine read it)."""
    base = float(part.get(prop, .5 if prop in ("x", "y") else 1.0))
    known = sorted((float(p["time"]), float(p[prop])) for p in part.get("keyframes") or [] if prop in p)
    if not known:
        return base
    if known[0][0] > 1e-9:
        known.insert(0, (0.0, base))
    if t <= known[0][0]:
        return known[0][1]
    mode = part.get("easing", "linear")
    for (t0, a), (t1, b) in zip(known, known[1:]):
        if t < t1:
            p = max(0.0, min(1.0, (t - t0) / (t1 - t0)))
            p = p ** 3 if mode == "ease_in" else 1 - (1 - p) ** 3 if mode == "ease_out" else p * p * (3 - 2 * p) if mode == "ease_in_out" else p
            return a + (b - a) * p
    return known[-1][1]


def is_backdrop(part: dict) -> bool:
    """A layer as big as the frame: a background, or a drawing laid over the whole composition (a contour, a pointer,
    a label line); it never moves on its own, only together with the props it is drawn over."""
    return float(part.get("width", 1)) >= .97 and float(part.get("height", 1)) >= .97


_INK: dict = {}


def ink_box(path) -> tuple[float, float, float, float] | None:
    """Where a PNG has ink (alpha), as fractions of the picture; None when it cannot be read."""
    if not path:
        return None
    try:
        import os
        from PIL import Image
        key = (str(path), os.stat(path).st_mtime_ns)
        if key not in _INK:
            with Image.open(path) as image:
                alpha = image.getchannel("A") if "A" in image.getbands() else None
                box = alpha.point(lambda v: 255 if v > 24 else 0).getbbox() if alpha else (0, 0, image.width, image.height)
                _INK[key] = None if box is None else (box[0] / image.width, box[1] / image.height, box[2] / image.width, box[3] / image.height)
        return _INK[key]
    except (OSError, ValueError):
        return None


def _box(part: dict, ink=None) -> tuple[float, float, float, float]:
    x, y, s = float(part.get("x", .5)), float(part.get("y", .5)), float(part.get("scale", 1))
    w, h = float(part.get("width", 1)) * s, float(part.get("height", 1)) * s
    l, t = x - w / 2, y - h / 2
    ink = ink or (0, 0, 1, 1)
    return l + ink[0] * w, t + ink[1] * h, l + ink[2] * w, t + ink[3] * h


def _overlap(a, b) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(a) -> float:
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def _bring_forward(part: dict, frame_duration: float) -> str | None:
    """Nothing new in the frame's last second: a layer that would come in there comes in earlier and keeps its end."""
    start, length = float(part["start"]), float(part["duration"])
    first = start + next((float(k["time"]) for k in sorted(part.get("keyframes") or [], key=lambda k: float(k["time"]))
                          if float(k.get("opacity", 1)) > .05), 0.0)
    latest = frame_duration - QUIET
    if start > .001 and first > latest + 1e-6:
        shift = min(start, first - max(0.0, latest))
        # the same entrance, earlier: its keyframes keep their times from the (earlier) start, the end stays
        part["start"], part["duration"] = round(start - shift, 3), round(length + shift, 3)
        return f"поява на {shift:.2f} с раніше"
    return None


def _recipe(project: dict, part: dict, spec, frame_duration: float, number, index: int, word_at) -> str:
    start, length = float(part["start"]), float(part["duration"])
    made = recipe(project, number, index, spec if isinstance(spec, (dict, str)) else None)
    local = 0.0
    if isinstance(spec, dict) and spec.get("at") is not None:
        local = float(spec["at"])
    elif word_at is not None:
        local = word_at - start
    if local < 0:   # the word is said before the layer's start: the layer starts with it
        part["start"], part["duration"] = round(max(0.0, start + local), 3), round(length - max(local, -start), 3)
        start, length, local = float(part["start"]), float(part["duration"]), 0.0
    top = max([float(part.get("opacity", 1))] + [float(k["opacity"]) for k in part.get("keyframes") or [] if "opacity" in k])
    part["keyframes"] = keyframes(project, made, duration=length, at=local, latest=frame_duration - QUIET - start,
                                  x=float(part.get("x", .5)), y=float(part.get("y", .5)),
                                  width=float(part.get("width", 1)), height=float(part.get("height", 1)),
                                  scale=float(part.get("scale", 1)), opacity=top)
    part["easing"] = "linear"
    return f"рух {made['enter']}+{made['life']}"


def _add_life(project: dict, part: dict, kind: str, phase: float, since: float, room, factor: float) -> None:
    """The layer's own keyframes resampled under linear easing, plus the life `kind` from `since` (seconds from the
    frame start, shared by a cluster so its members move as one) to the layer's end."""
    look = style(project)
    W, H = float(project.get("width", 1920)), float(project.get("height", 1080))
    start = float(part["start"])
    end = math.floor(float(part["duration"]) * 1000) / 1000
    local = max(0.0, since - start)
    own = sorted({float(k["time"]) for k in part.get("keyframes") or [] if float(k["time"]) <= end} | {0.0, end})
    span = max(1e-3, end - local)
    step = max(look["float_period"] / 12, span / max(1, MAX_POINTS - len(own) - 2), .12)
    count = max(1, math.ceil(span / step))
    times = sorted(set(own) | {round(local + span * i / count, 3) for i in range(count + 1)})
    fades = any("opacity" in k for k in part.get("keyframes") or [])
    points = []
    for t in times:
        point = {"time": round(t, 3)}
        for prop in ("x", "y", "scale") + (("opacity",) if fades else ()):
            point[prop] = value(part, prop, t)
        lt = t + start - since
        if lt > 0:
            lx, ly, ls = life(kind, lt, look, phase, H, room)
            envelope = _smooth(lt / .8) * factor
            point["x"] += lx * envelope / W
            point["y"] += ly * envelope / H
            point["scale"] *= 1 + (ls - 1) * envelope
        points.append({k: (round(v, 5) if k != "time" else v) for k, v in point.items()})
    part["keyframes"] = points
    part["easing"] = "linear"


def enliven_frame(project: dict, parts: list[dict], frame_duration: float, number: int | None,
                  words: dict | None = None, inks: dict | None = None) -> list[str]:
    """Bring the PNG layers of one native animation frame to life in place (start and duration relative to the
    frame). `words` maps a part's index to the frame second of its "motion" word, `inks` to its picture's ink box.

    - "motion" (a recipe name or {"enter", "life", "exit", "side", "delay", "word", "at"}) gives a layer the whole
      recipe; "motion": "still" leaves it as it is;
    - a layer that would appear in the frame's last second comes in earlier;
    - layers that stand still, or stop moving more than a second before their end, get the channel's life. Props that
      belong together (one drawn inside another, or under the same full-frame drawing: a contour, a pointer, a label
      line) move as one, with one phase and only a float, so nothing drawn over them slides off; next to a text or a
      shape that stays put they float three times less; the life starts when the group's own keyframed motion is over.
    Returns notes "title: what changed"."""
    words, inks = words or {}, inks or {}
    W, H = float(project.get("width", 1920)), float(project.get("height", 1080))
    notes: dict[int, list[str]] = {}
    image = [i for i, p in enumerate(parts) if p.get("kind") == "image" or p.get("content_type") == "image"]
    specs = {i: parts[i].pop("motion", None) for i in image}
    for i in image:
        if specs[i] in ("still", False):
            continue
        note = _bring_forward(parts[i], frame_duration)
        if note:
            notes.setdefault(i, []).append(note)
    for order, i in enumerate(i for i in image if specs[i] not in (None, "still", False) and not is_backdrop(parts[i])):
        notes.setdefault(i, []).append(_recipe(project, parts[i], specs[i], frame_duration, number, order, words.get(i)))
    # who belongs together
    free = [i for i in image if specs[i] is None and not is_backdrop(parts[i])]
    overlays = [i for i in image if specs[i] is None and is_backdrop(parts[i])]
    boxes = {i: _box(parts[i], inks.get(i)) for i in free + overlays}
    root = {i: i for i in free + overlays}

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    for a in free:
        for b in free:
            if a < b and _overlap(boxes[a], boxes[b]) >= .6 * min(_area(boxes[a]), _area(boxes[b])):
                root[find(a)] = find(b)
        for o in overlays:
            if inks.get(o) is None:
                continue   # a full-frame layer whose ink is unknown: nothing to tie it to
            if _overlap(boxes[a], boxes[o]) > 0:
                root[find(a)] = find(o)
    clusters: dict[int, list[int]] = {}
    for i in free + overlays:
        clusters.setdefault(find(i), []).append(i)
    others = [_box(p) for k, p in enumerate(parts) if k not in image and not is_backdrop(p)]
    for members in clusters.values():
        props = [i for i in members if i in free]
        if not props:
            continue
        ends = {i: math.floor(float(parts[i]["duration"]) * 1000) / 1000 for i in members}
        if any(_moving(parts[i]) and _moving(parts[i])[-1] >= ends[i] - 1.0 for i in members):
            continue   # the agent moves it to the end already
        made = recipe(project, number, props[0], {"enter": "none"})
        kind = made["life"] if len(members) == 1 else "float"
        # the life starts once every member's own motion is over; one shared offset never parts what is drawn together
        since = max([min(float(parts[i]["start"]) for i in members)] +
                    [float(parts[i]["start"]) + _moving(parts[i])[-1] for i in members if _moving(parts[i])])
        room_x = room_y = float("inf")
        for i in members:
            l, t, r, b = boxes[i]
            room_x, room_y = min(room_x, l * W, (1 - r) * W), min(room_y, t * H, (1 - b) * H)
        room = (max(0.0, room_x) * .8, max(0.0, room_y) * .8)
        if kind == "drift":
            span = max(float(parts[i]["start"]) + float(parts[i]["duration"]) for i in members) - since
            if min(room) < style(project)["drift_px_s"] * H / 1080 * span:
                kind = "float"
        near = any(_overlap(boxes[i], o) > 0 for i in members for o in others)
        factor = 1 / 3 if near else 1.0
        for i in members:
            _add_life(project, parts[i], kind, float(made["phase"]), since, room, factor)
            notes.setdefault(i, []).append(f"живе до кінця ({kind}{', разом із ' + str(len(members) - 1) if len(members) > 1 else ''})")
    return [f"{parts[i].get('title', 'PNG')}: {', '.join(n)}" for i, n in sorted(notes.items())]


def enliven(project: dict, part: dict, frame_duration: float, number: int | None, index: int = 0,
            word_at: float | None = None) -> str | None:
    """enliven_frame() for one layer alone (its full-frame drawing, if any, unknown)."""
    notes = enliven_frame(project, [part], frame_duration, number, {0: word_at} if word_at is not None else None)
    return ", ".join(n.split(": ", 1)[-1] for n in notes) or None


def enliven_layers(ctx, plan_frame: dict, parts: list[dict], frame_duration: float, frame_start: float) -> list[str]:
    """native_animation's call: the words of "motion" resolved to the voice's time in the frame and the PNGs' ink
    read from their files, then enliven_frame()."""
    import store
    words, inks = {}, {}
    try:
        for i, part in enumerate(parts):
            spec = part.get("motion")
            if isinstance(spec, dict) and spec.get("word"):
                import word_timing
                words[i] = word_timing.word_time(word_timing.frame_tokens(plan_frame, ctx.words()), str(spec["word"])) - frame_start
            if part.get("asset_id") and (part.get("kind") == "image" or part.get("content_type") == "image"):
                asset = next((a for a in ctx.project.get("assets", []) if a.get("id") == part["asset_id"]), None)
                inks[i] = ink_box(asset.get("path")) if asset else None
        return enliven_frame(ctx.project, parts, frame_duration, plan_frame.get("number"), words, inks)
    except ValueError as error:
        raise store.StudioError(str(error), 400) from None

BRIEF = ("Прозорі PNG у кадрі живуть до кінця кадру: студія дає їм рух каналу (поява slide|rise|drop|pop|fade, життя "
         "float|drift|pulse, кінець hold|out). Для шару зображення в op=\"animation\" передай \"motion\": {\"enter\": …, "
         "\"life\": …, \"word\": \"слово\"} (або \"motion\": \"drop\"), для accent kind=image ключі enter, life, exit; "
         "\"motion\": \"still\" лишає шар як є. Без motion нерухомий PNG отримає лише легке життя каналу, а поява в останню "
         "секунду кадру зсунеться раніше. Предмети групи з'являються по черзі на слова, а не всі разом і не однаково з кадру в кадр.")


def _glued_points(ctx, frame: dict, picture, title: str, centre, size, at: float, duration: float, spec: dict) -> list[dict]:
    clip = picture.clip if picture else None
    start = float(clip["start"]) if clip else float(frame["start"])
    mid = duration / 2
    base = None
    if picture is not None and spec.get("pin", True):
        u, v = picture.to_photo(centre[0], centre[1], mid)
        reference = picture.state(mid)[2]

        def base(t):
            px, py = picture.to_frame(u, v, t)
            return px / ctx.W, py / ctx.H, picture.state(t)[2] / reference
    words = str(title).split()
    index = int(words[0]) if words and words[0].isdigit() else 0
    made = recipe(ctx.project, frame.get("number"), index, {k: spec.get(k) for k in ("enter", "life", "exit", "side", "delay")})
    if made["exit"] == "out" and start + duration >= float(frame["end"]) - .05:
        made["exit"] = "hold"   # a prop that lives to the seam leaves with the transition
    return keyframes(ctx.project, made, duration=duration, at=at, latest=float(frame["end"]) - start - QUIET,
                     x=centre[0] / ctx.W, y=centre[1] / ctx.H, width=size[0] / ctx.W, height=size[1] / ctx.H, base=base,
                     opacity=float(spec.get("opacity", 1)))


def accent(ctx, frame: dict, picture, title: str, payload: dict, centre, size, at: float, duration: float, spec: dict | None) -> None:
    """An accent picture (montage_ops accent kind=image) with its whole motion in one clip: glued to the frame's photo
    (it rides the photo's pan and zoom with a little parallax), coming in by the channel's recipe at `at`."""
    points = _glued_points(ctx, frame, picture, title, centre, size, at, duration, spec or {})
    ctx.add(frame, picture, title, {**payload, "width": size[0] / ctx.W, "height": size[1] / ctx.H, "x": points[0]["x"],
                                    "y": points[0]["y"], "scale": 1.0, "opacity": 1.0, "keyframes": points, "easing": "linear"})


def is_living(clip: dict) -> bool:
    """An accent picture made by accent(): one linear clip carrying its own entrance, no separate «поява» clip."""
    return str(clip.get("title", "")).endswith(" картинка") and clip.get("easing") == "linear" and len(clip.get("keyframes") or []) > 8


def reglued(ctx, frame: dict, picture, clip: dict) -> dict:
    """The patch that glues a living accent picture to the frame's photo again (montage_ops.reglue): the same place at
    the frame's middle moment, the same moment of appearance, the recipe of this channel."""
    duration = picture.duration
    local = duration / 2 - (float(clip["start"]) - float(picture.clip["start"]))
    centre = (value(clip, "x", local) * ctx.W, value(clip, "y", local) * ctx.H)
    keys = clip.get("keyframes") or []
    at = next((float(k["time"]) for k in keys if float(k.get("opacity", 1)) > 0), 0.0)
    at = max(0.0, at - STEP)
    size = (float(clip.get("width", .2)) * ctx.W, float(clip.get("height", .2)) * ctx.H)
    spec = {"delay": 0, "opacity": max(float(k.get("opacity", 1)) for k in keys) if keys else 1.0}
    title = clip["title"].split(" акцент ", 1)[-1]
    want = centre
    for _ in range(4):   # the place without the life's offset at that moment: rebuild until the middle moment matches
        points = _glued_points(ctx, frame, picture, title, centre, size, at, duration, spec)
        got = (value({"keyframes": points}, "x", local) * ctx.W, value({"keyframes": points}, "y", local) * ctx.H)
        centre = (centre[0] + want[0] - got[0], centre[1] + want[1] - got[1])
    points = _glued_points(ctx, frame, picture, title, centre, size, at, duration, spec)
    return {"x": points[0]["x"], "y": points[0]["y"], "scale": 1.0, "keyframes": points, "easing": "linear"}

