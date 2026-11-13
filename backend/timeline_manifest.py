"""Shared Studio timeline manifest for export and finished-frame review."""
import copy
from pathlib import Path

import audio_level
import joins
import store


def valid_local_source(path: Path, project: dict) -> bool:
    branding=(store.under(path,store.DATA_ROOT/'channels'/project['channel_id']/'overlays')
              and any(a.get('source')=='channel-logo' and Path(a.get('path','')).resolve()==path
                      for a in project.get('assets',[])))
    return path.is_file() and (branding or any(store.under(path, root) for root in store.media_roots(project)) or store.under(path, Path(project["episode_path"])))


def build(project: dict, *, visual_only=False, include_transitions=True) -> dict:
    layers = []
    assets = {asset["id"]: asset for asset in store.discover_assets(project)}
    # the voice at 100% is the Studio's standard level (audio_level.py): the export plays its leveled copy, made now
    # if the background has not made it yet
    voices = {} if visual_only else audio_level._voice_paths(project)
    for voice_path in voices.values():
        audio_level.leveled(voice_path, wait=True)
    voice = {} if visual_only else audio_level.voice_gains(project)
    visual_count = 0
    for z, layer in enumerate(project.get("tracks", [])):
        rendered_clips = []
        for clip in layer.get("clips", []):
            kind = clip.get("kind")
            if visual_only and kind == "audio":
                continue
            if layer.get("hidden") and kind != "audio":
                continue   # a row switched off with its eye stays out of the film
            if kind not in {"video", "image", "text", "animation", "audio"}:
                raise store.StudioError("Невідомий тип кліпу")
            source = None
            needs_asset = kind in {"video", "image", "audio"} or kind == "animation" and clip.get("content_type") == "image"
            if needs_asset:
                asset = assets.get(clip.get("asset_id"))
                if asset is None:
                    raise store.StudioError("Для кліпу «%s» ще не вибрано матеріал" % clip.get("title", ""))
                source = Path(asset["path"]).resolve()
                if clip.get("asset_id") in voices:
                    source = audio_level.leveled(source).resolve()
                if source.parent != audio_level.leveled_dir().resolve() and not valid_local_source(source, project):
                    raise store.StudioError("Матеріал кліпу недоступний")
            if kind != "audio":
                visual_count += 1
            rendered_clips.append({"id": clip["id"], "type": kind, "source": str(source) if source else None, "text": clip.get("text", ""), "content_type": clip.get("content_type"), "color": clip.get("color", "#101114"), "start": float(clip["start"]), "duration": float(clip["duration"]), "trim_start": float(clip.get("trim_start", 0)), "volume": 0.0 if layer.get("muted") else float(clip.get("volume", 1)) * (voice.get(clip.get("asset_id"), 1.0) if kind == "audio" else 1.0), "transition": copy.deepcopy(clip.get("transition", {"type": "cut", "duration": 0})), "x": clip.get("x", .5), "y": clip.get("y", .5), "width": clip.get("width", 1), "height": clip.get("height", 1), "scale": clip.get("scale", 1), "opacity": clip.get("opacity", 1), "preset": clip.get("preset"), "preset_duration": clip.get("preset_duration", 0), "keyframes": copy.deepcopy(clip.get("keyframes", [])), "audio_role": clip.get("audio_role"), "easing": clip.get("easing", "linear")})
            for field in ("font_size", "text_words", "mask", "corner_radius", "shadow", "font_family", "font_weight", "text_align", "line_height", "word_entrance", "gradient", "blur", "motion_blur", "visual_effect"):
                if field in clip:
                    rendered_clips[-1][field] = copy.deepcopy(clip[field])
            if not clip.get("preset"):
                rendered_clips[-1].pop("preset")
                rendered_clips[-1].pop("preset_duration")
        layers.append({"id": layer["id"], "z": z, "clips": rendered_clips})
    if include_transitions:
        joins.transport(project,layers)
    if not visual_count:
        raise store.StudioError("Додайте хоча б один візуальний кліп перед експортом")
    return {"width": int(project.get("width", 1920)), "height": int(project.get("height", 1080)), "fps": int(project.get("fps", 30)), "duration": float(project.get("duration", 0)), "layer_mode": "item", "timeline_layers": layers}
