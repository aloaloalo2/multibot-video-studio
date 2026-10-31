"""The channel logo from the channel settings as the top layer of a project's timeline, over the whole video.

The logo is drawn into a transparent full-frame PNG with the same placement rule as everywhere else
(channel_branding.box), imported into the project and laid on its own top layer «Логотип каналу» as an overlay group,
so it is seen in the editor and in exports. A logo that changed, or a video that got longer, replaces the old clip; a
logo switched off or removed in the settings takes the layer away.
"""
from __future__ import annotations

from pathlib import Path

import channel_branding
import store

LOGO_TITLE = "Логотип каналу"


def clips(project: dict):
    return [(track, clip) for track in project.get("tracks", []) for clip in track.get("clips", []) if clip.get("title") == LOGO_TITLE]


def remove(pid: str) -> None:
    for track, clip in clips(store.load_project(pid)):
        store.apply_action(pid, "delete_clip", {"clip_id": clip["id"]})
        if len(track.get("clips", [])) == 1:
            store.apply_action(pid, "remove_layer", {"layer_id": track["id"]})


def place(pid: str) -> bool:
    """Put (or refresh) the channel logo layer on top of the project's timeline; False when the channel has no logo on."""
    project = store.load_project(pid)
    channel = next((c for c in store.list_channels() if c["id"] == project.get("channel_id")), None)
    logo = channel_branding.placement((channel or {}).get("settings", {}).get("logo"))
    source = channel_branding.logo_path(project.get("channel_id", ""))
    duration = float(project.get("duration") or 0)
    if not channel or not logo["enabled"] or not source.is_file() or duration <= 0:
        remove(pid)
        return False
    width, height = int(project.get("width") or 1920), int(project.get("height") or 1080)
    stamp = f"{source.stat().st_mtime_ns}-{logo['position']}-{logo['size']}-{logo['margin']}-{logo['opacity']}-{width}x{height}"
    name = f"Логотип каналу {stamp}.png"
    current = clips(project)
    if len(current) == 1:
        track, clip = current[0]
        asset = next((a for a in project.get("assets", []) if a.get("id") == clip.get("asset_id")), {})
        whole = abs(float(clip.get("start", 0))) < 1e-3 and abs(float(clip["start"]) + float(clip["duration"]) - duration) < 1e-3
        if whole and Path(asset.get("path", "")).name == name:
            # frames added later get layers above it: keep the logo the very top layer
            top = len(project["tracks"]) - 1
            if project["tracks"].index(track) != top:
                store.apply_action(pid, "move_layer", {"layer_id": track["id"], "to_index": top})
            return True
    remove(pid)
    target = store.project_dir(pid) / "branding" / name
    if not target.is_file():
        channel_branding.overlay_png(project["channel_id"], logo, (width, height), target)
    asset = store.import_asset_file(store.load_project(pid), target, "channel-logo")
    project = store.apply_action(pid, "add_layer", {"name": LOGO_TITLE, "to_index": len(store.load_project(pid)["tracks"])})
    layer = [track for track in project["tracks"] if track.get("name") == LOGO_TITLE and not track.get("clips")][-1]
    project = store.apply_action(pid, "add_clip", {"layer_id": layer["id"], "kind": "image", "asset_id": asset["id"],
                                                   "start": 0, "duration": duration, "title": LOGO_TITLE})
    clip = clips(project)[0][1]
    store.apply_action(pid, "group_clips", {"clip_ids": [clip["id"]], "title": LOGO_TITLE, "role": "overlay"})
    return True
