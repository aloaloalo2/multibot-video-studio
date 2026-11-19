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
    import completion_notices
    import published
    done = []
    for channel in store.list_channels():
        cid = channel.get("id")
        try:
            settings = store.read_channel_settings(store.get_channel_folder(cid), {}) or {}
        except (store.StudioError, OSError):
            continue
        export_since = _since(cid, "auto_export", settings.get("auto_export") is True)
        publish_since = _since(cid, "auto_publish", settings.get("auto_publish") is True)
        if export_since is None and publish_since is None:
            continue
        for item in store.list_projects(cid):
            pid = item["id"]
            try:
                project = store.load_project(pid)
            except store.StudioError:
                continue
            if project.get("deleted_at"):
                continue
            folder = store.project_dir(pid)
            exported = float(((store.read_json(completion_notices.path(pid), {}) or {}).get("export") or {}).get("at") or 0)
            request = project.get("production_request") or {}
            finished = float(request.get("finished_at") or 0)
            if (export_since is not None and request.get("status") == "done" and (request.get("quality") or {}).get("passed") is not False
                    and finished > export_since and exported < finished
                    and (store.read_json(folder / "auto-export.json", {}) or {}).get("request") != request.get("id")
                    and not _busy(pid, active_export) and store.plan_readiness(project).get("export_ready")):
                quality = settings.get("video_quality") if settings.get("video_quality") in store.VIDEO_QUALITIES else "standard"
                choices = store.video_bitrates(int(project.get("width") or 1920), int(project.get("height") or 1080), int(project.get("fps") or 25))
                store.atomic_json(folder / "auto-export.json", {"request": request.get("id"), "at": time.time()})
                try:
                    start_export(project, True, choices[store.VIDEO_QUALITIES.index(quality)])
                    done.append(f"export {pid}")
                except store.StudioError as error:
                    store.atomic_json(folder / "auto-export.json", {"request": request.get("id"), "at": time.time(), "error": str(error)})
            mark = store.read_json(published.path(pid), {}) or {}
            if (publish_since is not None and exported > publish_since and not mark.get("at")
                    and published.publishing({**item, "published": mark}) is None
                    and float((store.read_json(folder / "auto-publish.json", {}) or {}).get("export_at") or 0) < exported
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
            time.sleep(EVERY)
    threading.Thread(target=loop, name="auto-pipeline", daemon=True).start()
