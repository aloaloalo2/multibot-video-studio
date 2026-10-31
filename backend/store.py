"""Persistent, non-destructive local project model for VideoKey Studio."""

from __future__ import annotations

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
from pathlib import Path

import planner
import number_text
import display_text
import graphics
import joins
import typography


YOUTUBE_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("MULTIBOT_STUDIO_DATA", str(APP_ROOT / "backend" / "data"))).expanduser().resolve()
PROJECTS_ROOT = DATA_ROOT / "projects"
DISABLED_PATH = DATA_ROOT / "disabled_channels.json"
GLOBAL_SETTINGS_PATH = DATA_ROOT / "settings.json"
GLOBAL_DEFAULTS = {"default_width": 1920, "default_height": 1080, "default_fps": 30, "export_subfolder": ""}
PLAN_CONFIG = "video-plan.json"
MEDIA_EXTENSIONS = {".mp4": "video", ".mov": "video", ".webm": "video", ".mkv": "video", ".m4v": "video", ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image", ".bmp": "image", ".tif": "image", ".tiff": "image", ".wav": "audio", ".aiff": "audio", ".aif": "audio", ".mp3": "audio", ".m4a": "audio", ".aac": "audio", ".flac": "audio", ".ogg": "audio", ".opus": "audio"}
LOCK = threading.RLock()
_DURATION_CACHE = {}
_AUDIO_HASH_CACHE = {}


class StudioError(Exception):
    def __init__(self, message, status=400):
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


def read_json(path: Path, default=None):
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def global_settings() -> dict:
    saved = read_json(GLOBAL_SETTINGS_PATH, {})
    return {**GLOBAL_DEFAULTS, **saved} if isinstance(saved, dict) else dict(GLOBAL_DEFAULTS)


def update_global_settings(patch: dict) -> dict:
    if not isinstance(patch, dict) or set(patch) - set(GLOBAL_DEFAULTS):
        raise StudioError("Невідоме загальне налаштування")
    settings = {**global_settings(), **patch}
    for key, maximum in (("default_width", 7680), ("default_height", 4320)):
        value = settings[key]
        if type(value) is not int or not 128 <= value <= maximum or value % 2:
            raise StudioError("Розмір відео має бути парним числом від 128 до " + str(maximum))
    fps = settings["default_fps"]
    if type(fps) is not int or not 1 <= fps <= 120:
        raise StudioError("Частота кадрів має бути від 1 до 120")
    subfolder = settings["export_subfolder"]
    if not isinstance(subfolder, str) or len(subfolder) > 80 or subfolder in {".", ".."} or any(ch in subfolder for ch in "/\\\x00") or subfolder != subfolder.strip():
        raise StudioError("Папка експорту має бути однією назвою без роздільників")
    with LOCK:
        atomic_json(GLOBAL_SETTINGS_PATH, settings)
    return settings


def under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def channel_id(folder: Path) -> str:
    return hashlib.sha256(str(folder.resolve()).encode()).hexdigest()[:16]


def disabled_ids() -> set[str]:
    value = read_json(DISABLED_PATH, [])
    return set(value if isinstance(value, list) else [])


def channel_folders(include_disabled=False) -> list[Path]:
    result = []
    disabled = disabled_ids()
    if not YOUTUBE_ROOT.is_dir():
        return result
    for folder in YOUTUBE_ROOT.iterdir():
        if not folder.is_dir() or not (folder / PLAN_CONFIG).is_file():
            continue
        if include_disabled or channel_id(folder) not in disabled:
            result.append(folder)
    return sorted(result, key=lambda item: unicodedata.normalize("NFC", item.name).casefold())


def get_channel_folder(cid: str, include_disabled=False) -> Path:
    for folder in channel_folders(include_disabled=include_disabled):
        if channel_id(folder) == cid:
            return folder
    raise StudioError("Канал не знайдено", 404)


def validate_settings(value: dict) -> dict:
    if not isinstance(value, dict):
        raise StudioError("Налаштування мають бути об'єктом")
    name = value.get("display_name")
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name.strip()) > 80):
        raise StudioError("Назва каналу має містити від 1 до 80 символів")
    if value.get("motion_easing", "ease_in_out") not in {"linear", "ease_in", "ease_out", "ease_in_out"}:
        raise StudioError("Невідомий тип руху")
    if 'typography' in value:
        if not isinstance(value['typography'],dict):raise StudioError('Invalid typography')
        try:graphics.validate(value['typography'])
        except (ValueError,TypeError) as error:raise StudioError(str(error))
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
    settings = read_json(folder / PLAN_CONFIG, {})
    name = (settings.get("display_name") or "").strip() or folder.name
    return {"id": channel_id(folder), "name": unicodedata.normalize("NFC", name), "folder_name": unicodedata.normalize("NFC", folder.name),
            "path": str(folder), "settings": settings}


def list_channels() -> list[dict]:
    return [channel_record(folder) for folder in channel_folders()]


def add_channel(folder: Path, copy_from: str | None = None) -> dict:
    folder = folder.expanduser().resolve()
    if folder.parent != YOUTUBE_ROOT.resolve() or not folder.is_dir():
        raise StudioError("Оберіть папку каналу всередині YOUTUBE")
    config = folder / PLAN_CONFIG
    with LOCK:
        if not config.exists():
            if copy_from:
                template = read_json(get_channel_folder(copy_from) / PLAN_CONFIG, None)
            else:
                templates = channel_folders()
                template = read_json(templates[0] / PLAN_CONFIG, None) if templates else None
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
        if not folder.is_dir() or not (folder / PLAN_CONFIG).is_file():
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
    current = read_json(folder / PLAN_CONFIG, {})
    if not isinstance(patch, dict):
        raise StudioError("Налаштування мають бути об'єктом")
    next_value = copy.deepcopy(current)
    next_value.update(patch)
    if "weights" in patch:
        next_value["weights"] = patch["weights"]
    validate_settings(next_value)
    if "opening_clip_count" in patch:
        existing_types = list(next_value.get("opening_clip_types") or [])
        count = int(next_value["opening_clip_count"])
        next_value["opening_clip_types"] = (existing_types + ["stock_video"] * count)[:count]
    validate_settings(next_value)
    with LOCK:
        atomic_json(folder / PLAN_CONFIG, next_value)
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
    return upgrade_legacy_project(data)


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


def delete_project(pid: str) -> None:
    with LOCK:
        project = load_project(pid)
        project["deleted_at"] = time.time()
        project["revision"] = project.get("revision", 0) + 1
        save_project(project)


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
    if not project.get("episode_path") or not (Path(project["episode_path"]) / "razgon.json").is_file():
        return pictures
    import frame_progress   # it reads the project through this module
    return max(pictures, len(frame_progress.drawn(project["id"])))


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
            item = read_json(path)
            if not item.get("deleted_at") and (cid is None or item.get("channel_id") == cid):
                item = upgrade_legacy_project(item)
                cover_asset_id = project_cover_asset(item)
                result.append({"id": item["id"], "name": item["name"], "channel_id": item["channel_id"], "duration": item.get("duration", 0), "revision": item.get("revision", 0), "episode_path": item.get("episode_path"), "status": "draft", "has_plan": bool(item.get("plan_source")), "plan_stage": plan_readiness(item, stage_only=True)["stage"] if item.get("plan_source") else None, "scene_count": sum(len(track.get("clips", [])) for track in item.get("tracks", [])), "pictures": picture_count(item), "created_at": project_created_at(item, folder), "updated_at": round(path.stat().st_mtime * 1000)})
                result[-1]["cover_asset_id"] = cover_asset_id
                # the thumbnail the studio keeps (thumbnail_gen.preview), or one still only in the episode folder
                episode = Path(item.get("episode_path") or "") if item.get("episode_path") else None
                previews = [folder / "preview" / "Превью.png"] + ([episode / name for name in ("Превью.png", "Превью.jpg", "Превью.jpeg")] if episode else [])
                stamps = [path.stat().st_mtime_ns for path in previews if path.is_file()]
                if stamps:
                    result[-1]["preview_mtime"] = max(stamps)
        except (ValueError, KeyError):
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
    with LOCK:
        folder.mkdir(parents=True, exist_ok=False)
        global_defaults = global_settings()
        project = {"id": pid, "name": name, "channel_id": cid, "channel_name": unicodedata.normalize("NFC", channel.name), "episode_path": str(episode), "created_at": round(time.time() * 1000), "schema_version": 2, "layer_mode": "item", "revision": 0, "width": global_defaults["default_width"], "height": global_defaults["default_height"], "fps": global_defaults["default_fps"], "duration": 0.0, "scenes": [], "tracks": [{"id": "layer-1", "name": "Шар 1", "type": "universal", "z_index": 0, "clips": []}], "assets": [], "settings": read_json(channel / PLAN_CONFIG, {})}
        atomic_json(folder / "project.json", project)
    return project


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
        # The episode's own plan file mirrors the attached plan, so no older draft is left behind in the folder.
        episode_plan = Path(project["episode_path"]) / "План видео.json"
        if plan.get("frame_source") and episode_plan.is_file():
            atomic_json(episode_plan, plan)
        project["plan_source"] = str(path)
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
    if _PLAN_CACHE.get(key[0], (None,))[0] != key:
        _PLAN_CACHE[key[0]] = (key, planner.upgrade_legacy_number_format(validate_plan(read_json(path))))
        for stale in [item for item in _SYNCED_PLAN_CACHE if item[0][0] == key[0] and item[0] != key]:
            del _SYNCED_PLAN_CACHE[stale]
    plan = _PLAN_CACHE[key[0]][1]
    return (copy.deepcopy(plan) if private else plan), key


def load_project_plan(pid: str) -> dict | None:
    path = project_plan_file(load_project(pid))
    return cached_plan(path)[0] if path else None


def project_from_plan(cid: str, name: str, episode_path: str, plan: dict) -> dict:
    plan = validate_plan(plan)
    channel = get_channel_folder(cid)
    episode = validated_episode_path(channel, episode_path, validated_name(name))
    with LOCK:
        existing = next((item for item in list_projects(cid) if Path(item["episode_path"]).resolve() == episode), None)
        project = load_project(existing["id"]) if existing else create_project(cid, name, str(episode))
        return attach_plan(project["id"], plan)


def plan_settings_match(pid: str, plan: dict | None) -> bool | None:
    if not plan or not plan.get("settings_signature"):
        return None
    project = load_project(pid)
    channel = get_channel_folder(project["channel_id"])
    settings = read_json(channel / PLAN_CONFIG, {})
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
    result = {"stage": "draft", "plan_ready": False, "export_ready": False,
              "reason": "Це чернетка. Додайте таймінги фраз із готової озвучки"}
    try:
        key = None
        if plan is None:
            path = project_plan_file(project)
            plan, key = cached_plan(path, private=False) if path else (None, None)
        if not plan:
            result["reason"] = "Створіть план і додайте таймінги готової озвучки"
            return result
        if plan.get("timing", {}).get("status") != "audio_synced":
            return result
        audio = plan["timing"].get("audio", {})
        duration = audio.get("duration")
        # Full validation re-derives every number and timing; a plan file that has not changed gives the same answer.
        if key is None:
            planner.validate_synced_plan(plan, duration)
        else:
            if (key, duration) not in _SYNCED_PLAN_CACHE:
                try:
                    planner.validate_synced_plan(plan, duration)
                    _SYNCED_PLAN_CACHE[(key, duration)] = None
                except ValueError as error:
                    _SYNCED_PLAN_CACHE[(key, duration)] = str(error)
            if _SYNCED_PLAN_CACHE[(key, duration)] is not None:
                raise ValueError(_SYNCED_PLAN_CACHE[(key, duration)])
        result.update(stage="audio_synced", plan_ready=True, reason="Додайте повну озвучку на таймлайн для експорту")
        if stage_only:
            return result
        clips = [clip for track in project.get("tracks", []) for clip in track.get("clips", [])]
        full_voice = False
        for clip in clips:
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
            full_voice = abs(float(clip.get("start", 0))) < .001 and abs(float(clip.get("trim_start", 0))) < .001 and abs(float(clip.get("duration", 0)) - duration) < .002 and float(clip.get("volume", 1)) > 0
            if full_voice:
                break
        if full_voice:
            if abs(float(project.get("duration", 0)) - duration) > max(.002, 1 / max(1, int(project.get("fps", 30)))):
                result["reason"] = "Тривалість монтажу має відповідати готовій озвучці"
            else:
                result.update(export_ready=True, reason="")
    except (StudioError, ValueError, TypeError, KeyError, OSError) as error:
        result["reason"] = str(error) if isinstance(error, (ValueError, StudioError)) else "Перевірте озвучку та таймінги фраз"
    return result


def channel_animated(channel: Path) -> bool:
    return (read_json(channel / PLAN_CONFIG, {}) or {}).get("channel_kind") == "animated"


def await_voice(cid: str, name: str, episode: Path, script, project_id=None) -> dict:
    """An animated episode gets no plan before its voice: the Studio keeps the script and waits.

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
            found = next((item for item in list_projects(cid) if Path(item["episode_path"]).resolve() == episode), None)
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
        follow_title(project)
        project["revision"] = project.get("revision", 0) + 1
        save_project(project)
    url = f"/channels/{cid}/projects/{project['id']}/plan"
    return {"project": project, "plan": None, "plan_url": url, "awaiting_voice": True, "script_sha256": digest}


def generate_project_plan(cid: str, name: str, episode_path: str, *, script=None, script_path=None, duration=None, hints=None, project_id=None, narration=None, timings=None, weights=None, use_channel_weights=False) -> dict:
    """The only planning entry point. Read saved channel settings at execution time."""
    channel = get_channel_folder(cid)
    episode = validated_episode_path(channel, episode_path, validated_name(name))
    if script is not None and script_path is not None:
        raise StudioError("Передайте текст або файл сценарію")
    if script_path is not None:
        path = Path(script_path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".txt" or not under(path, episode):
            raise StudioError("Сценарій має бути TXT-файлом у папці випуску")
        script = path.read_text(encoding="utf-8-sig")
    # An animated channel never gets a plan split from the script alone: it waits for the voice and the director.
    if narration is None and timings is None and channel_animated(channel):
        return await_voice(cid, validated_name(name), episode, script, project_id)
    with LOCK:
        settings = validate_settings(read_json(channel / PLAN_CONFIG, {}))
        if project_id:
            existing_project = load_project(project_id)
        else:
            found = next((item for item in list_projects(cid) if Path(item["episode_path"]).resolve() == episode), None)
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
            if previous_plan and previous_plan.get("spoken_script") and number_text.to_digits(previous_plan["spoken_script"]) == script:
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
            planner.validate_synced_plan(plan, audio["duration"])
            # An animated film keeps its director's frames through every rebuild of the plan.
            try:
                plan = planner.keep_director_frames(plan, previous_plan)
            except (ValueError, TypeError, KeyError) as exc:
                raise StudioError("Кадри режисера не вдалося перенести на нову озвучку: " + str(exc)) from None
        plan["settings_scope"] = "project" if weights is not None else "channel"
        plan["channel_id"] = cid
        plan["generated_at"] = time.time()
        output = episode / "План видео.json"
        plan["report"]["json"] = str(output)
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
        # Keep a recoverable copy of every previous plan, including manual imports.
        if output.is_file():
            versions = project_dir(project["id"]) / "plan-history"
            versions.mkdir(exist_ok=True)
            shutil.copy2(output, versions / (str(time.time_ns()) + ".json"))
        atomic_json(output, plan)
        if audio:
            spoken_path = episode / "Сценарий для озвучки.txt"
            if spoken_path.exists() and spoken_path.read_text(encoding="utf-8-sig") != plan["spoken_script"]:
                spoken_path = episode / "ТЕХНИЧЕСКИЕ ФАЙЛЫ" / ("Озвученный сценарий " + plan["spoken_script_sha256"][:12] + ".txt")
            atomic_text(spoken_path, plan["spoken_script"])
            formatted_path = episode / "Сценарий.txt"
            if formatted_path.exists() and formatted_path.read_text(encoding="utf-8-sig") not in {script, build_script, plan["script"]}:
                formatted_path = episode / "Сценарий для студии.txt"
            atomic_text(formatted_path, plan["script"])
            plan["spoken_script_file"] = str(spoken_path)
            plan["report"]["formatted_script"] = str(formatted_path)
            atomic_json(output, plan)
        atomic_json(project_dir(project["id"]) / "imported-plan.json", plan)
        return {"project": project, "plan": plan, "plan_url": url, "settings_match": True}


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
    own_media = project_dir(project["id"]) / "media"
    existing = {asset["id"]: asset for asset in project.get("assets", []) if isinstance(asset, dict) and "id" in asset}
    # A file imported from the episode folder exists twice, as the Studio copy and as the original; the library shows
    # the copy only, unless the timeline uses the original itself. An import may add -xxxxxxxx to the name on a clash.
    used = {clip.get("asset_id") for track in project.get("tracks", []) for clip in track.get("clips", [])}
    copies = set()
    for asset in existing.values():
        path = Path(asset.get("path", ""))
        if under(path, own_media) and path.is_file():
            copies.add((re.sub(r"-[0-9a-f]{8}$", "", path.stem), path.suffix.lower(), path.stat().st_size))
    roots = [episode, own_media]
    for root in roots:
        if not root.is_dir():
            continue
        for current, dirs, files in os.walk(root):
            rel_depth = len(Path(current).relative_to(root).parts)
            if rel_depth >= 3:
                dirs[:] = []
            else:
                dirs[:] = [item for item in dirs if not item.startswith(".") and item not in {"node_modules", "ТЕХНИЧЕСКИЕ ФАЙЛЫ", "Архив"}]
            for name in files:
                if len(existing) >= limit:
                    break
                path = Path(current) / name
                if path.is_file() and media_kind(path) and under(path, root):
                    asset = asset_record(path, project["id"], "project" if root == own_media else "episode")
                    if root == episode and asset["id"] not in used and (path.stem, path.suffix.lower(), path.stat().st_size) in copies:
                        continue
                    existing.setdefault(asset["id"], asset)
    for asset in existing.values():
        if asset.get('kind') in {'image','video'}:
            path=Path(asset['path'])
            if path.is_file():asset['thumbnail_url']=f"/api/projects/{project['id']}/assets/{asset['id']}/thumbnail?v={path.stat().st_mtime_ns}"
    return list(existing.values())


def resolve_asset(project: dict, aid: str) -> dict:
    for asset in project.get('assets',[]):
        if asset.get('id')==aid:
            path=Path(asset['path']).resolve()
            if path.is_file() and (under(path,Path(project['episode_path'])) or under(path,project_dir(project['id'])/'media')):return asset
    for asset in discover_assets(project):
        if asset["id"] == aid:
            path = Path(asset["path"]).resolve()
            if not path.is_file() or not (under(path, Path(project["episode_path"])) or under(path, project_dir(project["id"]) / "media")):
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


def import_asset_file(project: dict, source: Path, source_name="local") -> dict:
    source = source.expanduser().resolve()
    if not source.is_file() or not media_kind(source):
        raise StudioError("Підтримуються тільки фото, відео й аудіо")
    if source.stat().st_size > 10 * 1024 ** 3:
        raise StudioError("Файл завеликий для імпорту")
    media_dir = project_dir(project["id"]) / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"[^\w. -]", "_", source.name).strip(". ") or "asset"
    dest = media_dir / base
    if dest.exists():
        dest = media_dir / (source.stem[:70] + "-" + uuid.uuid4().hex[:8] + source.suffix.lower())
    tmp = media_dir / (".import-" + uuid.uuid4().hex)
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
    media_dir = project_dir(project["id"]) / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"[^\w. -]", "_", filename).strip(". ") or "asset"
    destination = media_dir / base
    if destination.exists():
        destination = media_dir / (Path(base).stem[:70] + "-" + uuid.uuid4().hex[:8] + Path(base).suffix.lower())
    temporary = media_dir / (".upload-" + uuid.uuid4().hex)
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
            config=read_json(get_channel_folder(project['channel_id'])/PLAN_CONFIG,{}) if project.get('channel_id') else {}
            style_defaults=config.get('typography',{})
        try:clip.update(graphics.validate({**style_defaults,**payload}))
        except (ValueError,TypeError) as error:raise StudioError(str(error))
        if (kind=='text' or content_type=='text') and project.get('font_family'):
            clip['font_family']=project['font_family']
        clip["easing"] = project.get("settings", {}).get("motion_easing", "ease_in_out")
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
    if project.get('plan_source'):
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


RAZGON_RENDER = re.compile(r"(frame_\d{3}|music_sfx)(-[0-9a-f]{8})?\.(mp4|wav)")


def prune_razgon_renders(pid: str) -> dict:
    """Delete clip renders the Razgon bridge imported and later replaced.

    Only files the bridge names (frame_NNN.mp4, music_sfx.wav) in this project's media folder are candidates. A frame is
    changed in its code and never brought back (user, 30 October 2026: «старі кадри не треба зберігати... міняємо напряму
    код, без можливості повернути назад»), so a render stays only while the timeline shows it. The undo steps that still
    show a replaced one go with it, oldest first, so the steps left form one unbroken chain; redo steps holding one are
    cleared."""
    media = (project_dir(pid) / "media").resolve()
    with LOCK:
        project = load_project(pid)
        used = {clip.get("asset_id") for track in project.get("tracks", []) for clip in track.get("clips", [])}
        old = [asset for asset in project.get("assets", []) if asset.get("id") not in used
               and Path(asset.get("path", "")).parent.resolve() == media and RAZGON_RENDER.fullmatch(Path(asset.get("path", "")).name)]
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
            for key in ("plan_source", "plan_updated_at", "plan_original_source"):
                if key in project:
                    previous[key] = project[key]
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
    """«Почати створення відео»: the author asks the agent to make the first N frames of an animated film.

    The Studio only records the request; the agent picks it up, builds those frames in Razgon and puts them on the
    timeline. The same request is mirrored next to the episode so a terminal agent sees it without the Studio.
    """
    with LOCK:
        project = load_project(pid)
        plan = load_project_plan(pid)
        if not plan or plan.get("timing", {}).get("status") != "audio_synced":
            raise StudioError("Спершу додайте озвучку, щоб план став «За озвучкою»")
        if plan.get("frame_source") != planner.DIRECTOR_FRAME_SOURCE:
            raise StudioError("Кадри ще не розбиті режисером. Дочекайтеся режисури")
        total = len(plan["frames"])
        try:
            count = int(frames)
        except (TypeError, ValueError):
            raise StudioError("Вкажіть кількість кадрів") from None
        if not 1 <= count <= total:
            raise StudioError(f"Кількість кадрів має бути від 1 до {total}")
        import frame_progress   # it reads the project through this module
        # frames drawn as code are made: asking for them again would only start the agent over the same frames
        if set(range(1, count + 1)) <= set(frame_progress.drawn(pid)):
            raise StudioError(f"Кадри 1–{count} уже намальовані: їх видно в «Монтажі» в режимі «Наживо». "
                              "Готовий ролик рендерить «Експорт MP4».", 409)
        chosen = plan["frames"][:count]
        request = {"id": uuid.uuid4().hex[:12], "frames": count, "total_frames": total,
                   "start": chosen[0]["start"], "end": chosen[-1]["end"], "status": "requested",
                   "created_at": time.time(), "script_sha256": plan["script_sha256"]}
        project["production_request"] = request
        project["revision"] = project.get("revision", 0) + 1
        save_project(project)
        atomic_json(Path(project["episode_path"]) / "Запит на створення.json", request)
        return project
