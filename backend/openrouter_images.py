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
import openrouter_http   # busy providers and gateway errors are retried, unbilled
import uuid

from PIL import Image, UnidentifiedImageError

import credentials
import project_costs
import store

DEFAULT_MODEL = "openai/gpt-image-1-mini"
# A picture drawn from a reference, the host's avatar above all, goes to a stronger model: the mini one does not hold a
# face well (user, 17 November 2026: «якщо це стосується лиць… аватар мій… краще сильнішу модель, ця не тягне»).
# GPT Image 2.6 Sunburst is OpenAI's detail tier, keeps details consistent between edits and still draws transparent
# backgrounds; its tokens cost about 3.75 times the mini's (OpenRouter /images/models, the same day).
FACE_MODEL = "openai/gpt-image-2.6-sunburst"
BASE = "https://openrouter.ai/api/v1"
MAX_BYTES = 20 * 1024 * 1024


def refusal(code: int, detail: str) -> str:
    """OpenRouter's refusal in the author's words. A key with a daily cap answers 403 «Key limit exceeded (daily limit)»
    (18 November 2026: «$2.68 of $2.00 used»): the cap is the author's own setting of the key, shared with translations
    and DeepSeek."""
    import re
    if code == 403 and "Key limit exceeded" in detail:
        used = re.search(r"\$([\d.]+) of \$([\d.]+) used", detail)
        resets = re.search(r"resets (\d{4}-\d\d-\d\dT\d\d:\d\d)", detail)
        when = ""
        if resets:
            from datetime import datetime, timezone
            moment = datetime.strptime(resets.group(1), "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc).astimezone()
            when = f" Ліміт оновиться {moment:%d.%m о %H:%M}."
        spent = f" Витрачено ${used.group(1)} з ${used.group(2)} на день." if used else ""
        return ("Вичерпано денний ліміт ключа OpenRouter." + spent + when +
                " Його можна підняти в налаштуваннях ключа на openrouter.ai/settings/keys; цей ключ тратять і переклади.")
    if code == 402:
        # 402 also comes while money is left: a request whose possible cost is more than the balance still free, as
        # when several sheets are drawn at once (21 November 2026: about $2.75 left, sheets failed side by side and
        # went through one by one); OpenRouter's own words and the balance say which
        left = balance()
        return ("OpenRouter відмовив (402): на балансі замало вільних коштів для цього запиту" +
                (f", лишилося ${left:.2f}" if left is not None else "") +
                ". Поповніть баланс на openrouter.ai або малюйте аркуші по одному." +
                (f" Відповідь OpenRouter: {detail[:200]}" if detail else ""))
    return f"OpenRouter відповів {code}: {detail[:300]}"


def balance() -> float | None:
    """Dollars left on the OpenRouter account (GET /api/v1/credits), None when it cannot be read."""
    import json as _json
    import urllib.request as _request
    try:
        key = credentials.vault().read(credentials.service_name("openrouter"))
        call = _request.Request("https://openrouter.ai/api/v1/credits", headers={"Authorization": "Bearer " + key})
        data = _json.load(_request.urlopen(call, timeout=10)).get("data") or {}
        return float(data["total_credits"]) - float(data["total_usage"])
    except Exception:
        return None


def path(pid: str):
    return store.project_dir(pid) / "image-provider.json"


def setting(pid: str) -> dict:
    """The episode's own choice when it has one, else its channel's «Малює» (animation.image_provider in the channel's
    settings; user, 17 November 2026: «в студії прям вибирати, чи можна мені юзати ці асети»)."""
    data = store.read_json(path(pid), None)
    if isinstance(data, dict) and data.get("provider") in ("openrouter", "codex"):
        return data if data["provider"] == "openrouter" else {}
    try:
        project = store.load_project(pid)
    except (store.StudioError, OSError):
        return {}
    try:
        channel = store.read_channel_settings(store.get_channel_folder(project["channel_id"], include_disabled=True), {}) or {}
    except (store.StudioError, KeyError, OSError):
        channel = {}
    if (channel.get("animation") or {}).get("image_provider") == "openrouter":
        return {"provider": "openrouter", "model": DEFAULT_MODEL, "from_channel": True}
    # an animated film draws its PNG props through OpenRouter as the Studio's base, with nothing to choose (user,
    # 17 November 2026: «анімаційні ролики по дефолту… асети… через Open Router… вибирати це не потрібно»)
    if store.project_animated(project):
        return {"provider": "openrouter", "model": DEFAULT_MODEL, "from_kind": True}
    # a regular episode with Razgon and code-animation frames draws their PNG props there too; its photos and other
    # opaque pictures stay with Codex (user, 17 November 2026: «не анімаційні проекти, але там є розгон… теж все має
    # бути від OpenRouter, асети»)
    return {"provider": "openrouter", "model": DEFAULT_MODEL, "props_only": True}


def set_provider(pid: str, provider: str, model: str | None = None, everything: bool = False) -> dict:
    store.load_project(pid)
    if provider == "codex":
        # kept as a file, so an episode can draw with Codex although its channel chose OpenRouter
        store.atomic_json(path(pid), {"provider": "codex"})
        return {}
    if provider != "openrouter":
        raise store.StudioError("Невідомий спосіб малювання картинок")
    data = {"provider": "openrouter", "model": model or DEFAULT_MODEL}
    if everything:
        # «Продовжити через OpenRouter» after Codex ran out of its limit: every picture of the episode is drawn here, the
        # host's sheets and backgrounds too, not only transparent props (user, 17 November 2026)
        data["all"] = True
    store.atomic_json(path(pid), data)
    return data


def spent(pid: str) -> dict:
    """The sheets drawn here for the episode and what they cost, from the episode's cost receipts."""
    events = (store.read_json(store.project_dir(pid) / "project-costs.json", {}) or {}).get("events", {})
    mine = [e for key, e in events.items() if key.startswith("openrouter:sheet-")]
    return {"sheets": len(mine), "usd": round(sum(float(e.get("amount") or 0) for e in mine), 4)}


MAX_REFERENCES = 16              # gpt-image-1-mini's limit (GET /api/v1/images/models, input_references)
REFERENCE_BYTES = 8 * 1024 * 1024
REFERENCE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def references(paths) -> list[dict]:
    """Reference pictures for the drawing, such as the host's avatar (user, 17 November 2026: «може юзати мій аватар?»).
    OpenRouter takes them as input_references objects; a test the same day drew Karl from his avatar, recognisably."""
    found = []
    for item in list(paths or [])[:MAX_REFERENCES]:
        path = __import__("pathlib").Path(item)
        kind = REFERENCE_TYPES.get(path.suffix.lower())
        if not kind or not path.is_file() or path.stat().st_size > REFERENCE_BYTES:
            raise store.StudioError(f"Референс {path.name} не підходить: PNG, JPEG чи WebP до 8 МБ")
        found.append({"type": "image_url", "image_url": {"url": f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode()}})
    return found


THUMBNAIL_MODEL = FACE_MODEL
THUMBNAIL_REFS = 10


def draw_thumbnail(pid: str, prompt: str, refs=None) -> dict:
    """A YouTube thumbnail drawn by OpenRouter, in beta beside Codex (user, 18 November 2026: «підключи її до студії…
    щоб вона зробила мені прев'юшку… в бета-тесті… щоб я ціну знав»). The detail tier, 16:9, high quality, opaque;
    the same references Codex gets (the host, the video's stills, the logo). {'png': bytes, 'cost': usd, 'model'}."""
    store.load_project(pid)
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 30000:
        raise store.StudioError("Опишіть прев’ю")
    try:
        key = credentials.vault().read(credentials.service_name("openrouter"))
    except RuntimeError:
        raise store.StudioError("Додайте ключ OpenRouter у налаштуваннях студії", 503) from None
    body = {"model": THUMBNAIL_MODEL, "prompt": prompt.strip(), "background": "opaque", "aspect_ratio": "16:9",
            "quality": "high", "n": 1}
    if refs:
        body["input_references"] = references(list(refs)[:THUMBNAIL_REFS])
    request = urllib.request.Request(BASE + "/images", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     method="POST", headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with openrouter_http.urlopen(request, timeout=600) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(2000).decode("utf-8", "replace").replace(key, "[ключ]")
        raise store.StudioError(refusal(error.code, detail), 502) from None
    except (OSError, ValueError) as error:
        raise store.StudioError(f"OpenRouter не відповів: {error}", 502) from None
    cost = (result.get("usage") or {}).get("cost")
    amount = cost if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else None
    project_costs.record_at(store.project_dir(pid), "openrouter", amount, identity="thumbnail-" + str(result.get("id") or uuid.uuid4().hex),
                            category="thumbnail", estimated=amount is None)
    try:
        data = base64.b64decode(result["data"][0]["b64_json"], validate=True)
        if not 0 < len(data) <= MAX_BYTES:
            raise ValueError("size")
        with Image.open(io.BytesIO(data)) as image:
            saved = io.BytesIO()
            image.convert("RGB").save(saved, "PNG")
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error, UnidentifiedImageError):
        raise store.StudioError("OpenRouter не повернув картинку прев’ю", 502) from None
    return {"png": saved.getvalue(), "cost": amount, "model": THUMBNAIL_MODEL}


def draw(pid: str, prompt: str, aspect_ratio: str = "3:2", quality: str = "medium", refs=None, transparent: bool = True,
         detail: bool = False) -> dict:
    """One sheet: {'png': base64, 'cost': usd}, transparent unless the prompt asks for a background of its own. Never
    retried: a failed paid call is reported, not repeated."""
    chosen = setting(pid)
    if not chosen:
        raise store.StudioError("Для цього випуску картинки малює Codex", 409)
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 30000:
        raise store.StudioError("Опишіть картинку")
    if aspect_ratio not in {"1:1", "3:2", "2:3", "16:9", "9:16"} or quality not in {"low", "medium", "high"}:
        raise store.StudioError("Непідтримуваний формат картинки")
    try:
        key = credentials.vault().read(credentials.service_name("openrouter"))
    except RuntimeError:
        raise store.StudioError("Додайте ключ OpenRouter у налаштуваннях студії", 503) from None
    # a face from a reference, or a picture the agent marks as detailed, goes to the stronger model; the rest to the cheap
    # one, which draws animation props well (user, 17 November 2026: «якщо щось треба намалювати якісно, деталізовано…
    # старшу модель… поки ця дешева справляється окей»)
    # the cheap model only for transparent props: a photo, an infographic or anything with lettering on its own ground goes
    # to the stronger one (22 November 2026: photo sheets from the mini model came with garbled lettering and waxy faces)
    model = FACE_MODEL if refs or detail or not transparent else chosen.get("model") or DEFAULT_MODEL
    if model == DEFAULT_MODEL and aspect_ratio in {"16:9", "9:16"}:
        aspect_ratio = "3:2" if aspect_ratio == "16:9" else "2:3"   # the mini model draws only 1:1, 3:2 and 2:3
    body = {"model": model, "prompt": prompt.strip(), "background": "transparent" if transparent else "opaque", "aspect_ratio": aspect_ratio,
            "quality": quality, "n": 1}
    if refs:
        body["input_references"] = references(refs)
    request = urllib.request.Request(BASE + "/images", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     method="POST", headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with openrouter_http.urlopen(request, timeout=300) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(2000).decode("utf-8", "replace").replace(key, "[ключ]")
        raise store.StudioError(refusal(error.code, detail), 502) from None
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
            if transparent and (image.format != "PNG" or "A" not in image.getbands()):
                raise ValueError("not a transparent PNG")
            if image.format != "PNG":   # an opaque picture may come as JPEG or WebP: the tools expect a PNG
                saved = io.BytesIO()
                image.convert("RGB").save(saved, "PNG")
                data = saved.getvalue()
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error, UnidentifiedImageError):
        raise store.StudioError("OpenRouter не повернув прозорий PNG" if transparent else "OpenRouter не повернув картинку", 502) from None
    return {"png": base64.b64encode(data).decode(), "cost": amount, "model": model}
