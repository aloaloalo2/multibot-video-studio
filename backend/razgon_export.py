"""«Експорт MP4» for Razgon 2D episodes: the same film as the agent's `razgon_bridge.py push` + `final`.

An episode folder with razgon.json is drawn by Razgon 2D Studio. Its timeline holds one clip per Studio frame titled
«Razgon · кадр NNN»: a code block (an invisible shape that only the live preview draws over) or, after push, the
rendered MP4. The export hands the frames to `razgon_bridge.py export`, which renders every frame that has no rendered
clip yet, glues the clips, lays the channel plate on top and mixes Razgon's music and SFX under the original voice at
−14 LUFS, exactly as `final`. A timeline with anything else on it (own clips, transitions, effects, changed volume) is
not that film: it exports through the Studio engine. Its code blocks are rendered first by `razgon_bridge.py frames`
(a mixed episode, e.g. photos, stock and text frames around some Razgon frames), and the engine draws each block from
its rendered clip.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import razgon_live
import store

BRIDGE = Path(__file__).resolve().parents[1] / "tools" / "razgon_bridge.py"
FRAME_TITLE = re.compile(r"Razgon · кадр (\d{3})")
BED_TITLE = "Razgon · музика й ефекти"
OVERLAY_TITLE = "Плашка каналу"
LOGO_TITLE = "Логотип каналу"   # logo_layer.py: the channel logo from the settings, laid over the plate
EFFECTS = ("keyframes", "preset", "visual_effect", "mask", "corner_radius", "shadow", "gradient", "blur", "motion_blur")


class NotTheFilm(Exception):
    """The timeline differs from the Razgon film, so the bridge cannot make it."""


def _slot(start: float, end: float, fps: int) -> tuple[int, int]:
    # start + duration carries float noise (276.90000000000003 for 276.9), which tips a half-frame edge to the next frame
    return int(round(round(start, 6) * fps)), int(round(round(end, 6) * fps))


def _as_is(clip: dict) -> bool:
    """Drawn full frame from the start of its media, without motion, effect or a Studio transition."""
    frame = {"x": .5, "y": .5, "width": 1, "height": 1, "scale": 1}
    return (all(abs(float(clip.get(key, value)) - value) < 1e-6 for key, value in frame.items())
            and not any(clip.get(key) for key in EFFECTS) and abs(float(clip.get("trim_start", 0))) < 1e-6
            and (clip.get("transition") or {}).get("type", "cut") == "cut")


def _media(project: dict, clip: dict) -> str:
    try:
        return str(Path(store.resolve_asset(project, clip.get("asset_id"))["path"]).resolve())
    except store.StudioError:
        raise NotTheFilm(f"немає файлу кліпу «{clip.get('title', '')}»") from None


def _film(project: dict, info: dict) -> dict:
    """Which rendered clip the timeline holds for every frame of the Razgon film (None for a code block), and the plate."""
    link = store.read_json(info["project"] / "story" / "studio_frames.json", {})
    if link.get("project_id") != project["id"]:
        raise NotTheFilm("проєкт Razgon прив'язано до іншого випуску студії")
    plan = store.load_project_plan(project["id"]) or {}
    audio = (plan.get("timing") or {}).get("audio") or {}
    if plan.get("script_sha256") != link.get("script_sha256") or audio.get("sha256") != link.get("audio_sha256"):
        raise NotTheFilm("план у студії змінився після razgon_bridge.py prepare")
    fps = int(link["fps"])
    if int(project.get("fps", 30)) != fps:
        raise NotTheFilm("частота кадрів студії не збігається з Razgon")
    if project.get("join_transitions"):
        raise NotTheFilm("на стиках кадрів є переходи студії")
    voices = {link.get("voice_asset_id"), audio.get("asset_id")} - {None}
    duration = float(link["duration"])
    slots = {f["number"]: _slot(f["start"], f["end"], fps) for f in link["frames"]}
    clips, overlay, logo, voice = {}, None, None, False
    for track in project.get("tracks", []):
        for clip in track.get("clips", []):
            title, kind = clip.get("title", ""), clip.get("kind")
            match = FRAME_TITLE.fullmatch(title)
            whole = abs(float(clip.get("start", 0))) < 1e-3 and abs(float(clip["start"]) + float(clip["duration"]) - duration) < 1 / fps
            if match:
                number = int(match.group(1))
                if number not in slots or number in clips:
                    raise NotTheFilm(f"кадр {number} не з плану Razgon")
                if _slot(float(clip["start"]), float(clip["start"]) + float(clip["duration"]), fps) != slots[number]:
                    raise NotTheFilm(f"кадр {number} зсунуто з його місця")
                if kind == "video" and _as_is(clip) and float(clip.get("opacity", 1)) == 1:
                    clips[number] = _media(project, clip)
                elif kind == "animation" and clip.get("content_type") == "shape" and not any(clip.get(key) for key in EFFECTS):
                    clips[number] = None
                else:
                    raise NotTheFilm(f"кадр {number} змінено в студії")
            elif kind == "image" and title == OVERLAY_TITLE and overlay is None and whole and _as_is(clip) and float(clip.get("opacity", 1)) == 1:
                overlay = _media(project, clip)
            elif kind == "image" and title == LOGO_TITLE and logo is None and whole and _as_is(clip) and float(clip.get("opacity", 1)) == 1:
                logo = _media(project, clip)
            elif kind == "audio" and whole and not track.get("muted") and float(clip.get("volume", 1)) == 1 and abs(float(clip.get("trim_start", 0))) < 1e-6 \
                    and (clip.get("asset_id") in voices or title == BED_TITLE):
                voice = voice or clip.get("asset_id") in voices
            else:
                raise NotTheFilm(f"кліп «{title or kind}» не з фільму Razgon")
    missing = sorted(set(slots) - set(clips))
    if missing or not voice:
        raise NotTheFilm(f"на таймлайні немає кадру {missing[0]}" if missing else "на таймлайні немає оригінальної озвучки")
    return {"razgon": str(info["project"]), "clips": {str(number): clips[number] for number in sorted(clips)},
            "overlay": _layered(project, overlay, logo)}


def _layered(project: dict, plate: str | None, logo: str | None) -> str | None:
    """The bridge lays one full-frame picture over the film: the plate, the logo, or the logo drawn over the plate."""
    if not plate or not logo:
        return plate or logo
    from PIL import Image
    target = store.project_dir(project["id"]) / "branding" / f"plate+logo-{Path(plate).stem}-{Path(logo).stem}.png"
    if not target.is_file():
        with Image.open(plate) as under, Image.open(logo) as over:
            picture = under.convert("RGBA")
            picture.alpha_composite(over.convert("RGBA").resize(picture.size))
        target.parent.mkdir(parents=True, exist_ok=True)
        picture.save(target)
    return str(target)


def export_job(project: dict) -> dict | None:
    """The bridge's part of an export of this project, or None when it exports through the Studio engine."""
    if not (Path(project.get("episode_path", "")) / "razgon.json").is_file():
        return None
    blocks = [clip for track in project.get("tracks", []) for clip in track.get("clips", [])
              if FRAME_TITLE.fullmatch(clip.get("title", "")) and clip.get("kind") != "video"]
    info = razgon_live.link(project)
    try:
        if not info or not BRIDGE.is_file():
            raise NotTheFilm("не знайдено проєкт Razgon або razgon_bridge.py")
        spec = _film(project, info)
    except NotTheFilm as reason:
        if blocks and info and BRIDGE.is_file():
            return _mixed(project, info, blocks)
        if blocks:
            raise store.StudioError(f"Кадри Razgon ще не відрендерені, а студія не може їх зібрати: {reason}.", 409) from None
        return None
    spec["render"] = sum(1 for path in spec["clips"].values() if path is None)
    return spec


def _mixed(project: dict, info: dict, blocks: list[dict]) -> dict:
    """A timeline that is more than the Razgon film (photos, stock and text frames around some Razgon frames, or the
    author's own clips and transitions): `razgon_bridge.py frames` renders only the code blocks, then the Studio engine
    exports the whole timeline with each block drawn from its rendered clip. {clip id: frame number} of the blocks."""
    link = store.read_json(info["project"] / "story" / "studio_frames.json", {})
    if link.get("project_id") != project["id"]:
        raise store.StudioError("Проєкт Razgon прив'язано до іншого випуску студії.", 409)
    plan = store.load_project_plan(project["id"]) or {}
    audio = (plan.get("timing") or {}).get("audio") or {}
    if plan.get("script_sha256") != link.get("script_sha256") or audio.get("sha256") != link.get("audio_sha256"):
        raise store.StudioError("План у студії змінився після razgon_bridge.py prepare: кадри Razgon треба оновити.", 409)
    fps = int(link["fps"])
    slots = {f["number"]: _slot(f["start"], f["end"], fps) for f in link["frames"]}
    numbers = {}
    for clip in blocks:
        number = int(FRAME_TITLE.fullmatch(clip["title"]).group(1))
        if _slot(float(clip["start"]), float(clip["start"]) + float(clip["duration"]), fps) != slots.get(number):
            raise store.StudioError(f"Кадр Razgon {number} зсунуто з його місця в плані.", 409)
        numbers[clip["id"]] = number
    return {"mixed": True, "razgon": str(info["project"]), "blocks": numbers}


def frames_command(spec: dict) -> list[str]:
    numbers = ",".join(str(n) for n in sorted(set(spec["blocks"].values())))
    return [sys.executable, str(BRIDGE), "frames", "--razgon", spec["razgon"], "--numbers", numbers]


def point_blocks_at_clips(manifest: dict, spec: dict, clips: dict) -> None:
    """In the engine manifest each code block becomes its frame's rendered clip, full frame and opaque."""
    for layer in manifest.get("timeline_layers", []):
        for clip in layer.get("clips", []):
            number = spec["blocks"].get(clip["id"])
            if number is not None:
                clip.update(type="video", source=clips[str(number)], content_type=None, opacity=1, volume=0.0, trim_start=0.0)


def command(spec_path: Path, staging: Path) -> list[str]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    return [sys.executable, str(BRIDGE), "export", "--razgon", spec["razgon"], "--spec", str(spec_path), "--out", str(staging)]
