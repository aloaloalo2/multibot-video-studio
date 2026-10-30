"""Making the first N frames of an animated episode, started by «Створити N кадрів».

The production request (store.request_production) hands the frames to Claude Opus 5.5 (high effort) through Claude
Code on the user's subscription, in the YOUTUBE folder, as the channel rules' step 7 asks: scenes of the shots behind
those frames, props from the library or drawn by Codex (tools/codex_image.py), checks on contact sheets, then
razgon_bridge.py push puts the rendered frames on the Studio timeline. No final film and nothing published. The run
counts as done only when those frames are pictures on the timeline. Its state lives in the project's request.
"""
from __future__ import annotations

import subprocess, threading, time
from pathlib import Path

import director
import store

TIMEOUT = 6 * 3600
ACTIVE: set[str] = set()
LOCK = threading.Lock()


def set_request(pid: str, **fields) -> dict:
    """Update the project's production request and its mirror next to the episode."""
    with store.LOCK:
        project = store.load_project(pid)
        request = {**(project.get("production_request") or {}), **fields}
        project["production_request"] = request
        project["revision"] = project.get("revision", 0) + 1
        store.save_project(project)
        if project.get("episode_path") and Path(project["episode_path"]).is_dir():
            store.atomic_json(Path(project["episode_path"]) / "Запит на створення.json", request)
    return request


def drawn(project: dict, count: int) -> bool:
    """True when the first `count` director frames are rendered pictures on the timeline, not code blocks."""
    clips = [clip for track in project.get("tracks", []) for clip in track.get("clips", [])]
    return sum(clip.get("kind") in {"video", "image"} for clip in clips) >= count


def brief(project: dict, request: dict) -> str:
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    rel = episode.relative_to(root) if root in episode.parents else episode
    frames = ",".join(str(n) for n in range(1, request["frames"] + 1))
    return f"""Ти аніматор анімаційного випуску в MultiBot Video Studio. Режисуру вже зроблено, автор натиснув «Створити {request['frames']} кадрів».

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка «{rel}», канал «{episode.parent.name}».
Запит: кадри студії 1–{request['frames']} з {request['total_frames']}, від {request['start']:.2f} до {request['end']:.2f} с озвучки.
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.

Спершу прочитай правила: {root / 'AGENTS.md'}, {episode.parent / 'AGENTS.md'}, {root / 'MultiBot Video Studio' / 'AGENTS.md'} і навики Razgon
(«Навыки для переноса/razgon-2d-studio-plugin/skills»: make-2d-video, render-video). python3 tools/episode.py "{rel}" показує, де випуск.

Твоє завдання: крок 7 правил каналу для цих кадрів.
1. Сцени шотів, через які проходять кадри 1–{request['frames']} (story/shots.json проєкту Razgon), у scenes/ проєкту. Стиль, герої й декорації як у попередніх випусках каналу.
2. Предмети: якщо в config.json проєкту "assets": false, усе малюєш кодом. Інакше спершу бібліотека: python3 "What If/razgon-2d-studio/tools/library.py" search <слова> і use.
   Нові предмети малює Codex аркушем по 6: промпт у assets/src/prompt_X.txt, потім
   python3 "What If/razgon-2d-studio/tools/codex_image.py" --prompt <промпт> --out <assets/src/sheet_X.png>, потім tools/split_sheet.py --clean 40.
3. Перевірка: node render.mjs --project <проєкт> --sheet --scale 0.5 у папці What If/razgon-2d-studio, відкривай кожен аркуш і виправляй; direction_check.py без FAIL.
4. python3 tools/razgon_bridge.py push --razgon <проєкт> --frames {frames}: кадри рендеряться й лягають на таймлайн студії.

Не роби фінальний MP4, не змінюй режисуру й стиль, не чіпай кадри після {request['frames']}-го і нічого не публікуй.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською, наприклад «Рендерю аркуш кадрів 1–3».
Незалежні сцени можна писати паралельно помічниками (Agent), а сам ти режисер, який збирає їхню роботу.
Наприкінці коротко напиши українською: які кадри готові, які предмети додано, що лишилося або не вдалося."""


def run(pid: str, cli: Path) -> None:
    project = store.load_project(pid)
    request = project["production_request"]
    log = store.project_dir(pid) / f"production-{request['id']}.log"
    set_request(pid, status="in_progress", started_at=time.time(), model=director.MODEL, effort=director.EFFORT, error=None)
    fields = {}
    try:
        code, answer = director.claude(cli, brief(project, request), log, director.activity_path(pid, "production"), TIMEOUT)
        fields.update(cost_usd=answer.get("total_cost_usd"), summary=(answer.get("result") or "").strip()[-2000:], **director.spent(answer))
        if code or answer.get("is_error") or not drawn(store.load_project(pid), request["frames"]):
            fields.update(status="failed", error=(answer.get("result") or "Кадри не з'явилися на таймлайні студії")[-600:])
        else:
            fields.update(status="done")
    except subprocess.TimeoutExpired:
        fields.update(status="failed", error="Створення кадрів не вклалося в 6 годин")
    except (OSError, store.StudioError) as error:
        fields.update(status="failed", error=str(error))
    finally:
        set_request(pid, finished_at=time.time(), **fields)
        with LOCK:
            ACTIVE.discard(pid)


def start(pid: str) -> None:
    """Start making the requested frames; a request already in work is left to its run."""
    project = store.load_project(pid)
    if not director.animated(project) or not project.get("production_request"):
        return
    with LOCK:
        if pid in ACTIVE:
            return
        try:
            cli = director.executable()
        except RuntimeError as error:
            set_request(pid, status="failed", error=str(error))
            return
        ACTIVE.add(pid)
    threading.Thread(target=run, args=(pid, cli), daemon=True).start()


def reset_interrupted() -> None:
    """At start-up: a request left in work by a restart reads as failed, so the author can press the button again."""
    for item in store.list_projects():
        try:
            request = store.load_project(item["id"]).get("production_request") or {}
        except store.StudioError:
            continue
        if request.get("status") == "in_progress":
            set_request(item["id"], status="failed", error="Студію перезапустили під час створення кадрів. Натисніть ще раз.")
