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
import style_copy

LOCK = threading.Lock()
SAMPLES = (0.2, 0.5, 0.8)
LEGACY_FONTS = ("Fredoka", "Baloo 2", "Lilita One", "Bangers", "Bebas Neue", "Montserrat", "Permanent Marker", "Nunito", "Playfair Display")
TITLE_FONTS = ('Montserrat', 'Nunito', 'Roboto', 'Open Sans', 'Noto Sans', 'Noto Serif', 'Oswald', 'Roboto Condensed', 'Ubuntu', 'Rubik', 'Manrope', 'Exo 2', 'Comfortaa', 'PT Sans', 'PT Serif', 'Russo One', 'Unbounded')
STYLE_ID = re.compile(r"[a-z0-9_-]{1,40}")
HEX = re.compile(r"#[0-9a-fA-F]{6}")


class StyleLabError(ValueError):
    pass


def films(channel: Path) -> list[tuple[Path, Path]]:
    """(Razgon root, project) of the channel's Razgon films, newest first."""
    found = []
    links = []
    for metadata in store.PROJECTS_ROOT.glob('*/project.json'):
        try:
            project = store.read_json(metadata)
            if not project.get('deleted_at') and project.get('episode_path') and Path(project['episode_path']).resolve().parent == channel.resolve():
                links.append(store.razgon_link(project))
        except (OSError, ValueError, store.StudioError):
            continue
    for link in channel.glob("*/razgon.json"):
        try:
            data = json.loads(link.read_text(encoding="utf-8"))
            links.append(data)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for data in links:
        if not isinstance(data, dict):
            continue
        try:
            root, project = Path(data["razgon_root"]), Path(data["project"])
        except (KeyError, TypeError):
            continue
        if (root / "render.mjs").is_file() and (project / "story" / "shots.json").is_file() and (project / "scenes").is_dir():
            found.append((root, project))
    return sorted(set(found), key=lambda item: (item[1] / "story" / "shots.json").stat().st_mtime, reverse=True)


def presets(root: Path) -> list[dict]:
    """Built-in Razgon styles with their names and descriptions, read from engine/styles.js."""
    text = (root / "engine" / "styles.js").read_text(encoding="utf-8")
    block = text[text.index("export const STYLES"):]
    shared_ui = re.search(r"const UI\s*=\s*\{([^}]*)", text)
    def accent(ui):
        match = re.search(r"\baccent:\s*'(#[a-fA-F0-9]{6})'", ui)
        return match[1] if match else None
    shared = accent(shared_ui[1]) if shared_ui else None
    styles = []
    for m in re.finditer(r"^  (\w+): \{\n\s+name: '([^']*)', desc: '([^']*)'(.*?)^  \}", block, re.M | re.S):
        ui = re.search(r"\bui:\s*\{([^}]*)", m[4])
        color = (accent(ui[1]) if ui else None) or shared
        styles.append({"id": m[1], "name": m[2], "desc": m[3], **({"accent": color} if color else {})})
    return styles


def accent_color(cid: str, animation: dict) -> str | None:
    if animation.get("accent"):
        return animation["accent"]
    sid = animation.get("style")
    if not sid:
        return None
    if sid.startswith(("custom-", "studio-")):
        style = style_copy.find(cid, sid) or {}
        return style.get("def", {}).get("ui", {}).get("accent")
    try:
        styles = presets(store.YOUTUBE_ROOT / store.razgon_rel())
    except (OSError, ValueError):
        return None
    return next((s.get("accent") for s in styles if s["id"] == sid), None)


def validate(animation) -> None:
    if animation is None:
        return
    if not isinstance(animation, dict):
        raise StyleLabError("Невірні налаштування анімації")
    if "style" in animation and not (isinstance(animation["style"], str) and STYLE_ID.fullmatch(animation["style"])):
        raise StyleLabError("Невідомий стиль анімації")
    if "assets" in animation and not isinstance(animation["assets"], bool):
        raise StyleLabError("Невірний перемикач асетів")
    if "allow_stickmen" in animation and not isinstance(animation["allow_stickmen"], bool):
        raise StyleLabError("Невірний перемикач стікменів")
    if "title_font" in animation and animation["title_font"] not in TITLE_FONTS + LEGACY_FONTS:
        raise StyleLabError("Невідомий шрифт заголовків")
    if "accent" in animation and not (isinstance(animation["accent"], str) and HEX.fullmatch(animation["accent"])):
        raise StyleLabError("Колір акценту має бути у форматі #RRGGBB")


# Only styles with volume: gradients, light, glow or texture (user, 1 November 2026: flat styles «не підходять… об'єм не
# видно»). Chalk, Doodle, Ink, Cut-out, «Синє на білому» and «Біле на синьому» left the choice; films already in them
# still render, and a channel that uses one still sees it (cards(keep=…)), so saving its settings never swaps its style.
GALLERY = ("neon", "dusk", "clinic", "blueglow", "care")


def razgon_text(animation: dict | None) -> dict:
    """config.json keys that carry the channel text style into Razgon."""
    animation = animation or {}
    extra = {}
    if animation.get("title_font"):
        extra["fonts"] = {key: animation["title_font"] for key in ("title", "ui", "serif")}
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


def card_scene(root: Path, kind: str = "animated") -> tuple[Path, float]:
    """The scene and moment every style card shows (user, 1 November 2026). An animated channel sees the café of the
    kit's example film at 8 s, its characters in the style; a regular channel, whose Razgon frames explain rather than
    act, sees an infographic with no characters (examples/style-card-info at 2 s: a carrot, a brain and an eye joined by
    glowing arrows, labels and a title). The kit's examples reach every Razgon copy through razgon_sync; the older
    showcase scene (the character by a house) stays only where they are missing."""
    for folder, moment, kinds in (("style-card-info", 2.0, {"regular"}), ("reaction-time", 8.0, {"animated", "regular"})):
        example = root / "examples" / folder
        if kind in kinds and (example / "scenes").is_dir() and (example / "config.json").is_file():
            return example, moment
    return root / "showcase", 2.0


def card_set(root: Path, ids: list[str], stamp: int, font: str, assets: bool, definition: dict | None = None, kind: str = "animated") -> str:
    """Render the style card in every gallery style for one title font and assets choice, unless it is cached. A
    channel's own style (one id with its definition) travels in the config, as it does in a film."""
    scene, moment = card_scene(root, kind)
    template = Path(__file__).with_name("style_card_info.js") if kind == "regular" and scene.name == "style-card-info" else None
    revision = hashlib.sha256(template.read_bytes()).hexdigest() if template else None
    key_parts = ["all-fonts-full-frame-v3", scene.name, moment, font, assets, ids, stamp, definition]
    if revision:
        key_parts.append(revision)
    key = hashlib.sha256(json.dumps(key_parts, sort_keys=True).encode()).hexdigest()[:20]
    cache = card_dir(key)
    if all((cache / f"{sid}-0.jpg").exists() for sid in ids):
        return key
    folder = store.DATA_ROOT / "style-cards-lab" / key
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "build").mkdir(parents=True)
    for name in ("story", "scenes", "timeline") + (("assets",) if assets else ()):
        if (scene / name).exists():
            if template and name == "scenes":
                shutil.copytree(scene / name, folder / name)
                shutil.copyfile(template, folder / "scenes/shots/01_info.js")
            elif not (template and name == "assets"):
                os.symlink(scene / name, folder / name)
    # Style samples always show the full frame, including shots that requested cinematic bars.
    if (folder / 'story').is_symlink():
        (folder / 'story').unlink();shutil.copytree(scene / 'story', folder / 'story')
    shots_path = folder / 'story' / 'shots.json'
    if shots_path.is_file():
        story = json.loads(shots_path.read_text())
        for shot in story.get('shots', []):shot['bars'] = 'none'
        shots_path.write_text(json.dumps(story, ensure_ascii=False))
    if template:
        (folder / "assets").mkdir(exist_ok=True)
        names = []
        if assets:
            for name in ("carrots", "brain", "eye_model"):
                source = root / "library/props" / f"{name}.png"
                if source.is_file():
                    shutil.copyfile(source, folder / "assets" / source.name)
                    names.append(name)
        (folder / "assets/index.json").write_text(json.dumps(names))
    if not assets and not template:
        (folder / "assets").mkdir()
        (folder / "assets" / "index.json").write_text("[]")
    config = json.loads((scene / "config.json").read_text(encoding="utf-8"))
    config["bars"] = "none"
    config["fonts"] = {key: font for key in ("title", "ui", "serif")}
    config["assets"] = assets
    if definition:
        config.update(style=ids[0], styleDef=definition)
    (folder / "config.json").write_text(json.dumps(config, ensure_ascii=False))
    try:
        out = render_stills(root, folder, ids, [moment])
        cache.mkdir(parents=True, exist_ok=True)
        for sid in ids:
            shutil.copyfile(still(out, sid, moment), cache / f"{sid}-0.jpg")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return key


def cards(root: Path, own: list[dict] | None = None, keep=(), kind: str = "animated") -> dict:
    """The style card for every gallery style, title font and assets choice. They do not depend on the channel (its
    logo is laid over in the page), so the whole set is drawn once for the Studio, a few renders at a time, and
    switching a font or the assets in the settings only swaps pictures."""
    scene = card_scene(root, kind)[0]
    if not (scene / "scenes").is_dir():
        raise StyleLabError("Немає сцени-візитки Razgon")
    known = {style["id"]: style for style in presets(root)}
    ids = [sid for sid in GALLERY if sid in known]
    # a retired style a channel still uses gets its own small set, so the shared set (and its cache) stays the same
    kept = [{"id": sid, "def": None} for sid in dict.fromkeys(keep) if sid in known and sid not in ids]
    stamp = newest_mtime(scene / "scenes", scene / "story", scene / "assets", root / "engine")
    own = own or []
    combos = [(font, assets) for font in TITLE_FONTS for assets in (True, False)]
    jobs = [(None, combo) for combo in combos] + [(style, combo) for style in own + kept for combo in combos]
    run = lambda job: card_set(root, [job[0]["id"]] if job[0] else ids, stamp, *job[1], job[0]["def"] if job[0] else None, kind)
    with LOCK:
        with ThreadPoolExecutor(max_workers=3) as pool:
            keys = dict(zip([(job[0]["id"] if job[0] else None, *job[1]) for job in jobs], pool.map(run, jobs)))
    result = {font: {("1" if assets else "0"): {sid: f"/api/{CARDS}/{keys[None, font, assets]}/{sid}-0.jpg" for sid in ids}
                     for assets in (True, False)} for font in TITLE_FONTS}
    for style in own + kept:
        for font in TITLE_FONTS:
            for assets in (True, False):
                result[font]["1" if assets else "0"][style["id"]] = f"/api/{CARDS}/{keys[style['id'], font, assets]}/{style['id']}-0.jpg"
    # the Studio's own styles (style_copy.BUILTIN) lead the gallery and cannot be deleted; a channel's copied ones close it
    listed = lambda s: {"id": s["id"], "name": s["name"], "desc": s["desc"], **({} if s.get("builtin") else {"own": True})}
    return {"styles": [listed(s) for s in own if s.get("builtin")] + [known[sid] for sid in ids] + [known[s["id"]] for s in kept]
                  + [listed(s) for s in own if not s.get("builtin")],
            "cards": result, "keys": set(keys.values())}


def prune_cards(keep: set[str]) -> None:
    """Cards of an older engine or scene, or of a deleted style, are never asked for again."""
    with LOCK:
        for old in (store.DATA_ROOT / CARDS).iterdir() if (store.DATA_ROOT / CARDS).is_dir() else ():
            if old.is_dir() and old.name not in keep:
                shutil.rmtree(old)


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
            channels = store.list_channels()
            own = list({style["id"]: style for channel in channels for style in style_copy.load(channel["id"])}.values())
            saved = [((c.get("settings") or {}).get("animation") or {}).get("style") for c in channels]
            # only the kinds of card the channels need: an infographic for regular channels, characters for animated ones
            kinds = {channel_kind(c) for c in channels} or {"animated"}
            keys = set()
            for kind in sorted(kinds):
                keys |= cards(root, own, keep=[sid for sid in saved if sid], kind=kind).pop("keys")
            prune_cards(keys)
        except (StyleLabError, OSError, subprocess.SubprocessError, store.StudioError):
            pass


def channel_kind(channel: dict) -> str:
    return "animated" if (channel.get("settings") or {}).get("channel_kind") == "animated" else "regular"


def showcase(cid: str, kind: str | None = None) -> dict:
    """The style cards for a channel's settings, with the style its newest film uses now.

    A regular channel has no films of its own, yet its 2D-animation frames are Razgon scenes too: it borrows the
    Razgon studio of any animated channel, and its current style is the one saved in its settings."""
    choices = films(store.get_channel_folder(cid))
    channel = next((item for item in store.list_channels() if item["id"] == cid), {})
    saved = ((channel.get("settings") or {}).get("animation") or {}).get("style")
    if choices:
        root, project = choices[0]
        current = json.loads((project / "config.json").read_text(encoding="utf-8")).get("style")
    else:
        root = razgon_root()
        if root is None:
            raise StyleLabError("Немає сцени-візитки Razgon")
        current = saved
    # the kind the settings page shows now (a switch not saved yet), otherwise the channel's saved one
    kind = kind if kind in {"regular", "animated"} else channel_kind(channel)
    result = cards(root, style_copy.load(cid), keep=[sid for sid in (current, saved) if sid], kind=kind)
    result.pop("keys")
    return {"film_style": current, **result}


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
    own = style_copy.find(cid, only) if only else None
    if own:
        # a channel's own style draws the film the way a new film would: its definition in the config
        styles = [{"id": own["id"], "name": own["name"], "desc": own["desc"]}]
        text = {**text, "style": own["id"], "styleDef": own["def"]}
    elif only:
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
