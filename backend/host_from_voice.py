"""Host frames cut from the voice when the voice is a video of the host (user, 21 November 2026: «якщо я додаю відео,
і в мене в проєкті стоїть ведучий 15%, то чому його не будемо використовувати як в проєкті відео?»).

When the plan's voice asset is a video and the plan has frames in the «host» format, each such frame gets that very
video from the frame's own second (trim_start = the frame's start), muted: the lips match the voice exactly because it
is the same recording. It runs before the frame agent, so the agent sees those frames made and leaves them. No model,
no tokens; frames already on the timeline are left as they are."""
from __future__ import annotations

import hashlib
import random
import json
import math
from pathlib import Path

import montage_ops
import store


def _source_video(project: dict, sha: str | None) -> str | None:
    """The video the recognition took the voice from: a video voice is recognised from a sound track cut out of it
    (analysis_jobs), so the plan keeps only that sound's hash; the recognition's result names the video it came from."""
    if not sha:
        return None
    try:
        folder = store.project_dir(project["id"]) / "analysis"
    except store.StudioError:
        return None
    for result in sorted(folder.glob("*/result.json"),
                         key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            report = json.loads(result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        source = report.get("source") or {}
        if (report.get("audio") or {}).get("sha256") == sha and source.get("kind") == "video":
            return source.get("asset_id")
    return None


def voice_video(project: dict, plan: dict | None) -> dict | None:
    """The plan's voice when it is a video of the host on disk: the voice asset itself, or the video its sound came from."""
    audio = ((plan or {}).get("timing") or {}).get("audio") or {}
    aid = audio.get("asset_id")
    asset = next((a for a in project.get("assets", []) if a.get("id") == aid), None) if aid else None
    if not asset or asset.get("kind") != "video":
        found = _source_video(project, audio.get("sha256")) if project.get("id") else None
        asset = next((a for a in project.get("assets", []) if a.get("id") == found), None) if found else None
    if not asset or asset.get("kind") != "video" or not asset.get("path") or not Path(asset["path"]).is_file():
        return None
    return asset


MOVES = ("zoom_in", "zoom_out")


def host_directions(seed: str, count: int) -> list[str]:
    """The zoom of each host frame in its film's order (user, 26 November 2026: «зум чи не зум… уникализовувати, але
    перший кадр точно наближатись»): the first comes in, the others go in or out in an order of this film's own, the same
    every time the film is made and never three alike in a row."""
    rng = random.Random(int(hashlib.sha256(f"{seed}|host-zoom".encode()).hexdigest()[:16], 16))
    moves = ["zoom_in"][:max(0, count)]
    while len(moves) < count:
        pick = rng.choice(MOVES)
        if len(moves) >= 2 and moves[-1] == moves[-2] == pick:
            pick = MOVES[1 - MOVES.index(pick)]
        moves.append(pick)
    return moves


def host_bases(seed: str, count: int) -> list[float]:
    """The nearer end of each host frame's zoom, in percent above the whole picture: 0 to 6 by half points in an order of
    the film's own, two neighbours at least 1.5 apart (user, 26 November 2026: «в кожному кадрі є кадр 100%… має бути
    якась така різнообразія. В одному 100, в другому 105, в третьому 102»)."""
    rng = random.Random(int(hashlib.sha256(f"{seed}|host-zoom-base".encode()).hexdigest()[:16], 16))
    bases: list[float] = []
    while len(bases) < count:
        pick = rng.randint(0, 12) / 2
        if not bases or abs(pick - bases[-1]) >= 1.5:
            bases.append(pick)
    return bases


def host_index(plan: dict | None, number: int) -> int:
    hosts = [int(f.get("number") or 0) for f in (plan or {}).get("frames", []) if f.get("format") == "host"]
    return hosts.index(number) if number in hosts else 0


def host_base(seed: str, plan: dict | None, number: int) -> float:
    index = host_index(plan, number)
    return host_bases(seed, index + 1)[index]


def host_move(seed: str, plan: dict | None, number: int) -> str:
    """The zoom of plan frame `number`, counted along the film's host frames."""
    hosts = [int(f.get("number") or 0) for f in (plan or {}).get("frames", []) if f.get("format") == "host"]
    index = hosts.index(number) if number in hosts else 0
    return host_directions(seed, index + 1)[index]


def place(pid: str, redo: bool = False) -> list[int]:
    """Put the voice video into every host frame not made yet; returns the frame numbers placed. `redo` takes off
    host frames made otherwise (a picture drawn of the host before this existed) and puts the video in their place."""
    project = store.load_project(pid)
    plan = store.load_project_plan(pid)
    asset = voice_video(project, plan)
    if asset is None:
        return []
    made = set(store.made_frames(project, plan))
    fps = int(project.get("fps") or 25)
    length = store.media_duration(Path(asset["path"])) or 0
    ops, removed = [], []
    for frame in (plan or {}).get("frames") or []:
        number = int(frame.get("number") or 0)
        if frame.get("format") != "host" or not number or (number in made and not redo):
            continue
        start = math.floor(float(frame["start"]) * fps + .5 + 1e-8) / fps
        if length and length - start < float(frame["end"]) - start - 1 / fps:
            # the closing pause after the last words runs past the video: that frame stays as it is (montage_ops
            # refuses a video shorter than its frame)
            continue
        # (start above is the same whole-frame edge montage_ops.place gives the clip: picture and voice on one second)
        if number in made:
            removed.append({"op": "remove", "frame": number})
        # the host's slow 12% zoom; the first host frame comes in, the rest in this film's own order (host_directions)
        ops.append({"op": "place", "frame": number, "asset_id": asset["id"], "trim_start": start,
                    "motion": host_move(pid, plan, number), "zoom_base": host_base(pid, plan, number)})
    if not ops:
        return []
    if removed:
        # a frame still on the timeline refuses a place within the same batch, so the old frames go first
        montage_ops.run(pid, removed)
    montage_ops.run(pid, ops)
    return [op["frame"] for op in ops]
