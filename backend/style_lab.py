"""Style previews for animated channels: real Razgon frames of the channel's latest film in every style.

A lab project in the Studio data links to that film's story, scenes and timeline, so nothing in the film changes. Its
assets folder is either the film's own or empty (the scenes then draw their fallbacks), and its config carries the
channel's text style. render.mjs draws a few stills per style; they are cached by everything that shapes them.
The channel logo is not burnt in: the settings page lays it over each frame with the same rule as everywhere else.
"""
from __future__ import annotations

import hashlib, json, os, re, shutil, subprocess, threading
from pathlib import Path

import store

LOCK = threading.Lock()
SAMPLES = (0.2, 0.5, 0.8)
TITLE_FONTS = ("Fredoka", "Nunito", "Playfair Display")
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


def razgon_text(animation: dict | None) -> dict:
    """config.json keys that carry the channel text style into Razgon."""
    animation = animation or {}
    extra = {}
    if animation.get("title_font"):
        extra["fonts"] = {"title": animation["title_font"]}
    if animation.get("accent"):
        extra["ui"] = {"accent": animation["accent"]}
    return extra


def sample_times(project: Path) -> list[float]:
    story = json.loads((project / "story" / "shots.json").read_text(encoding="utf-8"))
    shots = story.get("shots") or []
    duration = float(story.get("duration") or (shots[-1]["end"] if shots else 0))
    times = []
    for share in SAMPLES:
        at = duration * share
        shot = next((s for s in shots if s["start"] <= at < s["end"]), None)
        times.append(round(shot["start"] + (shot["end"] - shot["start"]) * 0.45 if shot else at, 2))
    return times


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


def previews(cid: str, assets: bool = True, animation: dict | None = None) -> dict:
    """Frames of the channel's newest film in every built-in style; cached until the film, engine or choice changes."""
    channel = store.get_channel_folder(cid)
    choices = films(channel)
    if not choices:
        raise StyleLabError("У каналу ще немає роликів Razgon, з яких можна показати стиль")
    root, project = choices[0]
    styles, times, text = presets(root), sample_times(project), razgon_text(animation)
    identity = [str(project), assets, text, times, newest_mtime(project / "scenes", project / "story", root / "engine"),
                (project / "assets" / "index.json").stat().st_mtime_ns if (project / "assets" / "index.json").exists() else 0]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    cache = store.DATA_ROOT / "channels" / cid / "style-previews" / key
    ids = [style["id"] for style in styles]
    if not all((cache / f"{sid}-{i}.jpg").exists() for sid in ids for i in range(len(times))):
        with LOCK:
            folder = lab(cid, root, project, assets, text)
            result = subprocess.run(["node", "render.mjs", "--project", str(folder), "--styles", ",".join(ids), "--at", ",".join(map(str, times)),
                                     "--format", "jpeg"], cwd=root, capture_output=True, text=True, timeout=600)
            out = folder / "build" / "styles"
            if result.returncode or not out.is_dir():
                raise StyleLabError("Razgon не зміг намалювати кадри стилю: " + (result.stderr or result.stdout)[-300:])
            cache.mkdir(parents=True, exist_ok=True)
            # Keep a few recent variants (with and without assets, text choices) so switching back is instant.
            for old in sorted((d for d in cache.parent.iterdir() if d.is_dir() and d != cache), key=lambda d: d.stat().st_mtime)[:-5]:
                shutil.rmtree(old)
            for sid in ids:
                for i, at in enumerate(times):
                    source = out / f"{sid}_{at}s_{at:.2f}.jpeg"
                    if not source.exists():
                        source = next(out.glob(f"{sid}_*_{at:.2f}.jpeg"), None)
                    if source is None:
                        raise StyleLabError(f"Немає кадру стилю {sid} на {at} с")
                    shutil.copyfile(source, cache / f"{sid}-{i}.jpg")
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
