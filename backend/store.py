"""Persistent, non-destructive local project model for VideoKey Studio."""

from __future__ import annotations

import bisect
import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path

import planner
import number_text
import display_text
import graphics
import joins
import typography
import workspace_paths
import word_blacklist


YOUTUBE_ROOT = workspace_paths.youtube_root()


def razgon_link(project: dict) -> dict | None:
    """Read the authoritative Studio animation link, with legacy episode fallback for migration."""
    episode = Path(project.get("episode_path") or "")
    try:
        kept = project_dir(project["id"]) / "razgon-link.json"
    except (StudioError, KeyError):
        kept = None
    link = read_json(kept, None) if kept is not None else None
    if not isinstance(link, dict) or not link.get("project"):
        link = read_json(episode / "razgon.json", None) if project.get("episode_path") else None
    if isinstance(link, dict) and link.get("project"):
        if kept is not None and read_json(kept, None) != link:
            try:
                atomic_json(kept, link)
            except OSError:
                pass
    else:
        link = read_json(kept, None) if kept is not None else None
        if not isinstance(link, dict) or not link.get("project"):
            link = find_razgon_project(project.get("id"))
            if not link:
                return None
            if kept is not None:
                try:
                    atomic_json(kept, link)
                except OSError:
                    pass
    old, home = str(YOUTUBE_ROOT / "What If" / "razgon-2d-studio"), str(APP_ROOT / "razgon-2d-studio")
    if not Path(link.get("razgon_root") or "").is_dir() and Path(home).is_dir():
        link = {key: home + value[len(old):] if isinstance(value, str) and value.startswith(old) else value for key, value in link.items()}
    return link


_FOUND_RAZGON: dict[str, tuple[float, dict | None]] = {}


def find_razgon_project(pid: str | None) -> dict | None:
    """The Razgon project made for this studio project, found by the studio's id its story/studio_frames.json holds:
    an episode deleted before the studio kept its link still finds its animation."""
    if not pid:
        return None
    seen = _FOUND_RAZGON.get(pid)
    if seen and time.time() - seen[0] < 300:   # the list reads every project often: one search per 5 minutes a project
        return seen[1]
    found = None
    for root in (APP_ROOT / "razgon-2d-studio", YOUTUBE_ROOT / "What If" / "razgon-2d-studio"):
        for frames in root.glob("projects/*/story/studio_frames.json"):
            data = read_json(frames, None)
            if isinstance(data, dict) and data.get("project_id") == pid:
                found = {"razgon_root": str(root), "project": str(frames.parents[1])}
                break
        if found:
            break
    _FOUND_RAZGON[pid] = (time.time(), found)
    return found


def razgon_voice(project: dict, aid: str) -> Path | None:
    """The voice of an animated episode as its Razgon project keeps it (input/…, config.json's voiceover), when the
    asset is that voice: the studio's copy for an episode whose folder is gone."""
    link = razgon_link(project)
    if not link:
        return None
    razgon = Path(link["project"])
    frames = read_json(razgon / "story" / "studio_frames.json", None)
    config = read_json(razgon / "config.json", None)
    if not isinstance(config, dict) or not config.get("voiceover"):
        return None
    voice = razgon / config["voiceover"]
    if not voice.is_file():
        return None
    # the voice by its id (the bridge's record), the plan's voice, or the sound clip that runs the whole film from its
    # start: a copy put on the timeline under another id is the same voice (user, 2 November 2026: «озвучка пропала»)
    if isinstance(frames, dict) and frames.get("voice_asset_id") == aid:
        return voice
    try:
        plan_voice = (((load_project_narration(project["id"]) or {}).get("timing") or {}).get("audio") or {}).get("asset_id")
    except (StudioError, OSError, ValueError, KeyError):
        plan_voice = None
    if plan_voice == aid:
        return voice
    film = float(project.get("duration") or 0) or float((frames or {}).get("duration") or 0)
    for track in project.get("tracks", []):
        for clip in track.get("clips", []):
            if (clip.get("asset_id") == aid and clip.get("kind") == "audio" and float(clip.get("start") or 0) < 0.5
                    and film and float(clip.get("duration") or 0) >= 0.9 * film
                    and (clip.get("title") or "").strip().lower() in {"озвучка", "voiceover", "narration"}):
                return voice
    return None


def razgon_rel() -> str:
    """The Razgon working copy as a path from YOUTUBE, for the agents' briefs: in the studio's folder since 1 November
    2026 (tools/razgon_sync.move_home), in What If before the move."""
    home, old = APP_ROOT / "razgon-2d-studio", YOUTUBE_ROOT / "What If" / "razgon-2d-studio"
    place = old if (old / "render.mjs").is_file() and not (home / "render.mjs").is_file() else home
    return place.relative_to(YOUTUBE_ROOT).as_posix() if YOUTUBE_ROOT in place.parents else str(place)
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("MULTIBOT_STUDIO_DATA", str(APP_ROOT / "backend" / "data"))).expanduser().resolve()
PROJECTS_ROOT = DATA_ROOT / "projects"
DISABLED_PATH = DATA_ROOT / "disabled_channels.json"
GLOBAL_SETTINGS_PATH = DATA_ROOT / "settings.json"
# A channel's video format (its settings, «Формат відео»): the size and frame rate every new episode gets, and the
# quality the export window starts from. The bitrates grow with the picture: 2 Mbit/s suits Full HD, not 4K.
VIDEO_SIZES = {"1280x720": "HD", "1920x1080": "Full HD", "2560x1440": "2K", "3840x2160": "4K"}
VIDEO_FPS = (24, 25, 30, 50, 60)
VIDEO_QUALITIES = ("standard", "high", "max")
# a channel that chose nothing: Full HD at 25 frames a second, standard quality (user, 1 November 2026)
DEFAULT_VIDEO_SIZE, DEFAULT_VIDEO_FPS, DEFAULT_VIDEO_QUALITY = "1920x1080", 25, "standard"
VIDEO_BITRATES = {"1280x720": (1_000_000, 4_000_000, 6_000_000), "1920x1080": (2_000_000, 8_000_000, 12_000_000),
                  "2560x1440": (4_000_000, 14_000_000, 20_000_000), "3840x2160": (8_000_000, 32_000_000, 48_000_000)}


def video_bitrates(width: int, height: int, fps: int) -> tuple[int, int, int]:
    """The export window's three bitrates for this picture: by its size (the nearest of VIDEO_SIZES by pixels), half as
    much again at 50 or 60 frames a second."""
    pixels = width * height
    size = min(VIDEO_SIZES, key=lambda key: abs(int(key.split("x")[0]) * int(key.split("x")[1]) - pixels))
    factor = 1.5 if fps > 30 else 1
    return tuple(int(rate * factor) for rate in VIDEO_BITRATES[size])


GLOBAL_DEFAULTS = {"export_subfolder": "", "word_blacklist": []}
PLAN_CONFIG = "video-plan.json"
MEDIA_EXTENSIONS = {".mp4": "video", ".mov": "video", ".webm": "video", ".mkv": "video", ".m4v": "video", ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image", ".bmp": "image", ".tif": "image", ".tiff": "image", ".wav": "audio", ".aiff": "audio", ".aif": "audio", ".mp3": "audio", ".m4a": "audio", ".aac": "audio", ".flac": "audio", ".ogg": "audio", ".opus": "audio"}
LOCK = threading.RLock()
_DURATION_CACHE = {}
_AUDIO_HASH_CACHE = {}


# Messages of the timeline's checks (here, graphics.py, joins.py) as the author reads them: the studio speaks Ukrainian.
UKRAINIAN = {
    "Invalid typography": "Невірні налаштування шрифту каналу",
    "Invalid source offset": "Невірний початок фрагмента у файлі",
    "Invalid timed text layout": "Невірне розташування слів тексту",
    "Invalid timed text word": "Невірне слово тексту",
    "Timed text words must be ordered": "Слова тексту мають іти по черзі",
    "Timed text words need a positive box": "Слово тексту має мати розмір",
    "Timed text differs from clip text": "Слова не збігаються з текстом кліпу",
    "Invalid frame members": "Невірний склад кадру",
    "Frame title is empty": "Назва кадру порожня",
    "Invalid frame role": "Невідома роль кадру",
    "Frame group not found": "Кадр не знайдено",
    "Invalid mute state": "Невірний стан звуку",
    "Invalid visibility state": "Невірний стан видимості доріжки",
    "This layer has no picture": "На цій доріжці немає зображення",
    "This layer has no sound": "На цьому шарі немає звуку",
    "Stack group not found": "Групу не знайдено",
    "Invalid stack reference": "Невірне посилання на шар",
    "Invalid stack destination": "Невірне місце для шару",
    "Source offset is after the end of the file": "Початок фрагмента пізніше за кінець файлу",
    "Timed words require a text clip": "Слова з часом бувають лише в текстовому кліпі",
    "Invalid text role": "Невідома роль тексту",
    "Text frame is missing from the approved plan": "Текстового кадру немає в плані",
    "A text frame must contain its complete spoken passage": "Текстовий кадр має містити всі свої слова озвучки",
    "A text frame must begin with its first spoken word": "Текстовий кадр має починатися з першого слова озвучки",
    "Invalid batch size": "Забагато або замало дій за раз",
    "Unsupported batch action": "Ця дія не підтримується в пакеті",
    "Waveform requires audio": "Хвиля звуку буває лише в аудіо чи відео",
    "Invalid graphics value": "Невірне значення графіки",
    "Unknown mask": "Невідома маска",
    "Unknown font": "Невідомий шрифт",
    "Invalid text alignment": "Невідоме вирівнювання тексту",
    "Invalid gradient": "Невірний градієнт",
    "Invalid shadow color": "Невірний колір тіні",
    "Invalid shadow": "Невірна тінь",
    "Scene not found": "Кадр не знайдено",
    "Invalid transition endpoint": "Невірний край переходу",
    "A transition requires visual clips": "Перехід можливий лише між картинками чи відео",
    "Transitions can only be dropped onto touching frame edges": "Перехід ставиться лише на стик сусідніх кадрів",
    "Unknown transition": "Невідомий перехід",
    "Transition is longer than an adjacent frame": "Перехід довший за сусідній кадр",
}


class StudioError(Exception):
    def __init__(self, message, status=400):
        message = UKRAINIAN.get(str(message), message)
        if isinstance(message, str) and message.startswith(("Unknown visual effect", "Frame exceeds", "Invalid ")) and message not in UKRAINIAN.values():
            message = "Невірні параметри: " + message   # a rare check without a translation still says it is the input
        super().__init__(message)
        self.status = status


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        tmp.write_text(value, encoding="utf-8")
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            tmp.unlink()


_READ_SNAPSHOT = threading.local()


@contextmanager
def read_snapshot():
    """Request-local reuse for read-only views; changed files get a new stat key."""
    previous = getattr(_READ_SNAPSHOT, 'values', None)
    _READ_SNAPSHOT.values = previous if previous is not None else {}
    try:
        yield
    finally:
        _READ_SNAPSHOT.values = previous


def read_json(path: Path, default=None):
    if not path.exists():
        return copy.deepcopy(default)
    values = getattr(_READ_SNAPSHOT, 'values', None)
    if values is None:
        return json.loads(path.read_text(encoding="utf-8"))
    stamp = path.stat()
    key = (str(path), stamp.st_mtime_ns, stamp.st_size)
    if key not in values:
        values[key] = json.loads(path.read_text(encoding="utf-8"))
    return values[key]


def global_settings() -> dict:
    saved = read_json(GLOBAL_SETTINGS_PATH, {})
    # only today's keys: a size and frame rate saved by an older studio now live in each channel's settings
    values = {key: saved.get(key, value) for key, value in GLOBAL_DEFAULTS.items()} if isinstance(saved, dict) else dict(GLOBAL_DEFAULTS)
    return {**values, 'youtube_root': str(YOUTUBE_ROOT)}


def validated_youtube_root(value) -> Path:
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise StudioError('Укажіть папку YouTube')
    try:
        folder = Path(value.strip()).expanduser()
        if not folder.is_absolute():
            raise StudioError('Укажіть повний шлях до папки YouTube')
        folder = folder.resolve(strict=True)
        if not folder.is_dir():
            raise StudioError('Оберіть папку YouTube')
        if under(folder, APP_ROOT) or under(folder, DATA_ROOT) or has_channel_settings(folder):
            raise StudioError('Оберіть спільну папку з каналами')
        if not os.access(folder, os.R_OK | os.W_OK | os.X_OK):
            raise StudioError('Немає доступу до читання та запису в цю папку')
        next(folder.iterdir(), None)
    except (OSError, RuntimeError, ValueError):
        raise StudioError('Папка недоступна. Перевірте шлях і підключення диска') from None
    return folder


def app_rel() -> str:
    return workspace_paths.app_relative_to(YOUTUBE_ROOT)


def update_global_settings(patch: dict) -> dict:
    global YOUTUBE_ROOT
    if not isinstance(patch, dict) or set(patch) - (set(GLOBAL_DEFAULTS) | {'youtube_root'}):
        raise StudioError("Невідоме загальне налаштування")
    with LOCK:
        settings = {**global_settings(), **patch}
        try:
            settings['word_blacklist']=word_blacklist.normalize(settings['word_blacklist'])
        except ValueError as error:
            raise StudioError(str(error)) from None
        subfolder = settings["export_subfolder"]
        if not isinstance(subfolder, str) or len(subfolder) > 80 or subfolder in {".", ".."} or any(ch in subfolder for ch in "/\\\x00") or subfolder != subfolder.strip():
            raise StudioError("Папка експорту має бути однією назвою без роздільників")
        root = validated_youtube_root(settings['youtube_root']) if 'youtube_root' in patch else YOUTUBE_ROOT
        settings['youtube_root'] = str(root)
        atomic_json(GLOBAL_SETTINGS_PATH, settings)
        YOUTUBE_ROOT = root
    return settings


def under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def channel_id(folder: Path) -> str:
    return hashlib.sha256(str(folder.resolve()).encode()).hexdigest()[:16]


def channel_settings_path(folder: Path) -> Path:
    """Canonical configuration stays with the Studio's other channel data."""
    return DATA_ROOT / "channels" / channel_id(folder) / "settings.json"


def channel_settings_source(folder: Path) -> Path:
    """Read old installations without creating or mirroring files in YouTube."""
    internal = channel_settings_path(folder)
    return internal if internal.exists() else folder / PLAN_CONFIG


def read_channel_settings(folder: Path, default=None):
    return read_json(channel_settings_source(folder), default)


def has_channel_settings(folder: Path) -> bool:
    return channel_settings_source(folder).is_file()


def channel_rules_source(folder: Path) -> Path:
    internal = DATA_ROOT / "channels" / channel_id(folder) / "channel-rules.md"
    return internal if internal.exists() else folder / "AGENTS.md"


def disabled_ids() -> set[str]:
    value = read_json(DISABLED_PATH, [])
    return set(value if isinstance(value, list) else [])


def channel_folders(include_disabled=False) -> list[Path]:
    result = []
    disabled = disabled_ids()
    if not YOUTUBE_ROOT.is_dir():
        return result
    for folder in YOUTUBE_ROOT.iterdir():
        if not folder.is_dir() or not has_channel_settings(folder):
            continue
        if include_disabled or channel_id(folder) not in disabled:
            result.append(folder)
    return sorted(result, key=lambda item: unicodedata.normalize("NFC", item.name).casefold())


def get_channel_folder(cid: str, include_disabled=False) -> Path:
    for folder in channel_folders(include_disabled=include_disabled):
        if channel_id(folder) == cid:
            return folder
    raise StudioError("Канал не знайдено", 404)


DEFAULT_DIRECTOR_MODEL = "claude-opus-5-5"
DIRECTOR_MODELS = {DEFAULT_DIRECTOR_MODEL, "claude-fable-5-2"}


def validate_settings(value: dict) -> dict:
    if not isinstance(value, dict):
        raise StudioError("Налаштування мають бути об'єктом")
    if not isinstance(value.get("claude_effort", "high"), str) or value.get("claude_effort", "high") not in {"low", "medium", "high", "xhigh"}:
        raise StudioError("Невідомий рівень зусиль агента")
    if not isinstance(value.get("director_model", DEFAULT_DIRECTOR_MODEL), str) or value.get("director_model", DEFAULT_DIRECTOR_MODEL) not in DIRECTOR_MODELS:
        raise StudioError("Невідома модель режисера")
    if "sound" in value:
        import sound_settings
        try: value["sound"] = sound_settings.normalize(value["sound"])
        except ValueError as error: raise StudioError(str(error)) from None
    name = value.get("display_name")
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name.strip()) > 80):
        raise StudioError("Назва каналу має містити від 1 до 80 символів")
    if value.get("plan_mode", "director") not in {"director", "direct"}:
        raise StudioError("Невідомий режим створення ролика")
    if value.get("motion_easing", "ease_in_out") not in {"linear", "ease_in", "ease_out", "ease_in_out"}:
        raise StudioError("Невідомий тип руху")
    if value.get("text_look", "varied") not in {"varied", "dim"}:
        raise StudioError("Невідомий вигляд текстових вставок")
    if 'typography' in value:
        if not isinstance(value['typography'],dict):raise StudioError('Invalid typography')
        try:graphics.validate(value['typography'])
        except (ValueError,TypeError) as error:raise StudioError(str(error))
    if not isinstance(value.get("generated_image_style", ""), str) or len(value.get("generated_image_style", "")) > 4000:
        raise StudioError("Побажання до зображень мають містити до 4000 символів")
    if not isinstance(value.get("thumbnail_wishes", ""), str) or len(value.get("thumbnail_wishes", "")) > 4000:
        raise StudioError("Побажання до прев’ю мають містити до 4000 символів")
    if not isinstance(value.get("script_wishes", ""), str) or len(value.get("script_wishes", "")) > 30000:
        raise StudioError("Побажання сценаристу мають містити до 30000 символів")
    for flag in ('auto_narration', 'auto_montage'):
        if type(value.get(flag, False)) is not bool:
            raise StudioError("Автоматичні дії мають бути увімкнені або вимкнені")
    weights = value.get("weights")
    if not isinstance(weights, dict) or not weights:
        raise StudioError("Задайте частки форматів")
    allowed = {"stock_video", "generated_video", "stock_photo", "generated_photo", "animation", "razgon_2d", "text", "host"}
    if set(weights) - allowed:
        raise StudioError("Невідомий формат у частках")
    if any(type(item) not in (int, float) or not math.isfinite(item) or item < 0 for item in weights.values()):
        raise StudioError("Частки не можуть бути від'ємними")
    if abs(sum(weights.values()) - 100) > 0.001:
        raise StudioError("Сума часток має дорівнювати 100%")
    if not isinstance(value.get("first_clip_format", "auto"), str) or value.get("first_clip_format", "auto") not in allowed | {"auto", "video"}:
        raise StudioError("Невідомий формат початку")
    if type(value.get("first_clip_count", 1)) is not int or not 1 <= value.get("first_clip_count", 1) <= 30:
        raise StudioError("Кількість початкових кадрів має бути від 1 до 30")
    for key, lo, hi in (("first_clip_seconds", 0, 60), ("words_per_minute", 1, 1000)):
        if key in value and (type(value[key]) not in (int, float) or not math.isfinite(value[key]) or not lo <= value[key] <= hi):
            raise StudioError("Невірне значення: " + key)
    for key, lo, hi in (("opening_clip_count", 1, 30), ("opening_seconds", 10, 600), ("short_sentence_words", 1, 15), ("max_sentences_per_scene", 1, 10)):
        if key in value:
            try:
                number = float(value[key])
            except (TypeError, ValueError):
                raise StudioError("Невірне значення: " + key) from None
            if not math.isfinite(number) or not lo <= number <= hi:
                raise StudioError("Невірне значення: " + key)
            if key in {"opening_clip_count", "short_sentence_words", "max_sentences_per_scene"} and number != int(number):
                raise StudioError("Потрібне ціле число: " + key)
    if "video_size" in value and value["video_size"] not in VIDEO_SIZES:
        raise StudioError("Невідома роздільність відео")
    if "video_fps" in value and value["video_fps"] not in VIDEO_FPS:
        raise StudioError("Невідома частота кадрів")
    if "video_quality" in value and value["video_quality"] not in VIDEO_QUALITIES:
        raise StudioError("Невідома якість відео")
    if "accents" in value and not isinstance(value["accents"], bool):
        raise StudioError("Невірне значення: accents")
    if "people_style" in value and value["people_style"] not in {"stickman", "real", "real_older"}:
        raise StudioError("Невірне значення: people_style")
    if "opening_clip_types" in value and (not isinstance(value["opening_clip_types"], list) or any(item not in allowed for item in value["opening_clip_types"])):
        raise StudioError("Невірні типи вступних кліпів")
    import channel_branding
    try:
        channel_branding.validate(value)
    except channel_branding.BrandingError as error:
        raise StudioError(str(error)) from None
    return value


def channel_record(folder: Path) -> dict:
    # The name shown in the Studio can differ from the folder: the folder path is the channel's id, so it never moves.
    settings = read_channel_settings(folder, {})
    name = (settings.get("display_name") or "").strip() or folder.name
    icon = DATA_ROOT / "channels" / channel_id(folder) / "icon.png"
    try:
        icon_url = f"/api/channels/{channel_id(folder)}/icon?v={icon.stat().st_mtime_ns}"
    except FileNotFoundError:
        icon_url = None
    import channel_hero
    return {"hero_reference": channel_hero.info(channel_id(folder)), "icon_url": icon_url, "id": channel_id(folder), "name": unicodedata.normalize("NFC", name), "folder_name": unicodedata.normalize("NFC", folder.name),
            "path": str(folder), "settings": settings}


def channel_director_model(project: dict) -> str:
    try:
        settings = read_channel_settings(get_channel_folder(project["channel_id"], include_disabled=True), {})
    except (StudioError, KeyError):
        return DEFAULT_DIRECTOR_MODEL
    value = settings.get("director_model", DEFAULT_DIRECTOR_MODEL)
    return value if isinstance(value, str) and value in DIRECTOR_MODELS else DEFAULT_DIRECTOR_MODEL


def channel_effort(project: dict) -> str:
    try:
        settings = read_channel_settings(get_channel_folder(project["channel_id"], include_disabled=True), {})
    except (StudioError, KeyError):
        return "high"
    value = settings.get("claude_effort", "high")
    return value if isinstance(value, str) and value in {"low", "medium", "high", "xhigh"} else "high"


def list_channels() -> list[dict]:
    channels = [channel_record(folder) for folder in channel_folders()]
    saved = read_json(DATA_ROOT / "channel-order.json", [])
    order = {cid: index for index, cid in enumerate(saved) if isinstance(cid, str)} if isinstance(saved, list) else {}
    return sorted(channels, key=lambda channel: order.get(channel["id"], len(order)))


def reorder_channels(ids) -> list[dict]:
    if not isinstance(ids, list) or not all(isinstance(cid, str) for cid in ids) or len(set(ids)) != len(ids):
        raise StudioError("Передайте список каналів без повторів")
    with LOCK:
        channels = list_channels()
        if set(ids) != {channel["id"] for channel in channels}:
            raise StudioError("Список каналів змінився. Оновіть сторінку та спробуйте ще раз", 409)
        atomic_json(DATA_ROOT / "channel-order.json", ids)
        return list_channels()


def add_channel(folder: Path, copy_from: str | None = None) -> dict:
    folder = folder.expanduser().resolve()
    if folder.parent != YOUTUBE_ROOT.resolve() or not folder.is_dir():
        raise StudioError("Оберіть папку каналу всередині налаштованої папки YouTube")
    config = channel_settings_path(folder)
    with LOCK:
        if (folder / PLAN_CONFIG).exists():
            import technical_files
            technical_files.migrate_channel(folder)
        if not config.exists():
            if copy_from:
                template = read_channel_settings(get_channel_folder(copy_from), None)
            else:
                templates = channel_folders()
                template = read_channel_settings(templates[0], None) if templates else None
            if not template:
                template = {"short_sentence_words": 5, "max_sentences_per_scene": 4, "words_per_minute": 145, "opening_seconds": 90, "opening_clip_count": 6, "opening_clip_types": ["stock_video"] * 6, "weights": {"stock_video": 10, "stock_photo": 45, "generated_photo": 25, "animation": 20}}
            atomic_json(config, template)
        disabled = disabled_ids()
        disabled.discard(channel_id(folder))
        atomic_json(DISABLED_PATH, sorted(disabled))
    return channel_record(folder)


def create_channel(name: str, copy_from: str | None = None) -> dict:
    name = validated_name(name)
    folder = YOUTUBE_ROOT / name
    if folder.exists():
        if not folder.is_dir() or not has_channel_settings(folder):
            raise StudioError("Папка з такою назвою вже існує. Виберіть іншу назву")
        return add_channel(folder, copy_from)
    folder.mkdir(parents=False)
    return add_channel(folder, copy_from)


def disable_channel(cid: str) -> None:
    folder = get_channel_folder(cid)
    with LOCK:
        disabled = disabled_ids()
        disabled.add(channel_id(folder))
        atomic_json(DISABLED_PATH, sorted(disabled))


def update_channel_settings(cid: str, patch: dict) -> dict:
    folder = get_channel_folder(cid)
    current = read_channel_settings(folder, {})
    if not isinstance(patch, dict):
        raise StudioError("Налаштування мають бути об'єктом")
    next_value = copy.deepcopy(current)
    next_value.update(patch)
    if 'sound' in patch:
        import sound_settings
        try: next_value['sound'] = sound_settings.merge(current.get('sound'), patch['sound'])
        except ValueError as error: raise StudioError(str(error)) from None
    if "weights" in patch:
        next_value["weights"] = patch["weights"]
    validate_settings(next_value)
    if "opening_clip_count" in patch:
        existing_types = list(next_value.get("opening_clip_types") or [])
        count = int(next_value["opening_clip_count"])
        next_value["opening_clip_types"] = (existing_types + ["stock_video"] * count)[:count]
    validate_settings(next_value)
    with LOCK:
        import technical_files
        technical_files.migrate_channel(folder)
        atomic_json(channel_settings_path(folder), next_value)
    return channel_record(folder)


def project_dir(pid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{24}", pid):
        raise StudioError("Проєкт не знайдено", 404)
    folder = PROJECTS_ROOT / pid
    if not folder.is_dir():
        raise StudioError("Проєкт не знайдено", 404)
    return folder


def project_path(pid: str) -> Path:
    return project_dir(pid) / "project.json"


def project_created_at(project: dict, folder: Path) -> int:
    value = project.get("created_at")
    if type(value) in (int, float) and math.isfinite(value) and value > 0:
        return round(value * 1000 if value < 1e11 else value)
    stat = folder.stat()
    return round(getattr(stat, "st_birthtime", stat.st_mtime) * 1000)


def load_project(pid: str) -> dict:
    data = read_json(project_path(pid))
    if not isinstance(data, dict):
        raise StudioError("Пошкоджено файл проєкту", 500)
    if data.get("deleted_at"):
        raise StudioError("Проєкт видалено зі списку", 404)
    data["created_at"] = project_created_at(data, project_dir(pid))
    import logo_layer
    return logo_layer.bind(upgrade_legacy_project(data))


def item_layers(project: dict) -> dict:
    if project.get("layer_mode") == "item":
        return project
    previous = copy.deepcopy(project.get("tracks", []))
    tracks = []
    for old in previous:
        for index, clip in enumerate(old.get("clips", [])):
            tracks.append({**old, "id": old["id"] if index == 0 else old["id"] + "-" + clip["id"], "name": clip.get("title") or f"Шар {len(tracks) + 1}", "type": "universal", "z_index": len(tracks), "clips": [clip]})
    if not tracks:
        tracks = [{"id": "layer-1", "name": "Шар 1", "type": "universal", "z_index": 0, "clips": []}]
    project["previous_layer_layout"] = previous
    project["tracks"] = tracks
    project["layer_mode"] = "item"
    return project


def upgrade_legacy_project(project: dict) -> dict:
    if project.get("schema_version") == 2:
        return item_layers(project)
    previous_scenes = copy.deepcopy(project.get("scenes", []))
    previous_tracks = copy.deepcopy(project.get("tracks", []))
    visual = {"id": "legacy-visual", "name": "Відео", "type": "universal", "z_index": 0, "clips": []}
    for scene in previous_scenes:
        kind = scene.get("type", "image")
        clip = {"id": scene.get("id") or uuid.uuid4().hex[:12], "kind": "animation" if kind == "color" else kind, "start": scene.get("start", 0), "duration": scene.get("duration", 5), "trim_start": scene.get("trim_start", 0), "volume": scene.get("volume", 1), "title": scene.get("title", "Кадр"), "asset_id": scene.get("asset_id"), "text": scene.get("text", scene.get("title", "")) if kind == "text" else "", "transition": scene.get("transition", {"type": "cut", "duration": 0}), "x": .5, "y": .5, "width": 1, "height": 1, "scale": 1, "opacity": 1, "keyframes": scene.get("keyframes", []), "content_type": "shape" if kind == "color" else None, "color": scene.get("color", "#101114")}
        visual["clips"].append(clip)
    universal_tracks = [visual]
    for old in previous_tracks:
        clips = []
        for clip in old.get("clips", []):
            kind = "text" if old.get("type") == "text" else "audio"
            clips.append({"id": clip.get("id") or uuid.uuid4().hex[:12], "kind": kind, "start": clip.get("start", 0), "duration": clip.get("duration", 1), "trim_start": clip.get("trim_start", 0), "volume": clip.get("volume", 1), "title": clip.get("text", old.get("name", "Кліп")), "asset_id": clip.get("asset_id"), "text": clip.get("text", ""), "audio_role": old.get("type", "audio"), "transition": {"type": "cut", "duration": 0}, "x": .5, "y": .5, "width": 1, "height": 1, "scale": 1, "opacity": 1, "keyframes": []})
        if clips:
            universal_tracks.append({"id": "legacy-" + str(old.get("id", len(universal_tracks))), "name": old.get("name", "Шар"), "type": "universal", "z_index": len(universal_tracks), "clips": clips})
    project["legacy_backup"] = {"scenes": previous_scenes, "tracks": previous_tracks}
    project["schema_version"] = 2
    project["scenes"] = []
    project["tracks"] = universal_tracks
    recompute_universal_duration(project)
    return item_layers(project)


def save_project(project: dict) -> None:
    if "created_at" not in project:
        project["created_at"] = project_created_at(read_json(project_path(project["id"]), {}), project_dir(project["id"]))
    atomic_json(project_path(project["id"]), project)


def project_bytes(pid: str) -> int:
    """What deleting the project frees: its files in the studio, without hard links that the episode folder still holds,
    and the episode's VideoKey folder, which goes with it."""
    project = read_json(project_path(pid), {}) or {}
    roots = [project_dir(pid)] + ([Path(project["episode_path"]) / EPISODE_STORE] if project.get("episode_path") else [])
    return sum(stat.st_size for root in roots if root.is_dir() for item in root.rglob("*")
               if not item.is_symlink() and item.is_file() and (stat := item.stat()).st_nlink == 1)


def delete_project(pid: str) -> int:
    """Delete the project from the studio's disk: its folder with the montage, imported media, renders, history and
    thumbnail (user, 31 October 2026: «щоб вона видаляла проект з диску саме в студії»). The episode folder in the
    channel stays as it is. Returns the bytes freed."""
    with LOCK:
        project = read_json(project_path(pid), {}) or {}
        freed = project_bytes(pid)
        shutil.rmtree(project_dir(pid))
        # the episode's VideoKey folder holds what the studio brought in for it: it goes with the project, the author's
        # own files in the episode folder stay
        store = Path(project["episode_path"]) / EPISODE_STORE if project.get("episode_path") else None
        if store and store.is_dir():
            shutil.rmtree(store, ignore_errors=True)
    return freed


def restore_hidden_projects() -> list[str]:
    """A project stays in the studio when its episode folder is deleted (user, 1 November 2026: «якщо я видаляю з
    YouTube папку… в студії вона хай залишається… там є код, прев'ю, заголовок»). An earlier version hid such projects
    and marked them `episode_gone_at` to delete them later; this takes every mark off, at each start. Returns their ids."""
    restored = []
    if not PROJECTS_ROOT.is_dir():
        return restored
    for folder in PROJECTS_ROOT.iterdir():
        path = folder / "project.json"
        if not path.is_file():
            continue
        with LOCK:
            project = read_json(path, None)
            if isinstance(project, dict) and project.pop("episode_gone_at", None) is not None:
                save_project(project)
                restored.append(folder.name)
    return restored


def restore_project(pid: str) -> dict:
    with LOCK:
        project = read_json(project_path(pid))
        if not isinstance(project, dict):
            raise StudioError("Пошкоджено файл проєкту", 500)
        if project.pop("deleted_at", None):
            project["revision"] = project.get("revision", 0) + 1
            save_project(project)
        return upgrade_legacy_project(project)


def project_cover_asset(project: dict) -> str | None:
    """Choose montage media without probing files or starting a render."""
    assets = {asset["id"]: asset for asset in project.get("assets", [])}
    scene_ids = {ident for group in project.get("scene_groups", []) if group.get("role", "scene") == "scene" for ident in group.get("clip_ids", [])}
    candidates = [clip for layer in project.get("tracks", []) for clip in layer.get("clips", [])
                  if clip.get("kind") in {"video", "image"} and assets.get(clip.get("asset_id"), {}).get("kind") in {"video", "image"}]
    scene_media = [clip for clip in candidates if clip["id"] in scene_ids]
    if scene_media:
        candidates = scene_media
    if not candidates:
        return None
    return min(candidates, key=lambda clip: float(clip.get("start", 0)))["asset_id"]


def picture_count(project: dict) -> int:
    """Made frames: pictures on the timeline apart from the channel's logo and plate, or for a Razgon episode the frames
    drawn as code that only the export renders (the thumbnail needs a few)."""
    pictures = sum(clip.get("kind") in {"video", "image"} and not re.search("Логотип|Плашка", clip.get("title") or "")
                   for track in project.get("tracks", []) for clip in track.get("clips", []))
    if not razgon_link(project):
        return pictures
    import frame_progress   # it reads the project through this module
    return max(pictures, len(frame_progress.drawn(project["id"])))


def film_clips(project: dict) -> list[dict]:
    """Clips that are frames of the film itself: anything but sound, the channel's logo and plate (groups with the role
    «overlay» and clips titled «Логотип» or «Плашка»). The montage opens with the first of them (frontend editorUnlocked)."""
    overlay = {cid for group in project.get("scene_groups", []) if group.get("role") == "overlay" for cid in group.get("clip_ids", [])}
    return [clip for track in project.get("tracks", []) for clip in track.get("clips", [])
            if clip.get("kind") != "audio" and clip.get("id") not in overlay and not re.search("Логотип|Плашка", clip.get("title") or "")]


def channel_animated(channel: Path) -> bool:
    return (read_channel_settings(channel, {}) or {}).get("channel_kind") == "animated"


def project_plan_mode(project: dict) -> str:
    """A project's own choice, with its saved creation settings for legacy projects."""
    mode = project.get('plan_mode', (project.get('settings') or {}).get('plan_mode', 'director'))
    return 'direct' if mode == 'direct' else 'director'


def project_animated(project: dict) -> bool:
    if project.get('project_kind') in {'regular', 'animated'}:
        return project['project_kind'] == 'animated'
    try:
        return channel_animated(get_channel_folder(project["channel_id"], include_disabled=True))
    except (StudioError, KeyError):
        return False


def made_frames(project: dict, plan: dict | None) -> list[int]:
    """Numbers of the plan's frames that are made. An animated film's frame is made once its scene is written
    (frame_progress.py); another channel's frame once a clip of the film covers its middle, a Razgon code block
    counting only when its scene is written too."""
    frames = (plan or {}).get("frames") or []
    if project_animated(project):
        import frame_progress   # it reads the project through this module
        return sorted(set(frame_progress.drawn(project["id"])))
    # clips sorted by start with the furthest end so far: a frame looks only at the clips that can cover its middle
    # (a film of 500 frames and 3000 clips was 70 ms a project on every read of the list)
    clips = sorted(film_clips(project), key=lambda clip: float(clip["start"]))
    starts = [float(clip["start"]) for clip in clips]
    reach, furthest = [], float("-inf")
    for clip in clips:
        furthest = max(furthest, float(clip["start"]) + float(clip["duration"]))
        reach.append(furthest)
    drawn = None
    made = []
    for index, frame in enumerate(frames):
        middle = (float(frame["start"]) + float(frame["end"])) / 2
        number = int(frame.get("number") or index + 1)
        at = bisect.bisect_right(starts, middle) - 1
        while at >= 0 and reach[at] > middle:
            clip = clips[at]
            at -= 1
            if not middle < float(clip["start"]) + float(clip["duration"]):
                continue
            if clip.get("kind") == "animation" and re.fullmatch(r"Razgon · кадр \d{3}", clip.get("title") or ""):
                if drawn is None:
                    import frame_progress
                    drawn = set(frame_progress.drawn(project["id"]))
                if number not in drawn:
                    continue
            made.append(number)
            break
    return made


def listed_plan(project: dict) -> dict | None:
    """The project's plan for reading only, from the plan cache, without parsing project.json again."""
    path = project_plan_file(project)
    return cached_plan(path, private=False)[0] if path else None


def production_state(project: dict) -> dict | None:
    """The production request as the project list shows it: its state and how many of the asked frames are made."""
    request = project.get("production_request") or {}
    # Listing is read-only. A helper process has no copy of the server's ACTIVE set;
    # it must never turn a live agent into a failed job. Startup/server job checks settle interruptions.
    if not request.get("status"):
        return None
    state = {"status": request["status"], "frames": int(request.get("frames") or 0), "first": int(request.get("first") or 1),
             "limit": bool(request.get("limit")), "paused": bool(request.get("paused"))}
    if request.get('quality'):
        state['quality'] = {'passed': request['quality'].get('passed')}
    if request["status"] in {"requested", "in_progress", "failed"}:
        try:
            plan = listed_plan(project)
        except (StudioError, OSError, ValueError):
            plan = None
        # every made frame of the asked ones, earlier runs too: the card reads «86 з 107» for the whole film (user,
        # 4 November 2026: «краще залишити 107… всі кадри, які зроблені»), not «64 з 85» counted from the first gap
        state["made"] = sum(1 for number in made_frames(project, plan) if 1 <= number <= state["frames"])
    return state


def same_path(a, b) -> bool:
    """Two paths to the same place, whatever Unicode form their Cyrillic letters take (macOS keeps some names in NFD)."""
    norm = lambda p: unicodedata.normalize("NFC", str(Path(p).resolve()))
    return norm(a) == norm(b)


def project_for_episode(cid: str, episode) -> dict | None:
    """The live project of this channel kept in this episode folder. Reads only each project.json, not the list rows
    (covers, progress, plans), so it is cheap enough to run under LOCK."""
    if not PROJECTS_ROOT.is_dir():
        return None
    for folder in PROJECTS_ROOT.iterdir():
        try:
            item = read_json(folder / "project.json")
        except (OSError, ValueError, StudioError):
            continue
        if isinstance(item, dict) and not item.get("deleted_at") and item.get("channel_id") == cid and item.get("episode_path") \
                and same_path(item["episode_path"], episode):
            return item
    return None


_LISTED: dict[str, tuple[tuple, dict]] = {}


def listed_project(path: Path) -> dict:
    """A project.json as the list reads it, parsed and upgraded once per version of the file: the channel page asks for
    the list every few seconds while an agent works, and a long episode's file is megabytes of timeline."""
    stat = path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _LISTED.get(str(path))
    if cached and cached[0] == key:
        return cached[1]
    item = upgrade_legacy_project(read_json(path))
    _LISTED[str(path)] = (key, item)
    return item


def list_projects(cid: str | None = None) -> list[dict]:
    if cid is not None:
        get_channel_folder(cid, include_disabled=True)
    if not PROJECTS_ROOT.is_dir():
        return []
    result = []
    for folder in PROJECTS_ROOT.iterdir():
        path = folder / "project.json"
        if not path.is_file():
            continue
        try:
            item = listed_project(path)
            if not item.get("deleted_at") and (cid is None or item.get("channel_id") == cid):
                cover_asset_id = project_cover_asset(item)
                result.append({"id": item["id"], "name": item["name"], "channel_id": item["channel_id"], "duration": item.get("duration", 0), "revision": item.get("revision", 0), "episode_path": item.get("episode_path"), "status": "draft", "has_plan": bool(item.get("plan_source")), "plan_stage": plan_readiness(item, stage_only=True)["stage"] if item.get("plan_source") else None, "scene_count": sum(len(track.get("clips", [])) for track in item.get("tracks", [])), "pictures": picture_count(item), "created_at": project_created_at(item, folder), "updated_at": round(path.stat().st_mtime * 1000)})
                result[-1]["plan_mode"] = project_plan_mode(item)
                result[-1]["cover_asset_id"] = cover_asset_id
                # the film's length is its voice's, not how far the timeline is filled (a 30-minute film with four frames
                # placed read «00:04» on its card)
                if item.get("plan_source") or result[-1]["plan_mode"] == "direct":
                    try:
                        source = load_project_narration(item["id"]) if result[-1]["plan_mode"] == "direct" else listed_plan(item)
                        audio = ((source or {}).get("timing") or {}).get("audio") or {}
                        if audio.get("duration"):
                            result[-1]["voice_duration"] = float(audio["duration"])
                    except (StudioError, OSError, ValueError, TypeError):
                        pass
                result[-1]["production_request"] = production_state(item)
                # the thumbnail the studio keeps (thumbnail_gen.preview), or one still only in the episode folder
                episode = Path(item.get("episode_path") or "") if item.get("episode_path") else None
                previews = [folder / "preview" / "Превью.png"] + ([episode / name for name in ("Превью.png", "Превью.jpg", "Превью.jpeg")] if episode else [])
                stamps = [path.stat().st_mtime_ns for path in previews if path.is_file()]
                if stamps:
                    result[-1]["preview_mtime"] = max(stamps)
        except (ValueError, KeyError, TypeError, AttributeError, OSError, StudioError):
            continue
    return sorted(result, key=lambda item: (-item["created_at"], item["name"].casefold(), item["id"]))


def validated_name(name: str) -> str:
    if not isinstance(name, str):
        raise StudioError("Укажіть назву проєкту")
    name = name.strip()
    if not 1 <= len(name) <= 100 or name in {".", ".."} or any(ch in name for ch in "/\\\x00"):
        raise StudioError("Невірна назва проєкту")
    return name


def validated_episode_path(channel: Path, raw: str | None, name: str) -> Path:
    path = Path(raw).expanduser().resolve() if raw else (channel / name).resolve()
    if not under(path, channel) or path == channel.resolve():
        raise StudioError("Папка випуску має бути всередині каналу")
    return path


def episode_title(folder: Path) -> str | None:
    """The first A/B title in the episode's «Метаданные.txt»: the video's name on YouTube, if it is written yet."""
    meta = folder / "Метаданные.txt"
    if not meta.is_file():
        return None
    lines = meta.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        if re.match(r"\s*(ТАЙТЛ|ЗАГОЛОВ|HEADLINE|TITLE)", line, re.I):
            return next((item.strip() for item in lines[i + 1:] if item.strip() and not item.startswith("=")), None)
    return None


def follow_title(project: dict) -> bool:
    """A project is called by its video's first title (user, 30 October 2026: «заголовок має відповідати ... тайтлу»).
    A name the author chose stays: only one that is still the episode folder's name follows the title."""
    folder = Path(project.get("episode_path") or "")
    title = episode_title(folder) if project.get("episode_path") and folder.is_dir() else None
    if not title or project.get("name") == title or unicodedata.normalize("NFC", project.get("name") or "") != unicodedata.normalize("NFC", folder.name):
        return False
    try:
        project["name"] = validated_name(title)
    except StudioError:
        return False
    return True


def create_project(cid: str, name: str, episode_path: str | None = None) -> dict:
    channel = get_channel_folder(cid)
    name = validated_name(name)
    episode = validated_episode_path(channel, episode_path, name)
    try:
        name = validated_name(episode_title(episode) or name)      # the video's title names the project when it is written
    except StudioError:
        pass
    pid = uuid.uuid4().hex[:24]
    folder = PROJECTS_ROOT / pid
    # every episode has its folder in the channel from the start: its pictures and videos go there
    episode.mkdir(parents=True, exist_ok=True)
    # the channel's video format, or the studio's defaults for a channel that has none
    plan_config = read_channel_settings(channel, {}) or {}
    size = tuple(int(n) for n in plan_config.get("video_size", DEFAULT_VIDEO_SIZE).split("x"))
    fps = plan_config.get("video_fps", DEFAULT_VIDEO_FPS)
    with LOCK:
        folder.mkdir(parents=True, exist_ok=False)
        project = {"id": pid, "name": name, "channel_id": cid, "channel_name": unicodedata.normalize("NFC", channel.name), "episode_path": str(episode), "created_at": round(time.time() * 1000), "schema_version": 2, "layer_mode": "item", "revision": 0, "width": size[0], "height": size[1], "fps": fps, "duration": 0.0, "scenes": [], "tracks": [{"id": "layer-1", "name": "Шар 1", "type": "universal", "z_index": 0, "clips": []}], "assets": [], "settings": read_channel_settings(channel, {})}
        project["plan_mode"] = "direct" if plan_config.get("plan_mode") == "direct" else "director"
        project["project_kind"] = "animated" if plan_config.get("channel_kind") == "animated" else "regular"
        atomic_json(folder / "project.json", project)
        import language_defaults
        language_defaults.apply(project)
    note_topics(channel)
    return project


def note_topics(channel: Path) -> None:
    """The Studio's internal channel title ledger takes the new title (backend/topics.py); a problem never stops the action."""
    try:
        import topics
        topics.update(channel)
    except (OSError, StudioError, ImportError):
        pass


def import_plan(cid: str, plan_path: str, name: str | None = None) -> dict:
    channel = get_channel_folder(cid)
    path = Path(plan_path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".json" or not under(path, channel):
        raise StudioError("План має бути JSON-файлом у папці каналу")
    return import_plan_data(cid, read_json(path), name or path.parent.name, str(path.parent), str(path))


def validate_plan(plan: dict) -> dict:
    if not isinstance(plan, dict) or not isinstance(plan.get("frames"), list) or not plan["frames"]:
        raise StudioError("У плані немає кадрів")
    for frame in plan["frames"]:
        if not isinstance(frame, dict):
            raise StudioError("У плані є некоректний кадр")
        start, end = float(frame["start"]), float(frame["end"])
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise StudioError("У плані є кадр без тривалості")
        if frame.get("format") not in {"stock_video", "generated_video", "stock_photo", "generated_photo", "animation", "razgon_2d", "text", "host"}:
            raise StudioError("У плані є невідомий формат")
        if not isinstance(frame.get("sentences", []), list):
            raise StudioError("У плані є некоректні речення")
    return copy.deepcopy(plan)


def attach_timed_narration(project: dict, source: dict) -> bool:
    """Put the exact timed source on the montage once; never substitute another recording."""
    timing = source.get("timing") or {}
    audio = timing.get("audio") or {}
    if timing.get("status") != "audio_synced" or not audio.get("sha256"):
        return False
    for track in project.get("tracks", []):
        for clip in track.get("clips", []):
            if clip.get("kind") == "audio":
                try:
                    asset = resolve_asset(project, clip.get("asset_id"))
                    if audio_fingerprint(Path(asset["path"])) == audio["sha256"]:
                        return False
                except (StudioError, OSError):
                    pass
    for asset in discover_assets(project):
        if asset.get("kind") != "audio":
            continue
        path = Path(asset["path"])
        if audio_fingerprint(path) != audio["sha256"]:
            continue
        project.setdefault("tracks", []).append({"id": uuid.uuid4().hex[:12], "name": "Озвучка", "type": "universal",
            "z_index": len(project.get("tracks", [])), "clips": [{"id": uuid.uuid4().hex[:12], "kind": "audio",
            "asset_id": asset["id"], "start": 0, "duration": float(audio["duration"]), "trim_start": 0,
            "volume": 1, "title": "Озвучка"}]})
        return True
    return False


def attach_plan(pid: str, plan: dict) -> dict:
    plan = validate_plan(plan)
    with LOCK:
        project = load_project(pid)
        path = project_dir(pid) / "imported-plan.json"
        if path.is_file():
            versions = project_dir(pid) / "plan-history"
            versions.mkdir(exist_ok=True)
            shutil.copy2(path, versions / (str(time.time_ns()) + ".json"))
        atomic_json(path, plan)
        project["plan_source"] = str(path)
        attach_timed_narration(project, plan)
        project["plan_updated_at"] = time.time()
        project["revision"] = project.get("revision", 0) + 1
        save_project(project)
        return project


_PLAN_CACHE = {}
_SYNCED_PLAN_CACHE = {}


def project_plan_file(project: dict) -> Path | None:
    source = project.get("plan_source")
    if not source:
        return None
    path = Path(source).resolve()
    if path.suffix.lower() != ".json" or not (under(path, project_dir(project["id"])) or under(path, Path(project["episode_path"]))):
        raise StudioError("Файл плану недоступний", 404)
    if not path.is_file():
        raise StudioError("Файл плану не знайдено", 404)
    return path


def plan_file_key(path: Path) -> tuple:
    stat = path.stat()
    return (str(path), stat.st_mtime_ns, stat.st_size)


def cached_plan(path: Path, private: bool = True) -> tuple[dict, tuple]:
    """Parse and upgrade a plan once per file version. Pass private=False only to read without changing it."""
    key = plan_file_key(path)
    entry = _PLAN_CACHE.get(key[0])
    if not entry or entry[0] != key:
        entry = (key, planner.upgrade_legacy_number_format(validate_plan(read_json(path))))
        _PLAN_CACHE[key[0]] = entry
        # many server threads read these caches: walk a copy of the keys and drop entries that may already be gone
        for stale in [item for item in list(_SYNCED_PLAN_CACHE) if item[0][0] == key[0] and item[0] != key]:
            _SYNCED_PLAN_CACHE.pop(stale, None)
    plan = entry[1]
    return (copy.deepcopy(plan) if private else plan), key


def load_project_plan(pid: str) -> dict | None:
    path = project_plan_file(load_project(pid))
    return cached_plan(path)[0] if path else None


def load_project_source(pid: str) -> dict | None:
    """Real narration/transcription metadata, separate from any director's frame plan."""
    load_project(pid)
    source = read_json(project_dir(pid) / "source-timing.json")
    return source if isinstance(source, dict) else None


def load_project_narration(pid: str) -> dict | None:
    """The active workflow's narration; a preserved source cannot override a director-mode plan."""
    project = load_project(pid)
    if project_plan_mode(project) == "direct":
        source = load_project_source(pid)
        if source is not None:
            return source
        try:
            return load_project_plan(pid)
        except (StudioError, OSError, ValueError, TypeError, KeyError):
            # A legacy frame plan is optional in direct montage. A broken old attachment cannot hide source controls.
            return None
    return load_project_plan(pid)


def save_project_source(project: dict, script: str, *, narration=None, timings=None) -> dict:
    """Keep narration and measured phrases without inventing frames or changing the editable montage."""
    if not isinstance(script, str) or not script.strip():
        raise StudioError("Додайте сценарій випуску")
    if narration is not None and timings is not None:
        raise StudioError("Передайте один файл таймінгів")
    script = script.strip()
    source = {"schema_version": 1, "script": script,
              "script_sha256": hashlib.sha256(script.encode()).hexdigest(),
              "timing": {"status": "awaiting_voice"}, "updated_at": time.time()}
    audio = None
    if narration is not None:
        audio = narration_data(Path(project["episode_path"]), narration, project["id"])
        sentences = narration.get("sentences")
    elif timings is not None:
        if not isinstance(timings, dict):
            raise StudioError("Додайте таймінги фраз")
        audio = {"duration": timings.get("duration")}
        if timings.get("audio_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(timings["audio_sha256"])):
                raise StudioError("Некоректний відбиток аудіо у файлі таймінгів")
            audio["sha256"] = timings["audio_sha256"]
        if timings.get("asset_id"):
            asset = resolve_asset(project, timings["asset_id"])
            if asset.get("kind") != "audio":
                raise StudioError("Виберіть аудіофайл озвучки")
            path = Path(asset["path"])
            measured = media_duration(path)
            if not measured or abs(measured - float(audio.get("duration") or 0)) > .002:
                raise StudioError("Тривалість озвучки не відповідає таймінгам")
            digest = audio_fingerprint(path)
            if audio.get("sha256") and audio["sha256"] != digest:
                raise StudioError("Файл озвучки змінився. Додайте нові таймінги фраз")
            audio.update(asset_id=asset["id"], name=asset["name"], sha256=digest)
        sentences = timings.get("sentences")
    if audio is not None:
        try:
            sentences = planner.validate_sentence_timings(script, sentences, audio.get("duration"))
        except (ValueError, TypeError) as error:
            raise StudioError(str(error)) from None
        source["timing"] = {"status": "audio_synced", "audio": audio, "sentences": sentences}
        source["spoken_script"] = script
        source["spoken_script_sha256"] = source["script_sha256"]
    with LOCK:
        current = load_project(project["id"])
        old = load_project_source(project["id"])
        if audio is None and old and old.get("script_sha256") == source["script_sha256"]:
            source = old
        atomic_json(project_dir(project["id"]) / "source-timing.json", source)
        attach_timed_narration(current, source)
        current["voice_script"] = {"text": script, "sha256": source["script_sha256"], "saved_at": time.time()}
        current["revision"] = current.get("revision", 0) + 1
        save_project(current)
    return {"project": current, "plan": None, "source": source,
            "plan_url": f"/channels/{current['channel_id']}/projects/{current['id']}/plan",
            "awaiting_voice": source["timing"]["status"] != "audio_synced", "settings_match": None}


def project_from_plan(cid: str, name: str, episode_path: str, plan: dict) -> dict:
    plan = validate_plan(plan)
    channel = get_channel_folder(cid)
    episode = validated_episode_path(channel, episode_path, validated_name(name))
    with LOCK:
        existing = project_for_episode(cid, episode)
        project = load_project(existing["id"]) if existing else create_project(cid, name, str(episode))
        return attach_plan(project["id"], plan)


def plan_settings_match(pid: str, plan: dict | None) -> bool | None:
    if not plan or not plan.get("settings_signature"):
        return None
    project = load_project(pid)
    channel = get_channel_folder(project["channel_id"], include_disabled=True)
    settings = read_channel_settings(channel, {})
    if project.get("plan_weights") is not None:
        settings["weights"] = project["plan_weights"]
    return plan["settings_signature"] == planner.settings_signature(settings)


def audio_fingerprint(path):
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key not in _AUDIO_HASH_CACHE:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        _AUDIO_HASH_CACHE[key] = digest.hexdigest()
    return _AUDIO_HASH_CACHE[key]


def narration_data(episode, narration, project_id=None):
    if not isinstance(narration, dict) or not isinstance(narration.get("sentences"), list):
        raise StudioError("Додайте озвучку та файл таймінгів фраз")
    if narration.get("audio_path"):
        path = Path(narration["audio_path"]).expanduser().resolve()
        if not under(path, episode) or not path.is_file() or media_kind(path) != "audio":
            raise StudioError("Озвучка має бути аудіофайлом у папці цього випуску")
        asset = asset_record(path, project_id or "pending")
    elif project_id and narration.get("asset_id"):
        asset = resolve_asset(load_project(project_id), narration["asset_id"])
        path = Path(asset["path"])
        if asset.get("kind") != "audio":
            raise StudioError("Виберіть аудіофайл озвучки")
    else:
        raise StudioError("Додайте файл готової озвучки")
    duration = media_duration(path)
    if not duration:
        raise StudioError("Не вдалося визначити тривалість озвучки")
    digest = audio_fingerprint(path)
    if narration.get("audio_sha256") and narration["audio_sha256"] != digest:
        raise StudioError("Файл озвучки змінився. Додайте нові таймінги фраз")
    return {"asset_id": asset["id"], "name": asset["name"], "duration": duration, "sha256": digest}


def plan_readiness(project, plan=None, stage_only=False):
    """Derive readiness from the audio bytes and complete phrase timings, never a label."""
    mode = project_plan_mode(project)
    result = {"plan_mode": mode, "editor_ready": mode == "direct",
              "stage": "draft", "plan_ready": False, "export_ready": False,
              "reason": "Це чернетка. Додайте таймінги фраз із готової озвучки"}
    if mode == "direct":
        film_ids = {clip.get("id") for clip in film_clips(project)}
        visible = [clip for track in project.get("tracks", []) if not track.get("hidden")
                   for clip in track.get("clips", []) if clip.get("id") in film_ids
                   and float(clip.get("opacity", 1)) > 0 and float(clip.get("duration", 0)) > 0]
        ready = bool(visible) and float(project.get("duration") or 0) > 0
        result.update(stage="direct", export_ready=ready,
                      reason="" if ready else "Додайте кадри на таймлайн у вкладці «Монтаж»")
        return result
    try:
        key = None
        if plan is None:
            path = project_plan_file(project)
            plan, key = cached_plan(path, private=False) if path else (None, None)
        if not plan:
            result["reason"] = "Спочатку додайте озвучку на сторінці «План ролика»"
            return result
        if plan.get("timing", {}).get("status") != "audio_synced":
            return result
        audio = plan["timing"].get("audio", {})
        duration = audio.get("duration")
        # Full validation re-derives every number and timing; a plan file that has not changed gives the same answer.
        if key is None:
            planner.validate_synced_plan(plan, duration)
        else:
            missing = object()
            verdict = _SYNCED_PLAN_CACHE.get((key, duration), missing)
            if verdict is missing:
                try:
                    planner.validate_synced_plan(plan, duration)
                    verdict = None
                except ValueError as error:
                    verdict = str(error)
                _SYNCED_PLAN_CACHE[(key, duration)] = verdict
            if verdict is not None:
                raise ValueError(verdict)
        result.update(stage="audio_synced", plan_ready=True, editor_ready=bool(film_clips(project)), reason="Додайте повну озвучку на таймлайн для експорту")
        if stage_only:
            return result
        # a muted layer plays nothing in the export (app.normalize_for_engine): its voice does not count
        clips = [(bool(track.get("muted")), clip) for track in project.get("tracks", []) for clip in track.get("clips", [])]
        full_voice = muted_voice = False
        voice_ids = set()
        for muted, clip in clips:
            # the voice is the timed file itself, or any copy of it with the same bytes: timings attached by a file path
            # name the audio by an id made before the project had it, which no timeline clip carries (GORBUNOV-23)
            same = not audio.get("asset_id") or clip.get("asset_id") == audio["asset_id"]
            if clip.get("kind") != "audio" or not same and not audio.get("sha256"):
                continue
            asset = resolve_asset(project, clip.get("asset_id"))
            path = Path(asset["path"])
            measured = media_duration(path)
            if asset.get("kind") != "audio" or not measured or abs(measured - duration) > .002 or audio.get("sha256") and audio["sha256"] != audio_fingerprint(path):
                if same:
                    result["reason"] = "Озвучка на таймлайні не відповідає файлу таймінгів"
                continue
            if muted:
                muted_voice = True
                continue
            voice_ids.add(clip["id"])
            whole = abs(float(clip.get("start", 0))) < .001 and abs(float(clip.get("trim_start", 0))) < .001 and abs(float(clip.get("duration", 0)) - duration) < .002 and float(clip.get("volume", 1)) > 0
            full_voice = full_voice or whole
        if full_voice and len(voice_ids) > 1:
            # a second copy of the voice (a piece left on another layer) would play twice over the film
            full_voice = False
            result["reason"] = "Озвучка стоїть на таймлайні двічі: приберіть зайву копію"
        if not full_voice and muted_voice:
            result["reason"] = "Шар з озвучкою вимкнено: увімкніть звук озвучки перед експортом"
        if full_voice:
            if abs(float(project.get("duration", 0)) - duration) > max(.002, 1 / max(1, int(project.get("fps", 30)))):
                result["reason"] = "Тривалість монтажу має відповідати готовій озвучці"
            else:
                result.update(export_ready=True, reason="")
    except (StudioError, ValueError, TypeError, KeyError, OSError) as error:
        result["reason"] = str(error) if isinstance(error, (ValueError, StudioError)) else "Перевірте озвучку та таймінги фраз"
    return result


def save_voice_script(pid, text, *, source='author', expected_sha256=None):
    """Persist the author's current editor text, preserving earlier versions locally."""
    if not isinstance(text, str) or not 10 <= len(text.strip()) <= 200000:
        raise StudioError('Введіть сценарій від 10 до 200 000 символів')
    digest = hashlib.sha256(text.encode()).hexdigest()
    with LOCK:
        project = load_project(pid)
        previous = project.get('voice_script') or {}
        previous_text = previous.get('text') or ''
        if expected_sha256 is not None and hashlib.sha256(previous_text.encode()).hexdigest() != expected_sha256:
            raise StudioError('Сценарій уже змінено. Оновіть випуск.', 409)
        if previous_text == text:
            return previous
        if previous_text:
            old_digest = hashlib.sha256(previous_text.encode()).hexdigest()
            atomic_json(project_dir(pid)/'script-history'/f'{time.time_ns()}-{old_digest[:12]}.json', previous)
        record = {'text': text, 'sha256': digest, 'saved_at': time.time(), 'source': source}
        project['voice_script'] = record
        project['revision'] = project.get('revision', 0) + 1
        save_project(project)
        return record


def await_voice(cid: str, name: str, episode: Path, script, project_id=None) -> dict:
    """An episode gets no plan before its voice: the Studio keeps the script and waits.

    Its frames come from the director (Claude Opus 5.5) once the voice is recognised, never from the sentence
    splitter. A draft cut from the script alone moves to the plan history; a plan that follows the voice or the
    director is left alone."""
    if not isinstance(script, str) or not script.strip():
        raise StudioError("Додайте сценарій випуску")
    with LOCK:
        if project_id:
            project = load_project(project_id)
            if project["channel_id"] != cid or Path(project["episode_path"]).resolve() != episode:
                raise StudioError("Проєкт належить іншому випуску")
        else:
            found = project_for_episode(cid, episode)
            project = load_project(found["id"]) if found else create_project(cid, name, str(episode))
        plan = load_project_plan(project["id"])
        if plan and (plan.get("frame_source") or plan.get("timing", {}).get("status") == "audio_synced"):
            raise StudioError("План уже йде за озвучкою або режисурою. Нову озвучку додайте в плані випуску", 409)
        if plan:
            versions = project_dir(project["id"]) / "plan-history"
            versions.mkdir(exist_ok=True)
            for path in (project_plan_file(project), episode / "План видео.json"):
                if path is not None and path.is_file():
                    shutil.move(str(path), versions / (str(time.time_ns()) + "-" + path.name))
            project.pop("plan_source", None)
            project.pop("plan_updated_at", None)
        digest = hashlib.sha256(script.encode()).hexdigest()
        project["voice_script"] = {"text": script, "sha256": digest, "saved_at": time.time()}
        renamed = follow_title(project)
        project["revision"] = project.get("revision", 0) + 1
        save_project(project)
    if renamed:
        note_topics(episode.parent)
    url = f"/channels/{cid}/projects/{project['id']}/plan"
    return {"project": project, "plan": None, "plan_url": url, "awaiting_voice": True, "script_sha256": digest}


def generate_project_plan(cid: str, name: str, episode_path: str, *, script=None, script_path=None, duration=None, hints=None, project_id=None, narration=None, timings=None, weights=None, use_channel_weights=False) -> dict:
    """The only planning entry point. Read saved channel settings at execution time."""
    # an existing episode keeps working when its channel is switched off (a recognition that ends after it); a new one
    # cannot be started there
    channel = get_channel_folder(cid, include_disabled=project_id is not None)
    episode = validated_episode_path(channel, episode_path, validated_name(name))
    if script is not None and script_path is not None:
        raise StudioError("Передайте текст або файл сценарію")
    if script_path is not None:
        path = Path(script_path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".txt" or not under(path, episode):
            raise StudioError("Сценарій має бути TXT-файлом у папці випуску")
        script = path.read_text(encoding="utf-8-sig")
    mode_project = load_project(project_id) if project_id else project_for_episode(cid, episode)
    if (project_plan_mode(mode_project) if mode_project else (read_channel_settings(channel, {}) or {}).get("plan_mode")) == "direct":
        with LOCK:
            existing = load_project(project_id) if project_id else project_for_episode(cid, episode)
            if existing and (existing["channel_id"] != cid or Path(existing["episode_path"]).resolve() != episode):
                raise StudioError("Проєкт належить іншому випуску")
            project = existing or create_project(cid, name, str(episode))
            return save_project_source(project, script, narration=narration, timings=timings)
    # No channel gets a plan split from the script alone: it waits for the voice, and the director makes the frames
    # (user, 31 October 2026: «без озвучки план не може бути згенерований. І план завжди робить клод-код»).
    if narration is None and timings is None:
        return await_voice(cid, validated_name(name), episode, script, project_id)
    with LOCK:
        settings = validate_settings(read_channel_settings(channel, {}))
        if project_id:
            existing_project = load_project(project_id)
        else:
            found = project_for_episode(cid, episode)
            existing_project = load_project(found["id"]) if found else None
        if use_channel_weights:
            weights = None
        elif weights is None and existing_project:
            weights = existing_project.get("plan_weights")
        if weights is not None:
            settings = validate_settings({**settings, "weights": weights})
        if narration is not None and timings is not None:
            raise StudioError("Передайте один файл таймінгів")
        audio = narration_data(episode, narration, existing_project["id"] if existing_project else None) if narration is not None else None
        alignment = narration.get("sentences") if audio else None
        if timings is not None:
            if not isinstance(timings, dict) or not isinstance(timings.get("sentences"), list):
                raise StudioError("У файлі потрібні тривалість озвучки та таймінги всіх фраз")
            audio = {"duration": timings.get("duration")}
            if timings.get("audio_sha256"):
                if not re.fullmatch(r"[0-9a-f]{64}", str(timings["audio_sha256"])):
                    raise StudioError("Некоректний відбиток аудіо у файлі таймінгів")
                audio["sha256"] = timings["audio_sha256"]
            alignment = timings["sentences"]
        build_script = script
        previous_plan = None
        if existing_project:
            previous_plan = load_project_plan(existing_project["id"])
            if previous_plan and previous_plan.get("spoken_script") and script in {
                    number_text.to_digits(previous_plan["spoken_script"]),
                    planner.script_digits(previous_plan["spoken_script"], previous_plan.get("number_fixes"))}:
                build_script = previous_plan["spoken_script"]
        try:
            if audio and alignment is None:
                raise ValueError("Додайте таймінги кожної фрази")
            plan = planner.build_plan(build_script, settings, unicodedata.normalize("NFC", channel.name), audio["duration"] if audio else duration, hints, alignment)
        except (ValueError, TypeError, OverflowError) as exc:
            raise StudioError(str(exc)) from None
        if audio:
            plan["timing"]["audio"] = audio
            plan = planner.digitize_synced_plan(plan)
            # the agent's manual number writing survives a rebuild for every sentence the voice still says
            kept = {key: value for key, value in ((previous_plan or {}).get("number_fixes") or {}).items()
                    if key in set(planner.split_sentences(plan["spoken_script"]))}
            if kept:
                plan = planner.apply_number_fixes(plan, kept)
            planner.validate_synced_plan(plan, audio["duration"])
            # An animated film keeps its director's frames through every rebuild of the plan.
            try:
                plan = planner.keep_director_frames(plan, previous_plan)
            except (ValueError, TypeError, KeyError) as exc:
                raise StudioError("Кадри режисера не вдалося перенести на нову озвучку: " + str(exc)) from None
        plan["settings_scope"] = "project" if weights is not None else "channel"
        plan["channel_id"] = cid
        plan["generated_at"] = time.time()
        if project_id:
            project = load_project(project_id)
            if project["channel_id"] != cid or Path(project["episode_path"]).resolve() != episode:
                raise StudioError("Проєкт належить іншому випуску")
            project = attach_plan(project_id, plan)
        else:
            project = project_from_plan(cid, name, str(episode), plan)
        if weights is not None:
            project["plan_weights"] = copy.deepcopy(weights)
            save_project(project)
        elif use_channel_weights:
            project.pop("plan_weights", None)
            save_project(project)
        url = f"/channels/{cid}/projects/{project['id']}/plan"
        plan["report"].update(project_id=project["id"], plan_url=url)
        output = project_dir(project["id"]) / "imported-plan.json"
        plan["report"]["json"] = str(output)
        if audio:
            spoken_path = episode / "Сценарий для озвучки.txt"
            if spoken_path.exists() and spoken_path.read_text(encoding="utf-8-sig") != plan["spoken_script"]:
                spoken_path = project_dir(project["id"]) / "source-history" / ("Озвученный сценарий " + plan["spoken_script_sha256"][:12] + ".txt")
            atomic_text(spoken_path, plan["spoken_script"])
            formatted_path = episode / "Сценарий.txt"
            if formatted_path.exists() and formatted_path.read_text(encoding="utf-8-sig") not in {script, build_script, plan["script"]}:
                formatted_path = episode / "Сценарий для студии.txt"
            atomic_text(formatted_path, plan["script"])
            plan["spoken_script_file"] = str(spoken_path)
            plan["report"]["formatted_script"] = str(formatted_path)
        atomic_json(output, plan)
        return {"project": project, "plan": plan, "plan_url": url, "settings_match": True}


def number_fixes(pid: str, fixes=None, dry_run: bool = False) -> dict:
    """The sentences whose number writing the formatter changed, and the agent's manual choices for them.

    With `fixes` ({spoken sentence: studio text}) they are checked (only the writing of numbers may differ) and,
    unless dry_run, saved into the plan, its frames and the episode's «Сценарий.txt»."""
    project = load_project(pid)
    plan = load_project_plan(pid)
    if not plan or plan.get("number_format") != "digits_after_whisper":
        raise StudioError("Числа правлять тільки в плані за озвучкою")
    spoken = plan["spoken_script"]
    locale = number_text.detect_locale(spoken)
    current = plan.get("number_fixes") or {}
    rows = []
    for number, sentence in enumerate(planner.split_sentences(spoken), 1):
        auto = number_text.to_digits(sentence, locale)
        if auto != sentence or sentence in current:
            rows.append({"number": number, "spoken": sentence, "auto": auto, "text": current.get(sentence, auto)})
    if fixes is None:
        return {"sentences": rows, "fixes": len(current)}
    if not isinstance(fixes, dict):
        raise StudioError("Передайте fixes: {фраза озвучки: текст студії}")
    try:
        updated = planner.apply_number_fixes(plan, {**current, **fixes})
        planner.validate_synced_plan(updated, float(updated["timing"]["audio"]["duration"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise StudioError(str(exc)) from None
    changed = sum(1 for a, b in zip(plan["timing"]["sentences"], updated["timing"]["sentences"]) if a.get("text") != b.get("text"))
    result = {"ok": True, "changed": changed, "fixes": len(updated.get("number_fixes") or {})}
    if dry_run:
        return result
    attach_plan(pid, updated)
    episode = Path(project.get("episode_path") or "")
    formatted = episode / "Сценарий.txt"
    if episode.is_dir() and (not formatted.exists() or formatted.read_text(encoding="utf-8-sig") == plan["script"]):
        atomic_text(formatted, updated["script"])
        result["script_file"] = str(formatted)
    return result


def import_plan_data(cid: str, plan: dict, name: str, episode_path: str | None = None, source_path: str | None = None) -> dict:
    plan = validate_plan(plan)
    # A draft is only an attachment. It must never materialize a video timeline.
    if plan.get("timing", {}).get("status") != "audio_synced":
        return project_from_plan(cid, name, episode_path or str(get_channel_folder(cid) / validated_name(name)), plan)
    frames = plan.get("frames") if isinstance(plan, dict) else None
    if not isinstance(frames, list) or not frames:
        raise StudioError("У плані немає кадрів")
    scenes = []
    for frame in frames:
        if not isinstance(frame, dict):
            raise StudioError("У плані є некоректний кадр")
        start = float(frame["start"])
        end = float(frame["end"])
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise StudioError("У плані є кадр без тривалості")
        fmt = str(frame.get("format", "generated_photo"))
        kind = "video" if fmt.endswith("video") else "image" if fmt.endswith("photo") else "text" if fmt == "text" else "color"
        sentences = frame.get("sentences", [])
        if not isinstance(sentences, list):
            raise StudioError("У плані є некоректні речення")
        text = " ".join(str(item) for item in sentences)
        scenes.append({"id": uuid.uuid4().hex[:12], "start": start, "duration": end - start, "trim_start": 0.0, "title": text[:120] or "Кадр", "type": kind, "format": fmt, "asset_id": None, "transition": {"type": "cut", "duration": 0.0}, "volume": 1.0, "layers": []})
    project = create_project(cid, name, episode_path)
    ready = plan_readiness(project, plan)
    if not ready["plan_ready"]:
        raise StudioError(ready["reason"])
    project["tracks"][0]["clips"] = [{"id": scene["id"], "kind": "animation" if scene["format"] == "animation" else scene["type"] if scene["type"] != "color" else "animation", "start": scene["start"], "duration": scene["duration"], "trim_start": 0, "volume": 1, "title": scene["title"], "asset_id": None, "text": scene["title"] if scene["type"] == "text" else "", "content_type": "shape" if scene["type"] == "color" else None, "color": "#101114", "transition": {"type": "cut", "duration": 0}, "x": .5, "y": .5, "width": 1, "height": 1, "scale": 1, "opacity": 1, "keyframes": []} for scene in scenes]
    project.pop("layer_mode", None)
    item_layers(project)
    audio = plan["timing"]["audio"]
    if audio.get("asset_id"):
        project["tracks"].append({"id": "narration", "name": "Озвучка", "type": "universal", "z_index": len(project["tracks"]), "clips": [{"id": uuid.uuid4().hex[:12], "kind": "audio", "asset_id": audio["asset_id"], "start": 0, "duration": audio["duration"], "trim_start": 0, "volume": 1, "title": audio["name"]}]})
    recompute_universal_duration(project)
    imported_path = project_dir(project["id"]) / "imported-plan.json"
    atomic_json(imported_path, plan)
    project["plan_source"] = str(imported_path)
    if source_path:
        project["plan_original_source"] = source_path
    save_project(project)
    return project


def media_kind(path: Path) -> str | None:
    return MEDIA_EXTENSIONS.get(path.suffix.lower())


def media_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        stat = path.stat()
        key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        if key in _DURATION_CACHE:
            return _DURATION_CACHE[key]
        result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, timeout=8)
        duration = float(result.stdout.strip()) if result.returncode == 0 else 0
        value = round(duration, 3) if math.isfinite(duration) and duration > 0 else None
        _DURATION_CACHE[key] = value
        return value
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


# Studio-managed imports and generated assets stay in the application's project data.
# Old episode-local stores remain readable until explicitly relocated.
EPISODE_STORE = "VideoKey"


def media_dir(project: dict) -> Path:
    """Persistent imported/generated media, separate from disposable rendering caches."""
    return project_dir(project["id"]) / "media"


def cache_dir(project: dict) -> Path:
    """The studio's cache of an episode: export chunks, stills, stock sheets, frame renders, the render cache."""
    return project_dir(project["id"])


def media_roots(project: dict) -> list[Path]:
    """Internal media plus the legacy episode folder for compatibility."""
    roots=[media_dir(project)]
    if project.get("episode_path"):
        roots.append(Path(project["episode_path"]) / EPISODE_STORE / "Матеріали")
    return list(dict.fromkeys(roots))


def relocate_media(pid: str, expected_revision: int | None = None) -> dict:
    """Move tracked legacy imports into Studio while retaining asset ids and a rollback journal."""
    with LOCK:
        project=load_project(pid)
        if expected_revision is not None and project["revision"]!=expected_revision:
            raise StudioError("Проєкт змінився. Оновіть його перед перенесенням матеріалів.",409)
        legacy=Path(project.get("episode_path") or "")/EPISODE_STORE/"Матеріали"
        if not project.get("episode_path") or not legacy.is_dir():return {"project":project,"moved":0}
        target=media_dir(project);target.mkdir(parents=True,exist_ok=True)
        journal_dir=project_dir(pid)/"migrations"/str(time.time_ns());journal_dir.mkdir(parents=True)
        atomic_json(journal_dir/"project-before.json",project)
        moves={}
        try:
            for asset in project.get("assets",[]):
                source=Path(asset.get("path") or "").resolve()
                if str(source) in moves:
                    asset["path"]=moves[str(source)];continue
                if not source.is_file() or not under(source,legacy):continue
                if str(source) not in moves:
                    dest=claim_media_name(target,source.name)
                    shutil.move(str(source),str(dest));moves[str(source)]=str(dest.resolve())
                asset["path"]=moves[str(source)]
            atomic_json(journal_dir/"paths.json",moves)
            if moves:
                if read_json(project_path(pid),{}).get("revision")!=project["revision"]:
                    raise StudioError("Проєкт змінився під час перенесення. Матеріали повернуто на попереднє місце.",409)
                project["revision"]+=1;save_project(project)
                _DISCOVERED.pop(pid,None)
        except Exception:
            for source,dest in reversed(list(moves.items())):
                Path(source).parent.mkdir(parents=True,exist_ok=True)
                shutil.move(dest,source)
            raise
        # Remove only empty managed folders. Untracked files and the episode itself are preserved.
        for folder in [*sorted((x for x in legacy.rglob('*') if x.is_dir()),key=lambda x:len(x.parts),reverse=True),legacy,legacy.parent]:
            try:folder.rmdir()
            except OSError:pass
        return {"project":project,"moved":len(moves),"journal":str(journal_dir)}


def asset_record(path: Path, project_id: str, source="local") -> dict:
    resolved = path.resolve()
    asset = {"id": hashlib.sha256(str(resolved).encode()).hexdigest()[:20], "name": path.name, "kind": media_kind(path), "path": str(resolved), "source": source, "url": f"/api/projects/{project_id}/assets/{hashlib.sha256(str(resolved).encode()).hexdigest()[:20]}/file"}
    if asset["kind"] == "audio":
        duration = media_duration(resolved)
        if duration:
            asset["duration"] = duration
    return asset


def discover_assets(project: dict, limit=500) -> list[dict]:
    episode = Path(project["episode_path"])
    own = media_roots(project)
    existing = {asset["id"]: asset for asset in project.get("assets", []) if isinstance(asset, dict) and "id" in asset}
    known_paths={Path(asset["path"]).resolve() for asset in existing.values() if asset.get("path")}
    # A file imported from the episode folder exists twice, as the Studio copy and as the original; the library shows
    # the copy only, unless the timeline uses the original itself. An import may add -xxxxxxxx to the name on a clash.
    used = {clip.get("asset_id") for track in project.get("tracks", []) for clip in track.get("clips", [])}
    copies = set()
    for asset in existing.values():
        path = Path(asset.get("path", ""))
        if any(under(path, root) for root in own) and path.is_file():
            copies.add((re.sub(r"-[0-9a-f]{8}$", "", path.stem), path.suffix.lower(), path.stat().st_size))
    roots = [episode, *own]
    for root in roots:
        if not root.is_dir():
            continue
        for current, dirs, files in os.walk(root):
            rel_depth = len(Path(current).relative_to(root).parts)
            if rel_depth >= 3:
                dirs[:] = []
            else:
                dirs[:] = [item for item in dirs if not item.startswith(".") and item not in {"node_modules", "ТЕХНИЧЕСКИЕ ФАЙЛЫ", "Архив", EPISODE_STORE}]
            for name in files:
                if len(existing) >= limit:
                    break
                path = Path(current) / name
                if path.is_file() and media_kind(path) and under(path, root):
                    if path.resolve() in known_paths:continue
                    asset = asset_record(path, project["id"], "project" if root in own else "episode")
                    if root == episode and asset["id"] not in used and (path.stem, path.suffix.lower(), path.stat().st_size) in copies:
                        continue
                    existing.setdefault(asset["id"], asset)
    for asset in existing.values():
        if asset.get('kind') in {'image','video'}:
            path=Path(asset['path'])
            if path.is_file():asset['thumbnail_url']=f"/api/projects/{project['id']}/assets/{asset['id']}/thumbnail?v={path.stat().st_mtime_ns}"
    return list(existing.values())


_DISCOVERED: dict[str, tuple[float, int, list[dict]]] = {}


def discovered(project: dict) -> list[dict]:
    """discover_assets for a burst of file requests: the library asks for a thumbnail of every card at once, and each
    used to walk the whole episode folder again. A walk is reused for 5 seconds while the project stays the same."""
    now = time.monotonic()
    hit = _DISCOVERED.get(project["id"])
    version=(project.get('revision',0),project.get('branding_version'))
    if hit and now - hit[0] < 5 and hit[1] == version:
        return hit[2]
    found = discover_assets(project)
    _DISCOVERED[project["id"]] = (now, version, found)
    return found


def asset_available(project: dict, asset: dict) -> bool:
    """A file the library can show: on disk, or played from a copy the studio keeps (a sound of an episode whose folder
    is gone). Records whose file went with a deleted episode folder stay in the project for undo, not in the library
    (user, 2 November 2026: «в медіатеці… це не файли, це просто пустишки»)."""
    if Path(asset.get("path") or "").is_file():
        return True
    try:
        return Path(resolve_asset(project, asset["id"])["path"]).is_file()
    except (StudioError, OSError, KeyError):
        return False


def resolve_asset(project: dict, aid: str) -> dict:
    for asset in project.get('assets',[]):
        if asset.get('id')==aid:
            path=Path(asset['path']).resolve()
            if (asset.get('source')=='channel-logo' and path.is_file()
                    and under(path,DATA_ROOT/'channels'/project['channel_id']/'overlays')):
                return asset
            if path.is_file() and (under(path,Path(project['episode_path'])) or any(under(path, root) for root in media_roots(project))):return asset
            # the episode folder is gone: its sound plays from the studio's kept copy (backend/keep.py)
            kept = PROJECTS_ROOT / project['id'] / 'kept' / f"{aid}.m4a"
            if not path.is_file() and kept.is_file():
                return {**asset, 'path': str(kept), 'kept': True}
            voice = razgon_voice(project, aid) if not path.is_file() else None
            if voice:
                return {**asset, 'path': str(voice), 'kept': True}
            # The linked animation keeps its full-frame branding PNG even when the imported copy was cleaned.
            if not path.is_file() and asset.get('kind') == 'image':
                overlay_ids = {cid for group in project.get('scene_groups', []) if group.get('role') == 'overlay' for cid in group.get('clip_ids', [])}
                is_overlay = any(clip.get('asset_id') == aid and (clip.get('id') in overlay_ids or clip.get('title') in ('Плашка каналу', 'Логотип'))
                                 for track in project.get('tracks', []) for clip in track.get('clips', []))
                link = razgon_link(project) if is_overlay else None
                if link:
                    root = Path(link['project']).resolve()
                    config = read_json(root / 'config.json', {}) or {}
                    overlay = (root / config.get('overlay', '')).resolve()
                    if under(overlay, root) and overlay.is_file():
                        return {**asset, 'path': str(overlay), 'kept': True}
            # Razgon's music and effects bed, as its project keeps it after a render
            # (user, 2 November 2026: «в деяких проектах не находить доріжку музика й ефекти»): the studio's copy may be gone
            # with a cleanup, so the project's own bed is taken, else its music alone (the build keeps music.wav, the mix
            # is made from it); the export renders the whole mix anew either way
            link = razgon_link(project) if not path.is_file() and path.name.startswith('music_sfx') else None
            for bed in ([Path(link['project']) / 'build' / 'studio' / 'music_sfx.wav', Path(link['project']) / 'build' / 'music.wav']
                        if link else []):
                if bed.is_file():
                    return {**asset, 'path': str(bed), 'kept': True}
    # a file new in the folder since the last walk is looked for once more with a fresh one
    found = next((a for a in discovered(project) if a["id"] == aid), None)
    if found is None:
        _DISCOVERED.pop(project["id"], None)
    for asset in ([found] if found else discovered(project)):
        if asset["id"] == aid:
            path = Path(asset["path"]).resolve()
            if not path.is_file() or not (under(path, Path(project["episode_path"])) or any(under(path, root) for root in media_roots(project))):
                break
            return asset
    raise StudioError("Матеріал не знайдено", 404)


def clone_or_copy(source: Path, target: Path) -> None:
    """On APFS a clone shares the blocks of the source until either file changes, so an imported render takes no
    extra space and a later re-render of the source cannot alter the Studio's copy. Other disks get a plain copy."""
    if sys.platform == "darwin":
        try:
            import ctypes
            libc = ctypes.CDLL("/usr/lib/libSystem.dylib", use_errno=True)
            if libc.clonefile(os.fsencode(source), os.fsencode(target), 0) == 0:
                return
        except (OSError, AttributeError):
            pass
    with source.open("rb") as stream, target.open("wb") as copy:
        shutil.copyfileobj(stream, copy, length=1024 * 1024)


def claim_media_name(media_dir: Path, base: str) -> Path:
    """A file name in the project's media that no other import takes at the same moment: the name is created empty
    and exclusively, so two imports of «voice.wav» at once get two files instead of one overwriting the other."""
    for name in (base, Path(base).stem[:70] + "-" + uuid.uuid4().hex[:8] + Path(base).suffix.lower()):
        try:
            with open(media_dir / name, "x"):
                return media_dir / name
        except FileExistsError:
            continue
    raise StudioError("Не вдалося вибрати назву для медіафайлу")


def import_asset_file(project: dict, source: Path, source_name="local") -> dict:
    source = source.expanduser().resolve()
    if not source.is_file() or not media_kind(source):
        raise StudioError("Підтримуються тільки фото, відео й аудіо")
    if source.stat().st_size > 10 * 1024 ** 3:
        raise StudioError("Файл завеликий для імпорту")
    # Imports stay inside Studio, including generated sound and frame renders.
    folder = project_dir(project["id"]) / "media" if RAZGON_RENDER.fullmatch(source.name) else media_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"[^\w. -]", "_", source.name).strip(". ") or "asset"
    dest = claim_media_name(folder, base)
    tmp = folder / (".import-" + uuid.uuid4().hex)
    try:
        clone_or_copy(source, tmp)
        os.replace(str(tmp), str(dest))
    finally:
        if tmp.exists():
            tmp.unlink()
    asset = asset_record(dest, project["id"], source_name)
    with LOCK:
        latest = load_project(project["id"])
        latest.setdefault("assets", []).append(asset)
        latest["revision"] += 1
        save_project(latest)
    return asset


def import_asset_stream(project: dict, stream, size: int, filename: str) -> dict:
    if not isinstance(filename, str) or not 1 <= len(filename) <= 200 or any(char in filename for char in "/\\\x00"):
        raise StudioError("Невірна назва медіафайлу")
    if not 0 < size <= 10 * 1024 ** 3 or not media_kind(Path(filename)):
        raise StudioError("Підтримуються тільки фото, відео й аудіо до 10 ГБ")
    folder = project_dir(project["id"]) / "media" if RAZGON_RENDER.fullmatch(filename) else media_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"[^\w. -]", "_", filename).strip(". ") or "asset"
    destination = claim_media_name(folder, base)
    temporary = folder / (".upload-" + uuid.uuid4().hex)
    try:
        remaining = size
        with temporary.open("wb") as target:
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise StudioError("Завантаження перервано")
                target.write(chunk)
                remaining -= len(chunk)
        os.replace(str(temporary), str(destination))
    finally:
        if temporary.exists():
            temporary.unlink()
    asset = asset_record(destination, project["id"], "upload")
    with LOCK:
        latest = load_project(project["id"])
        latest.setdefault("assets", []).append(asset)
        latest["revision"] += 1
        save_project(latest)
    return asset


def recompute_timeline(project: dict) -> None:
    t = 0.0
    for scene in project["scenes"]:
        scene["start"] = round(t, 3)
        t += float(scene["duration"])
    project["duration"] = round(t, 3)


def keep_overlays_on_top(project: dict) -> None:
    """The channel's logo and plate (layers whose clips all belong to scene groups with the role «overlay») stay the top
    layers, so a layer added after them never lands over them: the higher a layer, the higher its row and its place in
    the picture (user, 30 October 2026)."""
    overlay = {cid for group in project.get("scene_groups") or [] if group.get("role") == "overlay" for cid in group.get("clip_ids", [])}
    tracks = project.get("tracks", [])
    top = [layer.get("id") for layer in tracks if layer.get("clips") and all(clip.get("id") in overlay for clip in layer["clips"])]
    if top and [layer.get("id") for layer in tracks[-len(top):]] != top:
        project["tracks"] = [layer for layer in tracks if layer.get("id") not in top] + [layer for layer in tracks if layer.get("id") in top]


def recompute_universal_duration(project: dict) -> None:
    project["duration"] = round(max((float(clip.get("start", 0)) + float(clip.get("duration", 0)) for layer in project.get("tracks", []) for clip in layer.get("clips", [])), default=0), 3)
    keep_overlays_on_top(project)
    for index, layer in enumerate(project.get("tracks", [])):
        layer["z_index"] = index


def layer_by_id(project: dict, layer_id: str) -> dict:
    for layer in project.get("tracks", []):
        if layer.get("id") == layer_id and layer.get("type") == "universal":
            return layer
    raise StudioError("Шар не знайдено", 404)


def clip_by_id(project: dict, clip_id: str) -> tuple[dict, dict]:
    for layer in project.get("tracks", []):
        for clip in layer.get("clips", []):
            if clip.get("id") == clip_id:
                return layer, clip
    raise StudioError("Кліп не знайдено", 404)


def finite_float(value, minimum=None, maximum=None, message="Невірне число") -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise StudioError(message) from None
    if not math.isfinite(result) or minimum is not None and result < minimum or maximum is not None and result > maximum:
        raise StudioError(message)
    return result


def validated_keyframes(value, duration: float) -> list[dict]:
    if not isinstance(value, list) or len(value) > 200:
        raise StudioError("Невірні ключові кадри")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise StudioError("Невірний ключовий кадр")
        point = {"time": finite_float(item.get("time"), 0, duration, "Невірний час ключового кадру")}
        for key in ("x", "y"):
            if key in item:
                point[key] = finite_float(item[key], -2, 2, "Невірна позиція ключового кадру")
        if "scale" in item:
            point["scale"] = finite_float(item["scale"], .05, 8, "Невірний масштаб ключового кадру")
        if "opacity" in item:
            point["opacity"] = finite_float(item["opacity"], 0, 1, "Невірна прозорість ключового кадру")
        result.append(point)
    return sorted(result, key=lambda item: item["time"])


def validated_text_layout(value, text, duration):
    if not isinstance(value, list) or len(value) > 200:
        raise StudioError("Invalid timed text layout")
    result = []
    previous = -1
    for word in value:
        if not isinstance(word, dict) or not str(word.get("text", "")).strip():
            raise StudioError("Invalid timed text word")
        point = {"text": str(word["text"]), "start": finite_float(word.get("start"), 0, duration)}
        if 'end' in word:
            point['end'] = finite_float(word['end'], point['start'], duration)
        if point["start"] < previous:
            raise StudioError("Timed text words must be ordered")
        previous = point["start"]
        for key in ("x", "y", "width", "height"):
            point[key] = finite_float(word.get(key), 0, 1)
        if not point["width"] or not point["height"]:
            raise StudioError("Timed text words need a positive box")
        result.append(point)
    if result and " ".join(w["text"] for w in result).split() != str(text).split():
        raise StudioError("Timed text differs from clip text")
    return result


def validated_preset(name, duration, clip_duration: float) -> tuple[str | None, float]:
    if name in (None, "", "none"):
        return None, 0.0
    if name not in {"fade_in", "fade_out", "slide_in", "slide_out", "zoom_in", "pop"}:
        raise StudioError("Невідомий анімаційний прийом")
    length = finite_float(duration if duration is not None else min(.4, clip_duration), .05, clip_duration, "Невірна тривалість анімації")
    return str(name), round(length, 3)


def reconcile_scene_groups(project):
    existing={c['id'] for t in project['tracks'] for c in t.get('clips',[])}
    groups=[]
    for group in project.get('scene_groups',[]):
        group['clip_ids']=[cid for cid in group['clip_ids'] if cid in existing]
        if group['clip_ids']: groups.append(group)
    if 'scene_groups' in project: project['scene_groups']=groups


def apply_group_action(project, action, payload):
    groups=project.setdefault('scene_groups',[])
    clips={c['id']:c for t in project['tracks'] for c in t.get('clips',[])}
    if action=='group_clips':
        ids=payload.get('clip_ids')
        if ids is None and isinstance(payload.get('clip_titles'),list):
            # clips added earlier in the same batch have no id the caller knows: name them by title (the newest one not
            # yet in a group), so a clip and its frame group are one undo step (montage_ops.place)
            occupied={cid for g in groups for cid in g['clip_ids']}
            ids=[]
            for title in payload['clip_titles']:
                found=[c for t in project['tracks'] for c in t.get('clips',[]) if c.get('title')==title and c['id'] not in occupied and c['id'] not in ids]
                if not found:raise StudioError(f'Кліп «{title}» не знайдено')
                ids.append(found[-1]['id'])
        if not isinstance(ids,list) or not 1<=len(ids)<=200 or any(not isinstance(cid,str) for cid in ids) or len(set(ids))!=len(ids) or any(cid not in clips for cid in ids):
            raise StudioError('Invalid frame members')
        occupied={cid for g in groups for cid in g['clip_ids']}
        if occupied.intersection(ids):raise StudioError('A clip is already grouped')
        title=str(payload.get('title') or 'Кадр').strip()[:120]
        if not title:raise StudioError('Frame title is empty')
        role=payload.get('role','scene')
        if role not in {'scene','overlay'}:raise StudioError('Invalid frame role')
        groups.append(dict(id=uuid.uuid4().hex[:12],title=title,clip_ids=ids,role=role))
        return
    group=next((g for g in groups if g['id']==payload.get('group_id')),None)
    if not group:raise StudioError('Frame group not found',404)
    if action=='ungroup_clips':groups.remove(group)
    elif action=='update_group':
        title=str(payload.get('title','')).strip()[:120]
        if not title:raise StudioError('Frame title is empty')
        group['title']=title
    elif action=='move_group':
        members=[clips[cid] for cid in group['clip_ids']]
        first=min(float(c['start']) for c in members)
        offset=finite_float(payload.get('start'),0,36000)-first
        if any(float(c['start'])+offset<0 or float(c['start'])+offset+float(c['duration'])>36000 for c in members):raise StudioError('Frame exceeds timeline bounds')
        for clip in members:clip['start']=round(float(clip['start'])+offset,3)
    elif action=='delete_group':
        remove=set(group['clip_ids'])
        for track in project['tracks']:track['clips']=[c for c in track['clips'] if c['id'] not in remove]
        project['tracks']=[t for t in project['tracks'] if t['clips']] or [dict(id='layer-1',name='Шар 1',type='universal',clips=[])]
        groups.remove(group)


def apply_universal_action(project: dict, action: str, payload: dict) -> bool:
    if action=='set_layer_mute':
        if not isinstance(payload.get('muted'),bool):raise StudioError('Invalid mute state')
        layer=layer_by_id(project,str(payload.get('layer_id')))
        if not any(c['kind'] in {'audio','video'} for c in layer['clips']):raise StudioError('This layer has no sound')
        layer['muted']=payload['muted']
        return True
    if action=='set_layer_hidden':
        # the eye of a picture row (user, 2 November 2026: «глазик… щоб виключити цю лінію»): hidden in the preview and
        # left out of the export, kept on the timeline; the row's sound goes with its picture
        if not isinstance(payload.get('hidden'),bool):raise StudioError('Invalid visibility state')
        layer=layer_by_id(project,str(payload.get('layer_id')))
        if not any(c['kind']!='audio' for c in layer['clips']):raise StudioError('This layer has no picture')
        if payload['hidden']:layer['hidden']=True
        else:layer.pop('hidden',None)
        return True
    if action=='set_project_font':
        try:family=graphics.validate({'font_family':payload.get('font_family')})['font_family']
        except (ValueError,TypeError) as error:raise StudioError(str(error))
        project['font_family']=family
        for track in project['tracks']:
            for clip in track['clips']:
                if clip['kind']=='text' or clip.get('content_type')=='text':typography.reflow(project,clip,family)
        return True
    if action=='set_join_transition':
        try:
            _,_,outgoing,_=joins.boundary(project,payload.get('from_ref'),payload.get('to_ref'))
            for clip in outgoing:
                if clip.get('kind')=='video' and payload.get('type')!='cut':
                    asset=resolve_asset(project,clip['asset_id']);available=media_duration(Path(asset['path']))
                    if available and clip.get('trim_start',0)+clip['duration']+float(payload.get('duration',.35))>available+.04:raise ValueError('The outgoing video needs extra frames for this transition')
            joins.set_transition(project,payload)
        except (ValueError,TypeError,KeyError) as error:raise StudioError(str(error))
        return True
    if action=='reorder_stack':
        groups=project.get('scene_groups',[])
        def resolve(ref):
            if ref=='scenes':wanted={cid for g in groups if g.get('role')!='overlay' for cid in g['clip_ids']}
            elif isinstance(ref,str) and ref.startswith('group:'):
                g=next((g for g in groups if g['id']==ref[6:]),None)
                if not g:raise StudioError('Stack group not found',404)
                wanted=set(g['clip_ids'])
            elif isinstance(ref,str) and ref.startswith('layer:'):
                return {layer_by_id(project,ref[6:])['id']}
            else:raise StudioError('Invalid stack reference')
            return {t['id'] for t in project['tracks'] if any(c['id'] in wanted for c in t['clips'])}
        source=resolve(payload.get('source'));target=resolve(payload.get('target'))
        if not source or not target or source.intersection(target):raise StudioError('Invalid stack destination')
        moving=[t for t in project['tracks'] if t['id'] in source]
        remaining=[t for t in project['tracks'] if t['id'] not in source]
        positions=[i for i,t in enumerate(remaining) if t['id'] in target]
        index=max(positions)+1 if payload.get('above') is True else min(positions)
        project['tracks']=remaining[:index]+moving+remaining[index:]
        recompute_universal_duration(project)
        return True
    if action in {'group_clips','ungroup_clips','update_group','move_group','delete_group'}:
        apply_group_action(project,action,payload)
        recompute_universal_duration(project)
        joins.reconcile(project)
        return True
    supported = {"add_layer", "remove_layer", "move_layer", "update_layer", "add_clip", "move_clip", "trim_clip", "split_clip", "replace_clip_asset", "set_clip_volume", "set_transition", "delete_clip", "update_clip"}
    if action not in supported or action == "set_transition" and "clip_id" not in payload:
        return False
    layers = project["tracks"]
    if action == "add_layer":
        if len(layers) >= 2000:
            raise StudioError("Досягнуто межі шарів")
        name = str(payload.get("name") or f"Шар {len(layers) + 1}").strip()[:80]
        if not name:
            raise StudioError("Назва шару порожня")
        layer = {"id": uuid.uuid4().hex[:12], "name": name, "type": "universal", "z_index": len(layers), "clips": []}
        index = int(payload.get("to_index", len(layers)))
        if not 0 <= index <= len(layers):
            raise StudioError("Невірне місце шару")
        layers.insert(index, layer)
    elif action == "remove_layer":
        if len(layers) <= 1:
            raise StudioError("Останній шар не можна видалити")
        layers.remove(layer_by_id(project, str(payload["layer_id"])))
    elif action == "move_layer":
        layer = layer_by_id(project, str(payload["layer_id"]))
        index = int(payload["to_index"])
        if not 0 <= index < len(layers):
            raise StudioError("Невірне місце шару")
        layers.remove(layer)
        layers.insert(index, layer)
    elif action == "update_layer":
        layer = layer_by_id(project, str(payload["layer_id"]))
        name = str(payload.get("name", "")).strip()[:80]
        if not name:
            raise StudioError("Назва шару порожня")
        layer["name"] = name
    elif action == "add_clip":
        layer = layer_by_id(project, str(payload["layer_id"]))
        kind = str(payload.get("kind") or payload.get("type") or "")
        if kind not in {"video", "image", "text", "animation", "audio"}:
            raise StudioError("Невідомий тип кліпу")
        start = finite_float(payload.get("start", 0), 0, 36000, "Невірний початок кліпу")
        duration = finite_float(payload.get("duration", 5), .1, 36000, "Невірна тривалість кліпу")
        asset = resolve_asset(project, payload["asset_id"]) if payload.get("asset_id") else None
        content_type = str(payload.get("content_type") or ("image" if asset else "shape")) if kind == "animation" else None
        needed_kind = "image" if kind == "animation" and content_type == "image" else kind if kind in {"video", "image", "audio"} else None
        if needed_kind and (asset is None or asset["kind"] != needed_kind):
            raise StudioError("Тип матеріалу не відповідає кліпу")
        if kind == "animation" and content_type not in {"text", "image", "shape", "gradient"}:
            raise StudioError("Невідомий тип анімації")
        if kind in {"video", "audio"}:
            trim_start = finite_float(payload.get("trim_start", 0), 0, 36000, "Invalid source offset")
            available = media_duration(Path(asset["path"])) if asset else None
            if available and trim_start >= available:
                raise StudioError("Source offset is after the end of the file")
            if available and trim_start + duration > available:
                duration = available - trim_start
        else:
            trim_start = 0.0
        if duration < .1:
            raise StudioError("Кліп надто короткий")
        title = str(payload.get("title") or (asset["name"] if asset else "Новий кліп")).strip()[:120]
        text = str(payload.get("text") or (title if kind == "text" else ""))
        if kind=='text' or kind=='animation' and content_type=='text':text=display_text.clean(text)
        if kind == "text" and not text.strip() or kind == "animation" and content_type == "text" and not text.strip():
            raise StudioError("Введіть текст кліпу")
        preset, preset_duration = validated_preset(payload.get("preset"), payload.get("preset_duration"), duration)
        default_color = "#ffffff" if kind == "text" or kind == "animation" and content_type == "text" else "#f0b429" if kind == "animation" else "#101114"
        clip = {"id": uuid.uuid4().hex[:12], "kind": kind, "asset_id": asset["id"] if asset else None, "start": round(start, 3), "duration": round(duration, 3), "trim_start": 0.0, "volume": finite_float(payload.get("volume", 0 if kind == "video" else 1), 0, 1.5, "Невірна гучність"), "title": title, "text": text, "content_type": content_type, "color": str(payload.get("color", default_color)), "transition": {"type": "cut", "duration": 0.0}, "x": finite_float(payload.get("x", .5), -2, 2), "y": finite_float(payload.get("y", .5), -2, 2), "width": finite_float(payload.get("width", 1), .01, 4), "height": finite_float(payload.get("height", 1), .01, 4), "scale": finite_float(payload.get("scale", 1), .05, 8), "opacity": finite_float(payload.get("opacity", 1), 0, 1), "preset": preset, "preset_duration": preset_duration, "keyframes": validated_keyframes(payload.get("keyframes", []), duration)}
        clip["trim_start"] = trim_start
        style_defaults={}
        if kind=='text' or content_type=='text':
            config=read_channel_settings(get_channel_folder(project['channel_id'],include_disabled=True),{}) if project.get('channel_id') else {}
            style_defaults=config.get('typography',{})
        try:clip.update(graphics.validate({**style_defaults,**payload}))
        except (ValueError,TypeError) as error:raise StudioError(str(error))
        if (kind=='text' or content_type=='text') and project.get('font_family'):
            clip['font_family']=project['font_family']
        # a clip glued to a photo takes the photo's motion curve (montage_ops), any other the project's
        clip["easing"] = payload["easing"] if payload.get("easing") in {"linear", "ease_in", "ease_out", "ease_in_out"} else project.get("settings", {}).get("motion_easing", "ease_in_out")
        if "font_size" in payload:
            clip["font_size"] = finite_float(payload["font_size"], 8, 300)
        if "text_words" in payload:
            if kind != "text" and content_type != "text":
                raise StudioError("Timed words require a text clip")
            clip["text_words"] = validated_text_layout(display_text.clean_words(payload["text_words"]), text, duration)
        if layer["clips"]:
            if len(layers) >= 2000:
                raise StudioError("Досягнуто межі шарів")
            layer = {"id": uuid.uuid4().hex[:12], "name": title or f"Шар {len(layers) + 1}", "type": "universal", "clips": []}
            layers.append(layer)
        layer["clips"].append(clip)
        apply_text_binding(project,clip,payload)
        if payload.get('group_id'):
            group=next((g for g in project.get('scene_groups',[]) if g['id']==payload['group_id']),None)
            if not group:raise StudioError('Frame group not found',404)
            group['clip_ids'].append(clip['id'])
    elif action == "move_clip":
        old_layer, clip = clip_by_id(project, str(payload["clip_id"]))
        target = layer_by_id(project, str(payload.get("to_layer_id", old_layer["id"])))
        start = finite_float(payload.get("start", clip["start"]), 0, 36000, "Невірне місце кліпу")
        clip["start"] = round(start, 3)
        if target is not old_layer and target["clips"]:
            index = layers.index(target)
            layers.remove(old_layer)
            layers.insert(index, old_layer)
        elif target is not old_layer:
            old_layer["clips"].remove(clip)
            target["clips"].append(clip)
            layers.remove(old_layer)
    elif action == "trim_clip":
        _, clip = clip_by_id(project, str(payload["clip_id"]))
        start = finite_float(payload.get("trim_start", clip.get("trim_start", 0)), 0, 36000, "Невірний початок обрізання")
        duration = finite_float(payload.get("duration", clip["duration"]), .1, 36000, "Невірна тривалість кліпу")
        if clip.get("asset_id") and clip["kind"] in {"video", "audio"}:
            asset = resolve_asset(project, clip["asset_id"])
            available = media_duration(Path(asset["path"]))
            if available and start + duration > available + .05:
                raise StudioError("Обрізання виходить за кінець файлу")
        clip["trim_start"] = round(start, 3)
        clip["duration"] = round(duration, 3)
        if clip.get("preset"):
            clip["preset_duration"] = min(float(clip.get("preset_duration", 0)), duration)
        clip["keyframes"] = [point for point in clip.get("keyframes", []) if float(point["time"]) <= duration]
    elif action == "split_clip":
        layer, clip = clip_by_id(project, str(payload["clip_id"]))
        at = finite_float(payload["at"], 0, 36000, "Невірне місце поділу")
        offset = at - float(clip["start"])
        if not .05 <= offset <= float(clip["duration"]) - .05:
            raise StudioError("Місце поділу має бути всередині кліпу")
        second = copy.deepcopy(clip)
        second["id"] = uuid.uuid4().hex[:12]
        second["preset"] = None
        second["preset_duration"] = 0.0
        second["start"] = round(at, 3)
        second["duration"] = round(float(clip["duration"]) - offset, 3)
        if clip["kind"] in {"video", "audio"}:
            second["trim_start"] = round(float(clip.get("trim_start", 0)) + offset, 3)
        second["keyframes"] = [{**point, "time": round(float(point["time"]) - offset, 3)} for point in clip.get("keyframes", []) if float(point["time"]) >= offset]
        clip["keyframes"] = [point for point in clip.get("keyframes", []) if float(point["time"]) < offset]
        clip["duration"] = round(offset, 3)
        layers.insert(layers.index(layer) + 1, {"id": uuid.uuid4().hex[:12], "name": second.get("title") or "Кадр", "type": "universal", "clips": [second]})
    elif action == "replace_clip_asset":
        _, clip = clip_by_id(project, str(payload["clip_id"]))
        asset = resolve_asset(project, payload["asset_id"])
        required = "image" if clip["kind"] == "animation" and clip.get("content_type") == "image" else clip["kind"]
        if required not in {"video", "image", "audio"} or asset["kind"] != required:
            raise StudioError("Тип матеріалу не відповідає кліпу")
        clip["asset_id"] = asset["id"]
        clip["title"] = asset["name"]
        clip["trim_start"] = 0.0
        if clip["kind"] in {"video", "audio"}:
            available = media_duration(Path(asset["path"]))
            if available:
                clip["duration"] = round(min(float(clip["duration"]), available), 3)
    elif action == "set_clip_volume":
        _, clip = clip_by_id(project, str(payload["clip_id"]))
        if clip["kind"] not in {"video", "audio"}:
            raise StudioError("Гучність доступна для відео та звуку")
        clip["volume"] = round(finite_float(payload["volume"], 0, 1.5, "Невірна гучність"), 3)
    elif action == "set_transition":
        layer, clip = clip_by_id(project, str(payload["clip_id"]))
        if clip["kind"] == "audio":
            raise StudioError("Перехід доступний лише для візуальних кліпів")
        kind = str(payload.get("type", payload.get("transition_type", "cut")))
        if kind not in {"cut", "crossfade", "swipe"}:
            raise StudioError("Невідомий перехід")
        duration = finite_float(payload.get("duration", 0 if kind == "cut" else .3), 0, min(5, float(clip["duration"])), "Невірна тривалість переходу")
        if kind != "cut":
            following = sorted((item for track in layers for item in track["clips"] if item["id"] != clip["id"] and item["kind"] != "audio" and float(item["start"]) >= float(clip["start"])), key=lambda item: float(item["start"]))
            if not following:
                raise StudioError("Додайте наступний візуальний кадр")
            gap = float(following[0]["start"]) - (float(clip["start"]) + float(clip["duration"]))
            if not (abs(gap) <= .05 or gap <= -duration + .05):
                raise StudioError("Для переходу поставте кліпи поруч або перекрийте їх")
        clip["transition"] = {"type": kind, "duration": round(duration, 3)}
    elif action == "delete_clip":
        layer, clip = clip_by_id(project, str(payload["clip_id"]))
        layer["clips"].remove(clip)
        if len(layers) > 1:
            layers.remove(layer)
    elif action == "update_clip":
        _, clip = clip_by_id(project, str(payload["clip_id"]))
        changes = payload.get("patch", payload.get("changes", {}))
        if not isinstance(changes, dict) or set(changes) - ({"title", "text", "color", "content_type", "x", "y", "width", "height", "scale", "opacity", "preset", "preset_duration", "keyframes", "font_size", "text_words", "text_role", "source_frame", "source_text"} | graphics.FIELDS):
            raise StudioError("Невідоме поле кліпу")
        try:clip.update(graphics.validate(changes))
        except (ValueError,TypeError) as error:raise StudioError(str(error))
        if (clip['kind']=='text' or clip.get('content_type')=='text') and project.get('font_family'):
            clip['font_family']=project['font_family']
        for key in ("x", "y"):
            if key in changes:
                clip[key] = finite_float(changes[key], -2, 2)
        for key in ("width", "height"):
            if key in changes:
                clip[key] = finite_float(changes[key], .01, 4)
        if "scale" in changes:
            clip["scale"] = finite_float(changes["scale"], .05, 8)
        if "opacity" in changes:
            clip["opacity"] = finite_float(changes["opacity"], 0, 1)
        if "keyframes" in changes:
            clip["keyframes"] = validated_keyframes(changes["keyframes"], float(clip["duration"]))
        if "preset" in changes or "preset_duration" in changes:
            clip["preset"], clip["preset_duration"] = validated_preset(changes.get("preset", clip.get("preset")), changes.get("preset_duration", clip.get("preset_duration")), float(clip["duration"]))
        for key in ("title", "text", "color"):
            if key in changes:
                clip[key] = str(changes[key])[:1000 if key == "text" else 120]
        if clip['kind']=='text' or clip.get('content_type')=='text':clip['text']=display_text.clean(clip.get('text',''))
        if "font_size" in changes:
            clip["font_size"] = finite_float(changes["font_size"], 8, 300)
        if "text" in changes and "text_words" not in changes:
            clip.pop("text_words", None)
        if "text_words" in changes:
            clip["text_words"] = validated_text_layout(display_text.clean_words(changes["text_words"]), clip.get("text", ""), float(clip["duration"]))
        if "content_type" in changes:
            content_type = str(changes["content_type"])
            if clip["kind"] != "animation" or content_type not in {"text", "image", "shape", "gradient"}:
                raise StudioError("Невірний тип анімації")
            clip["content_type"] = content_type
        apply_text_binding(project,clip,changes)
        if ('font_size' in changes or 'font_family' in changes) and 'text_words' not in changes:
            typography.reflow(project,clip,project.get('font_family',clip.get('font_family','Golos')))
    reconcile_scene_groups(project)
    joins.reconcile(project)
    recompute_universal_duration(project)
    return True


def apply_text_binding(project,clip,source):
    for key in ('text_role','source_frame','source_text'):
        if key in source:clip[key]=copy.deepcopy(source[key])
    if clip.get('text_role') not in (None,'full_frame','caption','label'):raise StudioError('Invalid text role')
    if clip.get('text_role')!='full_frame':return
    expected=clip.get('source_text')
    if project.get('plan_source') and project_plan_mode(project) != 'direct':
        plan=load_project_plan(project['id'])
        frame=next((f for f in (plan or {}).get('frames',[]) if f['number']==clip.get('source_frame')),None)
        if not frame or frame['format']!='text':raise StudioError('Text frame is missing from the approved plan')
        expected=' '.join(frame['sentences']);clip['source_text']=expected
    if not expected or ' '.join(display_text.clean(expected).split())!=' '.join(clip.get('text','').split()):
        raise StudioError('A text frame must contain its complete spoken passage')
    if clip.get('text_words') and clip['text_words'][0]['start']>.15:
        raise StudioError('A text frame must begin with its first spoken word')


def scene_by_id(project: dict, sid: str) -> dict:
    for scene in project.get("scenes", []):
        if scene.get("id") == sid:
            return scene
    raise StudioError("Кадр не знайдено", 404)


HISTORY_LIMIT = 30


def history_folder(pid: str) -> Path:
    return project_dir(pid) / "history"


def migrate_history(pid: str) -> None:
    """Move the old single history.json into one snapshot file per step."""
    legacy = project_dir(pid) / "history.json"
    if not legacy.is_file():
        return
    with LOCK:
        if not legacy.is_file():
            return
        data = read_json(legacy, {"past": [], "future": []})
        for side in ("past", "future"):
            for snapshot in data.get(side, [])[-HISTORY_LIMIT:]:
                push_history(pid, side, snapshot)
        legacy.unlink()


def history_entries(pid: str, side: str) -> list[Path]:
    folder = history_folder(pid) / side
    if not folder.is_dir():
        return []
    return sorted((path for path in folder.iterdir() if path.suffix == ".json" and path.stem.isdigit()), key=lambda path: int(path.stem))


def push_history(pid: str, side: str, snapshot: dict) -> None:
    entries = history_entries(pid, side)
    index = int(entries[-1].stem) + 1 if entries else 0
    folder = history_folder(pid) / side
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{index}.tmp-{uuid.uuid4().hex}"
    try:
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(str(tmp), str(folder / f"{index}.json"))
    finally:
        if tmp.exists():
            tmp.unlink()
    for path in entries[:max(0, len(entries) + 1 - HISTORY_LIMIT)]:
        path.unlink()


def pop_history(pid: str, side: str) -> dict | None:
    entries = history_entries(pid, side)
    if not entries:
        return None
    snapshot = read_json(entries[-1])
    entries[-1].unlink()
    return snapshot


def clear_history(pid: str, side: str) -> None:
    for path in history_entries(pid, side):
        path.unlink()


RAZGON_RENDER = re.compile(r"(frame_\d{3}|music_sfx)(-[0-9a-f]{8})?\.(mp4|wav|m4a)")   # m4a: the bed of razgon_bridge.py sound


def prune_razgon_renders(pid: str) -> dict:
    """Delete clip renders the Razgon bridge imported and later replaced by a newer render of the same frame.

    Only files the bridge names (frame_NNN.mp4, music_sfx.wav or .m4a) in this project's media folder are candidates. A frame is
    changed in its code and never brought back (user, 30 October 2026: «старі кадри не треба зберігати... міняємо напряму
    код, без можливості повернути назад»), so a render stays only while the timeline shows it. The undo steps that still
    show a replaced one go with it, oldest first, so the steps left form one unbroken chain; redo steps holding one are
    cleared."""
    with LOCK:
        project = load_project(pid)
        media = {root.resolve() for root in media_roots(project)}
        used = {clip.get("asset_id") for track in project.get("tracks", []) for clip in track.get("clips", [])}
        renders = [asset for asset in project.get("assets", []) if Path(asset.get("path", "")).parent.resolve() in media
                   and RAZGON_RENDER.fullmatch(Path(asset.get("path", "")).name)]
        # only a render that a newer render of the same frame replaced on the timeline goes; a frame the author deleted
        # keeps its file and its undo steps, so «Скасувати» can bring it back
        shown = {RAZGON_RENDER.fullmatch(Path(asset["path"]).name).group(1) for asset in renders if asset.get("id") in used}
        old = [asset for asset in renders if asset.get("id") not in used
               and RAZGON_RENDER.fullmatch(Path(asset["path"]).name).group(1) in shown]
        if not old:
            return {"removed": 0, "bytes": 0}
        migrate_history(pid)
        ids = {asset["id"] for asset in old}
        def holds(entry):
            snapshot = read_json(entry, {}) or {}
            return bool(ids & {clip.get("asset_id") for track in snapshot.get("tracks", []) for clip in track.get("clips", [])})
        past = history_entries(pid, "past")
        holding = [index for index, entry in enumerate(past) if holds(entry)]
        for entry in past[:holding[-1] + 1] if holding else []:
            entry.unlink()
        if any(holds(entry) for entry in history_entries(pid, "future")):
            clear_history(pid, "future")
        freed = 0
        for asset in old:
            path = Path(asset["path"])
            if path.is_file():
                freed += path.stat().st_size
                path.unlink()
        # The media list is not part of an edit, so the revision stays and an open editor is not interrupted.
        project["assets"] = [asset for asset in project.get("assets", []) if asset.get("id") not in ids]
        save_project(project)
    return {"removed": len(old), "bytes": freed}


def history_state(pid: str) -> dict:
    migrate_history(pid)
    return {"can_undo": bool(history_entries(pid, "past")), "can_redo": bool(history_entries(pid, "future"))}


def apply_action(pid: str, action: str, payload: dict, expected_revision: int | None = None) -> dict:
    with LOCK:
        project = load_project(pid)
        if expected_revision is not None and expected_revision != project.get("revision", 0):
            raise StudioError("Проєкт змінився. Оновіть сторінку перед правкою", 409)
        migrate_history(pid)
        if action in {"undo", "redo"}:
            source, target = ("past", "future") if action == "undo" else ("future", "past")
            previous = pop_history(pid, source)
            if previous is None:
                raise StudioError("Немає дії для повернення")
            previous = upgrade_legacy_project(previous)
            push_history(pid, target, project)
            # Undo restores the montage, not the media library: files imported or cleaned up since that step stay as they are now.
            current = {asset["id"]: asset for asset in project.get("assets", [])}
            restored = [asset for asset in previous.get("assets", []) if asset.get("id") not in current and Path(asset.get("path", "")).is_file()]
            previous["assets"] = list(current.values()) + restored
            # undo is about the montage: the plan, the frame agent's request, the episode's own shares, its voice text and
            # its restart stay as they are now (an undo once brought a finished run back to «in progress»)
            for key in ("plan_source", "plan_updated_at", "plan_original_source", "production_request", "plan_weights",
                        "voice_script", "restarted_at", "name"):
                if key in project:
                    previous[key] = project[key]
                else:
                    previous.pop(key, None)
            previous["revision"] = project.get("revision", 0) + 1
            save_project(previous)
            return previous
        previous = copy.deepcopy(project)
        if not isinstance(payload, dict):
            raise StudioError("Параметри дії мають бути об'єктом")
        if project.get("schema_version") == 2 and (action in {"add_scene", "add_track_clip", "remove_track_clip", "trim_scene", "move_scene", "split_scene", "replace_scene_asset", "add_text", "delete_scene", "duplicate_scene"} or action == "set_transition" and "clip_id" not in payload):
            raise StudioError("Оновіть редактор: ця дія належить старому формату проєкту")
        if action == "batch":
            edits = payload.get("actions")
            if not isinstance(edits, list) or not 1 <= len(edits) <= 1800:
                raise StudioError("Invalid batch size")
            for edit in edits:
                if not isinstance(edit, dict) or not apply_universal_action(project, edit.get("type"), edit.get("payload", {})):
                    raise StudioError("Unsupported batch action")
        elif action == "set_plan_mode":
            mode = payload.get('mode')
            if mode not in {'director', 'direct'}:
                raise StudioError('Невірний режим плану')
            import director, production
            if pid in director.ACTIVE or pid in production.ACTIVE:
                raise StudioError('Спочатку призупиніть створення кадрів або режисуру', 409)
            project['plan_mode'] = mode
        elif action == "rename_project":
            project["name"] = validated_name(payload.get("name"))
        elif project.get("schema_version") == 2 and apply_universal_action(project, action, payload):
            pass
        elif action == "add_scene":
            duration = float(payload.get("duration", 5))
            if not math.isfinite(duration) or not 0.1 <= duration <= 36000:
                raise StudioError("Невірна тривалість кадру")
            aid = payload.get("asset_id")
            asset = resolve_asset(project, aid) if aid else None
            if asset and asset["kind"] not in {"video", "image"}:
                raise StudioError("Для кадру потрібне фото або відео")
            if asset and asset["kind"] == "video":
                available = media_duration(Path(asset["path"]))
                if available:
                    if available < .1:
                        raise StudioError("Відеофайл надто короткий")
                    duration = min(duration, available)
            kind = asset["kind"] if asset else str(payload.get("type", "color"))
            if kind not in {"video", "image", "text", "color"} or (kind in {"video", "image"} and not asset):
                raise StudioError("Виберіть матеріал для кадру")
            title = str(payload.get("title") or (asset["name"] if asset else "Новий кадр")).strip()[:120]
            scene = {"id": uuid.uuid4().hex[:12], "start": 0.0, "duration": round(duration, 3), "trim_start": 0.0, "title": title, "type": kind, "asset_id": asset["id"] if asset else None, "transition": {"type": "cut", "duration": 0.0}, "volume": 1.0, "layers": []}
            if asset:
                scene["source"] = asset["path"]
            if kind == "text":
                scene["text"] = str(payload.get("text", title))
            index = int(payload.get("to_index", len(project["scenes"])))
            if not 0 <= index <= len(project["scenes"]):
                raise StudioError("Невірне місце кадру")
            project["scenes"].insert(index, scene)
            recompute_timeline(project)
        elif action == "add_track_clip":
            track_id = str(payload["track_id"])
            track = next((item for item in project["tracks"] if item.get("id") == track_id and item.get("type") in {"voice", "music", "sfx"}), None)
            if track is None:
                raise StudioError("Звукову доріжку не знайдено", 404)
            asset = resolve_asset(project, payload["asset_id"])
            if asset["kind"] != "audio":
                raise StudioError("Для звукової доріжки потрібен аудіофайл")
            start = float(payload.get("start", 0))
            duration = float(payload.get("duration", 0))
            volume = float(payload.get("volume", 1))
            if not all(math.isfinite(value) for value in (start, duration, volume)) or start < 0 or duration <= 0 or duration > 36000 or not 0 <= volume <= 1.5:
                raise StudioError("Невірні параметри звукового фрагмента")
            available = media_duration(Path(asset["path"]))
            if available and duration > available + .05:
                raise StudioError("Звуковий фрагмент довший за вибраний файл")
            track["clips"].append({"id": uuid.uuid4().hex[:12], "asset_id": asset["id"], "start": round(start, 3), "duration": round(duration, 3), "volume": round(volume, 3), "trim_start": 0.0})
        elif action == "remove_track_clip":
            clip_id = str(payload["clip_id"])
            clip = next((clip for track in project["tracks"] for clip in track.get("clips", []) if clip.get("id") == clip_id), None)
            if clip is None:
                raise StudioError("Звуковий фрагмент не знайдено", 404)
            for track in project["tracks"]:
                track["clips"] = [item for item in track.get("clips", []) if item.get("id") != clip_id]
        elif action == "trim_scene":
            scene = scene_by_id(project, payload["scene_id"])
            start = float(payload.get("start", scene.get("trim_start", 0)))
            duration = float(payload.get("duration", scene["duration"]))
            if start < 0 or duration <= 0 or duration > 36000:
                raise StudioError("Невірні межі обрізання")
            if scene.get("type") == "video" and scene.get("asset_id"):
                asset = resolve_asset(project, scene["asset_id"])
                available = media_duration(Path(asset["path"]))
                if available and start + duration > available + .05:
                    raise StudioError("Обрізання виходить за кінець відеофайлу")
            scene["trim_start"] = round(start, 3)
            scene["duration"] = round(duration, 3)
            recompute_timeline(project)
        elif action == "move_scene":
            scenes = project["scenes"]
            scene = scene_by_id(project, payload["scene_id"])
            index = int(payload["to_index"])
            if not 0 <= index < len(scenes):
                raise StudioError("Невірне місце кадру")
            scenes.remove(scene)
            scenes.insert(index, scene)
            recompute_timeline(project)
        elif action == "split_scene":
            scene = scene_by_id(project, payload["scene_id"])
            at = float(payload["at"])
            if scene["start"] < at < scene["start"] + scene["duration"]:
                offset = at - scene["start"]
            else:
                offset = at
            if not 0 < offset < scene["duration"]:
                raise StudioError("Місце поділу має бути всередині кадру")
            second = copy.deepcopy(scene)
            second["id"] = uuid.uuid4().hex[:12]
            second["trim_start"] = round(float(scene.get("trim_start", 0)) + offset, 3)
            second["duration"] = round(scene["duration"] - offset, 3)
            second["title"] = scene.get("title", "Кадр") + " (продовження)"
            scene["duration"] = round(offset, 3)
            project["scenes"].insert(project["scenes"].index(scene) + 1, second)
            recompute_timeline(project)
        elif action == "replace_scene_asset":
            scene = scene_by_id(project, payload["scene_id"])
            asset = resolve_asset(project, payload["asset_id"])
            if asset["kind"] not in {"video", "image"}:
                raise StudioError("Аудіо не можна вставити замість кадру")
            scene["asset_id"] = asset["id"]
            scene["type"] = asset["kind"]
            scene["source"] = asset["path"]
            scene["trim_start"] = 0.0
            if asset["kind"] == "video":
                available = media_duration(Path(asset["path"]))
                if available:
                    if available < .1:
                        raise StudioError("Відеофайл надто короткий")
                    scene["duration"] = round(min(float(scene["duration"]), available), 3)
                    recompute_timeline(project)
        elif action == "set_transition":
            scene = scene_by_id(project, payload["scene_id"])
            transition = str(payload.get("transition_type", "cut"))
            if transition not in {"cut", "crossfade", "swipe"}:
                raise StudioError("Невідомий перехід")
            duration = float(payload.get("duration", 0 if transition == "cut" else 0.3))
            if duration < 0 or duration > min(5, scene["duration"]):
                raise StudioError("Невірна тривалість переходу")
            scene["transition"] = {"type": transition, "duration": round(duration, 3)}
        elif action == "set_clip_volume":
            value = float(payload["volume"])
            if not 0 <= value <= 1.5:
                raise StudioError("Гучність має бути від 0 до 1.5")
            found = False
            for track in project["tracks"]:
                for clip in track.get("clips", []):
                    if clip.get("id") == payload["clip_id"]:
                        clip["volume"] = value
                        found = True
            for scene in project["scenes"]:
                if scene["id"] == payload["clip_id"]:
                    scene["volume"] = value
                    found = True
            if not found:
                raise StudioError("Звуковий фрагмент не знайдено", 404)
        elif action == "add_text":
            start = float(payload["start"])
            duration = float(payload["duration"])
            text = str(payload["text"]).strip()
            if start < 0 or duration <= 0 or start + duration > project["duration"] + 0.01 or not 1 <= len(text) <= 300:
                raise StudioError("Невірний текстовий фрагмент")
            track = next(item for item in project["tracks"] if item["type"] == "text")
            track["clips"].append({"id": uuid.uuid4().hex[:12], "start": round(start, 3), "duration": round(duration, 3), "text": text})
        elif action == "delete_scene":
            scene = scene_by_id(project, payload["scene_id"])
            project["scenes"].remove(scene)
            recompute_timeline(project)
        elif action == "duplicate_scene":
            scene = scene_by_id(project, payload["scene_id"])
            duplicate = copy.deepcopy(scene)
            duplicate["id"] = uuid.uuid4().hex[:12]
            project["scenes"].insert(project["scenes"].index(scene) + 1, duplicate)
            recompute_timeline(project)
        else:
            raise StudioError("Дію ще не підтримано: " + str(action))
        project["revision"] = project.get("revision", 0) + 1
        push_history(pid, "past", previous)
        clear_history(pid, "future")
        save_project(project)
        return project


def request_production(pid: str, frames) -> dict:
    """«Почати створення ролика»: the author asks the frame agent (production.py) to make the first N frames.

    Any channel: an animated film once the director has split it, a photo channel once its plan follows the voice.
    The same request is mirrored next to the episode so a terminal agent sees it without the Studio.
    """
    with LOCK:
        project = load_project(pid)
        if project_plan_mode(project) == "direct":
            raise StudioError("Режим «Без плану»: створюйте ролик у вкладці «Монтаж» або через API", 409)
        plan = load_project_plan(pid)
        if not plan or plan.get("timing", {}).get("status") != "audio_synced":
            raise StudioError("Спершу додайте озвучку, щоб план став «За озвучкою»")
        animated = project_animated(project)
        if animated and plan.get("frame_source") != planner.DIRECTOR_FRAME_SOURCE:
            raise StudioError("Кадри ще не розбиті режисером. Дочекайтеся режисури")
        if plan.get("director_stale"):
            raise StudioError("Сценарій розходиться з озвучкою. Режисер має заново розбити кадри")
        if (project.get("production_request") or {}).get("status") in {"requested", "in_progress"}:
            raise StudioError("Агент уже створює кадри цього ролика", 409)
        import director
        if pid in director.ACTIVE:
            raise StudioError("Режисер ще розкладає озвучку на кадри. Дочекайтеся, поки він закінчить", 409)
        total = len(plan["frames"])
        try:
            count = int(frames)
        except (TypeError, ValueError):
            raise StudioError("Вкажіть кількість кадрів") from None
        if not 1 <= count <= total:
            raise StudioError(f"Кількість кадрів має бути від 1 до {total}")
        # made frames (drawn as code, or on the timeline) are not asked for again: that would only start the agent
        # over the same frames
        made = set(made_frames(project, plan))
        if set(range(1, count + 1)) <= made:
            raise StudioError(f"Кадри 1–{count} уже створені: їх видно в «Монтажі». Готовий ролик збирає «Експорт MP4».", 409)
        # the first frame the agent makes: frames already made before it are not part of this request's progress
        first = next(n for n in range(1, count + 1) if n not in made)
        chosen = plan["frames"][:count]
        request = {"id": uuid.uuid4().hex[:12], "frames": count, "first": first, "total_frames": total,
                   "start": chosen[0]["start"], "end": chosen[-1]["end"], "status": "requested",
                   "created_at": time.time(), "script_sha256": plan["script_sha256"]}
        project["production_request"] = request
        project["revision"] = project.get("revision", 0) + 1
        save_project(project)
        atomic_json(project_dir(pid) / "production-request.json", request)
        return project
