"""OpenRouter image generation for editable transparent project assets."""

from __future__ import annotations

import base64
import binascii
import io
import json
import math
import tempfile
import urllib.request
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

import agent_openrouter
import agent_storage
import credentials
import store


TRANSPARENT_MODEL = "openai/gpt-image-1-mini"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


def validate_transparent_png(data):
    """Reject fake transparency, empty images and unexpectedly large outputs."""
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_IMAGE_BYTES:
        raise store.StudioError("Зображення порожнє або завелике.", 502)
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or image.width * image.height > MAX_IMAGE_PIXELS:
                raise store.StudioError("Сервіс повернув невідповідний формат або розмір зображення.", 502)
            if "A" not in image.getbands() and "transparency" not in image.info:
                raise store.StudioError("Зображення не має прозорого фону.", 502)
            alpha = image.convert("RGBA").getchannel("A")
            minimum, maximum = alpha.getextrema()
            if minimum == 255 or maximum == 0:
                raise store.StudioError("Зображення не містить видимого об'єкта з прозорим фоном.", 502)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise store.StudioError("Сервіс повернув пошкоджене зображення.", 502) from None


def generate_image_asset(project_id, prompt, *, transparent=False, aspect_ratio="1:1", quality="medium"):
    """Generate one image; the calling workflow must obtain spending authorization."""
    project = store.load_project(project_id)
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
        raise store.StudioError("Опишіть зображення для генерації.")
    if aspect_ratio not in {"1:1", "3:2", "2:3"} or quality not in {"low", "medium", "high"}:
        raise store.StudioError("Непідтримувані параметри прозорого зображення.")
    try:
        key = credentials.vault().read(credentials.service_name("openrouter"))
    except RuntimeError:
        raise store.StudioError("Додайте ключ OpenRouter у налаштуваннях студії.", 503) from None
    payload = {"model": TRANSPARENT_MODEL, "prompt": prompt.strip(), "background": "transparent" if transparent else "opaque", "aspect_ratio": aspect_ratio, "quality": quality, "n": 1}
    request = urllib.request.Request(agent_openrouter.BASE + "/images", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST", headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"})
    amount, request_id = None, None
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            request_id = response.headers.get("X-Generation-Id") if hasattr(response, "headers") else None
            result = json.load(response)
        request_id = request_id or result.get("id")
        cost = result.get("usage", {}).get("cost")
        if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0:
            amount = cost
        encoded = result["data"][0]["b64_json"]
        if not isinstance(encoded, str) or len(encoded) > (MAX_IMAGE_BYTES * 4 // 3 + 8):
            raise ValueError("Invalid image size")
        data = base64.b64decode(encoded, validate=True)
        if transparent:
            validate_transparent_png(data)
        else:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG" or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Invalid image")
                image.verify()
    except store.StudioError:
        raise
    except (OSError, ValueError, KeyError, IndexError, TypeError, binascii.Error):
        raise store.StudioError("Не вдалося отримати прозоре зображення від OpenRouter.", 502) from None
    finally:
        agent_storage.add_cost(project_id, "image", TRANSPARENT_MODEL, amount, request_id)
    with tempfile.TemporaryDirectory(prefix="studio-agent-image-") as folder:
        source = Path(folder) / ("agent-" + uuid.uuid4().hex[:12] + ".png")
        source.write_bytes(data)
        return store.import_asset_file(project, source, "openrouter")


def generate_transparent_asset(project_id, prompt, *, aspect_ratio="1:1", quality="medium"):
    return generate_image_asset(project_id, prompt, transparent=True, aspect_ratio=aspect_ratio, quality=quality)
