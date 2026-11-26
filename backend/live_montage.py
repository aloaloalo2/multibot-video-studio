"""Two montage operations for films already made, both deterministic and free (no Claude, no HeyGen).

`host_inset`: the host's frames move inside his speech, half a second from each side, and the neighbouring frames' main
pictures take those moments, so a transition at a host's seam plays over him talking, never over the frozen silence
HeyGen renders around a phrase (user, 26 November 2026: «Аватар 3… застиглі моменти… тиша… кадри сусідні… довші…
обрізати його зліва і справа… на півсекунди… як живий монтаж»). The plan's frames get the same edges
(planner.aligned_times with the frame's `host_inset`); captions, accents and words keep their own times.

`frame_camera`: a studio animation frame already on the timeline gets the same gentle move of the whole frame as the
`camera` field of the animation op (native_animation.apply_camera), every layer together.
"""
import copy
import math
from pathlib import Path

import montage_ops
import native_animation
import planner
import store


def _base(clip, start, end, fps):
    """A clip that carries the frame's picture: it spans the whole frame and is no caption."""
    near = 1.5 / fps + 1e-6
    return (clip.get("kind") != "text" and abs(float(clip["start"]) - start) <= near
            and abs(float(clip["start"]) + float(clip["duration"]) - end) <= near)


def _stretched(keyframes, old, new):
    if not keyframes or old <= 0:
        return keyframes
    k = new / old
    return [{**p, "time": round(min(float(p["time"]) * k, montage_ops.end_time(new)), 4)} for p in keyframes]


def _spare(project, clip):
    """Seconds of a video clip's own footage after its end on the timeline; None for a picture or code."""
    if clip.get("kind") != "video":
        return None
    asset = next((a for a in project.get("assets", []) if a.get("id") == clip.get("asset_id")), None)
    total = store.media_duration(Path(asset["path"])) if asset and asset.get("path") else None
    if not total:
        return 0.0
    rate = float(clip.get("speed") or 1)
    return total - float(clip.get("trim_start") or 0) - float(clip["duration"]) * rate


FREEZE_NOISE, FREEZE_MIN = .001, .12   # a picture this still for this long is HeyGen's frozen host, not a calm talk


def living_span(path, length):
    """(first, last) moment of a host video where he still moves: the frozen stretches that touch its start or its end
    (HeyGen holds him still in a quiet start or a fading last syllable, not only in silence) are left out."""
    import re
    import subprocess
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vf", f"freezedetect=n={FREEZE_NOISE}:d={FREEZE_MIN}",
                          "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=300).stderr
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", out)]
    spans = [(a, ends[i] if i < len(ends) else length) for i, a in enumerate(starts)]
    # frozen at the start or the end: pieces a tenth of a second apart are one stretch, and a stretch that stops within
    # 0.4 s of the edge counts (HeyGen often lets the head drift a little after the face has stopped)
    first, last = 0.0, length
    reach = .4
    for a, b in spans:
        if a <= first + reach:
            first, reach = max(first, b), .1
    reach = .4
    for a, b in reversed(spans):
        if b >= last - reach:
            last, reach = min(last, a), .1
    return first, last


def _join_need(project, left_id, right_id):
    """Seconds a transition at this seam takes from the left side past the seam and from the right side before it."""
    for join in project.get("join_transitions", []):
        if join["from_ref"].endswith(left_id) and join["to_ref"].endswith(right_id):
            lead = float(join.get("lead") or 0)
            return float(join["duration"]) - lead, lead
    return 0.0, 0.0


def host_inset(ctx, spec: dict) -> None:
    fps = int(ctx.project.get("fps") or 25)
    snap = lambda t: round(math.floor(float(t) * fps + .5 + 1e-8) / fps, 6)   # half a frame rounds up, as the studio's edges
    plan = ctx.plan or {}
    frames = plan.get("frames") or []
    wanted = set(spec.get("frames") or []) or None
    groups = {f["number"]: f for f in ctx.frames if f["number"] is not None}
    new_frames = copy.deepcopy(frames)
    patches = {}
    done, skipped = [], []

    def patch(clip, **fields):
        patches.setdefault(clip["id"], {}).update(fields)

    for i, frame in enumerate(frames):
        if frame.get("format") != "host" or (wanted and frame["number"] not in wanted):
            continue
        timings = [t for t in frame.get("sentence_timings") or [] if isinstance(t, dict)]
        if not timings or i == 0 or i == len(frames) - 1:
            continue
        a, b = float(timings[0]["start"]), float(timings[-1]["end"])
        cut = max(0.0, min(planner.HOST_INSET, (b - a - planner.HOST_MIN_VISIBLE) / 2))
        host, prev, nxt = groups.get(frame["number"]), groups.get(frames[i - 1]["number"]), groups.get(frames[i + 1]["number"])
        if not (host and prev and nxt):
            skipped.append(frame["number"])
            continue
        s0, e0 = host["start"], host["end"]
        s1, e1 = (s0, e0) if frame.get("host_inset") else (a + cut, b - cut)
        # and inside the moments he really moves, with room for the transitions on both seams
        video = next((c for c in host["clips"] if c.get("kind") == "video"), None)
        asset = video and next((x for x in ctx.project.get("assets", []) if x.get("id") == video.get("asset_id")), None)
        if asset and asset.get("path") and spec.get("living", True):
            length = store.media_duration(Path(asset["path"])) or 0
            if length:
                first, last = living_span(asset["path"], length)
                rate, trim = float(video.get("speed") or 1), float(video.get("trim_start") or 0)
                at = lambda v: float(video["start"]) + (v - trim) / rate           # the video's moment on the timeline
                need_in = _join_need(ctx.project, prev["group"]["id"], host["group"]["id"])[1]
                need_out = _join_need(ctx.project, host["group"]["id"], nxt["group"]["id"])[0]
                s1, e1 = max(s1, at(first) + need_in + 1 / fps), min(e1, at(last) - need_out - 1 / fps)
        s1, e1 = snap(s1), snap(e1)
        if e1 - s1 < planner.HOST_MIN_VISIBLE - 1e-6:
            middle = (s1 + e1) / 2
            s1, e1 = snap(max(s0, middle - planner.HOST_MIN_VISIBLE / 2)), snap(min(e0, middle + planner.HOST_MIN_VISIBLE / 2))
        if abs(s1 - s0) < 1e-6 and abs(e1 - e0) < 1e-6:
            continue
        din, dout = round(s1 - s0, 6), round(e0 - e1, 6)
        if din < 0 or dout < 0 or e1 - s1 < planner.HOST_MIN_VISIBLE - 1e-6:
            skipped.append(frame["number"])
            continue
        prev_base = [c for c in prev["clips"] if _base(c, prev["start"], prev["end"], fps)]
        next_base = [c for c in nxt["clips"] if _base(c, nxt["start"], nxt["end"], fps)]
        # a stock video beside him needs footage for the longer time, or the host stays as he is
        if not prev_base or not next_base or any((_spare(ctx.project, c) or 0) < d - 1e-6
                                                 for c, d in [(c, din) for c in prev_base if c.get("kind") == "video"]
                                                 + [(c, dout) for c in next_base if c.get("kind") == "video"]):
            skipped.append(frame["number"])
            continue
        for c in host["clips"]:
            start, length = float(c["start"]), float(c["duration"])
            new_start, new_length = start, length
            if abs(start - s0) <= 1.5 / fps:
                new_start, new_length = s1, length - din
                if c.get("kind") == "video":
                    patch(c, trim_start=round(float(c.get("trim_start") or 0) + din * float(c.get("speed") or 1), 6))
            if abs(start + length - e0) <= 1.5 / fps:
                new_length -= dout
            if (new_start, new_length) != (start, length):
                patch(c, start=round(new_start, 6), duration=round(new_length, 6),
                      keyframes=_stretched(c.get("keyframes"), length, new_length))
        for c in prev_base:
            length = float(c["duration"])
            patch(c, duration=round(length + din, 6), keyframes=_stretched(c.get("keyframes"), length, length + din))
        # whatever else held to the end of the frame before him (its text, accents, graphics) holds to the new end, as it
        # was: left at the old end, a text frame stood half a second on its bare background (user, 26 November 2026)
        for c in prev["clips"]:
            if c in prev_base or abs(float(c["start"]) + float(c["duration"]) - prev["end"]) > 1.5 / fps:
                continue
            patch(c, duration=round(float(c["duration"]) + din, 6))
        for c in next_base:
            length = float(c["duration"])
            patch(c, start=round(float(c["start"]) - dout, 6), duration=round(length + dout, 6),
                  keyframes=_stretched(c.get("keyframes"), length, length + dout))
        new_frames[i]["host_inset"] = planner.HOST_INSET
        new_frames[i]["host_edges"] = [s1, e1]      # where the montage has him; the plan check reads these
        new_frames[i].update(start=s1, end=e1)
        new_frames[i - 1]["end"] = s1
        new_frames[i + 1]["start"] = e1
        done.append(frame["number"])
    for clip_id, fields in patches.items():
        clip = next(c for f in ctx.frames for c in f["clips"] if c["id"] == clip_id)
        if "start" in fields:
            ctx.actions.append({"type": "move_clip", "payload": {"clip_id": clip_id, "start": fields["start"]}})
        if "duration" in fields or "trim_start" in fields:
            ctx.actions.append({"type": "trim_clip", "payload": {"clip_id": clip_id, "duration": fields.get("duration", clip["duration"]),
                                                                 "trim_start": fields.get("trim_start", clip.get("trim_start", 0))}})
        if fields.get("keyframes") and clip.get("keyframes"):   # after the trim, which drops keyframes past the old length
            ctx.actions.append({"type": "update_clip", "payload": {"clip_id": clip_id, "patch": {"keyframes": fields["keyframes"]}}})
    # the studio checks transitions after every action of a batch, and halfway through (the host already narrower, his
    # neighbour not yet longer) a seam gapes and its transition goes: each one at a moved seam is set again at the end
    moved = {groups[n]["group"]["id"] for i, f in enumerate(frames) if f["number"] in done
             for n in (frames[i - 1]["number"], f["number"], frames[i + 1]["number"])}
    for join in ctx.project.get("join_transitions", []):
        if {join["from_ref"].split(":")[-1], join["to_ref"].split(":")[-1]} & moved:
            ctx.actions.append({"type": "set_join_transition", "payload": {"from_ref": join["from_ref"], "to_ref": join["to_ref"],
                                                                          "type": join["type"], "duration": join["duration"]}})
    ctx.new_plan = dict(plan, frames=new_frames) if done else None
    ctx.report.append(f"ведучий усередині своєї мови: кадри {', '.join(map(str, done)) or '—'}"
                      + (f"; лишились як були: {', '.join(map(str, skipped))}" if skipped else ""))


MOVES = ("pan_right", "zoom_in", "pan_left", "zoom_out")


def stands_still(frame: dict) -> bool:
    """True when nothing in the frame moves the picture: no video, no Razgon block, no motion preset and no layer whose
    keyframes change its place or size (a motion-code layer may animate inside itself; the frame still stands)."""
    for c in frame["clips"]:
        if c.get("frame_background") or "чорний фон" in str(c.get("title", "")):
            continue
        if c.get("kind") == "video" or str(c.get("title", "")).startswith("Razgon") or c.get("preset"):
            return False
        if c.get("content_type") == "code":
            continue
        points = c.get("keyframes") or []
        for key in ("x", "y", "scale"):
            values = [float(p[key]) for p in points if key in p]
            if values and max(values) - min(values) > 1e-4:
                return False
    return True


def frame_camera(ctx, spec: dict) -> None:
    """spec: {"frames": [N, …] (every frame that stands still when empty), "move": one of native_animation.CAMERA_MOVES
    or "alternate" (default), "amount": 0.02…0.12}. The whole frame moves as one: its picture, motion code and accents
    keep their places on each other. A frame that moves already is left alone (user, 26 November 2026: «там де камера не
    рухається там треба кадр рухати… для ефекту руху»; frame 71 of Astrofizika, a photo under motion code, stood still)."""
    fps = int(ctx.project.get("fps") or 25)
    wanted = set(spec.get("frames") or [])
    move, amount, k = spec.get("move", "alternate"), spec.get("amount", native_animation.CAMERA_AMOUNT), 0
    moved = []
    for frame in ctx.frames:
        if wanted and frame["number"] not in wanted:
            continue
        if not stands_still(frame):
            continue
        layers = [c for c in frame["clips"] if not c.get("frame_background") and "чорний фон" not in str(c.get("title", ""))
                  and c.get("kind") != "audio"]
        if not layers:
            continue
        name = MOVES[k % len(MOVES)] if move == "alternate" else move
        k += 1
        camera = native_animation.camera_move({"move": name, "amount": amount})
        start, duration = frame["start"], frame["end"] - frame["start"]
        for c in layers:
            part = dict(c, start=float(c["start"]) - start, duration=float(c["duration"]))
            native_animation.apply_camera(part, camera, duration, fps)
            ctx.actions.append({"type": "update_clip", "payload": {"clip_id": c["id"], "patch": {
                "keyframes": part["keyframes"], "easing": "linear"}}})
        moved.append(f"{frame['number']} {name}")
    ctx.report.append("камера кадрів: " + (", ".join(moved) or "—"))


def apply_host_inset(pid: str, frames=None, dry_run: bool = False) -> dict:
    """The op; montage_ops.run attaches the plan with the new edges after the batch."""
    return montage_ops.run(pid, [{"op": "host_inset", "frames": frames or []}], dry_run=dry_run)
