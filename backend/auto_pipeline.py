"""«Автоекспорт» and «Автопублікація» of a channel (its settings, section «Автоматика»; user, 19 November 2026: «додай
Автоекспорт і автопублікація»).

Every minute the studio looks at the episodes of channels with these boxes on:
- auto_export: frames made by the frame agent (its request done and passed) and no export after them; once nothing
  works on the episode (director, frames, the film's music), the export starts with the channel's quality;
- auto_publish: an export finished and the episode is not on YouTube nor waiting for it: it goes into the publishing
  queue (backend/published.py), which a publishing Claude session takes.

Only what happens after a box is switched on counts: switching it on never exports or publishes a channel's older
episodes (the moment is kept per channel in auto-pipeline.json). Each episode is handled once per frame run and once per
export (auto-export.json, auto-publish.json beside the project)."""
from __future__ import annotations

import threading
import time

import store

EVERY = 60
STATE = "auto-pipeline.json"
# a finished frame run or export wakes the loop at once (user, 21 November 2026: «кадри, галочка висить там 10 секунд, і
# тоді починається експорт»; «висить кнопка опублікувати… а потім… запускається»): the next step starts within a second
WAKE = threading.Event()


def kick() -> None:
    WAKE.set()


def due(project: dict, settings: dict, exported: float, since: dict) -> str | None:
    """«export» or «publish» when the channel's automation is about to do that step for this episode, else None. The
    card shows that step as coming instead of a button the author might press meanwhile. `since` holds the moments the
    boxes went on ({"auto_export": t, "auto_publish": t}, None when off)."""
    import published
    pid = project["id"]
    folder = store.project_dir(pid)
    request = project.get("production_request") or {}
    finished = float(request.get("finished_at") or 0)
    export_since, publish_since = since.get("auto_export"), since.get("auto_publish")
    if (export_since is not None and request.get("status") == "done" and (request.get("quality") or {}).get("passed") is not False
            and finished > export_since and exported < finished
            and (store.read_json(folder / "auto-export.json", {}) or {}).get("request") != request.get("id")):
        return "export"
    mark = store.read_json(published.path(pid), {}) or {}
    if (publish_since is not None and exported > publish_since and not mark.get("at")
            and published.publishing({"id": pid, "published": mark}) is None
            and float((store.read_json(folder / "auto-publish.json", {}) or {}).get("export_at") or 0) < exported):
        return "publish"
    return None


def listed(item: dict, project: dict, settings: dict) -> str | None:
    """due() for the project list, reading the switch-on moments without writing them."""
    cid = item.get("channel_id")
    flags = [flag for flag in ("auto_export", "auto_publish") if settings.get(flag) is True]
    if not flags:
        return None
    row = (store.read_json(store.DATA_ROOT / STATE, {}) or {}).get(cid) or {}
    since = {flag: (row.get(flag) if flag in flags else None) for flag in ("auto_export", "auto_publish")}
    if since["auto_export"] is None and since["auto_publish"] is None:
        return None
    return due(project, settings, float(item.get("last_export_at") or 0), since)


def _since(cid: str, flag: str, on: bool) -> float | None:
    """When the channel's box was first seen on (None while it is off); switching it off forgets the moment."""
    path = store.DATA_ROOT / STATE
    data = store.read_json(path, {}) or {}
    row = data.setdefault(cid, {})
    if not on:
        if flag in row:
            row.pop(flag)
            store.atomic_json(path, data)
        return None
    if flag not in row:
        row[flag] = time.time()
        store.atomic_json(path, data)
    return row[flag]


def _busy(pid: str, active_export) -> bool:
    import director
    import production
    import razgon_sound
    sound = (razgon_sound.state(pid) or {}).get("status") in {"queued", "running"}
    return bool(active_export(pid)) or pid in production.ACTIVE or pid in director.ACTIVE or pid in razgon_sound.ACTIVE or sound


def tick(start_export, active_export) -> list[str]:
    """One round over the episodes of the channels with a box on. Each project.json is read through the list's cache
    (store.listed_project, parsed once per version of the file) and the conditions are due()'s own; the whole project
    is loaded only for an episode about to export (it used to load every episode of those channels every minute:
    39 projects, 16 MB of JSON, about 1.2 s of parsing a round)."""
    import completion_notices
    import published
    done, channels = [], {}
    for channel in store.list_channels():
        cid = channel.get("id")
        try:
            settings = store.read_channel_settings(store.get_channel_folder(cid), {}) or {}
        except (store.StudioError, OSError):
            continue
        since = {flag: _since(cid, flag, settings.get(flag) is True) for flag in ("auto_export", "auto_publish")}
        if since["auto_export"] is not None or since["auto_publish"] is not None:
            channels[cid] = (settings, since)
    if not channels or not store.PROJECTS_ROOT.is_dir():
        return done
    for path in store.PROJECTS_ROOT.glob("*/project.json"):
        try:
            item = store.listed_project(path)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, store.StudioError):
            continue
        if item.get("deleted_at") or item.get("channel_id") not in channels or not item.get("id"):
            continue
        settings, since = channels[item["channel_id"]]
        pid = item["id"]
        folder = store.project_dir(pid)
        exported = float(((store.read_json(completion_notices.path(pid), {}) or {}).get("export") or {}).get("at") or 0)
        # each step on its own, as before: a new frame run may export while the previous export goes to YouTube
        if (due(item, settings, exported, {"auto_export": since["auto_export"]}) == "export"
                and not _busy(pid, active_export)):
            try:
                project = store.load_project(pid)
            except store.StudioError:
                project = None
            if project and store.plan_readiness(project).get("export_ready"):
                request = project.get("production_request") or {}
                quality = settings.get("video_quality") if settings.get("video_quality") in store.VIDEO_QUALITIES else "standard"
                choices = store.video_bitrates(int(project.get("width") or 1920), int(project.get("height") or 1080), int(project.get("fps") or 25))
                store.atomic_json(folder / "auto-export.json", {"request": request.get("id"), "at": time.time()})
                try:
                    start_export(project, True, choices[store.VIDEO_QUALITIES.index(quality)])
                    done.append(f"export {pid}")
                except store.StudioError as error:
                    store.atomic_json(folder / "auto-export.json", {"request": request.get("id"), "at": time.time(), "error": str(error)})
        if (due(item, settings, exported, {"auto_publish": since["auto_publish"]}) == "publish"
                and not active_export(pid)):
            store.atomic_json(folder / "auto-publish.json", {"export_at": exported, "at": time.time()})
            try:
                published.enqueue(pid)
                done.append(f"publish {pid}")
            except store.StudioError:
                pass
    return done


def start(start_export, active_export) -> None:
    def loop():
        while True:
            try:
                tick(start_export, active_export)
            except Exception:
                import traceback
                traceback.print_exc()
            WAKE.wait(EVERY)
            WAKE.clear()
    threading.Thread(target=loop, name="auto-pipeline", daemon=True).start()
