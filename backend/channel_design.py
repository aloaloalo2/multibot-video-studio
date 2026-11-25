"""Each channel's own design, made for it on this computer and never shared (user, 25 November 2026: «текстові вставки… для
цього каналу… на іншому комп'ютері ті самі вставки… не мають права існувати… для іншого каналу не може бути, що… напихає
той самий шаблон… зоряні ці штуки, ту саму сітку з такими самими кольорами… щоб канали були аутентичні… шаблонних навіть
стрілочок… або обводки не має бути»).

A channel gets a design kit the first time one of its films needs it: a palette, its own looks of text frames, a pattern
for their backgrounds (grid, dots, crosses, diagonals, rings…), the effects it layers and how its arrows and rings are
drawn, all drawn from a random seed of this computer. The kit stays the channel's from film to film; each film shifts
it a little (hue, opacity, blur, the pattern's step) from its own id, so two films of one channel are related and never
the same. The kit lives in the Studio's data of the channel (`design-kit.json`); a channel moved to another computer
(channel_transfer) does not take it, so it gets a kit of its own there. No model and no request: all by code.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import random
import secrets
from pathlib import Path

import store

KIT_VERSION = 1
ENTRANCES = ["blur_up", "up", "pop", "fade", "letters_fade", "letters_up", "letters_blur"]
PATTERNS = ["grid", "dots", "cross", "diagonal", "rings", "fine-grid"]
# textures that cover the whole frame evenly (montage_ops.BAND_EFFECTS and BANNED_EFFECTS never go on a background)
EFFECTS = ["capcut_e01", "capcut_e02", "capcut_e03", "capcut_e04", "capcut_e05", "capcut_e06", "capcut_e13"]
HEADS = ["open", "filled", "barb"]
RINGS = ["solid", "dashed"]


def _hex(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _rgb(color: str) -> tuple:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _hue(color: str) -> float | None:
    try:
        r, g, b = (c / 255 for c in _rgb(color))
    except (ValueError, IndexError):
        return None
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    return h if s > .12 else None


def path_for(channel_id: str) -> Path:
    return store.DATA_ROOT / "channels" / channel_id / "design-kit.json"


def generate(seed: str, accent: str | None = None) -> dict:
    """A whole kit from a seed; the channel's accent colour, when it has one, leads the palette."""
    rng = random.Random(seed)
    base = _hue(accent) if accent else None
    if base is None:
        base = rng.random()
    second = (base + rng.choice([-1, 1]) * rng.uniform(.12, .45)) % 1.0
    palette = {"base": base, "second": second,
               "accent": accent or _hex(base, rng.uniform(.55, .85), rng.uniform(.8, 1.0)),
               "accent2": _hex(second, rng.uniform(.45, .8), rng.uniform(.75, 1.0)),
               "ink": _hex(base, rng.uniform(0, .08), rng.uniform(.94, 1.0))}
    looks = []
    entrances = rng.sample(ENTRANCES, 4)
    for k in range(rng.randint(4, 6)):
        light = rng.random() < .18
        hue = base if k % 2 == 0 else second
        looks.append({
            "veil": _hex(hue, rng.uniform(.05, .45) if not light else rng.uniform(.02, .12),
                         rng.uniform(.02, .12) if not light else rng.uniform(.88, .96)),
            "veil_opacity": round(rng.uniform(.46, .74), 3), "blur": rng.randint(16, 40),
            "color": _hex(hue, rng.uniform(.0, .25), .08) if light else _hex(hue, rng.uniform(0, .22), rng.uniform(.93, 1.0)),
            "entrance": entrances[k % len(entrances)],
            "zoom": [round(rng.uniform(1.0, 1.12), 3), round(rng.uniform(1.0, 1.12), 3)],
        })
    dim = []
    for k in range(4):
        hue = (base + k * rng.uniform(.06, .2)) % 1.0
        dim.append({
            "veil": _hex(hue, rng.uniform(.1, .4), rng.uniform(.01, .04)), "veil_opacity": round(rng.uniform(.72, .84), 3),
            "blur": rng.randint(30, 44), "color": _hex(hue, rng.uniform(0, .15), rng.uniform(.92, 1.0)),
            "entrance": entrances[k % len(entrances)], "zoom": [round(rng.uniform(1.0, 1.12), 3), round(rng.uniform(1.0, 1.12), 3)],
            "flow": [_hex(hue + d, rng.uniform(.4, .75), rng.uniform(.1, .2)) for d in (0, .08, -.1)] + [_hex(hue, .1, .06)],
            "glow": _hex(hue + rng.uniform(-.05, .05), rng.uniform(.4, .7), rng.uniform(.85, 1.0)),
        })
    pattern = {"kind": rng.choice(PATTERNS), "step": round(rng.uniform(1 / 26, 1 / 13), 4), "major": rng.randint(3, 6),
               "line": _hex(base, rng.uniform(.08, .35), rng.uniform(.18, .3)),
               "line2": _hex(base, rng.uniform(.08, .35), rng.uniform(.3, .45)),
               "field": _hex(base, rng.uniform(.1, .5), rng.uniform(.02, .06)), "vignette": round(rng.uniform(.55, .95), 3),
               "width": rng.choice([1, 1, 2])}
    effects = [{"effect": name, "strength": round(rng.uniform(.15, .38), 2)} for name in rng.sample(EFFECTS, rng.randint(2, 4))]
    accents = {"stroke": rng.randint(6, 12), "head": rng.choice(HEADS), "head_size": round(rng.uniform(2.2, 3.4), 2),
               "bend": round(rng.uniform(.05, .3), 2), "ring": rng.choice(RINGS), "ring_width": rng.randint(5, 10),
               "edge": _hex(base, rng.uniform(.2, .5), rng.uniform(.04, .12)), "edge_width": rng.randint(2, 5)}
    return {"version": KIT_VERSION, "seed": seed, "palette": palette, "text_looks": looks, "dim_looks": dim,
            "pattern": pattern, "effects": effects, "accents": accents}


def kit(channel_id: str, accent: str | None = None) -> dict:
    """The channel's kit, made once on this computer from a fresh random seed."""
    path = path_for(channel_id)
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved.get("version") == KIT_VERSION:
            return saved
    except (OSError, ValueError):
        pass
    made = generate(f"{channel_id}:{secrets.token_hex(16)}", accent)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        store.atomic_json(path, made)
    except OSError:
        pass
    return made


def for_project(project: dict) -> dict:
    channel = project.get("channel_id")
    if not channel:   # a project without a channel (a test, a draft) gets a kit for this moment only, never saved
        return generate(f"none:{project.get('id')}")
    accent = None
    try:
        settings = store.read_channel_settings(store.get_channel_folder(channel, include_disabled=True), {}) or {}
        accent = settings.get("accent_color")
    except Exception:
        pass
    return kit(channel, accent if isinstance(accent, str) and accent.startswith("#") else None)


def _rng(project: dict, *salt) -> random.Random:
    key = "|".join([str(project.get("id") or ""), *map(str, salt)])
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


def _shift(color: str, rng: random.Random, hue: float = .02, value: float = .04) -> str:
    r, g, b = (c / 255 for c in _rgb(color))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return _hex(h + rng.uniform(-hue, hue), s * rng.uniform(.9, 1.1), v + rng.uniform(-value, value))


def text_look(project: dict, number: int, dim: bool = False) -> dict:
    """The look of text frame `number`: the channel's own looks in a film's own order, each a little changed in this film;
    two neighbouring text frames never share one."""
    design = for_project(project)
    looks = design["dim_looks" if dim else "text_looks"]
    order = list(range(len(looks)))
    _rng(project, "order", dim).shuffle(order)
    base = dict(looks[order[number % len(order)]])
    rng = _rng(project, "look", number)
    base["veil"] = _shift(base["veil"], rng, .015, .02)
    base["veil_opacity"] = round(min(.9, max(.35, base["veil_opacity"] + rng.uniform(-.05, .05))), 3)
    base["blur"] = max(10, int(base["blur"] + rng.randint(-4, 4)))
    base["zoom"] = tuple(base["zoom"])
    if base.get("flow"):
        base["flow"] = [_shift(c, rng, .02, .02) for c in base["flow"]]
    return base


def pattern(project: dict) -> dict:
    """The channel's background pattern as this film draws it: the step, the colours and the vignette shift a little."""
    spec = dict(for_project(project)["pattern"])
    rng = _rng(project, "pattern")
    spec["step"] = round(spec["step"] * rng.uniform(.88, 1.12), 5)
    spec["line"], spec["line2"], spec["field"] = (_shift(spec[k], rng, .02, .03) for k in ("line", "line2", "field"))
    spec["vignette"] = round(min(1, max(.4, spec["vignette"] + rng.uniform(-.08, .08))), 3)
    return spec


def accent_style(project: dict) -> dict:
    return dict(for_project(project)["accents"])


def brief(project: dict) -> str:
    """A few lines for the director and the frame agent: this channel's own palette, effects and accent style."""
    design = for_project(project)
    p, a = design["palette"], design["accents"]
    effects = ", ".join(f"{e['effect']} ~{e['strength']}" for e in design["effects"])
    return (f"\nВЛАСНИЙ ДИЗАЙН КАНАЛУ (згенерований лише для нього на цьому комп'ютері, не копіюй оформлення інших каналів і "
            f"загальних прикладів): акцентні кольори {p['accent']} і {p['accent2']}, текст {p['ink']}; фон текстових вставок "
            f"студія малює сама з візерунком каналу ({design['pattern']['kind']}); ефекти тла каналу: {effects} (можна "
            f"поєднувати два, у кожному ролику трохи інакше); стрілки й обведення студія малює стилем каналу "
            f"(наконечник {a['head']}, лінія {a['stroke']} px, обведення {a['ring']}). Від ролика до ролика зберігай цей стиль, "
            f"але варіюй деталі, щоб жодна вставка не була копією.\n")
