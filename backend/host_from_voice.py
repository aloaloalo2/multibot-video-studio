"""Host frames cut from the voice when the voice is a video of the host (user, 21 November 2026: «якщо я додаю відео,
і в мене в проєкті стоїть ведучий 15%, то чому його не будемо використовувати як в проєкті відео?»).

When the plan's voice asset is a video and the plan has frames in the «host» format, each such frame gets that very
video from the frame's own second (trim_start = the frame's start), muted: the lips match the voice exactly because it
is the same recording. It runs before the frame agent, so the agent sees those frames made and leaves them. No model,
no tokens; frames already on the timeline are left as they are."""
from __future__ import annotations

import math

import montage_ops
import store


def voice_video(project: dict, plan: dict | None) -> dict | None:
    """The plan's voice asset when it is a video file on disk."""
    aid = (((plan or {}).get("timing") or {}).get("audio") or {}).get("asset_id")
    asset = next((a for a in project.get("assets", []) if a.get("id") == aid), None) if aid else None
    if not asset or asset.get("kind") != "video" or not asset.get("path"):
        return None
    return asset


def place(pid: str) -> list[int]:
    """Put the voice video into every host frame not made yet; returns the frame numbers placed."""
    project = store.load_project(pid)
    plan = store.load_project_plan(pid)
    asset = voice_video(project, plan)
    if asset is None:
        return []
    made = set(store.made_frames(project, plan))
    fps = int(project.get("fps") or 25)
    ops = []
    for frame in (plan or {}).get("frames") or []:
        number = int(frame.get("number") or 0)
        if frame.get("format") != "host" or not number or number in made:
            continue
        # the same whole-frame edge montage_ops.place gives the clip, so the picture and the voice stay on one second
        start = math.floor(float(frame["start"]) * fps + .5 + 1e-8) / fps
        # the host's slow 12% zoom, in and out by turns (the channels' rule: a host frame zooms 10-15%)
        ops.append({"op": "place", "frame": number, "asset_id": asset["id"], "trim_start": start,
                    "motion": "zoom_in" if len(ops) % 2 == 0 else "zoom_out"})
    if not ops:
        return []
    montage_ops.run(pid, ops)
    return [op["frame"] for op in ops]
