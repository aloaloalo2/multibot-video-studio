#!/usr/bin/env python3
"""Find every jump at a junction of a Razgon film: the camera jerks, a figure snaps to another pose or face, a thing vanishes.

    python3 "VideoKey Studio/tools/cut_check.py" --razgon "What If/razgon-2d-studio/projects/<slug>" [--only e01,e13] [--scale 0.5]

A junction is where one take hands over to the next one (shots.json) or one part of a joined take to the next part
("parts"). For each it renders four frames in a row on the frame grid: two before and two after. The picture is cut
into small cells; a cell jumps when it changes across the junction much more than it changes between two ordinary
frames on either side. A camera jerk moves almost every cell, a pose or face that snaps moves a few cells while the
rest of the picture stays. Between the parts of a joined take, a camera pan that goes on across the junction is taken
out first: each pair of frames is compared after the move of the whole picture between them, the junction after the move
seen on both sides of it (episode 06, 31 October 2026: on fast pans the picture entering at the edge read as a jump on
smooth joins). Designed transitions between takes are compared as they are.

  FAIL  a hard cut inside one place (the same set): the takes must be joined into one take or get a designed
        transition with a real change of time, subject or mode;
  FAIL  a joined part or a designed transition whose first frame does not follow the frame before it;
  FAIL  an action that starts over: the picture just after the junction is nearly the picture of a moment a second or
        more before it, though the scene moved since then (05 Frozen Body, 30 October 2026: the plunge through the ice
        ended a take, a flash, and the next take dived again). Checked at every junction, other places included.
A hard cut between different places is a real cut and is listed only.

Writes build/cuts/report.json and build/cuts/cuts_NN.png (failures first): left = last frame before, right = first
frame after, red boxes = cells that jumped. Also build/cuts/seams_NN.png: for every junction between takes a strip of
six moments, three before and three after it, to look at with your own eyes. A new camera hides a replay from any pixel
test, so the agent opens every strip and checks that the action goes on across the junction and does not start over.
Exit code 1 when anything FAILs.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

CELL = 24          # cell size in pixels of the rendered still
PIX = 28           # a pixel "changed" when its brightness moved by more than this (0..255)
JUMP = 0.06        # a cell jumps when the junction changes this share of its pixels more than ordinary motion does
CELLS_FAIL = 3     # this many jumping cells make the junction fail
HARD = {"cut", "smash", "flash"}   # transitions that cut at once by design (smash and flash only add an impact)
REPLAY_SAME = 0.035   # mean brightness difference (0..1) under which two pictures show the same moment
REPLAY_MOVED = 0.06   # ... and over which the scene had moved on before the junction
BACK = (0.6, 1.0, 1.5, 2.0, 2.6, 3.2)
STRIP_BACK, STRIP_AHEAD = (1.5, 0.6, 0.2), (0.2, 0.7, 1.2)   # the six moments of a seam strip   # seconds before the transition where the action may already have happened
AHEAD = (0.2, 0.7, 1.2)                  # seconds after the transition where a replay would show


def overlap(a: np.ndarray, b: np.ndarray, d: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, tuple[slice, slice]]:
    """The parts of a and b that show the same place when the picture moved by d = (dx, dy) from a to b, and where that
    part lies in b."""
    dx, dy = d
    h, w = a.shape
    ys, xs = slice(max(0, dy), h + min(0, dy)), slice(max(0, dx), w + min(0, dx))
    return a[max(0, -dy):h + min(0, -dy), max(0, -dx):w + min(0, -dx)], b[ys, xs], (ys, xs)


def pan(a: np.ndarray, b: np.ndarray) -> tuple[int, int]:
    """How far the whole picture moved from a to b (a camera pan), by phase correlation; (0, 0) when a shift does not
    bring the two pictures closer, as in a zoom or a still camera."""
    h, w = a.shape
    win = np.outer(np.hanning(h), np.hanning(w))
    r = np.fft.fft2(a * win).conj() * np.fft.fft2(b * win)
    y, x = np.unravel_index(np.argmax(np.fft.ifft2(r / (np.abs(r) + 1e-9)).real), (h, w))
    d = (int(x - w if x > w // 2 else x), int(y - h if y > h // 2 else y))
    if d == (0, 0) or abs(d[0]) > w // 4 or abs(d[1]) > h // 4:
        return (0, 0)
    sa, sb, _ = overlap(a, b, d)
    return d if np.abs(sa - sb).mean() < np.abs(a - b).mean() else (0, 0)


def moved(a: np.ndarray, b: np.ndarray, d: tuple[int, int] = (0, 0)) -> np.ndarray:
    """Share of changed pixels in every cell of b, after the camera moved the whole picture by d. The strip that came
    in at the edge with the pan is new picture, not a change, and is not counted."""
    sa, sb, (ys, xs) = overlap(a, b, d)
    changed = np.zeros(b.shape, dtype=bool)
    changed[ys, xs] = np.abs(sa - sb) > PIX
    h, w = changed.shape[0] // CELL * CELL, changed.shape[1] // CELL * CELL
    return changed[:h, :w].reshape(h // CELL, CELL, w // CELL, CELL).mean(axis=(1, 3))


def small(im: Image.Image) -> np.ndarray:
    return np.asarray(im.convert("L").resize((96, 54)), dtype=np.float32) / 255


def replay(before: list, after: list) -> tuple[float, float] | None:
    """(when before the junction, how alike) when a picture after it repeats an earlier moment of the scene that had
    moved on since; None when the action just goes on."""
    last = small(before[0][1])
    best = None
    for back, im in before[1:]:
        a = small(im)
        if np.abs(a - last).mean() < REPLAY_MOVED:
            continue                      # nothing moved between that moment and the junction: a hold, not an action
        for _, bim in after:
            d = float(np.abs(small(bim) - a).mean())
            if d < REPLAY_SAME and (best is None or d < best[1]):
                best = (back, d)
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--razgon", required=True)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--only", default="", help="comma-separated take ids: check only junctions that start these takes")
    a = ap.parse_args()
    proj = Path(a.razgon).resolve()
    root = proj.parent.parent
    fps = json.loads((proj / "config.json").read_text()).get("fps", 25)
    shots = json.loads((proj / "story" / "shots.json").read_text())["shots"]
    joins = []
    for prev, nxt in zip(shots, shots[1:]):
        kind = (nxt.get("in") or {}).get("type", "cut")
        last = (prev.get("parts") or [{"id": prev["id"]}])[-1]["id"]
        joins.append({"from": last, "to": nxt["id"], "t": nxt["start"], "type": kind, "same_set": prev.get("set") == nxt.get("set")})
    for s in shots:
        ps = s.get("parts") or []
        for p, q in zip(ps, ps[1:]):
            joins.append({"from": p["id"], "to": q["id"], "t": q["start"], "type": "join", "same_set": True})
    joins.sort(key=lambda j: j["t"])
    if a.only:
        want = set(a.only.split(","))
        joins = [j for j in joins if j["to"] in want or j["from"] in want]
    durations = {s["id"]: float((s.get("in") or {}).get("dur") or 0) for s in shots}
    for j in joins:
        f0 = math.ceil(j["t"] * fps - 1e-6)            # the first frame of the new take
        j["frames"] = [f0 - 2, f0 - 1, f0, f0 + 1]
        half = durations.get(j["to"], 0) / 2 if j["type"] not in ("join", "cut") else 0
        j["back"] = [(b, round((j["t"] - half - b) * fps)) for b in (0.2,) + BACK]
        j["ahead"] = [(b, round((j["t"] + half + b) * fps)) for b in AHEAD]
    need = sorted({f for j in joins for f in j["frames"] + [x for _, x in j["back"] + j["ahead"]] if f >= 0})
    stills, keep = proj / "build" / "stills", proj / "build" / "cuts" / "frames"
    keep.mkdir(parents=True, exist_ok=True)
    for f in keep.glob("*.png"):
        f.unlink()
    for i in range(0, len(need), 120):   # render.mjs empties build/stills on every run: keep each batch aside
        chunk = ",".join(f"{f / fps:.2f}" for f in need[i:i + 120])
        subprocess.run(["node", "render.mjs", "--project", str(proj.relative_to(root)), "--stills", chunk, "--scale", str(a.scale)],
                       cwd=root, check=True, capture_output=True)
        for f in stills.glob("*.png"):
            if not f.name.startswith("sheet"):
                f.replace(keep / f.name)

    def still(f):
        hit = sorted(keep.glob(f"*_{f / fps:.2f}.png"))
        return Image.open(hit[0]).convert("RGB") if hit else None

    fails = []
    for j in joins:
        imgs = [still(f) for f in j["frames"]]
        j["imgs"] = imgs
        if any(im is None for im in imgs):
            j["status"] = "no frames"; continue
        L = [np.asarray(im.convert("L"), dtype=np.float32) for im in imgs]
        # the parts of a joined take share one camera, so a pan going on across their junction moves the picture there by
        # about as much as on either side of it: the junction is measured after that same move, and a camera that jerks
        # at the junction is still off by the jerk. A designed transition hands over to another take with its own camera
        # and changes the picture by design (an iris grows fastest at the junction), so it is compared as it is.
        p0, p2 = (pan(L[0], L[1]), pan(L[2], L[3])) if j["type"] == "join" else ((0, 0), (0, 0))
        expect = (round((p0[0] + p2[0]) / 2), round((p0[1] + p2[1]) / 2))
        jump, before, after = moved(L[1], L[2], expect), moved(L[0], L[1], p0), moved(L[2], L[3], p2)
        j["pan"] = [list(p0), list(expect), list(p2)]
        excess = jump - 2 * np.maximum(before, after)
        cells = np.argwhere(excess > JUMP)
        j["jump_cells"] = int(len(cells))
        j["jump"] = round(float(jump.mean()) * 100, 2)
        j["motion"] = round(float(np.maximum(before, after).mean()) * 100, 2)
        j["cells"] = cells.tolist()
        before = [(b, still(f)) for b, f in j["back"]]
        after = [(b, still(f)) for b, f in j["ahead"]]
        again = None if any(im is None for _, im in before + after) else replay(before, after)
        if again:
            j["status"] = f"FAIL: the action starts over (the picture of {again[0]} s before the junction comes back)"
        elif j["type"] in HARD and not j["same_set"]:
            j["status"] = "cut to another place"
        elif j["type"] in HARD:
            j["status"] = "FAIL: hard cut inside one place"
        elif len(cells) >= CELLS_FAIL:
            j["status"] = f"FAIL: {len(cells)} cells jump"
        else:
            j["status"] = "ok"
        if j["status"].startswith("FAIL"):
            fails.append(j)
    order = sorted(joins, key=lambda j: (not j.get("status", "").startswith("FAIL"), -j.get("jump_cells", 0)))
    out = proj / "build" / "cuts"
    for f in out.glob("cuts_*.png"):
        f.unlink()
    show = [j for j in order if j.get("imgs") and None not in j["imgs"]]   # a frame that did not render cannot be drawn
    show = [j for j in show if j.get("status") not in ("ok", "cut to another place")] or show[:8]
    per = 6
    for n in range(0, len(show), per):
        group = show[n:n + per]
        w, h = group[0]["imgs"][1].size
        sheet = Image.new("RGB", (w * 2 + 12, (h + 28) * len(group)), (18, 18, 18)); d = ImageDraw.Draw(sheet)
        for k, j in enumerate(group):
            y = k * (h + 28)
            sheet.paste(j["imgs"][1], (0, y + 24)); sheet.paste(j["imgs"][2], (w + 12, y + 24))
            for r, c in j["cells"]:
                for ox in (0, w + 12):
                    d.rectangle([ox + c * CELL, y + 24 + r * CELL, ox + (c + 1) * CELL - 1, y + 24 + (r + 1) * CELL - 1], outline=(255, 60, 60))
            d.text((6, y + 6), f"{j['from']} -> {j['to']}  t={j['t']:.2f}  {j['type']}  {j['status']}", fill=(255, 210, 90))
        sheet.save(out / f"cuts_{n // per + 1:02d}.png")
    # the seam strips: one row per junction between takes, three moments before | three after
    takes = [j for j in joins if j["type"] != "join"]
    for f in out.glob("seams_*.png"):
        f.unlink()
    for n in range(0, len(takes), 6):
        group, rows = takes[n:n + 6], []
        for j in group:
            pics = [still(f) for b, f in j["back"] if b in STRIP_BACK][::-1] + [still(f) for b, f in j["ahead"] if b in STRIP_AHEAD]
            if any(p is None for p in pics):
                continue
            rows.append((j, pics))
        if not rows:
            continue
        w, h = 320, 180
        sheet = Image.new("RGB", (w * 6 + 16, (h + 26) * len(rows)), (18, 18, 18)); d = ImageDraw.Draw(sheet)
        for k, (j, pics) in enumerate(rows):
            y = k * (h + 26)
            for i, p in enumerate(pics):
                sheet.paste(p.resize((w, h)), (i * w + (16 if i >= 3 else 0), y + 24))
            d.rectangle([3 * w + 4, y + 24, 3 * w + 11, y + 24 + h], fill=(255, 210, 90))
            d.text((6, y + 6), f"{j['from']} -> {j['to']}  t={j['t']:.2f}  {j['type']}   -1.5 s, -0.6, -0.2 | +0.2, +0.7, +1.2", fill=(255, 210, 90))
        sheet.save(out / f"seams_{n // 6 + 1:02d}.png")
    for j in joins:
        j.pop("imgs", None)
    (out / "report.json").write_text(json.dumps(order, ensure_ascii=False, indent=1))
    print(f"Junctions checked: {len(joins)}; failures: {len(fails)}")
    for j in fails:
        print(f"  FAIL {j['from']} -> {j['to']}  t={j['t']:.2f}  {j['type']}  {j['status']}")
    print(f"Sheets: {out}/cuts_NN.png (failures first); seam strips to look at: {out}/seams_NN.png")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
