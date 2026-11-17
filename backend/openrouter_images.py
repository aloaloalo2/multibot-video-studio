"""Prop sheets drawn through OpenRouter in place of Codex, for one episode at a time.

The author turns it on for an episode when Codex's limit has run out (17 November 2026: «бо кодекс знову закінчився
ліміт… давай через опен роутер цей ролик весь»). The frame agent keeps calling tools/codex_image.py as before; for an
episode with `image-provider.json` set to openrouter, that tool asks the Studio to draw here. Each sheet is paid from the
OpenRouter balance and its real cost goes to the episode's costs.

A test on 17 November 2026 drew the same six-prop sheet two ways: `openai/gpt-image-1-mini` with the images endpoint's
transparent background gave a clean 3:2 sheet, every prop whole, for $0.0128 in 18 s; `openai/gpt-5-image-mini` through
chat gave a square with four props cut by the edge for $0.046 in 49 s. So the first is the default.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import math
import urllib.error
import urllib.request
import uuid

from PIL import Image, UnidentifiedImageError

import credentials
import project_costs
import store

DEFAULT_MODEL = "openai/gpt-image-1-mini"
BASE = "https://openrouter.ai/api/v1"
MAX_BYTES = 20 * 1024 * 1024


def path(pid: str):
    return store.project_dir(pid) / "image-provider.json"


def setting(pid: str) -> dict:
    data = store.read_json(path(pid), {}) or {}
    return data if data.get("provider") == "openrouter" else {}


def set_provider(pid: str, provider: str, model: str | None = None) -> dict:
    store.load_project(pid)
    if provider == "codex":
        path(pid).unlink(missing_ok=True)
        return {}
    if provider != "openrouter":
        raise store.StudioError("Невідомий спосіб малювання картинок")
    data = {"provider": "openrouter", "model": model or DEFAULT_MODEL}
    store.atomic_json(path(pid), data)
    return data


def spent(pid: str) -> dict:
    """The sheets drawn here for the episode and what they cost, from the episode's cost receipts."""
    events = (store.read_json(store.project_dir(pid) / "project-costs.json", {}) or {}).get("events", {})
    mine = [e for key, e in events.items() if key.startswith("openrouter:sheet-")]
    return {"sheets": len(mine), "usd": round(sum(float(e.get("amount") or 0) for e in mine), 4)}


def draw(pid: str, prompt: str, aspect_ratio: str = "3:2", quality: str = "medium") -> dict:
    """One transparent sheet: {'png': base64, 'cost': usd}. Never retried: a failed paid call is reported, not repeated."""
    chosen = setting(pid)
    if not chosen:
        raise store.StudioError("Для цього випуску картинки малює Codex", 409)
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 30000:
        raise store.StudioError("Опишіть картинку")
    if aspect_ratio not in {"1:1", "3:2", "2:3"} or quality not in {"low", "medium", "high"}:
        raise store.StudioError("Непідтримуваний формат картинки")
    try:
        key = credentials.vault().read(credentials.service_name("openrouter"))
    except RuntimeError:
        raise store.StudioError("Додайте ключ OpenRouter у налаштуваннях студії", 503) from None
    model = chosen.get("model") or DEFAULT_MODEL
    body = {"model": model, "prompt": prompt.strip(), "background": "transparent", "aspect_ratio": aspect_ratio,
            "quality": quality, "n": 1}
    request = urllib.request.Request(BASE + "/images", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     method="POST", headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(2000).decode("utf-8", "replace").replace(key, "[ключ]")
        raise store.StudioError(f"OpenRouter відповів {error.code}: {detail[:300]}", 502) from None
    except (OSError, ValueError) as error:
        raise store.StudioError(f"OpenRouter не відповів: {error}", 502) from None
    cost = (result.get("usage") or {}).get("cost")
    amount = cost if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else None
    identity = "sheet-" + str(result.get("id") or uuid.uuid4().hex)
    project_costs.record_at(store.project_dir(pid), "openrouter", amount, identity=identity, category="image", estimated=amount is None)
    try:
        data = base64.b64decode(result["data"][0]["b64_json"], validate=True)
        if not 0 < len(data) <= MAX_BYTES:
            raise ValueError("size")
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or "A" not in image.getbands():
                raise ValueError("not a transparent PNG")
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error, UnidentifiedImageError):
        raise store.StudioError("OpenRouter не повернув прозорий PNG", 502) from None
    return {"png": base64.b64encode(data).decode(), "cost": amount, "model": model}
