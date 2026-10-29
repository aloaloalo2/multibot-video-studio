"""Style previews for animated channels: real Razgon frames of the channel's latest film in every style.

A lab project in the Studio data links to that film's story, scenes and timeline, so nothing in the film changes. Its
assets folder is either the film's own or empty (the scenes then draw their fallbacks), and its config carries the
channel's text style. render.mjs draws a few stills per style; they are cached by everything that shapes them.
The channel logo is not burnt in: the settings page lays it over each frame with the same rule as everywhere else.
"""
from __future__ import annotations

import hashlib, json, os, re, shutil, subprocess, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import store

LOCK = threading.Lock()
SAMPLES = (0.2, 0.5, 0.8)
TITLE_FONTS = ("Fredoka", "Baloo 2", "Lilita One", "Bangers", "Bebas Neue", "Montserrat", "Permanent Marker", "Nunito", "Playfair Display")
STYLE_ID = re.compile(r"[a-z0-9_-]{1,40}")
HEX = re.compile(r"#[0-9a-fA-F]{6}")


class StyleLabError(ValueError):
    pass


def films(channel: Path) -> list[tuple[Path, Path]]:
    """(Razgon root, project) of the channel's Razgon films, newest first."""
    found = []
    for link in channel.glob("*/razgon.json"):
        try:
            data = json.loads(link.read_text(encoding="utf-8"))
            root, project = Path(data["razgon_root"]), Path(data["project"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if (root / "render.mjs").is_file() and (project / "story" / "shots.json").is_file() and (project / "scenes").is_dir():
            found.append((root, project))
    return sorted(found, key=lambda item: (item[1] / "story" / "shots.json").stat().st_mtime, reverse=True)


def presets(root: Path) -> list[dict]:
    """Built-in Razgon styles with their names and descriptions, read from engine/styles.js."""
    text = (root / "engine" / "styles.js").read_text(encoding="utf-8")
    block = text[text.index("export const STYLES"):]
    return [{"id": m.group(1), "name": m.group(2), "desc": m.group(3)}
            for m in re.finditer(r"^  (\w+): \{\n\s+name: '([^']*)', desc: '([^']*)'", block, re.M)]


def validate(animation) -> None:
    if animation is None:
        return
    if not isinstance(animation, dict):
        raise StyleLabError("Невірні налаштування анімації")
    if "style" in animation and not (isinstance(animation["style"], str) and STYLE_ID.fullmatch(animation["style"])):
        raise StyleLabError("Невідомий стиль анімації")
    if "assets" in animation and not isinstance(animation["assets"], bool):
        raise StyleLabError("Невірний перемикач асетів")
    if "title_font" in animation and animation["title_font"] not in TITLE_FONTS:
        raise StyleLabError("Невідомий шрифт заголовків")
    if "accent" in animation and not (isinstance(animation["accent"], str) and HEX.fullmatch(animation["accent"])):
        raise StyleLabError("Колір акценту має бути у форматі #RRGGBB")


GALLERY = ("neon", "dusk", "doodle", "ink", "cutout", "chalk")


def razgon_text(animation: dict | None) -> dict:
    """config.json keys that carry the channel text style into Razgon."""
    animation = animation or {}
    extra = {}
    if animation.get("title_font"):
        extra["fonts"] = {"title": animation["title_font"]}
    if animation.get("accent"):
        extra["ui"] = {"accent": animation["accent"]}
    return extra


def render_stills(root: Path, folder: Path, ids: list[str], times: list[float]) -> Path:
    result = subprocess.run(["node", "render.mjs", "--project", str(folder), "--styles", ",".join(ids), "--at", ",".join(map(str, times)), "--format", "jpeg"],
                            cwd=root, capture_output=True, text=True, timeout=600)
    out = folder / "build" / "styles"
    if result.returncode or not out.is_dir():
        raise StyleLabError("Razgon не зміг намалювати кадри стилю: " + (result.stderr or result.stdout)[-300:])
    return out


def still(out: Path, sid: str, at: float) -> Path:
    source = out / f"{sid}_{at}s_{at:.2f}.jpeg"
    if not source.exists():
        source = next(out.glob(f"{sid}_*_{at:.2f}.jpeg"), None)
    if source is None:
        raise StyleLabError(f"Немає кадру стилю {sid} на {at} с")
    return source


def prune(cache: Path, keep: int = 5) -> None:
    for old in sorted((d for d in cache.parent.iterdir() if d.is_dir() and d != cache), key=lambda d: d.stat().st_mtime)[:-keep]:
        shutil.rmtree(old)


CARDS = "style-cards"


def card_dir(key: str) -> Path:
    return store.DATA_ROOT / CARDS / key


def card_set(root: Path, ids: list[str], stamp: int, font: str, assets: bool) -> str:
    """Render the style card in every gallery style for one title font and assets choice, unless it is cached."""
    scene = root / "showcase"
    key = hashlib.sha256(json.dumps(["showcase", font, assets, ids, stamp], sort_keys=True).encode()).hexdigest()[:20]
    cache = card_dir(key)
    if all((cache / f"{sid}-0.jpg").exists() for sid in ids):
        return key
    folder = store.DATA_ROOT / "style-cards-lab" / key
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "build").mkdir(parents=True)
    for name in ("story", "scenes", "timeline") + (("assets",) if assets else ()):
        if (scene / name).exists():
            os.symlink(scene / name, folder / name)
    if not assets:
        (folder / "assets").mkdir()
        (folder / "assets" / "index.json").write_text("[]")
    config = json.loads((scene / "config.json").read_text(encoding="utf-8"))
    config["fonts"] = {"title": font}
    (folder / "config.json").write_text(json.dumps(config, ensure_ascii=False))
    try:
        out = render_stills(root, folder, ids, [2.0])
        cache.mkdir(parents=True, exist_ok=True)
        for sid in ids:
            shutil.copyfile(still(out, sid, 2.0), cache / f"{sid}-0.jpg")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return key


def cards(root: Path) -> dict:
    """The style card for every gallery style, title font and assets choice. They do not depend on the channel (its
    logo is laid over in the page), so the whole set is drawn once for the Studio, a few renders at a time, and
    switching a font or the assets in the settings only swaps pictures."""
    scene = root / "showcase"
    if not (scene / "scenes").is_dir():
        raise StyleLabError("Немає сцени-візитки Razgon")
    known = {style["id"]: style for style in presets(root)}
    ids = [sid for sid in GALLERY if sid in known]
    stamp = newest_mtime(scene / "scenes", scene / "story", scene / "assets", root / "engine")
    combos = [(font, assets) for font in TITLE_FONTS for assets in (True, False)]
    with LOCK:
        with ThreadPoolExecutor(max_workers=3) as pool:
            keys = dict(zip(combos, pool.map(lambda combo: card_set(root, ids, stamp, *combo), combos)))
        # Cards of an older engine or scene are never asked for again.
        for old in (store.DATA_ROOT / CARDS).iterdir():
            if old.is_dir() and old.name not in keys.values():
                shutil.rmtree(old)
    return {"styles": [known[sid] for sid in ids],
            "cards": {font: {("1" if assets else "0"): {sid: f"/api/{CARDS}/{keys[font, assets]}/{sid}-0.jpg" for sid in ids}
                             for assets in (True, False)} for font in TITLE_FONTS}}


def razgon_root() -> Path | None:
    """The Razgon studio of any channel that has an animated film."""
    for channel in store.list_channels():
        try:
            choices = films(store.get_channel_folder(channel["id"]))
        except store.StudioError:
            continue
        if choices:
            return choices[0][0]
    return None


def warm() -> None:
    """Draw any missing style cards in the background when the Studio starts, so settings open with them ready."""
    root = razgon_root()
    if root is not None:
        try:
            cards(root)
        except (StyleLabError, OSError, subprocess.SubprocessError):
            pass


def showcase(cid: str) -> dict:
    """The style cards for a channel's settings, with the style its newest film uses now."""
    choices = films(store.get_channel_folder(cid))
    if not choices:
        raise StyleLabError("Немає сцени-візитки Razgon")
    root, project = choices[0]
    current = json.loads((project / "config.json").read_text(encoding="utf-8")).get("style")
    return {"film_style": current, **cards(root)}


def card_file(key: str, name: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{20}", key) or not re.fullmatch(r"[a-z0-9_-]+-0\.jpg", name):
        raise StyleLabError("Невірний кадр")
    path = card_dir(key) / name
    if not path.is_file():
        raise StyleLabError("Кадр стилю не знайдено")
    return path


HERO = re.compile(r"\bclose\b|\bclose-up\b|\bbig face\b")
DIAGRAM = re.compile(r"blueprint|diagram|chart|graph|\bmap\b|cross-section|x-ray|\bcell\b|molecule")


def shot_score(shot: dict) -> int:
    """Shots that show the character close and in a real place show a style best; schemes and charts show it least."""
    text = (shot.get("scene") or "").lower()
    return 3 * bool(HERO.search(text)) + 2 * bool(re.search(r"\byou\b", text)) - 4 * bool(DIAGRAM.search(text))


def sample_times(project: Path) -> list[float]:
    """Three moments: the best character shots, each from a different set; evenly spaced moments when shots say nothing."""
    story = json.loads((project / "story" / "shots.json").read_text(encoding="utf-8"))
    shots = story.get("shots") or []
    picked, sets = [], set()
    for shot in sorted(shots, key=shot_score, reverse=True):
        if shot_score(shot) <= 0 or shot.get("set") in sets:
            continue
        picked.append(shot); sets.add(shot.get("set"))
        if len(picked) == len(SAMPLES):
            break
    duration = float(story.get("duration") or (shots[-1]["end"] if shots else 0))
    for share in SAMPLES[len(picked):]:
        at = duration * share
        rest = [s for s in shots if s not in picked and shot_score(s) >= 0]
        shot = min(rest, key=lambda s: abs((s["start"] + s["end"]) / 2 - at), default=None)
        picked.append(shot or {"start": at, "end": at})
    return [round(s["start"] + (s["end"] - s["start"]) * 0.45, 2) for s in picked]


def newest_mtime(*folders: Path) -> int:
    return max((f.stat().st_mtime_ns for folder in folders if folder.exists() for f in folder.rglob("*") if f.is_file()), default=0)


def lab(cid: str, root: Path, project: Path, assets: bool, text: dict) -> Path:
    """A project folder that borrows the film's story and scenes but has its own config and assets choice."""
    folder = store.DATA_ROOT / "channels" / cid / "style-lab" / ("assets" if assets else "plain")
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "build").mkdir(parents=True)
    for name in ("story", "timeline", "scenes", "input"):
        if (project / name).exists():
            os.symlink(project / name, folder / name)
    if assets and (project / "assets").is_dir():
        os.symlink(project / "assets", folder / "assets")
    else:
        (folder / "assets").mkdir()
        (folder / "assets" / "index.json").write_text("[]")
    config = json.loads((project / "config.json").read_text(encoding="utf-8"))
    config["overlay"] = None
    config.update(text)
    (folder / "config.json").write_text(json.dumps(config, ensure_ascii=False))
    return folder


def previews(cid: str, assets: bool = True, animation: dict | None = None, only: str | None = None) -> dict:
    """Frames of the channel's newest film in every built-in style; cached until the film, engine or choice changes."""
    channel = store.get_channel_folder(cid)
    choices = films(channel)
    if not choices:
        raise StyleLabError("У каналу ще немає роликів Razgon, з яких можна показати стиль")
    root, project = choices[0]
    styles, times, text = presets(root), sample_times(project), razgon_text(animation)
    if only:
        styles = [style for style in styles if style["id"] == only]
        if not styles:
            raise StyleLabError("Невідомий стиль")
    identity = [str(project), assets, text, times, only, newest_mtime(project / "scenes", project / "story", root / "engine"),
                (project / "assets" / "index.json").stat().st_mtime_ns if (project / "assets" / "index.json").exists() else 0]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    cache = store.DATA_ROOT / "channels" / cid / "style-previews" / key
    ids = [style["id"] for style in styles]
    if not all((cache / f"{sid}-{i}.jpg").exists() for sid in ids for i in range(len(times))):
        with LOCK:
            folder = lab(cid, root, project, assets, text)
            out = render_stills(root, folder, ids, times)
            cache.mkdir(parents=True, exist_ok=True)
            # Keep a few recent variants (styles, with and without assets, text choices) so switching back is instant.
            prune(cache, keep=12)
            for sid in ids:
                for i, at in enumerate(times):
                    shutil.copyfile(still(out, sid, at), cache / f"{sid}-{i}.jpg")
    current = json.loads((project / "config.json").read_text(encoding="utf-8")).get("style")
    return {"film": project.name, "film_style": current, "times": times, "key": key,
            "styles": [{**style, "frames": [f"/api/channels/{cid}/style-previews/{key}/{style['id']}-{i}.jpg" for i in range(len(times))]} for style in styles]}


def preview_file(cid: str, key: str, name: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{20}", key) or not re.fullmatch(r"[a-z0-9_-]+-\d\.jpg", name):
        raise StyleLabError("Невірний кадр")
    path = store.DATA_ROOT / "channels" / cid / "style-previews" / key / name
    if not path.is_file():
        raise StyleLabError("Кадр стилю не знайдено")
    return path
