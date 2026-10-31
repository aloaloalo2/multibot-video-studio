"""Short views of the studio for agents: what runs now, and a project frame by frame with its problems.

A project answer is about half a megabyte on a long episode (GORBUNOV-23: 284 clips); an agent that only needs to know
what each frame holds and what is wrong reads a few lines per frame instead (GET /api/projects/<id>/summary).
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import montage_ops
import store

BUSY = {"queued", "running", "in_progress", "cancelling"}


def _name(clip: dict, assets: dict) -> str:
    if clip.get("kind") == "text" or clip.get("content_type") == "text":
        text = " ".join(str(clip.get("text", "")).split())
        return "«" + (text[:34] + "…" if len(text) > 35 else text) + "»"
    if clip.get("asset_id"):
        name = Path(assets.get(clip["asset_id"], {}).get("path", "") or clip.get("title", "")).name
        return name if len(name) <= 30 else name[:14] + "…" + name[-14:]
    if str(clip.get("title", "")).startswith("Razgon"):
        return "блок Razgon"
    return clip.get("content_type") or clip.get("kind", "")


def _motion(clip: dict) -> str:
    points = clip.get("keyframes") or []
    if not points:
        return ""
    start, end = 0.0, float(clip.get("duration", 0))
    s0, s1 = (montage_ops.keyframe_value(clip, "scale", t) for t in (start, end))
    x0, x1 = (montage_ops.keyframe_value(clip, "x", t) for t in (start, end))
    parts = []
    if abs(s1 - s0) > 1e-3:
        parts.append(f"зум {s0:.2f}→{s1:.2f}")
    if abs(x1 - x0) > 1e-3:
        parts.append(f"зсув {100 * (x1 - x0):+.0f}%")
    return " ".join(parts)


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def _uncovered(project: dict, clip: dict) -> str | None:
    """A full-frame landscape photo that leaves a strip of the frame empty at its start, middle or end."""
    if clip.get("kind") != "image" or float(clip.get("width", 1)) < .999 or float(clip.get("height", 1)) < .999:
        return None
    try:
        picture = montage_ops.Picture(project, clip)
    except (store.StudioError, OSError, KeyError):
        return None
    if picture.portrait:
        return None
    for moment in (0.0, picture.duration / 2, picture.duration - 1e-3):
        x, y, s = picture.state(moment)
        left, right = x * picture.W - picture.cw * s / 2, x * picture.W + picture.cw * s / 2
        top, bottom = y * picture.H - picture.ch * s / 2, y * picture.H + picture.ch * s / 2
        gap = max(left, top, picture.W - right, picture.H - bottom)
        if gap > 1.5:
            return f"відкритий край {gap:.0f}px на {moment:.1f}с"
    return None


def project_summary(project: dict, readiness: dict | None = None, plan: dict | None = None) -> dict:
    """{"head": [...lines], "frames": [{"n", "line", "issues"}], "issues": [...]} — the text an agent reads."""
    if plan is None:
        try:
            plan = store.load_project_plan(project["id"])
        except (store.StudioError, OSError, ValueError):
            plan = None
    fps = float(project.get("fps", 30))
    tolerance = 1 / fps + 1e-3
    assets = {a["id"]: a for a in project.get("assets", [])}
    frames = montage_ops.frame_groups(project, plan)
    joins_by_from = {j["from_ref"]: j for j in project.get("join_transitions", [])}
    issues, rows = [], []
    formats = Counter()
    for index, frame in enumerate(frames):
        problems = []
        plan_frame = frame.get("plan")
        fmt = plan_frame.get("format") if plan_frame else None
        main = montage_ops.main_picture(project, frame)
        if not fmt:
            fmt = "razgon_2d" if any(str(c.get("title", "")).startswith("Razgon") for c in frame["clips"]) else \
                "text" if any(c.get("text_role") == "full_frame" for c in frame["clips"]) else (main or {}).get("kind", "?")
        formats[fmt] += frame["end"] - frame["start"]
        if plan_frame and (abs(plan_frame["start"] - frame["start"]) > tolerance or abs(plan_frame["end"] - frame["end"]) > tolerance):
            problems.append(f"межі не як у плані ({plan_frame['start']:.2f}–{plan_frame['end']:.2f})")
        following = frames[index + 1] if index + 1 < len(frames) else None
        if following and following["start"] - frame["end"] > tolerance:
            problems.append(f"порожньо {following['start'] - frame['end']:.2f}с до наступного")
        if following and frame["end"] - following["start"] > tolerance and not joins_by_from.get("group:" + frame["group"]["id"]):
            problems.append(f"заходить на наступний на {frame['end'] - following['start']:.2f}с")
        accents = Counter()
        for clip in frame["clips"]:
            if clip.get("asset_id"):
                try:
                    asset = store.resolve_asset(project, clip["asset_id"])
                except store.StudioError:
                    problems.append(f"немає файлу «{clip.get('title')}»")
                    continue
                if clip.get("kind") == "video":
                    available = store.media_duration(Path(asset["path"]))
                    join = joins_by_from.get("group:" + frame["group"]["id"])
                    tail = float(join["duration"]) if join and abs(float(clip["start"]) + float(clip["duration"]) - frame["end"]) < .05 else 0
                    if available and float(clip.get("trim_start", 0)) + float(clip["duration"]) + tail > available + .04:
                        problems.append(f"відео «{clip.get('title')}» коротше за кадр{' з переходом' if tail else ''}")
            late = [p for p in clip.get("keyframes") or [] if float(p["time"]) > float(clip["duration"]) + 1e-6]
            if late:
                problems.append(f"ключі після кінця «{clip.get('title')}»")
            if clip.get("text_words") and any(float(w["start"]) > float(clip["duration"]) for w in clip["text_words"]):
                problems.append(f"слова після кінця «{clip.get('title')}»")
            if montage_ops.is_accent(clip):
                accents[str(clip.get("title", "")).split()[-1]] += 1
        uncovered = _uncovered(project, main) if main else None
        if uncovered:
            problems.append(uncovered)
        join = joins_by_from.get("group:" + frame["group"]["id"])
        content = (f"{main.get('kind')} {_name(main, assets)} {_motion(main)}".strip() if main else
                   ", ".join(_name(c, assets) for c in frame["clips"][:2]))
        extra = " +" + " ".join(f"{k}{v if v > 1 else ''}" for k, v in sorted(accents.items())) if accents else ""
        out = f" → {join['type']} {float(join['duration']):.2f}" if join else ""
        number = frame["number"] if frame["number"] is not None else frame["group"].get("title")
        line = f"{number:>4} {_clock(frame['start'])}–{_clock(frame['end'])} {fmt:<15} {content}{extra}{out}"
        rows.append({"n": number, "start": round(frame["start"], 3), "end": round(frame["end"], 3), "format": fmt, "group_id": frame["group"]["id"],
                     "line": line, "issues": problems})
        issues += [f"кадр {number}: {p}" for p in problems]
    seams = sum(1 for a, b in zip(frames, frames[1:]) if abs(a["end"] - b["start"]) <= tolerance)
    designed = len(project.get("join_transitions", []))
    into_text = sum(1 for j in project.get("join_transitions", []) for f in frames
                    if "group:" + f["group"]["id"] == j["to_ref"] and montage_ops._full_frame_text(f))
    repeats = 0
    ordered = [joins_by_from.get("group:" + f["group"]["id"]) for f in frames]
    for a, b in zip(ordered, ordered[1:]):
        if a and b and a["type"] == b["type"] and a["type"] != "crossfade":
            repeats += 1
    if into_text:
        issues.append(f"переходів у текстові кадри: {into_text} (там має бути склейка)")
    if repeats:
        issues.append(f"однакових переходів поспіль (крім розчинення): {repeats}")
    clips = [c for t in project.get("tracks", []) for c in t.get("clips", [])]
    voices = [c for c in clips if c.get("kind") == "audio" and c.get("asset_id") in (project.get("audio_gain") or {})]
    for voice in voices:
        if abs(float(voice.get("volume", 1)) - 1) > 1e-6:
            issues.append(f"озвучка «{voice.get('title')}» на {float(voice['volume']) * 100:.0f}%, стандарт 100%")
    plate = next((g for g in project.get("scene_groups", []) if g.get("role") == "overlay"), None)
    if plate:
        top = {c["id"] for t in project["tracks"][-len(plate["clip_ids"]):] for c in t["clips"]}
        if not set(plate["clip_ids"]) <= top:
            issues.append("плашка каналу не на верхніх шарах")
    readiness = readiness or {}
    total = sum(formats.values()) or 1
    head = [f"{project.get('name')} · {project['id']} · rev {project.get('revision', 0)} · {_clock(float(project.get('duration', 0)))} · {int(fps)} fps",
            f"план: {(plan or {}).get('timing', {}).get('status', 'немає')} · експорт: {'готовий' if readiness.get('export_ready') else readiness.get('reason') or '?'}",
            f"кадрів {len(frames)}: " + ", ".join(f"{k} {100 * v / total:.0f}%" for k, v in formats.most_common()),
            f"стиків {seams}, переходів {designed} ({100 * designed / max(1, seams):.0f}%), шарів {len(project.get('tracks', []))}, кліпів {len(clips)}"]
    return {"head": head, "fps": int(fps), "revision": project.get("revision", 0), "frames": rows, "issues": issues}


def studio_status(active_exports: list[dict], project_jobs) -> dict:
    """What the studio is doing now: running exports and every project's busy jobs (the list studio_restart.py checks
    before a restart). `project_jobs(pid)` gives {what: status} for one project."""
    busy = [f"експорт {job['project_id']}: {job.get('progress', 0)}%, {job.get('stage', '')}" for job in active_exports if job.get("status") in BUSY]
    names = {c["id"]: c.get("name") for c in store.list_channels()}
    for item in store.list_projects():
        for what, status in project_jobs(item["id"]).items():
            if status in BUSY:
                busy.append(f"{what}: {names.get(item.get('channel_id'), '')} / {item.get('name') or item['id']} ({item['id']})")
    return {"busy": busy, "exports": active_exports}
