"""Does the text of each motion-code clip read on what lies under it in the export, and is it the same colour everywhere?

    python3 backend/motion_text_check.py P [--clips K034,K035] [--json out.json]

For every motion-code clip (content_type "code") the clip's own runtime lists the lines of text it draws at a dozen
moments (tools/motion_code_render.mjs --text-scan); at up to three moments that show every line, it draws the clip with
and without its letters (--text-pairs), the export's renderer draws the film at that moment without this clip
(engine/still.py), and the clip without its letters is laid over it the way the export lays it (the clip's place and
zoom). Each line's colour is compared with what the eye holds it against, a band 2–4 px around its letters in the
finished picture (an outline, a shadow or a plate the code drew counts): WCAG contrast against the 25th and the 75th
percentile of the luminance there, the worse one, with Razgon's thresholds (2.6:1, 3.5:1 for letters under 40 px). The report also counts the
colours of the text over all clips: one accent everywhere is the channel's template, not the scene's colour (user,
26 November 2026: «контрастність… шаблонність тексту, колір шаблонності»).

Nothing is changed and no paid service is used; it renders locally at low priority."""
from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store  # noqa: E402
import motion_code  # noqa: E402

MIN_CONTRAST, MIN_CONTRAST_SMALL, SMALL_PX = 2.6, 3.5, 40
SCAN_MOMENTS = 12
MAX_MOMENTS = 3


def _srgb(value: float) -> float:
    value /= 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    r, g, b = (float(c) for c in rgb[:3])
    return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)


def luminance_array(rgb: np.ndarray) -> np.ndarray:
    c = rgb.astype(np.float64) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def ratio(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def parse_colour(text: str):
    """#rgb, #rrggbb or rgb()/rgba() as the canvas gives fillStyle; None for a gradient or pattern."""
    text = str(text or "").strip().lower()
    match = re.fullmatch(r"#([0-9a-f]{6})", text)
    if match:
        value = match.group(1)
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)), 1.0
    match = re.fullmatch(r"#([0-9a-f]{3})", text)
    if match:
        return tuple(int(c * 2, 16) for c in match.group(1)), 1.0
    match = re.fullmatch(r"rgba?\(([^)]*)\)", text)
    if match:
        parts = [p.strip() for p in match.group(1).split(",")]
        try:
            rgb = tuple(int(float(p)) for p in parts[:3])
            return rgb, float(parts[3]) if len(parts) > 3 else 1.0
        except (ValueError, IndexError):
            return None
    return None


def _node(arguments: list, timeout: int = 300) -> dict:
    result = subprocess.run(["nice", "-n", "10", "node", str(motion_code.RENDERER), "--studio", motion_code.STUDIO_URL,
                             "--modules", str(motion_code._modules()), *arguments], capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "error": (result.stdout + result.stderr)[-800:]}


def pick_moments(moments: list) -> list:
    """Up to MAX_MOMENTS moments that together show every line of text at full strength, the fullest first."""
    seen, chosen = set(), []
    # the latest moment first among equals: a line written or typed in is whole by then
    shown = [(m["t"], {x["text"] for x in m["texts"] if float(x.get("alpha", 1)) >= .9}) for m in reversed(moments)]
    while len(chosen) < MAX_MOMENTS:
        best = max(shown, key=lambda item: len(item[1] - seen), default=None)
        if not best or not best[1] - seen:
            break
        chosen.append(best[0])
        seen |= best[1]
    return sorted(chosen)


def _value_at(points: list, key: str, default: float, t: float) -> float:
    points = sorted((p for p in points if key in p), key=lambda p: p["time"])
    if not points:
        return default
    if t <= points[0]["time"]:
        return float(points[0][key])
    for a, b in zip(points, points[1:]):
        if t <= b["time"]:
            u = (t - a["time"]) / max(1e-9, b["time"] - a["time"])
            return float(a[key]) + (float(b[key]) - float(a[key])) * u
    return float(points[-1][key])


def place(clip: dict, t: float, width: int, height: int):
    """(scale, centre x, centre y) of the clip's picture on the frame at t seconds from its start."""
    points = clip.get("keyframes") or []
    scale = _value_at(points, "scale", float(clip.get("scale", 1)), t)
    return scale, _value_at(points, "x", float(clip.get("x", .5)), t) * width, _value_at(points, "y", float(clip.get("y", .5)), t) * height


def laid(picture: Image.Image, scale: float, cx: float, cy: float, width: int, height: int) -> Image.Image:
    """The clip's canvas as the export lays it: scaled about its centre, centred at (cx, cy)."""
    inverse = (1 / scale, 0, picture.width / 2 - cx / scale, 0, 1 / scale, picture.height / 2 - cy / scale)
    return picture.transform((width, height), Image.AFFINE, inverse, resample=Image.BILINEAR)


def _still(manifest: dict, moment: float, folder: Path) -> Image.Image:
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"under-{moment:.3f}.png"
    key = folder / f"under-{moment:.3f}.key"
    # the picture depends only on what plays around that moment: the clips near it, the film's size and rate
    near = [c for layer in manifest["timeline_layers"] for c in layer["clips"] if c.get("type") != "audio"
            and float(c["start"]) - 2 < moment < float(c["start"]) + float(c["duration"]) + 2]
    stamp = __import__("hashlib").sha256(json.dumps([manifest["width"], manifest["height"], manifest["fps"], near],
                                                    sort_keys=True, default=str).encode()).hexdigest()
    if output.is_file() and key.is_file() and key.read_text() == stamp:   # a check run again over the same film
        return Image.open(output).convert("RGB")
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(["nice", "-n", "10", sys.executable, str(store.APP_ROOT / "engine" / "still.py"), "--project", str(path),
                             "--time", f"{moment:.3f}", "--output", str(output)], capture_output=True, text=True, timeout=600)
    if result.returncode or not output.is_file():
        raise RuntimeError((result.stdout + result.stderr)[-600:])
    key.write_text(stamp)
    return Image.open(output).convert("RGB")


def measure(under: np.ndarray, with_text: Image.Image, without: Image.Image, entry: dict, place_at, width: int, height: int) -> dict | None:
    """The contrast of one line of text against the picture under it (letters left out), or None when it cannot be told."""
    colour = parse_colour(entry.get("fill"))
    if colour is None:
        return None
    rgb, fill_alpha = colour
    alpha = float(entry.get("alpha", 1)) * fill_alpha
    if alpha < .5:
        return None
    scale, cx, cy = place_at
    x0, y0, x1, y1 = entry["box"]
    # the box on screen, as the clip's zoom and place move it
    sx0, sy0 = (x0 - width / 2) * scale + cx, (y0 - height / 2) * scale + cy
    sx1, sy1 = (x1 - width / 2) * scale + cx, (y1 - height / 2) * scale + cy
    left, top = max(0, int(sx0) - 3), max(0, int(sy0) - 3)
    right, bottom = min(width, int(sx1) + 4), min(height, int(sy1) + 4)
    if right - left < 4 or bottom - top < 4:
        return None
    a = np.asarray(with_text, dtype=np.int16)[top:bottom, left:right]
    b = np.asarray(without, dtype=np.int16)[top:bottom, left:right]
    letters = np.abs(a - b).max(axis=2) > 24
    if letters.sum() < 12:
        return None
    base = np.median(under[top:bottom, left:right].reshape(-1, 3), axis=0)
    seen = np.array(rgb) * alpha + base * (1 - alpha)
    # the letters' own colour, an outline or a shadow the code drew around them left out of it
    face = letters & (np.abs(a - seen).max(axis=2) < 48)
    if face.sum() < 12:
        face = letters
    grow = lambda mask, size: np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(size))) > 0
    # what the eye holds the letters against: a band 2–4 px around them in the finished picture, so an outline, a shadow
    # or a plate the code drew counts, and the rest of the box does not
    ring = grow(face, 9) & ~grow(face, 5)
    around = a[ring]
    if around.shape[0] < 30:
        around = np.asarray(under, dtype=np.int16)[top:bottom, left:right][~grow(letters, 7)]
    if around.shape[0] < 30:
        return None
    lum = luminance_array(around.reshape(-1, 3).clip(0, 255))
    dark, light = float(np.percentile(lum, 25)), float(np.percentile(lum, 75))
    text_lum = luminance(seen)
    worst = min(ratio(text_lum, dark), ratio(text_lum, light))
    size = None
    match = re.search(r"(\d+(?:\.\d+)?)px", str(entry.get("font") or ""))
    if match:
        size = float(match.group(1)) * float(entry.get("scale") or 1) * scale
    need = MIN_CONTRAST_SMALL if size and size < SMALL_PX else MIN_CONTRAST
    # a cut line (user, 26 November 2026: «текст обрізаний не допускай»): past the frame's edge, or its letters drawn
    # over clearly less than its own box (a clip of the code, a mask, a writing reveal that stops short)
    cut = None
    if sx0 < -2 or sy0 < -2 or sx1 > width + 2 or sy1 > height + 2:
        cut = "за краєм кадру"
    else:
        columns = np.where(letters.any(axis=0))[0]
        drawn = (columns[-1] - columns[0] + 1) if columns.size else 0
        if sx1 - sx0 > 24 and drawn < .88 * (sx1 - sx0):
            cut = f"видно {round(100 * drawn / (sx1 - sx0))}% ширини"
    return {"cut": cut, "text": entry["text"], "fill": entry.get("fill"), "contrast": round(worst, 2), "need": need,
            "px": round(size) if size else None, "under": "#%02x%02x%02x" % tuple(int(v) for v in base),
            "box": [round(sx0), round(sy0), round(sx1), round(sy1)]}


def check(pid: str, only: list[str] | None = None, work: Path | None = None) -> dict:
    sys.path.insert(0, str(store.APP_ROOT / "backend"))
    import app  # the manifest exactly as the export builds it
    project = store.load_project(pid)
    width, height = int(project.get("width") or 1920), int(project.get("height") or 1080)
    base = app.normalize_for_engine(project)
    clips = [c for t in project.get("tracks", []) for c in t.get("clips", []) if c.get("content_type") == "code"]
    if only:
        clips = [c for c in clips if any(str(c.get("title", "")).startswith(f"{key} ") or key == c["id"] for key in only)]
    work = work or Path(tempfile.mkdtemp(prefix="motion-text-", dir=store.cache_dir(project)))
    found, colours, errors = [], collections.Counter(), []
    for clip in sorted(clips, key=lambda c: float(c["start"])):
        title = clip.get("title") or clip["id"]
        length = float(clip["duration"])
        spec = motion_code.spec(project, clip)
        folder = work / clip["id"]
        folder.mkdir(parents=True, exist_ok=True)
        spec_file = folder / "spec.json"
        store.atomic_json(spec_file, spec)
        moments = [round(.2 + (length - .4) * i / (SCAN_MOMENTS - 1), 3) for i in range(SCAN_MOMENTS)] if length > .6 else [length / 2]
        scan = _node(["--spec", str(spec_file), "--text-scan", ",".join(map(str, moments))])
        if not scan.get("ok"):
            errors.append({"clip": title, "error": scan.get("error")})
            continue
        broken = set()
        for moment in scan["moments"]:
            for entry in moment["texts"]:
                if float(entry.get("alpha", 1)) >= .9:
                    colours[str(entry.get("fill")).lower()] += 1
                # the canvas's own default: the code set a font the canvas refused (a stray brace, a bad size)
                if str(entry.get("font")) == "10px sans-serif":
                    broken.add(entry["text"])
        if broken:
            errors.append({"clip": title, "error": "шрифт не прийнято, текст 10px: " + ", ".join(sorted(broken))[:200]})
        chosen = pick_moments(scan["moments"])
        if not chosen:
            continue
        pairs = _node(["--spec", str(spec_file), "--text-pairs", ",".join(f"{t:.3f}" for t in chosen), "--out-dir", str(folder)])
        if not pairs.get("ok"):
            errors.append({"clip": title, "error": pairs.get("error")})
            continue
        manifest = copy.deepcopy(base)
        for layer in manifest["timeline_layers"]:
            layer["clips"] = [c for c in layer["clips"] if c.get("id") != clip["id"]]
        for pair in pairs["pairs"]:
            t = float(pair["t"])
            try:
                under = _still(manifest, float(clip["start"]) + t, folder)
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                errors.append({"clip": title, "error": str(error)[-300:]})
                continue
            at = place(clip, t, width, height)
            ground = under.convert("RGBA")
            bare = Image.alpha_composite(ground, laid(Image.open(pair["without"]).convert("RGBA"), *at, width, height)).convert("RGB")
            drawn = Image.alpha_composite(ground, laid(Image.open(pair["with"]).convert("RGBA"), *at, width, height)).convert("RGB")
            under_px = np.asarray(bare)
            for entry in pair["texts"]:
                result = measure(under_px, drawn, bare, entry, at, width, height)
                if result:
                    found.append({"clip": title, "time": round(float(clip["start"]) + t, 2), **result})
    weak = [item for item in found if item["contrast"] < item["need"]]
    cut = [item for item in found if item.get("cut")]
    texts = sum(colours.values()) or 1
    template = [{"colour": colour, "share": round(count / texts, 2)} for colour, count in colours.most_common(6)]
    return {"clips": len(clips), "lines": len(found), "weak": weak, "cut": cut, "colours": template, "errors": errors, "work": str(work),
            "measured": found}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--clips", default="")
    parser.add_argument("--json")
    parser.add_argument("--work", help="a folder of an earlier run: pictures of the same film are taken from it")
    args = parser.parse_args()
    report = check(args.project, [c for c in args.clips.split(",") if c] or None, Path(args.work) if args.work else None)
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"моушн-код: {report['clips']} кліпів, {report['lines']} написів виміряно, слабкий контраст: {len(report['weak'])}")
    for item in report["weak"]:
        print(f"  {item['time']:8.2f} с  {item['clip'][:34]:34} «{item['text'][:30]}» {item['contrast']}:1 (треба {item['need']}) колір {item['fill']} на {item['under']}")
    print(f"обрізаних написів: {len(report['cut'])}")
    for item in report["cut"]:
        print(f"  {item['time']:8.2f} с  {item['clip'][:34]:34} «{item['text'][:30]}» {item['cut']}")
    print("кольори тексту: " + ", ".join(f"{c['colour']} {round(c['share'] * 100)}%" for c in report["colours"]))
    for error in report["errors"]:
        print(f"  помилка {error['clip']}: {error['error']}")


if __name__ == "__main__":
    main()
