"""Making the first N frames of an episode, started by «Почати створення ролика» on the plan of any channel.

A photo channel's frames (stock photos and videos, pictures Codex draws, the author's own pictures from the episode
folder, text frames and Razgon frames of a mixed episode) are made by the same agent with photo_brief: it places each
frame on the timeline with tools/studio.py place, and the run is done when each of the requested frames has its clip
(store.made_frames). An animated film's frames follow below.

The production request (store.request_production) hands the frames to Claude Opus 5.5 (extra-high effort) through Claude
Code on the user's subscription, in the YOUTUBE folder, as the channel rules' step 7 asks: scenes of the shots behind
those frames, props from the library or drawn by Codex (tools/codex_image.py), checks on contact sheets. The frames stay
«Кадр N» code blocks on the timeline that the live preview draws: nothing is rendered until the author presses «Експорт
MP4», which renders the blocks (razgon_export.py; user, 30 October 2026: «має показати мені код, і коли я нажимаю
експорт, тоді починається рендер»). No final film and nothing published. The run counts as done only when every one of
those frames has its scene written and stands on the timeline as a code block. Its state lives in the project's request.
"""
from __future__ import annotations

import subprocess, threading, time
from pathlib import Path

import director
import frame_progress
import logo_layer
import store

TIMEOUT = 6 * 3600
# The film itself is drawn at extra-high effort (user, 30 October 2026: «я хочу, щоб ролик складав надвисокий Опус 5.5»);
# the director keeps high.
EFFORT = "xhigh"
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


def drawn(pid: str, count: int) -> bool:
    """True when the first `count` frames are made: on a photo channel each has its clip on the timeline
    (store.made_frames); on an animated one each of the first `count` director frames has its scene written (frame_progress.py) and stands on the
    timeline as its «Кадр N» code block, not as a rendered clip."""
    blocks = {clip.get("title") for track in store.load_project(pid).get("tracks", []) for clip in track.get("clips", [])
              if clip.get("kind") == "animation"}
    project = store.load_project(pid)
    if not store.project_animated(project):
        return set(range(1, count + 1)) <= set(store.made_frames(project, store.load_project_plan(pid)))
    made = set(frame_progress.drawn(pid))
    return all(number in made and f"Razgon · кадр {number:03d}" in blocks for number in range(1, count + 1))


# What the author checks first, so the agent checks it before it calls a frame done (user, 30 October 2026: long, wrongly
# bent legs and bare triangles instead of props were handed in as finished frames).
QUALITY = """5. Здача тільки після власного перегляду. Подивись кожен кадр очима глядача на кількох стоп-кадрах (tools/frame_review.py або стоп-кадри
   render.mjs; вони тільки для твоєї перевірки й у студію не йдуть) і виправ, доки все не так:
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
   - стики: дія не починається заново після стику. Запусти python3 "VideoKey Studio/tools/cut_check.py" --razgon <проєкт> --only <шоти цих кадрів> і
     переглянь кожну смугу build/cuts/seams_NN.png очима: після стику дія йде далі з того стану, де закінчилась;
   - кадр має бути привабливим, як у топових каналів: глибина, світло, деталі;
   - швидкість: g.filter (blur, brightness) діє окремим проходом на відеокарті на кожен виклик малювання, тож не став його
     на шар, де малюється багато фігур. Групу розмивай одним blurLayer(g, px, fn, cam, depth), предмети затемнюй через
     pic(..., { shade }). node render.mjs --project <проєкт> --speed-check (у папці What If/razgon-2d-studio) має показати OK:
     дубль, повільніший за 2,5 медіани, перепиши (у 06 такі дублі рендерилися в 4–6 разів довше за решту);
   - текст у кадрі лише там, де він щось додає: цифри, роки й дати, виміри, дані, порівняння (їх показуй, навіть коли їх називає
     озвучка), підпис до предмета, який інакше не впізнати. Жодних словесних рядків, що повторюють озвучку (імена, посади, фрази:
     вони виглядають як субтитри), і жодних плашок під текстом: напис без підкладки через
     label() з engine/ui2d.js: чистий текст без фону, заливки чи ореолу, крупніший, ніж був би на плашці.
   Кадр, що не пройшов цю перевірку, не готовий: не здавай його, а виправ. Автор не перевіряє за тебе: якщо на кадрі
   лишилась хоч одна видима вада, кадр не здається."""


def brief(project: dict, request: dict, notes: str = "") -> str:
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    rel = episode.relative_to(root) if root in episode.parents else episode
    frames = ",".join(str(n) for n in range(1, request["frames"] + 1))
    remarks = (f"Автор подивився кадри 1–{request['frames']} і просить виправити:\n{notes.strip()}\n\n"
               "Виправ саме це у сценах цих кадрів, перевір усі кадри за пунктом 5 і зроби крок 4.\n\n"
               if notes.strip() else "")
    return f"""Ти аніматор анімаційного випуску в VideoKey Studio. Режисуру вже зроблено, автор натиснув «Створити {request['frames']} кадрів».

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка «{rel}», канал «{episode.parent.name}».
Запит: кадри студії 1–{request['frames']} з {request['total_frames']}, від {request['start']:.2f} до {request['end']:.2f} с озвучки.
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.

Спершу прочитай правила: {root / 'AGENTS.md'}, {episode.parent / 'AGENTS.md'}, {store.APP_ROOT / 'AGENTS.md'} і навики Razgon
(«{store.APP_ROOT.name}/razgon-plugin/razgon-2d-studio-plugin/skills»: make-2d-video, render-video). python3 "{store.APP_ROOT.name}/tools/episode.py" "{rel}" показує, де випуск.

{remarks}Твоє завдання: крок 7 правил каналу для цих кадрів.
Кадри, сцени яких уже написані, не переробляй, якщо автор не просить правок саме до них.
1. Сцени шотів, через які проходять кадри 1–{request['frames']} (story/shots.json проєкту Razgon), у scenes/ проєкту. Стиль, герої й декорації як у попередніх випусках каналу.
2. Предмети: якщо в config.json проєкту "assets": false, усе малюєш кодом. Інакше спершу бібліотека: python3 "What If/razgon-2d-studio/tools/library.py" search <слова> і use.
   Нові предмети малює Codex аркушем по 6: промпт у assets/src/prompt_X.txt, потім
   python3 "What If/razgon-2d-studio/tools/codex_image.py" --prompt <промпт> --out <assets/src/sheet_X.png>, потім tools/split_sheet.py --clean 40.
3. Перевірка: node render.mjs --project <проєкт> --sheet --scale 0.5 у папці What If/razgon-2d-studio, відкривай кожен аркуш і виправляй; direction_check.py без FAIL.
{QUALITY}
4. python3 "{store.APP_ROOT.name}/tools/razgon_bridge.py" slots --razgon <проєкт> --frames {frames}: кадри стоять на таймлайні студії блоками-кодом
   «Кадр N», і автор дивиться їх у режимі «Наживо», де код Razgon малює картинку. Кадр, уже відрендерений раніше, ця команда
   знову робить блоком.
   Не рендери відео кадрів: не запускай razgon_bridge.py push, final чи export, а render.mjs запускай тільки з --sheet
   або для стоп-кадрів. Рендер і склейку робить сама студія, коли автор натисне «Експорт MP4».

Довгі перевірки (cut_check.py, frame_review.py, render.mjs) запускай на передньому плані з timeout до 600000 мс і чекай результату
в тій самій команді, без run_in_background: коли ти закінчуєш відповідь, сесія закривається, і фонова перевірка обривається разом з нею.

Не роби фінальний MP4, не змінюй режисуру й стиль, не чіпай кадри після {request['frames']}-го і нічого не публікуй.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською, наприклад «Рендерю аркуш кадрів 1–3».
Незалежні сцени можна писати паралельно помічниками (Agent), а сам ти режисер, який збирає їхню роботу.
Наприкінці коротко напиши українською: які кадри готові, які предмети додано, що лишилося або не вдалося."""


# The channels' own rule for every picture (user): people are stick figures in every frame of every channel, apart from
# the host, and so in every prompt for a picture.
PEOPLE = ("Люди в кожному кадрі, крім кадрів ведучого, лише стикмени: і на картинках, і в кожному промпті для картинки "
          "чи відео прямо пиши, що всі люди намальовані стикменами. Стокове фото чи відео з живими людьми не бери.")


def photo_brief(project: dict, request: dict, notes: str = "") -> str:
    """The brief for a photo channel: each frame by its format, placed at its time on the timeline."""
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    rel = episode.relative_to(root) if root in episode.parents else episode
    tools = store.APP_ROOT.name + "/tools"
    remarks = (f"Автор подивився кадри 1–{request['frames']} і просить виправити:\n{notes.strip()}\n\n"
               "Виправ саме це, перевір усі кадри за пунктом 5 і доведи решту до кінця.\n\n" if notes.strip() else "")
    return f"""Ти монтажер випуску в VideoKey Studio. План кадрів іде за озвучкою, автор натиснув «Почати створення ролика».

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка «{rel}», канал «{episode.parent.name}».
Запит: кадри студії 1–{request['frames']} з {request['total_frames']}, від {request['start']:.2f} до {request['end']:.2f} с озвучки.
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.

Спершу прочитай правила: {root / 'AGENTS.md'}, {episode.parent / 'AGENTS.md'}, {store.APP_ROOT / 'AGENTS.md'},
{store.APP_ROOT / 'CLAUDE.md'} і {store.APP_ROOT / 'docs/AI_VIDEO_WORKFLOW.md'}. План кадрів (формат, час і слова кожного кадру):
python3 "{tools}/studio.py" summary {project['id']} і GET http://127.0.0.1:8770/api/projects/{project['id']}/plan
(python3 -c з urllib).

{remarks}Твоє завдання: кадри 1–{request['frames']}, кожен за своїм форматом у плані і за змістом своїх слів.
Кадри, які вже стоять на таймлайні, не переробляй, якщо автор не просить правок саме до них.
1. Картинки автора першими: якщо автор сам поклав картинки чи відео в папку випуску (find "{rel}" -maxdepth 2 -type f),
   а вони пасують до кадру, бери їх.
2. Стокові фото й відео (формати stock_photo, stock_video): python3 "{tools}/pixabay.py" search image|video "англійські слова",
   вибери кадр за змістом і завантаж: python3 "{tools}/pixabay.py" download image|video ID --dir "{rel}".
3. Створені картинки (generated_photo, generated_video як картинка з рухом): малює Codex через термінал:
   промпт у файлі, потім python3 "What If/razgon-2d-studio/tools/codex_image.py" --prompt <файл промпту> --out "{rel}/кадри/кадр_NNN.png".
   {PEOPLE}
4. Текстові кадри (text) робиш сам: python3 "{tools}/studio.py" place {project['id']} N --text ставить слова кадру на весь екран.
   Кадри 2D-анімації Razgon (razgon_2d) пишеш кодом через python3 "{tools}/razgon_bridge.py" (slots --frames N), як у правилах каналу,
   без рендеру відео.
   Кожну картинку чи відео ставиш на таймлайн у час кадру: python3 "{tools}/studio.py" place {project['id']} N <файл> [--motion zoom_in|zoom_out|none].
5. Перевірка: python3 "{tools}/studio.py" summary {project['id']} --frames 1-{request['frames']} --issues без проблем, і стоп-кадр
   кожного кадру (python3 "{tools}/studio.py" still {project['id']} fN) ти переглядаєш очима: картинка відповідає словам кадру,
   люди лише стикмени, нічого не обрізано, текст читається. Кадр із вадою виправ (replace) і перевір ще раз.

Не запускай експорт, не змінюй план і налаштування каналу, не чіпай кадри після {request['frames']}-го і нічого не публікуй.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською повним реченням, наприклад «Шукаю стокове фото для кадру 3.».
Довгі команди запускай на передньому плані з timeout до 600000 мс, без run_in_background.
Незалежні кадри можна робити паралельно помічниками (Agent), а ти збираєш їхню роботу.
Наприкінці коротко напиши українською повними реченнями: які кадри готові, звідки картинки, що лишилося або не вдалося."""


def run(pid: str, cli: Path, notes: str = "") -> None:
    project = store.load_project(pid)
    request = project["production_request"]
    log = store.project_dir(pid) / f"production-{request['id']}.log"
    started = time.time()
    set_request(pid, status="in_progress", started_at=started, model=director.MODEL, effort=EFFORT, error=None, limit=False)
    fields = {}
    try:
        # a fix goes on in the run's own session, so the agent keeps everything it already knows about these frames
        text = brief(project, request, notes) if store.project_animated(project) else photo_brief(project, request, notes)
        code, answer = director.claude(cli, text, log, director.activity_path(pid, "production"), TIMEOUT,
                                       resume=request.get("session_id") if notes.strip() else None, effort=EFFORT)
        spent_before = float(request.get("cost_usd") or 0) if notes.strip() else 0
        fields.update(cost_usd=spent_before + float(answer.get("total_cost_usd") or 0) if answer.get("total_cost_usd") else request.get("cost_usd"),
                      session_id=answer.get("session_id") or request.get("session_id"),
                      summary=(answer.get("result") or "").strip()[-2000:], **director.spent(answer, started))
        if director.limit_stop(answer):
            # a pause, not a failure: what is made stays, and «Продовжити» picks the same session up once the limit resets
            fields.update(status="failed", limit=True, error=director.limit_stop(answer))
        elif code or answer.get("is_error") or not drawn(pid, request["frames"]):
            missing = ("Не всі кадри намальовані й стоять на таймлайні студії блоками-кодом" if store.project_animated(project)
                       else "Не всі вибрані кадри стоять на таймлайні студії")
            fields.update(status="failed", error=(answer.get("result") or missing)[-600:])
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
        if not director.cancelled(pid, "production"):
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


RESUME = ("Ліміт підписки оновився. Продовж роботу над цими кадрами з того місця, де зупинився: не переробляй уже готове, "
          "доведи решту кадрів до кінця з тією ж перевіркою якості й зроби крок 4 без рендеру відео.")


def resume(pid: str) -> dict:
    """Go on with frames a run left when the subscription limit ran out, in that run's own session."""
    request = store.load_project(pid).get("production_request") or {}
    # a run stopped before the limit was marked keeps only the CLI's English note
    if request.get("status") != "failed" or not (request.get("limit") or director.limit_stop({"result": request.get("error")})):
        raise store.StudioError("Агент не стоїть на паузі через ліміт")
    return fix(pid, RESUME)


def start(pid: str, notes: str = "") -> None:
    """Start making the requested frames on any channel; a request already in work is left to its run."""
    project = store.load_project(pid)
    if not project.get("production_request") or not project.get("episode_path"):
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


# A request just written waits this long for its run to start before it can read as stale.
START_GRACE = 30


def settle(pid: str, project: dict | None = None) -> dict | None:
    """A request that says the agent works while no agent of this Studio runs (a restart, a run that never started:
    31 October 2026 a finished film read «Створюємо кадри» for good) is put right: done when every requested frame is
    made, otherwise stopped, so the button can be pressed again. Returns the request as it stands."""
    project = project or store.load_project(pid)
    request = project.get("production_request") or {}
    if request.get("status") not in {"requested", "in_progress"} or pid in ACTIVE:
        return request or None
    if request["status"] == "requested" and time.time() - float(request.get("created_at") or 0) < START_GRACE:
        return request
    try:
        made = drawn(pid, int(request.get("frames") or 0))
    except (store.StudioError, OSError, ValueError, KeyError):
        made = False
    fields = {"status": "done", "error": None} if made else {
        "status": "failed", "error": "Агент зупинився, не закінчивши кадри. Виберіть кадри й почніть ще раз."}
    return set_request(pid, finished_at=time.time(), **fields)


def reset_interrupted() -> None:
    """At start-up: a request left in work by a restart is settled (done if its frames are made, else stopped)."""
    for item in store.list_projects():
        try:
            settle(item["id"])
        except store.StudioError:
            continue
