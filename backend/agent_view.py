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


def _picture(project: dict, clip: dict):
    """The clip as the export draws it, or None when its file cannot be read."""
    if clip.get("kind") != "image":
        return None
    try:
        return montage_ops.Picture(project, clip)
    except (store.StudioError, OSError, KeyError):
        return None


SLIVER = .03   # a strip up to 3% of the frame over a field is an accident, a wider one a designed margin


def _uncovered(project: dict, clip: dict, picture=None, field: bool = False) -> str | None:
    """A full-frame landscape photo that leaves a strip of the frame empty at its start, middle or end. Over a solid
    field (the black ground the studio puts under every frame) only a thin strip counts: a few pixels at the edges
    are a picture that missed the frame, a wide margin is the frame's design (26 November 2026)."""
    if clip.get("kind") != "image" or float(clip.get("width", 1)) < .999 or float(clip.get("height", 1)) < .999:
        return None
    picture = picture or _picture(project, clip)
    if picture is None or picture.portrait:
        return None
    for moment in (0.0, picture.duration / 2, picture.duration - 1e-3):
        x, y, s = picture.state(moment)
        left, right = x * picture.W - picture.cw * s / 2, x * picture.W + picture.cw * s / 2
        top, bottom = y * picture.H - picture.ch * s / 2, y * picture.H + picture.ch * s / 2
        gaps = [left, top, picture.W - right, picture.H - bottom]
        if field:
            gaps = [g for g in gaps if g <= SLIVER * min(picture.W, picture.H)]
        gap = max(gaps, default=0.0)
        if gap > 1.5:
            return f"відкритий край {gap:.0f}px на {moment:.1f}с"
    return None


def _bare_portrait(project: dict, clip: dict, frame: dict, picture=None, level: dict | None = None) -> bool:
    """A narrow picture (narrower than the frame) with no full-frame clip under it in its own frame."""
    if clip.get("kind") != "image":
        return False
    picture = picture or _picture(project, clip)
    if picture is None or not picture.portrait:
        return False
    if level is None:
        level = {c["id"]: i for i, track in enumerate(project.get("tracks", [])) for c in track.get("clips", [])}
    mine = level.get(clip["id"], 0)
    return not any(c is not clip and level.get(c["id"], 0) < mine and c.get("kind") in ("image", "video", "animation")
                   and float(c.get("width", 1)) >= .99 and float(c.get("height", 1)) >= .99 for c in frame["clips"])


def _solid_backing(clip: dict, picture: dict) -> bool:
    """A stationary opaque field must cover the whole picture interval and the whole canvas."""
    if (clip.get("kind") != "animation" or clip.get("content_type") != "shape"
            or not str(clip.get("title", "")).endswith(" фон") or clip.get("keyframes")
            or clip.get("mask", "none") != "none" or float(clip.get("rotation", 0)) != 0
            or float(clip.get("opacity", 1)) < 1):
        return False
    color = str(clip.get("color", ""))
    if len(color) != 7 or not color.startswith("#"):
        return False
    start, duration = float(clip.get("start", 0)), float(clip.get("duration", 0))
    pstart = float(picture.get("start", 0))
    if start > pstart + 1e-6 or start + duration < pstart + float(picture.get("duration", 0)) - 1e-6:
        return False
    scale = float(clip.get("scale", 1))
    return all(float(clip.get(size, 0)) * scale >= 1 + 2 * abs(float(clip.get(axis, .5)) - .5)
               for size, axis in (("width", "x"), ("height", "y")))


def project_summary(project: dict, readiness: dict | None = None, plan: dict | None = None) -> dict:
    """{"head": [...lines], "frames": [{"n", "line", "issues"}], "issues": [...]} — the text an agent reads."""
    if plan is None:
        plan = montage_ops.project_plan(project)
    fps = float(project.get("fps", 30))
    tolerance = 1 / fps + 1e-3
    assets = {a["id"]: a for a in project.get("assets", [])}
    frames = montage_ops.frame_groups(project, plan)
    level = {c["id"]: i for i, track in enumerate(project.get("tracks", [])) for c in track.get("clips", [])}
    resolved: dict[str, dict | None] = {}   # asset id -> its file (one asset often stands in several clips)
    lengths: dict[str, float | None] = {}

    def resolve(aid: str) -> dict | None:
        if aid not in resolved:
            try:
                resolved[aid] = store.resolve_asset(project, aid)
            except store.StudioError:
                resolved[aid] = None
        return resolved[aid]

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
                asset = resolve(clip["asset_id"])
                if asset is None:
                    problems.append(f"немає файлу «{clip.get('title')}»")
                    continue
                if clip.get("kind") == "video":
                    if asset["path"] not in lengths:
                        lengths[asset["path"]] = store.media_duration(Path(asset["path"]))
                    available = lengths[asset["path"]]
                    # a transition going out past the video's end holds its last picture (joins.held_source): only a
                    # video shorter than its own frame is a problem
                    if available and float(clip.get("trim_start", 0)) + float(clip["duration"]) > available + .04:
                        problems.append(f"відео «{clip.get('title')}» коротше за кадр")
            late = [p for p in clip.get("keyframes") or [] if float(p["time"]) > float(clip["duration"]) + 1e-6]
            if late:
                problems.append(f"ключі після кінця «{clip.get('title')}»")
            if clip.get("text_words") and any(float(w["start"]) > float(clip["duration"]) for w in clip["text_words"]):
                problems.append(f"слова після кінця «{clip.get('title')}»")
            if montage_ops.is_accent(clip) and not montage_ops.is_entrance(clip):
                accents[str(clip.get("title", "")).split()[-1]] += 1
        field = main and any(_solid_backing(c, main) for c in frame["clips"] if c is not main)
        picture = _picture(project, main) if main else None
        uncovered = _uncovered(project, main, picture, bool(field)) if picture else None
        if uncovered:
            problems.append(uncovered)
        elif picture and _bare_portrait(project, main, frame, picture, level):
            # a vertical photo with nothing under it on the whole frame: its sides show the neighbour frame in every
            # transition (22 November 2026: «під картинкою нема просто чорного фона»)
            problems.append("вертикальне фото без тла: під ним нічого на весь кадр")
        if fmt == "text":
            # nothing new comes on over the background once the frame is in: no word, no drawing (22 November 2026: «36
            # кадр стоїть без тексту 2 секунди»; 27 November 2026, Astéroïde 37 and 86: «це вважається вже… як брак»). A
            # motion-code layer counts from the moment it draws something new, and what came in under the transition into
            # the frame does not count («як будто воно там було»)
            came_in = montage_ops.incoming(project, frame)
            alive = montage_ops.first_shown(project, frame, came_in)
            if alive is None or alive - came_in > montage_ops.LEAD_GAP:
                wait = (alive if alive is not None else frame["end"] - frame["start"]) - came_in
                problems.append(f"мертвий кадр {wait:.1f} с після переходу: нічого не з'являється (графіка чи слово з голосом)")
            # the voice says why we are here before the words on screen do («чому ми перейшли до нього, не ясно»)
            shown = [float(c["start"]) + min((float(w.get("start", 0)) for w in c.get("text_words") or []), default=0.0)
                     for c in frame["clips"] if c.get("kind") == "text" and str(c.get("text") or "").strip()]
            timings = (plan_frame or {}).get("sentence_timings") or []
            spoken = max(frame["start"], float(timings[0]["start"])) if timings else frame["start"]
            if shown and min(shown) - spoken > montage_ops.LEAD_GAP:
                problems.append(f"текст запізнюється за голосом на {min(shown) - spoken:.1f} с (lead_text дає підводку)")
            if montage_ops.text_layout_changes(frame, (int(project.get("width") or 1920), int(project.get("height") or 1080))):
                # its words stand off the middle or apart from one another (Andromeda 40, 25 November 2026)
                problems.append("текст розкиданий, не одним блоком по центру (compose_text збирає)")
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
    # a host or full-frame text frame comes in and goes out with a transition (user, 21 November 2026)
    joined = {(j["from_ref"], j["to_ref"]) for j in project.get("join_transitions", [])}
    bare = sum(1 for a, b in zip(frames, frames[1:]) if abs(a["end"] - b["start"]) <= tolerance
               and (montage_ops._host_or_text(a) or montage_ops._host_or_text(b))
               and ("group:" + a["group"]["id"], "group:" + b["group"]["id"]) not in joined)
    repeats = 0
    ordered = [joins_by_from.get("group:" + f["group"]["id"]) for f in frames]
    for a, b in zip(ordered, ordered[1:]):
        if a and b and a["type"] == b["type"] and a["type"] != "crossfade":
            repeats += 1
    if bare:
        issues.append(f"стиків біля кадрів ведучого чи тексту без переходу: {bare} (там завжди перехід)")
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


def studio_status(active_exports: list[dict], project_jobs, candidates=None) -> dict:
    """What the studio is doing now: running exports and every project's busy jobs (the list studio_restart.py checks
    before a restart). `project_jobs(pid)` gives {what: status} for one project; `candidates`, when given, are the only
    projects that can be busy (the work this server holds in memory), so the rest are not read at all."""
    busy = [f"експорт {job['project_id']}: {job.get('progress', 0)}%, {job.get('stage', '')}" for job in active_exports if job.get("status") in BUSY]
    names = {c["id"]: c.get("name") for c in store.list_channels()}
    active_channels, exporting = set(), set()
    activities = []
    for job in active_exports:
        if job.get("status") in BUSY:
            try:
                exporting.add(store.listed_project(store.project_dir(job["project_id"]) / "project.json").get("channel_id"))
            except (OSError, ValueError, store.StudioError):
                pass
    active_channels |= exporting
    for pid in sorted(candidates) if candidates is not None else [item["id"] for item in store.list_projects()]:
        try:
            item = store.listed_project(store.project_dir(pid) / "project.json")
        except (OSError, ValueError, store.StudioError):
            continue
        if item.get("deleted_at"):
            continue
        for what, status in project_jobs(item["id"]).items():
            if status in BUSY:
                activities.append({"project_id": pid, "channel_id": item.get("channel_id"), "kind": what, "status": status})
                active_channels.add(item.get("channel_id"))
                busy.append(f"{what}: {names.get(item.get('channel_id'), '')} / {item.get('name') or pid} ({pid})")
    import published   # an episode waiting for or going through its YouTube publication turns its channel's spinner
    publishing = published.active_channels()
    active_channels |= publishing
    # a channel with an export running or queued shows its spinner in the export's amber (user, 14 November 2026)
    return {"busy": busy, "exports": active_exports, "active_channels": sorted(x for x in active_channels if x),
            "exporting_channels": sorted(x for x in exporting if x), "activities": activities,
            "publishing_channels": sorted(publishing - {x for x in active_channels if x in exporting})}
