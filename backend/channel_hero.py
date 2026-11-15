"""The channel's main character: one photo kept in Studio data, used for thumbnails and, since 15 November 2026, for
the pictures and animation assets of the frames too (user: «студія має мати доступ до головного героя не тільки для
превью а і для картинок або анімацій… генерувати його в різних позах»). The photo may have any shape: it is scaled to
fit 1600 px, never cropped. Every use draws the same person anew: another pose, angle, emotion and framing, never the
photo pasted in (user: «не точ в точ такий самий герой якбудто його вирізали вставили… ракурс емоція і т д унікальні»)."""
from __future__ import annotations

import base64
import binascii
import io
import os
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

import store


def path(cid: str) -> Path:
    return store.DATA_ROOT / 'channels' / cid / 'thumbnail-hero.png'


def info(cid: str) -> dict | None:
    file = path(cid)
    try:
        return {'url': f'/api/channels/{cid}/thumbnail-hero?v={file.stat().st_mtime_ns}'}
    except FileNotFoundError:
        return None


def save(cid: str, data: str) -> dict:
    store.get_channel_folder(cid)
    if not isinstance(data, str) or len(data) > 9 * 1024 * 1024:
        raise store.StudioError('Оберіть фото героя до 6 МБ', 400)
    try:
        raw = base64.b64decode(data.split(',', 1)[-1], validate=True)
        if not raw or len(raw) > 6 * 1024 * 1024:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    except (ValueError, binascii.Error, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise store.StudioError('Оберіть фото PNG, JPG або WebP до 6 МБ', 400) from None
    target = path(cid)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f'.hero-{uuid.uuid4().hex}.png')
    try:
        image.save(temp, format='PNG', optimize=True)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return info(cid)


def remove(cid: str) -> None:
    store.get_channel_folder(cid)
    path(cid).unlink(missing_ok=True)


def prepare(project: dict, work: Path, enabled: bool | None = None) -> tuple[Path | None, str]:
    if enabled is not None and not isinstance(enabled, bool):
        raise store.StudioError('Оберіть, чи використовувати головного героя', 400)
    cid = project.get('channel_id')
    source = path(cid) if cid else None
    if not source or not source.is_file():
        return None, ''
    if enabled is False:
        return None, '\nHost choice for this image: do not include the channel host, even if visible in the style or base images. Preserve other story subjects.\n'
    # Snapshot the photo for this run, so a later channel upload cannot change its identity mid-generation.
    target = work / 'Головний герой.png'
    target.write_bytes(source.read_bytes())
    return target, '''
MAIN CHARACTER REFERENCE: the attached image "Головний герой.png" defines the channel host.
Include this recognizable person prominently in this thumbnail. Preserve their identity, facial features and age.
The photo is an identity reference only: draw the person anew for this idea, never a copy, cutout or paste of it.
Choose a fresh camera angle (for example three-quarter, profile, low or high angle, close-up or waist-up), a pose and
gesture that act out the story, and a strong emotion that fits the title (shock, fear, delight, suspicion, awe...).
Do not repeat the reference's head tilt, gaze, expression, framing, clothes or lighting; adapt clothes and light to the
scene and the channel's visual style, so every thumbnail of the channel shows the host differently.
Do not replace them with a generic person.
This host choice takes priority over instructions to preserve characters in other reference images.
'''


def production_rule(project: dict) -> str:
    """The lines a frame agent and the director get when the channel has a main character photo."""
    cid = project.get('channel_id')
    source = path(cid) if cid else None
    if not source or not source.is_file():
        return ''
    return (f"\nГоловний герой каналу: фото {source}. Коли кадр показує ведучого чи головного героя каналу, малюй саме його:"
            f" додай до codex_image.py --ref \"{source}\" і напиши в промпті, що це референс лише зовнішності."
            " Щоразу інша поза, ракурс, емоція, жест, одяг і світло за змістом кадру, у стилі каналу; не копія й не вирізка фото."
            " Для анімаційного каналу малюй героя в стилі анімації впізнаваним за рисами обличчя, зачіскою й віком."
            " Інших людей і героїв сюжету цим фото не підміняй.\n")
