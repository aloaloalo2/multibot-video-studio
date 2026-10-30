"""Project cards show a sharp 16:9 cover taken from a telling moment of the montage.

The first frame is often a fade from black (Razgon films) or an empty title, so a few scene frames from the first half
of the video are sampled and the one with the most visible detail wins. The result is cached by the exact frames it was
chosen from, so it is computed again only when those clips change.
"""
from __future__ import annotations

import hashlib, io, json, os, subprocess, threading, uuid
from pathlib import Path

from PIL import Image, ImageOps, ImageStat

import store
import thumbnail_gen

SIZE = (960, 540)
CANDIDATES = 6
VERSION = 1
LOCK = threading.Semaphore(2)


def candidates(project: dict) -> list[tuple[Path, str, float]]:
    """(file, kind, second within the file) for scene photos and videos spread over the first half of the video."""
    overlay = {cid for group in project.get("scene_groups", []) if group.get("role") == "overlay" for cid in group.get("clip_ids", [])}
    scene = {cid for group in project.get("scene_groups", []) if group.get("role", "scene") != "overlay" for cid in group.get("clip_ids", [])}
    assets = {asset["id"]: asset for asset in store.discover_assets(project)}
    clips = []
    for track in project.get("tracks", []):
        for clip in track.get("clips", []):
            asset = assets.get(clip.get("asset_id"), {})
            kind = asset.get("kind")
            if kind not in {"video", "image"} or clip["id"] in overlay or (scene and clip["id"] not in scene):
                continue
            clips.append((float(clip.get("start", 0)), clip, asset))
    if not clips:
        return []
    clips.sort(key=lambda item: item[0])
    half = max(float(project.get("duration") or 0), clips[-1][0]) / 2
    early = [item for item in clips if item[0] <= half] or clips
    step = max(1, len(early) // CANDIDATES)
    picked = early[::step][:CANDIDATES]
    return [(Path(asset["path"]), asset["kind"], float(clip.get("trim_start", 0)) + float(clip.get("duration", 0)) / 2)
            for _, clip, asset in picked if Path(asset["path"]).is_file()]


def frame(path: Path, kind: str, second: float) -> Image.Image:
    if kind == "image":
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
        backdrop = Image.new("RGBA", image.size, "#16171a")
        return Image.alpha_composite(backdrop, image).convert("RGB")
    result = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{max(0.0, second):.3f}", "-i", str(path), "-frames:v", "1",
                             "-vf", f"scale={SIZE[0]}:{SIZE[1]}:force_original_aspect_ratio=increase", "-f", "image2pipe", "-c:v", "png", "-"],
                            capture_output=True, timeout=20)
    if result.returncode or not result.stdout:
        raise ValueError("Frame unavailable")
    with Image.open(io.BytesIO(result.stdout)) as image:
        return image.convert("RGB")


def score(image: Image.Image) -> float:
    """Detail that is actually visible: contrast, penalised for frames that are nearly black or washed out."""
    stats = ImageStat.Stat(image.convert("L").resize((96, 54)))
    mean, spread = stats.mean[0], stats.stddev[0]
    if mean < 28 or mean > 235:
        return spread * 0.1
    return spread


def thumbnail(project: dict) -> Path | None:
    """The project's YouTube thumbnail, which the studio keeps in its own folder (thumbnail_gen.preview), fitted to the card."""
    source = thumbnail_gen.preview(project)
    if not source:
        return None
    stat = source.stat()
    cache = store.project_dir(project["id"]) / "thumbnails"
    dest = cache / f"preview-{stat.st_mtime_ns}-{stat.st_size}.webp"
    if dest.exists():
        return dest
    with LOCK:
        cache.mkdir(parents=True, exist_ok=True)
        for old in cache.glob("preview-*.webp"):
            old.unlink()
        with Image.open(source) as image:
            fitted = ImageOps.fit(image.convert("RGB"), SIZE, Image.Resampling.LANCZOS)
        temp = cache / f"preview-{uuid.uuid4().hex}.tmp.webp"
        fitted.save(temp, format="WEBP", quality=85, method=4)
        os.replace(temp, dest)
    return dest


def get(project: dict) -> Path | None:
    made = thumbnail(project)
    if made:
        return made
    picks = candidates(project)
    if not picks:
        return None
    identity = [VERSION] + [[str(path), path.stat().st_size, path.stat().st_mtime_ns, round(second, 2)] for path, _, second in picks]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
    cache = store.project_dir(project["id"]) / "thumbnails"
    dest = cache / f"cover-{key}.webp"
    if dest.exists():
        return dest
    with LOCK:
        if dest.exists():
            return dest
        best, best_score = None, -1.0
        for path, kind, second in picks:
            try:
                image = frame(path, kind, second)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                continue
            value = score(image)
            if value > best_score:
                best, best_score = image, value
        if best is None:
            return None
        cache.mkdir(parents=True, exist_ok=True)
        for old in cache.glob("cover-*.webp"):
            old.unlink()
        temp = cache / f"cover-{uuid.uuid4().hex}.tmp.webp"
        try:
            ImageOps.fit(best, SIZE, Image.Resampling.LANCZOS).save(temp, format="WEBP", quality=82, method=4)
            os.replace(temp, dest)
        finally:
            if temp.exists():
                temp.unlink()
        return dest
