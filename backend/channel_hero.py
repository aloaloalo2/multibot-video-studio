"""Optional channel host reference for thumbnail generation, kept in Studio data."""
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
Adapt their pose, expression, clothes and lighting to the idea and the channel's visual style.
This photo is an identity reference, not the requested composition or background. Do not replace them with a generic person.
This host choice takes priority over instructions to preserve characters in other reference images.
'''
