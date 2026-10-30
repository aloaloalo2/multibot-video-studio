"""Direction of an animated episode by Claude Opus 5.5 (high effort), started as soon as the voice is recognised.

For a channel of kind "animated" the Studio hands the episode to Claude Code once Whisper has turned the voice into
timed words and the plan follows the voice. Claude Code runs on the user's claude.ai subscription, in the YOUTUBE
folder, and does the director's steps of the channel rules: razgon_bridge.py prepare, the shot table (story/gen_shots.py)
written by meaning, direction_check.py without FAIL, and razgon_bridge.py plan, which writes the frame plan back into
the Studio. It draws no scenes and renders nothing. The state of the run lives next to the project (director.json), its
full answer in director.log, and the plan page shows it.
"""
from __future__ import annotations

import json, re, shutil, subprocess, threading, time
from pathlib import Path

import store

MODEL = "claude-opus-5-5"
EFFORT = "high"
TIMEOUT = 3 * 3600
ACTIVE: set[str] = set()
LOCK = threading.Lock()
# Bash is limited to the commands direction needs; file edits are accepted inside the YOUTUBE folder; Opus may send
# helpers off in parallel.
ALLOWED = ["Read", "Write", "Edit", "Glob", "Grep", "Agent", "Task"] + [f"Bash({cmd}:*)" for cmd in
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
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською, наприклад «Читаю правила каналу».
Наприкінці коротко напиши українською: скільки шотів і кадрів студії вийшло, які епізоди, що лишилося з WARN і що не вдалося, якщо таке було."""


def spent(answer: dict) -> dict:
    """What a run actually used, from Claude Code's answer: tokens in (cached ones included) and out, and minutes."""
    usage = answer.get("usage") if isinstance(answer.get("usage"), dict) else {}
    number = lambda key: int(usage.get(key) or 0)
    return {"tokens_in": number("input_tokens") + number("cache_creation_input_tokens") + number("cache_read_input_tokens"),
            "tokens_out": number("output_tokens"), "minutes": round(float(answer.get("duration_ms") or 0) / 60000, 1)}


# What the agent is doing, in the author's words: each command or file it touches becomes one line of the activity
# feed on the plan, so the author sees the work move.
# Each line also names who does it: Opus directs and writes, Codex draws props, Razgon renders, the Studio keeps the plan
# and timeline, and helpers are the agents Opus sends off in parallel.
COMMANDS = [("razgon_bridge.py prepare", "studio", "Готує проєкт Razgon зі студії"), ("gen_shots.py", "opus", "Розбиває озвучку на шоти"),
            ("direction_check", "opus", "Перевіряє режисуру"), ("razgon_bridge.py check", "studio", "Перевіряє, що шоти покривають озвучку"),
            ("razgon_bridge.py plan", "studio", "Записує план кадрів у студію"), ("razgon_bridge.py push", "razgon", "Рендерить кадри й кладе їх на таймлайн"),
            ("codex_image.py", "codex", "Малює аркуш предметів"), ("split_sheet", "codex", "Ріже аркуш на окремі предмети"),
            ("library.py", "studio", "Шукає предмети в бібліотеці"), ("--sheet", "razgon", "Рендерить аркуш кадрів для перевірки"),
            ("render.mjs", "razgon", "Рендерить пробні кадри"), ("episode.py", "studio", "Дивиться, на якому кроці випуск"),
            ("frame_review", "opus", "Переглядає кадри")]


def describe(tool: str, args: dict) -> tuple[str, str] | None:
    """(who, what) for one action of the agent, or None for the ones not worth a line."""
    name = Path(str(args.get("file_path") or args.get("path") or "")).name
    if tool == "Bash":
        command = str(args.get("command") or "")
        found = next(((who, text) for key, who, text in COMMANDS if key in command), None)
        return found or (("opus", f"Команда: {args['description']}") if args.get("description") else None)
    if tool in {"Task", "Agent"}:
        return "helper", str(args.get("description") or "Окреме завдання")
    if tool in {"Write", "Edit", "MultiEdit"} and name:
        return "opus", f"Пише сцену {name}" if "/scenes/" in str(args.get("file_path")) else f"Пише {name}"
    if tool == "Read" and name and not re.search(r"tool-results|/tmp/|/private/var/|/T/", str(args.get("file_path") or "")):
        return "opus", f"Читає {name}"
    return None


def activity_path(pid: str, kind: str) -> Path:
    return store.project_dir(pid) / f"{kind}-activity.json"


def claude(cli: Path, prompt: str, log: Path, activity: Path, timeout: int) -> tuple[int, dict]:
    """Run Claude Code on a brief, streaming its events: the log keeps them all, the activity feed the readable ones.
    Returns the exit code and the final result event (cost, usage, the agent's last message)."""
    command = [str(cli), "--model", MODEL, "--effort", EFFORT, "--strict-mcp-config", "--permission-mode", "acceptEdits",
               "--allowedTools", *ALLOWED, "--output-format", "stream-json", "--verbose", "-p"]
    process = subprocess.Popen(command, cwd=store.YOUTUBE_ROOT, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    expired = threading.Event()
    watchdog = threading.Timer(timeout, lambda: (expired.set(), process.kill()))
    watchdog.start()
    answer, steps = {}, []
    store.atomic_json(activity, [])
    try:
        process.stdin.write(prompt)
        process.stdin.close()
        with log.open("w", encoding="utf-8") as out:
            for line in process.stdout:
                out.write(line)
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "result":
                    answer = event
                if event.get("type") != "assistant":
                    continue
                for part in (event.get("message") or {}).get("content") or []:
                    action = describe(part.get("name"), part.get("input") or {}) if part.get("type") == "tool_use" else None
                    if action and (not steps or steps[-1]["text"] != action[1]):
                        steps = (steps + [{"t": time.time(), "who": action[0], "text": action[1]}])[-40:]
                        store.atomic_json(activity, steps)
        process.wait()
    finally:
        watchdog.cancel()
    if expired.is_set():
        raise subprocess.TimeoutExpired(command, timeout)
    return process.returncode, answer or {"is_error": True, "result": "Claude Code завершився без відповіді"}


def run(pid: str, cli: Path) -> None:
    data = state(pid) or {}
    project = store.load_project(pid)
    data.update(status="running", started_at=time.time(), model=MODEL, effort=EFFORT, error=None, summary=None)
    save(pid, data)
    try:
        code, answer = claude(cli, brief(project), store.project_dir(pid) / "director.log", activity_path(pid, "director"), TIMEOUT)
        plan = store.load_project_plan(pid) or {}
        plan_file = store.project_plan_file(store.load_project(pid))
        # the run counts only if it wrote a fresh director plan into the Studio
        directed = (plan.get("frame_source") == "razgon-direction" and not plan.get("director_stale")
                    and plan_file is not None and plan_file.stat().st_mtime >= data["started_at"])
        if code or answer.get("is_error") or not directed:
            data.update(status="failed", error=(answer.get("result") or "Режисура не записала план кадрів у студію")[-600:])
        else:
            data.update(status="done", summary=(answer.get("result") or "").strip()[-2000:], frames=len(plan.get("frames") or []))
        data.update(cost_usd=answer.get("total_cost_usd"), session_id=answer.get("session_id"), turns=answer.get("num_turns"), **spent(answer))
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
