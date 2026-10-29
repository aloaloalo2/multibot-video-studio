"""Channel identity: whether a channel makes regular or animated videos, and its logo and where it sits in the frame.

The logo file lives with the Studio data, the placement lives in the channel settings. One placement function is used
by every place that draws the logo (settings preview, style previews, Razgon overlay, export), so they always agree.
"""
from __future__ import annotations

import base64, binascii, io, math, os, uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

import store

KINDS = {"regular", "animated"}
POSITIONS = ("top-left", "top-center", "top-right", "middle-left", "middle-right", "bottom-left", "bottom-center", "bottom-right")
LOGO_DEFAULTS = {"enabled": True, "position": "top-right", "size": 12, "margin": 3, "opacity": 100}
LIMITS = {"size": (3, 40), "margin": (0, 15), "opacity": (10, 100)}
MAX_SIDE = 1200


class BrandingError(ValueError):
    pass


def validate(settings: dict) -> None:
    """Check the channel kind and logo placement inside saved channel settings."""
    if "channel_kind" in settings and settings["channel_kind"] not in KINDS:
        raise BrandingError("Невідомий тип каналу")
    import style_lab
    try:
        style_lab.validate(settings.get("animation"))
    except style_lab.StyleLabError as error:
        raise BrandingError(str(error)) from None
    logo = settings.get("logo")
    if logo is None:
        return
    if not isinstance(logo, dict):
        raise BrandingError("Невірні налаштування логотипа")
    if "enabled" in logo and not isinstance(logo["enabled"], bool):
        raise BrandingError("Невірний перемикач логотипа")
    if logo.get("position", LOGO_DEFAULTS["position"]) not in POSITIONS:
        raise BrandingError("Невідоме місце логотипа")
    for key, (lo, hi) in LIMITS.items():
        if key in logo:
            value = logo[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
                raise BrandingError("Невірне значення логотипа: " + key)


def placement(logo: dict | None) -> dict:
    """Logo settings with defaults filled in."""
    return {**LOGO_DEFAULTS, **(logo or {})}


def box(logo: dict | None, logo_size: tuple[int, int], frame: tuple[int, int]) -> tuple[int, int, int, int]:
    """Pixel rectangle (x, y, width, height) of the logo in a frame. Size and margin are percent of the frame width."""
    spec = placement(logo)
    fw, fh = frame
    lw, lh = logo_size
    width = max(1, round(fw * spec["size"] / 100))
    height = max(1, round(width * lh / max(1, lw)))
    margin = round(fw * spec["margin"] / 100)
    row, col = spec["position"].split("-")
    x = {"left": margin, "center": (fw - width) // 2, "right": fw - width - margin}[col]
    y = {"top": margin, "middle": (fh - height) // 2, "bottom": fh - height - margin}[row]
    return x, y, width, height


def logo_path(cid: str) -> Path:
    return store.DATA_ROOT / "channels" / cid / "logo.png"


def save_logo(cid: str, data: str) -> dict:
    """Store an uploaded logo (base64 image) as a PNG with transparency, at most MAX_SIDE pixels on its long side."""
    store.get_channel_folder(cid)
    if not isinstance(data, str) or not data:
        raise BrandingError("Оберіть файл логотипа")
    try:
        raw = base64.b64decode(data.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise BrandingError("Файл логотипа пошкоджено") from None
    try:
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
    except (UnidentifiedImageError, OSError):
        raise BrandingError("Логотип має бути картинкою PNG, JPG або WEBP") from None
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    target = logo_path(cid)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".logo-{uuid.uuid4().hex}.png")
    try:
        image.save(temp, format="PNG", optimize=True)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return logo_info(cid)


def remove_logo(cid: str) -> None:
    store.get_channel_folder(cid)
    path = logo_path(cid)
    if path.exists():
        path.unlink()


def logo_info(cid: str) -> dict | None:
    path = logo_path(cid)
    if not path.is_file():
        return None
    with Image.open(path) as image:
        width, height = image.size
    return {"url": f"/api/channels/{cid}/logo?v={path.stat().st_mtime_ns}", "width": width, "height": height}


def draw(frame: Image.Image, cid: str, logo: dict | None) -> Image.Image:
    """The frame with the channel logo on top, or the frame unchanged when there is no logo or it is switched off."""
    spec = placement(logo)
    path = logo_path(cid)
    if not spec["enabled"] or not path.is_file():
        return frame
    with Image.open(path) as source:
        mark = source.convert("RGBA")
    x, y, width, height = box(spec, mark.size, frame.size)
    mark = mark.resize((width, height), Image.Resampling.LANCZOS)
    if spec["opacity"] < 100:
        alpha = mark.getchannel("A").point(lambda value: round(value * spec["opacity"] / 100))
        mark.putalpha(alpha)
    result = frame.convert("RGBA")
    result.alpha_composite(mark, (x, y))
    return result


def overlay_png(cid: str, logo: dict | None, frame: tuple[int, int], target: Path) -> Path | None:
    """A transparent full-frame PNG with the logo placed, as Razgon's config.overlay expects."""
    canvas = Image.new("RGBA", frame, (0, 0, 0, 0))
    result = draw(canvas, cid, logo)
    if result is canvas:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    result.save(target, format="PNG")
    return target
