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
import logo_layer
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


# What the author checks first, so the agent checks it before it calls a frame done (user, 30 October 2026: long, wrongly
# bent legs and bare triangles instead of props were handed in as finished frames).
QUALITY = """5. Здача тільки після власного перегляду. Подивись кожен кадр очима глядача на кількох стоп-кадрах (tools/frame_review.py або стоп-кадри
   render.mjs) і виправ, доки все не так:
   - пропорції героїв як у попередніх випусках каналу: ноги й руки не довші за норму, коліна й лікті згинаються природно, у правильний бік;
   - жоден предмет не намальований голою примітивною фігурою (трикутник, коло, прямокутник замість речі): такий предмет бери з бібліотеки
     або замов у Codex і став через pic();
   - логіка: кожен кадр показує саме те, що звучить у ньому, без дивних поз, накладань і обрізаних голів;
   - простір: кожен предмет, дерево, камінь і герой стоїть на своїй землі чи схилі, а не висить у повітрі; лінії схилу, землі,
     горизонту й краї декорацій не перерізають дерева, каміння й героїв; лижі, палиці й інші речі там, де мають бути;
   - глибина одна на предмет: що за краєм схилу, те схил закриває; що на схилі, те поверх схилу; хто ближче, той попереду.
     Предмет не буває водночас переднім планом для лінії схилу й заднім планом для героя;
   - поява: ніщо не з'являється й не зникає миттєво («блим»): герой, предмет чи напис проявляється плавно, виїжджає з краю,
     виходить з-за іншого предмета або входить у кадр сам;
   - стики: дія не починається заново після стику. Запусти tools/cut_check.py --razgon <проєкт> --only <шоти цих кадрів> і
     переглянь кожну смугу build/cuts/seams_NN.png очима: після стику дія йде далі з того стану, де закінчилась;
   - кадр має бути привабливим, як у топових каналів: глибина, світло, деталі;
   - текст у кадрі лише там, де він щось додає: цифри, роки й дати, виміри, дані, порівняння (їх показуй, навіть коли їх називає
     озвучка), підпис до предмета, який інакше не впізнати. Жодних словесних рядків, що повторюють озвучку (імена, посади, фрази:
     вони виглядають як субтитри), і жодних плашок під текстом: напис без підкладки через
     label() з engine/ui2d.js: чистий текст без фону, заливки чи ореолу, крупніший, ніж був би на плашці.
   Кадр, що не пройшов цю перевірку, не готовий: не клади його в студію, а виправ. Автор не перевіряє за тебе: якщо на кадрі
   лишилась хоч одна видима вада, кадр не здається."""


def brief(project: dict, request: dict, notes: str = "") -> str:
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    rel = episode.relative_to(root) if root in episode.parents else episode
    frames = ",".join(str(n) for n in range(1, request["frames"] + 1))
    remarks = (f"Автор подивився кадри 1–{request['frames']} і просить виправити:\n{notes.strip()}\n\n"
               "Виправ саме це у сценах цих кадрів, перевір усі кадри за пунктом 5 і поклади виправлені кадри в студію знову (крок 4).\n\n"
               if notes.strip() else "")
    return f"""Ти аніматор анімаційного випуску в MultiBot Video Studio. Режисуру вже зроблено, автор натиснув «Створити {request['frames']} кадрів».

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка «{rel}», канал «{episode.parent.name}».
Запит: кадри студії 1–{request['frames']} з {request['total_frames']}, від {request['start']:.2f} до {request['end']:.2f} с озвучки.
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.

Спершу прочитай правила: {root / 'AGENTS.md'}, {episode.parent / 'AGENTS.md'}, {root / 'MultiBot Video Studio' / 'AGENTS.md'} і навики Razgon
(«Навыки для переноса/razgon-2d-studio-plugin/skills»: make-2d-video, render-video). python3 tools/episode.py "{rel}" показує, де випуск.

{remarks}Твоє завдання: крок 7 правил каналу для цих кадрів.
Кадри, що вже лежать на таймлайні студії готовим відео, не переробляй, якщо автор не просить правок саме до них.
1. Сцени шотів, через які проходять кадри 1–{request['frames']} (story/shots.json проєкту Razgon), у scenes/ проєкту. Стиль, герої й декорації як у попередніх випусках каналу.
2. Предмети: якщо в config.json проєкту "assets": false, усе малюєш кодом. Інакше спершу бібліотека: python3 "What If/razgon-2d-studio/tools/library.py" search <слова> і use.
   Нові предмети малює Codex аркушем по 6: промпт у assets/src/prompt_X.txt, потім
   python3 "What If/razgon-2d-studio/tools/codex_image.py" --prompt <промпт> --out <assets/src/sheet_X.png>, потім tools/split_sheet.py --clean 40.
3. Перевірка: node render.mjs --project <проєкт> --sheet --scale 0.5 у папці What If/razgon-2d-studio, відкривай кожен аркуш і виправляй; direction_check.py без FAIL.
{QUALITY}
4. python3 tools/razgon_bridge.py push --razgon <проєкт> --frames {frames}: кадри рендеряться й лягають на таймлайн студії.

Не роби фінальний MP4, не змінюй режисуру й стиль, не чіпай кадри після {request['frames']}-го і нічого не публікуй.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською, наприклад «Рендерю аркуш кадрів 1–3».
Незалежні сцени можна писати паралельно помічниками (Agent), а сам ти режисер, який збирає їхню роботу.
Наприкінці коротко напиши українською: які кадри готові, які предмети додано, що лишилося або не вдалося."""


def run(pid: str, cli: Path, notes: str = "") -> None:
    project = store.load_project(pid)
    request = project["production_request"]
    log = store.project_dir(pid) / f"production-{request['id']}.log"
    started = time.time()
    set_request(pid, status="in_progress", started_at=started, model=director.MODEL, effort=director.EFFORT, error=None)
    fields = {}
    try:
        # a fix goes on in the run's own session, so the agent keeps everything it already knows about these frames
        code, answer = director.claude(cli, brief(project, request, notes), log, director.activity_path(pid, "production"), TIMEOUT,
                                       resume=request.get("session_id") if notes.strip() else None)
        spent_before = float(request.get("cost_usd") or 0) if notes.strip() else 0
        fields.update(cost_usd=spent_before + float(answer.get("total_cost_usd") or 0) if answer.get("total_cost_usd") else request.get("cost_usd"),
                      session_id=answer.get("session_id") or request.get("session_id"),
                      summary=(answer.get("result") or "").strip()[-2000:], **director.spent(answer, started))
        if code or answer.get("is_error") or not drawn(store.load_project(pid), request["frames"]):
            fields.update(status="failed", error=(answer.get("result") or "Кадри не з'явилися на таймлайні студії")[-600:])
        else:
            fields.update(status="done")
            try:
                logo_layer.place(pid)   # the channel logo from the settings goes over the new frames
            except (OSError, store.StudioError):
                pass
    except subprocess.TimeoutExpired:
        fields.update(status="failed", error="Створення кадрів не вклалося в 6 годин")
    except (OSError, store.StudioError) as error:
        fields.update(status="failed", error=str(error))
    finally:
        set_request(pid, finished_at=time.time(), **fields)
        with LOCK:
            ACTIVE.discard(pid)


def fix(pid: str, notes: str) -> dict:
    """The author's remarks on the frames already made: the agent fixes them in the same session and puts them back."""
    notes = str(notes or "").strip()
    if not notes:
        raise store.StudioError("Напишіть, що виправити")
    project = store.load_project(pid)
    request = project.get("production_request") or {}
    if request.get("status") not in {"done", "failed"}:
        raise store.StudioError("Агент ще працює над цими кадрами")
    set_request(pid, status="requested", notes=notes[:4000], fixes=int(request.get("fixes") or 0) + 1)
    start(pid, notes)
    return store.load_project(pid)


def start(pid: str, notes: str = "") -> None:
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
    threading.Thread(target=run, args=(pid, cli, notes), daemon=True).start()


def reset_interrupted() -> None:
    """At start-up: a request left in work by a restart reads as failed, so the author can press the button again."""
    for item in store.list_projects():
        try:
            request = store.load_project(item["id"]).get("production_request") or {}
        except store.StudioError:
            continue
        if request.get("status") == "in_progress":
            set_request(item["id"], status="failed", error="Студію перезапустили під час створення кадрів. Натисніть ще раз.")
