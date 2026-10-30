"""«Почати заново» on an animated episode: the plan goes back to an empty episode that waits for its script and voice.

The director and the frame agent are stopped first, with every tool they started. Then everything the Studio holds for
the episode moves into restarts/<time>/ next to the project, so nothing is lost: project.json, the frame plan and its
copy in the episode folder, the production request, the pointer to the voice recognition, and the runs' states, logs
and feeds. restore.json there says where each file came from. The project keeps its id, name, folder and media library;
its timeline goes back to one empty layer and its undo history is cleared. Files the agents drew in the episode folder
stay where they are.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import analysis_jobs
import director
import production
import store

# What a project keeps through a restart: who it is, where its episode lives, its frame size and its media library.
KEEP = ("id", "name", "channel_id", "channel_name", "episode_path", "created_at", "schema_version", "width", "height",
        "fps", "assets", "settings")
STOP_WAIT = 15


def stop_runs(pid: str) -> None:
    """Stop the director and the frame agent on this project and wait until their threads have let go of it."""
    runs = [(director, "director"), (production, "production")]
    busy = [(module, kind) for module, kind in runs if pid in module.ACTIVE]
    for module, kind in busy:
        director.stop(pid, kind)
    deadline = time.time() + STOP_WAIT
    while any(pid in module.ACTIVE for module, _ in busy) and time.time() < deadline:
        time.sleep(.1)
    if any(pid in module.ACTIVE for module, _ in busy):
        raise store.StudioError("Агент ще не зупинився. Спробуйте ще раз за хвилину", 409)


def restart(pid: str) -> dict:
    project = store.load_project(pid)
    if not director.animated(project):
        raise store.StudioError("Почати заново можна лише випуск анімаційного каналу")
    folder = store.project_dir(pid)
    pointer = store.read_json(folder / "analysis-state.json", {}) or {}
    if pointer.get("job_id") in analysis_jobs.ACTIVE_JOBS:
        raise store.StudioError("Студія ще розпізнає озвучку. Зачекайте, доки вона закінчить, і почніть заново", 409)
    stop_runs(pid)
    with store.LOCK:
        project = store.load_project(pid)
        backup = folder / "restarts" / time.strftime("%Y-%m-%d %H-%M-%S")
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / "project.json", backup / "project.json")
        episode = Path(project.get("episode_path") or folder)
        try:
            plan = store.project_plan_file(project)
        except store.StudioError:
            plan = None
        files = [plan, episode / "План видео.json", episode / "Запит на створення.json", folder / "analysis-state.json",
                 store.history_folder(pid), director.state_path(pid), folder / "director.log",
                 director.activity_path(pid, "director"), director.activity_path(pid, "production"),
                 *sorted(folder.glob("production-*.log"))]
        moved = {}
        for path in dict.fromkeys(item for item in files if item is not None):
            if not path.exists():
                continue
            target = backup / (f"випуск - {path.name}" if path.parent == episode else path.name)
            shutil.move(str(path), target)
            moved[target.name] = str(path)
        store.atomic_json(backup / "restore.json", {"restarted_at": time.time(), "files": moved})
        fresh = {key: project[key] for key in KEEP if key in project}
        fresh.update(revision=project.get("revision", 0) + 1, layer_mode="item", duration=0.0, scenes=[], restarted_at=time.time(),
                     tracks=[{"id": "layer-1", "name": "Шар 1", "type": "universal", "z_index": 0, "clips": []}])
        store.save_project(fresh)
        return store.load_project(pid)
