"""The channel's logo on its thumbnails (user, 15 November 2026: «прикріпляти до прев'ю логотип… в якому углі я хочу…
або сам Codex має одразу генерувати картинку разом з цим логотипом… галочку, якщо я ставлю, то прев'юшка буде з
логотипом»).

The logo is the channel's own file (channel_branding.logo_path, the one the films carry). The setting lives in the channel
settings as `thumbnail_logo`:
- a corner: Codex keeps that corner free and the studio lays the file on the finished picture itself, so the logo is
  exact. The picture without the logo stays in «Без логотипа», and an edit of that version starts from it, so a
  remark never ends with two logos;
- «auto»: the file goes to Codex with the prompt, and Codex places it where the composition has room.
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path

from PIL import Image, UnidentifiedImageError

import channel_branding

CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
POSITIONS = ("auto", *CORNERS)
DEFAULTS = {"enabled": False, "position": "auto", "size": 14}
SIZE = (5, 30)          # percent of the thumbnail's width
MARGIN = 3              # percent of the width, as for the films' logo
RAW = "Без логотипа"
REFERENCE = "Логотип каналу.png"


def validate(value) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise channel_branding.BrandingError("Невірні налаштування логотипа на прев’ю")
    if "enabled" in value and not isinstance(value["enabled"], bool):
        raise channel_branding.BrandingError("Невірний перемикач логотипа на прев’ю")
    if value.get("position", DEFAULTS["position"]) not in POSITIONS:
        raise channel_branding.BrandingError("Невідоме місце логотипа на прев’ю")
    size = value.get("size", DEFAULTS["size"])
    if type(size) not in (int, float) or not math.isfinite(size) or not SIZE[0] <= size <= SIZE[1]:
        raise channel_branding.BrandingError("Невірний розмір логотипа на прев’ю")


def spec(project: dict, settings: dict) -> dict | None:
    """The setting with its logo file, or None when the box is off or the channel has no logo."""
    value = {**DEFAULTS, **(settings.get("thumbnail_logo") or {})}
    cid = project.get("channel_id")
    if not value["enabled"] or not cid:
        return None
    path = channel_branding.logo_path(cid)
    return {**value, "path": path} if path.is_file() else None


def prepare(logo: dict | None, work: Path) -> tuple[Path | None, str]:
    """The image to attach for Codex (auto only) and the lines added to the drawing prompt."""
    if not logo:
        return None, ""
    if logo["position"] in CORNERS:
        corner = logo["position"].replace("-", " ")
        return None, (f"\nCHANNEL LOGO SPACE: keep the {corner} corner of the image (about {round(logo['size']) + 4}% of "
                      "the width) calm and free of faces, the main subject and lettering: the studio puts the channel "
                      "logo there afterwards. Do not draw any logo, watermark or channel name yourself.\n")
    target = work / REFERENCE
    shutil.copyfile(logo["path"], target)
    return target, (f'\nCHANNEL LOGO: the attached image "{REFERENCE}" is the channel\'s logo. Put it on this thumbnail '
                    f"once, about {round(logo['size'])}% of the image width, where the composition has room: near an "
                    "edge or a corner, never over a face, the main subject or the headline. Reproduce the logo exactly as "
                    "attached: the same shapes, colours, letters and proportions, not redrawn, restyled or translated, "
                    "fully readable. It is not a reference for the scene's style.\n")


def clean(work: Path, name: str) -> Path | None:
    """The version's picture before the studio laid the logo on it, if it has one."""
    path = work / RAW / name
    return path if path.is_file() else None


def stamp(picture: Path, logo: dict | None, work: Path) -> bool:
    """Lay the logo in its corner on the finished picture; keep the picture without it. False when nothing was laid."""
    if not logo or logo["position"] not in CORNERS:
        return False
    try:
        with Image.open(logo["path"]) as source:
            mark = source.convert("RGBA")
        with Image.open(picture) as made:
            image = made.convert("RGBA")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        return False
    (work / RAW).mkdir(exist_ok=True)
    shutil.copyfile(picture, work / RAW / picture.name)
    x, y, width, height = channel_branding.box({"position": logo["position"], "size": logo["size"], "margin": MARGIN},
                                               mark.size, image.size)
    mark = mark.resize((width, height), Image.Resampling.LANCZOS)
    image.alpha_composite(mark, (x, y))
    staged = picture.with_name(".logo-" + picture.name)
    image.convert("RGB").save(staged, format="PNG", optimize=True)
    staged.replace(picture)
    return True
