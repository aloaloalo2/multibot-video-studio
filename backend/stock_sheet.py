"""A contact sheet of stock candidates for one frame, so an agent picks a Pixabay photo or video by looking at it.

`studio.py stock P N "query" [--video]` (POST /api/projects/<id>/stock-sheet) searches Pixabay, draws the candidates'
previews numbered on one PNG with their length for a video, and answers its path with one short line per candidate.
The agent looks at the one picture instead of reading lists of tags, then `studio.py stock-pick P N ID` downloads the
chosen one into the project and places it as frame N. Pictures of people are not filtered here: the channel rule (only
stick figures) is the agent's to apply on the sheet.
"""
from __future__ import annotations

import hashlib
import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import store

TILE = (360, 203)
COLUMNS = 4
GAP = 10


def fetch(url: str) -> bytes:
    """A preview image from Pixabay's CDN (public, no key)."""
    request = urllib.request.Request(url, headers={"User-Agent": "VideoKey-Studio/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def preview_url(hit: dict, kind: str) -> str | None:
    if kind == "video":
        videos = hit.get("videos") or {}
        for size in ("medium", "small", "tiny", "large"):
            if (videos.get(size) or {}).get("thumbnail"):
                return videos[size]["thumbnail"]
        return None
    return hit.get("webformatURL") or hit.get("previewURL")


def _font(size: int):
    for name in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def sheet(project: dict, frame: int, query: str, kind: str = "image", count: int = 8) -> dict:
    if kind not in {"image", "video"} or not 1 <= len(query or "") <= 100 or not 1 <= int(count) <= 16:
        raise store.StudioError("Потрібні слова пошуку (до 100 знаків), тип image або video і від 1 до 16 варіантів")
    import app   # the Pixabay client the library uses, with the key from the Keychain
    pixabay = app.pixabay_module()
    try:
        hits = (pixabay.api_get(kind, q=query, per_page=max(3, int(count)), safesearch="true") or {}).get("hits", [])[:int(count)]
    except RuntimeError as error:
        raise store.StudioError(str(error), 503) from None
    if not hits:
        return {"sheet": None, "candidates": [], "note": "Нічого не знайдено: спробуйте інші англійські слова"}
    rows = (len(hits) + COLUMNS - 1) // COLUMNS
    canvas = Image.new("RGB", (COLUMNS * TILE[0] + (COLUMNS + 1) * GAP, rows * TILE[1] + (rows + 1) * GAP), (18, 18, 20))
    draw, big, small = ImageDraw.Draw(canvas), _font(30), _font(18)
    candidates = []
    for index, hit in enumerate(hits):
        x = GAP + (index % COLUMNS) * (TILE[0] + GAP)
        y = GAP + (index // COLUMNS) * (TILE[1] + GAP)
        url = preview_url(hit, kind)
        try:
            with Image.open(io.BytesIO(fetch(url))) as picture:
                picture = picture.convert("RGB")
                picture.thumbnail(TILE)
                canvas.paste(picture, (x + (TILE[0] - picture.width) // 2, y + (TILE[1] - picture.height) // 2))
        except Exception:   # a missing preview leaves a grey tile with its number, the candidate stays pickable
            draw.rectangle([x, y, x + TILE[0], y + TILE[1]], fill=(45, 45, 50))
        number = str(index + 1)
        draw.rectangle([x, y, x + 46, y + 40], fill=(240, 180, 41))
        draw.text((x + 23, y + 20), number, fill=(20, 16, 8), font=big, anchor="mm")
        if kind == "video" and hit.get("duration"):
            label = f"{hit['duration']} с"
            box = draw.textbbox((0, 0), label, font=small)
            draw.rectangle([x + TILE[0] - box[2] - 16, y + TILE[1] - 30, x + TILE[0], y + TILE[1]], fill=(0, 0, 0))
            draw.text((x + TILE[0] - box[2] - 8, y + TILE[1] - 26), label, fill=(255, 255, 255), font=small)
        size = ""
        if kind == "video":
            biggest = max(((v or {}).get("width", 0), (v or {}).get("height", 0)) for v in (hit.get("videos") or {}).values()) if hit.get("videos") else (0, 0)
            size = f"{biggest[0]}x{biggest[1]}" if biggest[0] else ""
        else:
            size = f"{hit.get('imageWidth', '')}x{hit.get('imageHeight', '')}".strip("x")
        candidates.append({"n": index + 1, "id": hit.get("id"), "duration": hit.get("duration") if kind == "video" else None,
                           "size": size, "tags": hit.get("tags") or ""})
    folder = store.project_dir(project["id"]) / "stock"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"frame_{int(frame):03d}-{kind}-{hashlib.sha256(query.encode()).hexdigest()[:8]}.png"
    canvas.save(folder / name)
    return {"sheet": str(folder / name), "candidates": candidates}
