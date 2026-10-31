"""Copy someone else's look into a channel's own Razgon style.

DeepSeek looks at a picture (a frame of another channel, an illustration) and describes its drawing in the fields a
Razgon style has: one palette for every lighting mood, the colour grade, and the drawing manner (line tremor, ink
outline, flat fills, paper, tones). Everything it returns is checked and clamped here, so a bad answer can only give a
plain style, never a broken render. The channel keeps its copied styles in the Studio data next to its logo; the
settings page shows them with the template styles, and razgon_bridge.py puts the chosen one into a new film's config.
"""
from __future__ import annotations

import base64, binascii, hashlib, io, json, math, re, time, urllib.error, urllib.request

from PIL import Image, ImageOps, UnidentifiedImageError

import agent_openrouter
import credentials
import store

MOODS = ("day", "golden", "dusk", "night", "storm", "interiorWarm", "interiorCool", "void")
PALETTE = ("ambient", "key", "rim", "wall", "floor", "dark", "practical", "grass", "road", "fog")
UI = ("card", "cardLine", "text", "sub", "accent", "gold", "cream")
HEX = re.compile(r"#[0-9a-fA-F]{6}")
STYLE_ID = re.compile(r"custom-[0-9a-f]{10}")
MAX_STYLES = 12

PROMPT = """You turn the look of a picture into a style for Razgon, a 2D animation engine that draws stick-figure
characters (round head, line limbs, a coloured top), simple sets (sky, ground, houses, rooms, trees) and props with
canvas shapes. Study only HOW the picture is drawn: its colours, its lines, its fills, its light, its paper or texture.
Ignore what it shows. Answer with one JSON object and nothing else, in exactly this shape:

{
  "name": "2-3 English words",
  "name_uk": "2-3 Ukrainian words",
  "desc_uk": "one Ukrainian sentence about the look: colours, lines, fills, texture",
  "palette": {
    "sky": ["#rrggbb", "#rrggbb", "#rrggbb"],  // top to horizon, 2 to 4 colours
    "ambient": "#rrggbb", "key": "#rrggbb", "rim": "#rrggbb", "wall": "#rrggbb", "floor": "#rrggbb",
    "dark": "#rrggbb", "practical": "#rrggbb", "grass": "#rrggbb", "road": "#rrggbb", "fog": "#rrggbb"
  },
  "ink": "#rrggbb",          // colour of character bodies and outlines
  "feature": "#rrggbb",      // eyes and mouth drawn on the ink head
  "rimWidth": 0,             // 0 to 6: width of a light rim around characters (0 = none, 4 = cinematic)
  "ui": { "card": "#rrggbb", "cardLine": "#rrggbb", "text": "#rrggbb", "sub": "#rrggbb", "accent": "#rrggbb", "gold": "#rrggbb", "cream": "#rrggbb" },
  "grade": { "contrast": 1.0, "sat": 1.0, "vignette": 0.3, "grain": 0.04, "bloom": 0.3 },
  "manner": {
    "wobble": 0,             // 0 to 4 px: hand-drawn line tremor (0 = clean vector)
    "boil": 0,               // 0 to 12: how many times a second the tremor redraws (0 = still)
    "outline": null,         // or { "color": "#rrggbb", "width": 0.5 to 6 } when shapes have an ink outline
    "flat": false,           // true when fills are flat colour without gradients
    "glow": true,            // false when there is no glowing light at all
    "fillAlpha": 1,          // 0.1 to 1: below 1 when fills are see-through (chalk, watercolour wash)
    "tones": null,           // or 2 to 6 "#rrggbb" when the picture uses only a few tones (ink, two-tone print)
    "shadow": null,          // or { "x": -12 to 12, "y": -12 to 12, "color": "#rrggbb" } for a hard cast shadow (paper cut-out)
    "lineScale": 1,          // 0.5 to 2.5: line weight
    "grayscale": false,      // true when the picture has no colour
    "paper": null            // or { "color": "#rrggbb", "amount": 0 to 0.6 } when there is a paper, board or canvas texture
  }
}

Colours: ui.card is a caption card background, ui.text and ui.cream must read on it, ui.accent is the brightest
highlight colour. The palette must keep characters (ink) readable against the sky and walls."""


class StyleCopyError(ValueError):
    pass


def path(cid: str):
    return store.DATA_ROOT / "channels" / cid / "custom-styles.json"


def load(cid: str) -> list[dict]:
    store.get_channel_folder(cid)
    try:
        styles = json.loads(path(cid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [style for style in styles if isinstance(style, dict) and STYLE_ID.fullmatch(str(style.get("id")))] if isinstance(styles, list) else []


def find(cid: str, sid: str) -> dict | None:
    return next((style for style in load(cid) if style["id"] == sid), None)


def save_all(cid: str, styles: list[dict]) -> None:
    target = path(cid)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(styles, ensure_ascii=False, indent=1), encoding="utf-8")
    temp.replace(target)


def remove(cid: str, sid: str) -> None:
    styles = load(cid)
    if not any(style["id"] == sid for style in styles):
        raise StyleCopyError("Такого стилю немає")
    save_all(cid, [style for style in styles if style["id"] != sid])


def picture(data: str) -> str:
    """The uploaded picture as a JPEG data URL at most 1024 px on its long side: enough to read a look, cheap to send."""
    if not isinstance(data, str) or not data:
        raise StyleCopyError("Оберіть картинку")
    try:
        raw = base64.b64decode(data.split(",", 1)[-1], validate=True)
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (binascii.Error, ValueError, UnidentifiedImageError, OSError):
        raise StyleCopyError("Картинка має бути PNG, JPG або WEBP") from None
    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def ask(image_url: str, note: str = "") -> dict:
    try:
        key = credentials.vault().read(credentials.service_name("openrouter"))
    except RuntimeError:
        raise StyleCopyError("Додайте ключ OpenRouter у налаштуваннях студії") from None
    text = PROMPT + (f"\n\nThe user adds: {note.strip()[:400]}" if note and note.strip() else "")
    # Short reasoning: the look is read from the picture, and long thinking only uses up the answer's tokens.
    payload = {"model": agent_openrouter.MODEL, "max_tokens": 6000, "reasoning": {"effort": "low"}, "response_format": {"type": "json_object"},
               "messages": [{"role": "user", "content": [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": image_url}}]}]}
    request = urllib.request.Request(agent_openrouter.BASE + "/chat/completions", data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            content = json.load(response)["choices"][0]["message"]["content"]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        raise StyleCopyError("DeepSeek не відповів. Перевірте ключ OpenRouter і спробуйте ще раз") from None
    content = re.sub(r"//[^\n]*", "", content or "")
    match = re.search(r"\{.*\}", content, re.S)
    try:
        answer = json.loads(match.group(0)) if match else None
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        raise StyleCopyError("DeepSeek повернув не стиль. Спробуйте іншу картинку")
    return answer


def colour(value, fallback: str) -> str:
    return value.lower() if isinstance(value, str) and HEX.fullmatch(value) else fallback


def number(value, lo: float, hi: float, fallback: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        return fallback
    return round(min(hi, max(lo, float(value))), 3)


def label(value, fallback: str, size: int = 40) -> str:
    text = re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""
    return text[:size] or fallback


def style_def(answer: dict) -> dict:
    """A Razgon style (the shape of engine/styles.js) from DeepSeek's answer, with every value checked."""
    pal = answer.get("palette") if isinstance(answer.get("palette"), dict) else {}
    sky = [colour(c, "") for c in pal.get("sky", [])] if isinstance(pal.get("sky"), list) else []
    sky = [c for c in sky if c][:4]
    if len(sky) < 2:
        sky = ["#8fb0d8", "#efe3d2"]
    defaults = {"ambient": "#6f7d96", "key": "#fff3dc", "rim": "#fff1d6", "wall": "#8d8496", "floor": "#5f5866", "dark": "#2f2a36",
                "practical": "#ffe2a8", "grass": "#4f8a55", "road": "#5d5a66", "fog": "#dfe4f0"}
    mood = {"sky": sky, **{k: colour(pal.get(k), defaults[k]) for k in PALETTE}}
    ui_in = answer.get("ui") if isinstance(answer.get("ui"), dict) else {}
    ui_defaults = {"card": "#1b2030", "cardLine": "#5a6480", "text": "#e6e9f0", "sub": "#9aa3b8", "accent": "#ff6f61", "gold": "#ffd47e", "cream": "#fff1dc"}
    grade_in = answer.get("grade") if isinstance(answer.get("grade"), dict) else {}
    m = answer.get("manner") if isinstance(answer.get("manner"), dict) else {}
    manner = {"wobble": number(m.get("wobble"), 0, 4, 0), "boil": number(m.get("boil"), 0, 12, 0), "flat": m.get("flat") is True,
              "glow": m.get("glow") is not False, "lineScale": number(m.get("lineScale"), 0.5, 2.5, 1)}
    if isinstance(m.get("outline"), dict):
        manner["outline"] = {"color": colour(m["outline"].get("color"), colour(answer.get("ink"), "#111111")), "width": number(m["outline"].get("width"), 0.5, 6, 2.5)}
    alpha = number(m.get("fillAlpha"), 0.1, 1, 1)
    if alpha < 1:
        manner["fillAlpha"] = alpha
    if isinstance(m.get("tones"), list):
        tones = [c for c in (colour(t, "") for t in m["tones"]) if c][:6]
        if len(tones) >= 2:
            manner["tones"] = tones
    if isinstance(m.get("shadow"), dict):
        manner["shadow"] = {"x": number(m["shadow"].get("x"), -12, 12, 6), "y": number(m["shadow"].get("y"), -12, 12, 8),
                            "color": colour(m["shadow"].get("color"), "#28160a") + "55"}
    if m.get("grayscale") is True:
        manner["imageFilter"] = "grayscale(1) contrast(1.2)"
    if isinstance(m.get("paper"), dict):
        amount = number(m["paper"].get("amount"), 0, 0.6, 0.3)
        if amount > 0:
            manner["paper"] = {"color": colour(m["paper"].get("color"), "#f4efe4"), "amount": amount}
    plain = manner == {"wobble": 0, "boil": 0, "flat": False, "glow": True, "lineScale": 1}
    grade = {"contrast": number(grade_in.get("contrast"), 0.7, 1.4, 1), "sat": number(grade_in.get("sat"), 0, 1.6, 1),
             "lift": [0, 0, 0], "gamma": [1, 1, 1], "gain": [1, 1, 1], "vignette": number(grade_in.get("vignette"), 0, 1, 0.35),
             "grain": number(grade_in.get("grain"), 0, 0.15, 0.04), "bloom": number(grade_in.get("bloom"), 0, 1, 0.3 if manner["glow"] else 0)}
    if manner.get("imageFilter"):
        grade["sat"] = 0
    ink = colour(answer.get("ink"), "#111111")
    return {"name": label(answer.get("name"), "Copied Style"), "desc": label(answer.get("desc_uk"), "", 200),
            "ink": ink, "inkFar": colour(pal.get("dark"), ink), "feature": colour(answer.get("feature"), "#f4efe6"),
            "rimWidth": number(answer.get("rimWidth"), 0, 6, 0), "ui": {k: colour(ui_in.get(k), ui_defaults[k]) for k in UI},
            "grade": grade, "moods": {name: mood for name in MOODS}, **({} if plain else {"manner": manner})}


def create(cid: str, data: str, note: str = "") -> dict:
    """Ask DeepSeek for the look of a picture and keep it as the channel's own style."""
    styles = load(cid)
    if len(styles) >= MAX_STYLES:
        raise StyleCopyError(f"У каналу вже {MAX_STYLES} своїх стилів. Видаліть зайвий")
    image = picture(data)
    answer = ask(image, note)
    definition = style_def(answer)
    sid = "custom-" + hashlib.sha256((image + json.dumps(definition, sort_keys=True) + str(time.time())).encode()).hexdigest()[:10]
    style = {"id": sid, "name": label(answer.get("name_uk"), definition["name"]), "desc": definition["desc"], "def": definition,
             "created": time.strftime("%Y-%m-%d %H:%M")}
    save_all(cid, styles + [style])
    return style
