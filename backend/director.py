"""Direction of an animated episode by Claude Opus 5.5 (high effort), started as soon as the voice is recognised.

For a channel of kind "animated" the Studio hands the episode to Claude Code once Whisper has turned the voice into
timed words and the plan follows the voice. Claude Code runs on the user's claude.ai subscription, in the YOUTUBE
folder, and does the director's steps of the channel rules: razgon_bridge.py prepare, the shot table (story/gen_shots.py)
written by meaning, direction_check.py without FAIL, and razgon_bridge.py plan, which writes the frame plan back into
the Studio. It draws no scenes and renders nothing. The state of the run lives next to the project (director.json), its
full answer in director.log, and the plan page shows it.
"""
from __future__ import annotations

import json, shutil, subprocess, threading, time
from pathlib import Path

import store

MODEL = "claude-opus-5-5"
EFFORT = "high"
TIMEOUT = 3 * 3600
ACTIVE: set[str] = set()
LOCK = threading.Lock()
# Bash is limited to the commands direction needs; file edits are accepted inside the YOUTUBE folder.
ALLOWED = ["Read", "Write", "Edit", "Glob", "Grep"] + [f"Bash({cmd}:*)" for cmd in
           ("python3", "node", "ls", "cat", "head", "tail", "wc", "grep", "find", "mkdir", "cp", "mv", "diff", "jq")]


def state_path(pid: str) -> Path:
    return store.project_dir(pid) / "director.json"


def state(pid: str) -> dict | None:
    data = store.read_json(state_path(pid), None)
    if isinstance(data, dict) and data.get("status") in {"queued", "running"} and pid not in ACTIVE:
        data.update(status="failed", error="Студію перезапустили під час режисури. Запустіть її ще раз.")
    return data


def save(pid: str, data: dict) -> None:
    store.atomic_json(state_path(pid), data)


def executable() -> Path:
    found = shutil.which("claude")
    if found:
        return Path(found)
    candidates = [Path.home() / ".local/bin/claude", Path.home() / ".claude/local/claude"]
    bundled = Path.home() / "Library/Application Support/Claude/claude-code"
    if bundled.is_dir():
        candidates += sorted(bundled.glob("*/*/claude.app/Contents/MacOS/claude"), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Не знайдено Claude Code на цьому Mac")


def animated(project: dict) -> bool:
    channel = next((c for c in store.list_channels() if c["id"] == project.get("channel_id")), None)
    return bool(channel) and (channel.get("settings") or {}).get("channel_kind") == "animated"


def brief(project: dict) -> str:
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    channel = episode.parent
    rel = episode.relative_to(root) if root in episode.parents else episode
    return f"""Ти режисер анімаційного випуску в MultiBot Video Studio. Озвучку щойно розпізнано, план студії «За озвучкою».

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка випуску «{rel}», канал «{channel.name}».
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.

Спершу прочитай правила: {root / 'AGENTS.md'}, {channel / 'AGENTS.md'}, {root / 'MultiBot Video Studio' / 'AGENTS.md'} і навик режисури Razgon
(What If/razgon-2d-studio/skills або плагін «Навыки для переноса/razgon-2d-studio-plugin/skills/make-2d-video»: storytelling і story breakdown).
Подивись, як зроблено режисуру попередніх випусків: What If/razgon-2d-studio/projects/*/story/gen_shots.py.

Твоє завдання: режисура й план кадрів, кроки 3–5 правил каналу.
1. python3 tools/episode.py "{rel}" показує, на якому кроці випуск. Якщо проєкту Razgon ще немає:
   python3 tools/razgon_bridge.py prepare --project-id {project['id']}
2. Режисура за змістом озвучки: напиши story/gen_shots.py проєкту Razgon (таблиця дублів: речення, епізод, декорація, перехід, що в кадрі)
   і запусти його. Кадри ділиш за змістом, не за кількістю слів. Потім python3 What If/razgon-2d-studio/tools/direction_check.py --project <проєкт>
   має пройти без FAIL. На WARN відповідай у story/bible.md або виправляй.
3. python3 tools/razgon_bridge.py check --razgon <проєкт>, потім python3 tools/razgon_bridge.py plan --razgon <проєкт>: план кадрів іде в студію.

Не малюй сцени, не генеруй картинки, не рендери відео, не змінюй стиль у config.json і нічого не публікуй: це наступні кроки, і їх запускає користувач.
Наприкінці коротко напиши українською: скільки шотів і кадрів студії вийшло, які епізоди, що лишилося з WARN і що не вдалося, якщо таке було."""


def run(pid: str, cli: Path) -> None:
    data = state(pid) or {}
    project = store.load_project(pid)
    log = store.project_dir(pid) / "director.log"
    data.update(status="running", started_at=time.time(), model=MODEL, effort=EFFORT, error=None, summary=None)
    save(pid, data)
    command = [str(cli), "--model", MODEL, "--effort", EFFORT, "--strict-mcp-config", "--permission-mode", "acceptEdits",
               "--allowedTools", *ALLOWED, "--output-format", "json", "-p"]
    try:
        result = subprocess.run(command, input=brief(project), cwd=store.YOUTUBE_ROOT, text=True, capture_output=True, timeout=TIMEOUT)
        log.write_text(result.stdout + ("\n--- stderr ---\n" + result.stderr if result.stderr else ""), encoding="utf-8")
        try:
            answer = json.loads(result.stdout)
        except ValueError:
            answer = {"is_error": True, "result": (result.stderr or result.stdout)[-500:]}
        plan = store.load_project_plan(pid) or {}
        plan_file = store.project_plan_file(store.load_project(pid))
        # the run counts only if it wrote a fresh director plan into the Studio
        directed = (plan.get("frame_source") == "razgon-direction" and not plan.get("director_stale")
                    and plan_file is not None and plan_file.stat().st_mtime >= data["started_at"])
        if result.returncode or answer.get("is_error") or not directed:
            data.update(status="failed", error=(answer.get("result") or "Режисура не записала план кадрів у студію")[-600:])
        else:
            data.update(status="done", summary=(answer.get("result") or "").strip()[-2000:], frames=len(plan.get("frames") or []))
        data.update(cost_usd=answer.get("total_cost_usd"), session_id=answer.get("session_id"), turns=answer.get("num_turns"))
    except subprocess.TimeoutExpired:
        data.update(status="failed", error="Режисура не вклалася в 3 години")
    except (OSError, store.StudioError) as error:
        data.update(status="failed", error=str(error))
    finally:
        data["finished_at"] = time.time()
        save(pid, data)
        with LOCK:
            ACTIVE.discard(pid)


def start(pid: str, reason: str = "voice") -> dict:
    """Start the director for an animated project; a second start while one runs returns the running one."""
    project = store.load_project(pid)
    if not animated(project):
        raise store.StudioError("Режисура Opus потрібна лише анімаційним каналам")
    if not project.get("episode_path"):
        raise store.StudioError("У випуску немає папки")
    with LOCK:
        if pid in ACTIVE:
            return state(pid)
        try:
            cli = executable()
        except RuntimeError as error:
            raise store.StudioError(str(error), 503) from None
        ACTIVE.add(pid)
        data = {"status": "queued", "reason": reason, "queued_at": time.time(), "model": MODEL, "effort": EFFORT}
        save(pid, data)
    threading.Thread(target=run, args=(pid, cli), daemon=True).start()
    return data


def after_voice(pid: str) -> None:
    """Called when a voice analysis has been applied to the plan: animated channels go on to direction by themselves."""
    try:
        plan = store.load_project_plan(pid) or {}
        # a new recognition of the same sentences keeps the director's frames; only a fresh or changed text needs a pass
        if plan.get("frame_source") == "razgon-direction" and not plan.get("director_stale"):
            return
        if animated(store.load_project(pid)):
            start(pid, "voice")
    except store.StudioError:
        pass
