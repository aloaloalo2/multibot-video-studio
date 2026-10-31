#!/usr/bin/env python3
"""Frame review: look at every frame of the film, three stills each, before the film is handed over.

    python3 tools/frame_review.py --project projects/<slug> sheets [--frames 1-12] [--scale 0.34]
    python3 tools/frame_review.py --project projects/<slug> mark 1-4,7 ok
    python3 tools/frame_review.py --project projects/<slug> mark 5 bug "the patient floats above the mattress"
    python3 tools/frame_review.py --project projects/<slug> status

A frame is a Studio frame (story/studio_frames.json) or, without one, a shot (story/shots.json). `sheets` renders three
stills of every frame from the live code (at 20%, 50% and 80% of it, away from the transitions at its edges) and lays
them out in build/review/review_NN.png, four frames per sheet: frame number, time, takes and the narration line above
the three pictures. Open every sheet and check every frame against the checklist in references/render-qc.md
(«Frame review»): bodies and poses that are physically wrong (lying on a bed, sitting on a chair, holding things,
standing on the floor), things that float, overlap or pass through each other, a picture that does not match the
words, text and labels, framing, and anything that simply looks unfinished or ugly. Then `mark` each frame ok, or bug
with a note; fix the bugs and run `sheets` again.

A verdict belongs to the pixels it was given on: `sheets` hashes every still, and a frame whose stills changed since
its verdict (a fix, or a change in a shared set or engine file) goes back to «not reviewed», while untouched frames keep
theirs. `status` exits 1 until every frame is ok on the current code: the film is not handed over before that.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

PER_SHEET = 4
SPOTS = (0.2, 0.5, 0.8)
FONT_FILES = ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def font(size):
    for f in FONT_FILES:
        if os.path.isfile(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def frames_of(proj: Path) -> list[dict]:
    """The units to review: Studio frames when the film has them, else shots. Each knows the takes it shows."""
    shots = json.loads((proj / "story" / "shots.json").read_text())["shots"]
    def takes(a, b):
        out = []
        for s in shots:
            for p in (s.get("parts") or [{"id": s["id"], "start": s["start"]}]):
                end = next((q["start"] for q in (s.get("parts") or [])[1:] if q["start"] > p["start"]), s["end"])
                if p["start"] < b and end > a and p["id"] not in out:
                    out.append(p["id"])
        return out
    sf = proj / "story" / "studio_frames.json"
    if sf.is_file():
        items = [(f["number"], f["start"], f["end"], " ".join(f.get("sentences") or [])) for f in json.loads(sf.read_text())["frames"]]
    else:
        items = [(k + 1, s["start"], s["end"], s.get("line", "")) for k, s in enumerate(shots)]
    return [{"n": n, "start": a, "end": b, "line": line, "takes": takes(a, b)} for n, a, b, line in items]


def thumb(path: Path):
    return Image.open(path).convert("L").resize((128, 72), Image.BOX) if path.is_file() else None


def same_picture(a, b) -> bool:
    """Two stills of one moment are the same picture when no more than a few pixels of their 128×72 thumbnails differ
    by more than 10 levels: a speck of drifting dust is not a change, a moved arm or a new object is."""
    if a is None or b is None:
        return False
    return sum(ImageChops.difference(a, b).histogram()[11:]) <= 3


def pick(spec: str, total: int) -> set[int]:
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out |= set(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return {n for n in out if 1 <= n <= total}


def load_state(path: Path) -> dict:
    return json.loads(path.read_text()) if path.is_file() else {"frames": {}}


def code_mtime(proj: Path) -> float:
    root = proj.parent.parent
    files = [p for d in ("scenes", "story", "assets", "input") for p in (proj / d).rglob("*") if p.is_file()]
    files += [proj / "config.json"] + [p for p in (root / "engine").rglob("*.js")]
    return max((p.stat().st_mtime for p in files if p.is_file()), default=0)


def sheets(proj: Path, root: Path, a) -> None:
    fps = json.loads((proj / "config.json").read_text()).get("fps", 25)
    frames = frames_of(proj)
    want = pick(a.frames, len(frames)) if a.frames else {f["n"] for f in frames}
    todo = [f for f in frames if f["n"] in want]
    for f in todo:   # on the frame grid, inside the frame, away from its first and last 0.5 s (transitions)
        lo, hi = f["start"] + min(0.5, (f["end"] - f["start"]) * 0.2), f["end"] - min(0.5, (f["end"] - f["start"]) * 0.2)
        f["times"] = [round(round(min(hi, max(lo, f["start"] + (f["end"] - f["start"]) * k)) * fps) / fps, 2) for k in SPOTS]
    out = proj / "build" / "review"
    keep = out / "frames"
    keep.mkdir(parents=True, exist_ok=True)
    stills = proj / "build" / "stills"
    times = sorted({t for f in todo for t in f["times"]})
    before = {t: thumb(keep / f"{t:.2f}.png") for t in times}   # the stills of the last run, to tell a real change from dust
    errors = []   # a scene that throws draws an ERROR line into its frame: the film is not reviewed until there are none
    for i in range(0, len(times), 90):   # render.mjs empties build/stills on every run: keep each batch aside
        chunk = ",".join(f"{t:.2f}" for t in times[i:i + 90])
        r = subprocess.run(["node", "render.mjs", "--project", str(proj.relative_to(root)), "--stills", chunk, "--scale", str(a.scale)],
                           cwd=root, capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stdout[-1500:] + r.stderr[-1500:])
        for line in (r.stdout + r.stderr).splitlines():
            if "error" in line.lower():
                errors.append(line.strip())
        for p in stills.glob("*.png"):
            if not p.name.startswith("sheet"):
                p.replace(keep / p.name.split("_")[-1])
        print(f"  stills {min(i + 90, len(times))}/{len(times)}", flush=True)
    state_path = out / "review.json"
    state = load_state(state_path)
    reset = 0
    for f in todo:
        imgs = [Image.open(keep / f"{t:.2f}.png").convert("RGB") for t in f["times"]]
        f["imgs"] = imgs
        digest = hashlib.sha1(b"".join(im.tobytes() for im in imgs)).hexdigest()
        old = state["frames"].get(str(f["n"]), {})
        same = all(same_picture(before[t], thumb(keep / f"{t:.2f}.png")) for t in f["times"])
        if old.get("pixels") != digest and old.get("verdict") and not same:
            reset += 1
            old = {}
        state["frames"][str(f["n"])] = {**old, "pixels": digest, "times": f["times"], "takes": f["takes"]}
    for p in out.glob("review_*.png"):
        p.unlink()
    w, h = todo[0]["imgs"][0].size
    head, gap = 54, 8
    f1, f2 = font(22), font(16)
    for s in range(0, len(todo), PER_SHEET):
        group = todo[s:s + PER_SHEET]
        sheet = Image.new("RGB", (w * 3 + gap * 2, (h + head + gap) * len(group)), (14, 14, 16))
        d = ImageDraw.Draw(sheet)
        for k, f in enumerate(group):
            y = k * (h + head + gap)
            v = state["frames"][str(f["n"])].get("verdict")
            mark = {"ok": "  ✓ ok", "bug": "  ✗ BUG"}.get(v, "")
            d.text((8, y + 4), f"Кадр {f['n']}   {f['start']:.1f}–{f['end']:.1f} s   {', '.join(f['takes'])}{mark}", font=f1, fill=(255, 210, 90))
            line = f["line"] if len(f["line"]) < 230 else f["line"][:227] + "…"
            d.text((8, y + 31), line, font=f2, fill=(200, 200, 210))
            for j, im in enumerate(f["imgs"]):
                sheet.paste(im, (j * (w + gap), y + head))
                d.text((j * (w + gap) + 6, y + head + 4), f"{f['times'][j]:.2f}s", font=f2, fill=(255, 255, 255))
        sheet.save(out / f"review_{s // PER_SHEET + 1:02d}.png")
    state["sheets_at"] = time.time()
    state["total"] = len(frames)
    state["errors"] = sorted(set(errors))[:40]
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print(f"Sheets: {out}/review_NN.png ({-(-len(todo) // PER_SHEET)} sheets, {len(todo)} frames, 3 stills each)")
    if reset:
        print(f"{reset} frames changed since their verdict and need a new look")
    if errors:
        print(f"RENDER ERRORS ({len(set(errors))}): fix them first, the stills of those frames show the error text")
        for e in sorted(set(errors))[:12]:
            print("  " + e)


def mark(proj: Path, a) -> None:
    state_path = proj / "build" / "review" / "review.json"
    state = load_state(state_path)
    if not state["frames"]:
        sys.exit("Run `sheets` first")
    for n in sorted(pick(a.frames, state.get("total", 10 ** 6))):
        entry = state["frames"].get(str(n))
        if not entry:
            sys.exit(f"Frame {n} has no stills yet: run `sheets` for it first")
        entry.update(verdict=a.verdict, note=a.note or "", at=time.time())
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print(f"Marked {a.frames} {a.verdict}" + (f": {a.note}" if a.note else ""))


def status(proj: Path) -> int:
    state = load_state(proj / "build" / "review" / "review.json")
    total = len(frames_of(proj))
    frames = state.get("frames", {})
    bugs = [(n, e.get("note", "")) for n, e in frames.items() if e.get("verdict") == "bug"]
    unseen = [n for n in range(1, total + 1) if frames.get(str(n), {}).get("verdict") is None]
    stale = state.get("sheets_at", 0) < code_mtime(proj)
    errors = state.get("errors") or []
    ok = total - len(bugs) - len(unseen)
    print(f"Frames reviewed ok: {ok}/{total}")
    for n, note in sorted(bugs, key=lambda x: int(x[0])):
        print(f"  BUG  кадр {n}: {note}")
    if unseen:
        print(f"  not reviewed: {', '.join(map(str, unseen[:30]))}{'…' if len(unseen) > 30 else ''}")
    if stale:
        print("  the code changed after the last sheets: run `sheets` again (unchanged frames keep their verdict)")
    for e in errors[:8]:
        print(f"  RENDER ERROR  {e}")
    return 0 if not bugs and not unseen and not stale and not errors else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheets"); s.add_argument("--frames", default=""); s.add_argument("--scale", type=float, default=0.34)
    m = sub.add_parser("mark"); m.add_argument("frames"); m.add_argument("verdict", choices=["ok", "bug"]); m.add_argument("note", nargs="?", default="")
    sub.add_parser("status")
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    proj = (root / a.project).resolve() if not Path(a.project).is_absolute() else Path(a.project)
    if a.cmd == "sheets":
        sheets(proj, root, a)
    elif a.cmd == "mark":
        mark(proj, a)
    else:
        sys.exit(status(proj))


if __name__ == "__main__":
    main()
