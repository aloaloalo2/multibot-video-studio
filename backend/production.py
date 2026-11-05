"""Making the first N frames of an episode, started by «Почати створення ролика» on the plan of any channel.

A photo channel's frames (stock photos and videos, pictures Codex draws, the author's own pictures from the episode
folder, text frames and Razgon frames of a mixed episode) are made by the same agent with photo_brief: it places each
frame on the timeline with tools/studio.py place, and the run is done when each of the requested frames has its clip
(store.made_frames). An animated film's frames follow below.

The production request (store.request_production) hands the frames to Claude Opus 5.5 (high effort) through Claude
Code on the user's subscription, in the YOUTUBE folder, as the channel rules' step 7 asks: scenes of the shots behind
those frames, props from the library or drawn by Codex (tools/codex_image.py), checks on contact sheets. The frames stay
«Кадр N» code blocks on the timeline that the live preview draws: nothing is rendered until the author presses «Експорт
MP4», which renders the blocks (razgon_export.py; user, 30 October 2026: «має показати мені код, і коли я нажимаю
експорт, тоді починається рендер»). No final film and nothing published. The run counts as done only when every one of
those frames has its scene written and stands on the timeline as a code block. Its state lives in the project's request.
"""
from __future__ import annotations

import json, subprocess, threading, time
from pathlib import Path

import director
import frame_progress
import logo_layer
import production_context
import razgon_sound
import store

TIMEOUT = 6 * 3600
# Frame creation and direction both use high effort (user choice, 5 November 2026).
EFFORT = "high"
ACTIVE: set[str] = set()
LOCK = threading.Lock()


def run_log(pid: str, request: dict) -> Path:
    suffix = f"-fix{request['fixes']}" if request.get("fixes") else ""
    return store.project_dir(pid) / f"production-{request['id']}{suffix}.log"


def set_request(pid: str, **fields) -> dict:
    """Update the project's production request and its mirror next to the episode."""
    with store.LOCK:
        project = store.load_project(pid)
        request = {**(project.get("production_request") or {}), **fields}
        project["production_request"] = request
        # the request's state is not an edit of the montage: the revision stays, so an open editor is not told the
        # project changed under it at every start and end of a run
        store.save_project(project)
        store.atomic_json(store.project_dir(pid) / "production-request.json", request)
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
   - стики: дія не починається заново після стику. Запусти python3 "<студія>/tools/cut_check.py" --razgon <проєкт> --only <шоти цих кадрів> і
     переглянь кожну смугу build/cuts/seams_NN.png очима: після стику дія йде далі з того стану, де закінчилась;
   - кадр має бути привабливим, як у топових каналів: глибина, світло, деталі;
   - швидкість: g.filter (blur, brightness) діє окремим проходом на відеокарті на кожен виклик малювання, тож не став його
     на шар, де малюється багато фігур. Групу розмивай одним blurLayer(g, px, fn, cam, depth), предмети затемнюй через
     pic(..., { shade }). node render.mjs --project <проєкт> --speed-check (у папці Razgon) має показати OK:
     дубль, повільніший за 2,5 медіани, перепиши (у 06 такі дублі рендерилися в 4–6 разів довше за решту);
   - текст у кадрі лише там, де він щось додає: цифри, роки й дати, виміри, дані, порівняння (їх показуй, навіть коли їх називає
     озвучка), підпис до предмета, який інакше не впізнати. Жодних словесних рядків, що повторюють озвучку (імена, посади, фрази:
     вони виглядають як субтитри), і жодних плашок під текстом: напис без підкладки через
     label() з engine/ui2d.js: чистий текст без фону, заливки чи ореолу, крупніший, ніж був би на плашці. Став його на спокійну
     ділянку кадру: легку тінь і темний тон на світлому фоні label() дає сам, але на строкатому фоні напис губиться.
   Кадр, що не пройшов цю перевірку, не готовий: не здавай його, а виправ. Автор не перевіряє за тебе: якщо на кадрі
   лишилась хоч одна видима вада, кадр не здається."""


def brief(project: dict, request: dict, notes: str = "") -> str:
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    rel = episode.relative_to(root) if root in episode.parents else episode
    frames = ",".join(str(n) for n in range(1, request["frames"] + 1))
    remarks = (f"Автор подивився кадри 1–{request['frames']} і просить виправити:\n{notes.strip()}\n\n"
               "Виправ потрібні сцени, перевір змінені кадри й їхні сусідні стики та зроби крок 4.\n\n"
               if notes.strip() else "")
    if request.get("continuation_mode") == "handoff":
        remarks = f"Продовження зі збережених файлів:\n{notes.strip()}\n\n"
    return f"""Ти аніматор анімаційного випуску в VideoKey Studio. Режисуру вже зроблено, автор натиснув «Створити {request['frames']} кадрів».

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка «{rel}», канал «{episode.parent.name}».
Запит: кадри студії 1–{request['frames']} з {request['total_frames']}, від {request['start']:.2f} до {request['end']:.2f} с озвучки.
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.
Службові JSON, плани, таймінги, запити й проміжні файли зберігай усередині VideoKey Studio. Папка випуску містить матеріали користувача та готові результати. План отримуй через API студії; зв’язок анімації через GET/POST /api/projects/<id>/razgon-link.

Спершу прочитай правила: {root / 'AGENTS.md'}, {episode.parent / 'AGENTS.md'} і навики Razgon
(«{store.APP_ROOT.name}/razgon-plugin/razgon-2d-studio-plugin/skills»: make-2d-video, render-video). Великі документи самої
студії (її AGENTS.md, CLAUDE.md, docs/) і сценарії інших випусків не читай: це зайві токени, а все потрібне для кадрів є тут і в навиках. python3 "{store.APP_ROOT.name}/tools/episode.py" "{rel}" показує, де випуск.

{remarks}Твоє завдання: крок 7 правил каналу для цих кадрів.
Кадри, сцени яких уже написані, не переробляй, якщо автор не просить правок саме до них.
Звук фільму (music, sfx і amb у story/shots.json) розставив режисер: не видаляй і не переписуй його. Музику й ефекти на таймлайн студія
кладе сама після твоєї роботи, без рендеру.
1. Сцени шотів, через які проходять кадри 1–{request['frames']} (story/shots.json проєкту Razgon), у scenes/ проєкту. Стиль, герої й декорації як у попередніх випусках каналу.
2. Предмети: якщо в config.json проєкту "assets": false, усе малюєш кодом. Інакше перевір assets/library-picks.json і вже прикріплені предмети.
   Далі один точний пошук: python3 "{store.razgon_rel()}/tools/library.py" search <слова> --limit 6 --sheet <аркуш.png> і use.
   Подивись один аркуш, вибери відповідний предмет. Якщо відповідного немає, одразу підготуй промпт для генерації.
   Не переглядай бібліотеку по колу й не генеруй уже вибраний предмет заново.
   Нові предмети малює Codex аркушем по 6: промпт у assets/src/prompt_X.txt, потім
   python3 "{store.razgon_rel()}/tools/codex_image.py" --prompt <промпт> --out <assets/src/sheet_X.png>, потім tools/split_sheet.py --clean 40.
3. Перевірка: tools/frame_review.py --project <проєкт> sheets --frames <нові або змінені кадри> у папці {store.razgon_rel()}.
   Переглянь аркуші й познач результат через mark; direction_check.py без FAIL. Один набір аркушів для перевірки композиції й логіки.
{QUALITY.replace("<студія>", store.APP_ROOT.name)}
4. python3 "{store.APP_ROOT.name}/tools/razgon_bridge.py" slots --razgon <проєкт> --frames {frames}: кадри стоять на таймлайні студії блоками-кодом
   «Кадр N», і автор дивиться їх у режимі «Наживо», де код Razgon малює картинку. Кадр, уже відрендерений раніше, ця команда
   знову робить блоком.
   Не рендери відео кадрів: не запускай razgon_bridge.py push, final чи export, а render.mjs запускай тільки з --sheet
   або для стоп-кадрів. Рендер і склейку робить сама студія, коли автор натисне «Експорт MP4».

Довгі перевірки (cut_check.py, frame_review.py, render.mjs) запускай на передньому плані з timeout до 600000 мс і чекай результату
в тій самій команді, без run_in_background: коли ти закінчуєш відповідь, сесія закривається, і фонова перевірка обривається разом з нею.

Не роби фінальний MP4, не змінюй режисуру й стиль, не чіпай кадри після {request['frames']}-го і нічого не публікуй.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською, наприклад «Рендерю аркуш кадрів 1–3».
Працюй із короткою картою кадрів студії. Не передавай помічникам копію великої розмови.
Наприкінці коротко напиши українською: які кадри готові, які предмети додано, що лишилося або не вдалося."""


# The channels' own rule for every picture (user): people are stick figures in every frame of every channel, apart from
# the host, and so in every prompt for a picture.
PEOPLE = ("Люди в кожному кадрі, крім кадрів ведучого, лише стикмени: і на картинках, і в кожному промпті для картинки "
          "чи відео прямо пиши, що всі люди намальовані стикменами. Стокове фото чи відео з живими людьми не бери.")


def accents_step(project: dict, tools: str) -> str:
    """What the channel's settings say about accents (an arrow, a ring or a caption over a picture, «Акценти на кадрах»)."""
    try:
        settings = store.read_json(store.get_channel_folder(project["channel_id"], include_disabled=True) / store.PLAN_CONFIG, {}) or {}
    except (store.StudioError, KeyError):
        settings = {}
    if not settings.get("accents"):
        return ("6. Акцентів (стрілок, кіл, підписів поверх фото) не додавай: у налаштуваннях каналу вони вимкнені.")
    return f"""6. Акценти для різноманіття (увімкнені в налаштуваннях каналу): приблизно на кожен третій-четвертий кадр з фото чи стоковим відео,
   де це допомагає зрозуміти сказане, додай один акцент: стрілку на деталь, про яку саме говорять, коло навколо неї або короткий підпис
   (число, назва предмета). Спершу подивись стоп-кадр кадру (python3 "{tools}/studio.py" still {project['id']} fN), щоб узяти точки, потім
   python3 "{tools}/studio.py" accent {project['id']} N arrow --from x,y --to x,y --word слово (або circle --at x,y --radii rx,ry, text --phrase "слова голосу" --at x,y).
   Не на текстових кадрах, не на кадрах ведучого й анімації; не два акценти поспіль на сусідніх кадрах. Перевір стоп-кадром, що акцент на місці."""


def photo_brief(project: dict, request: dict, notes: str = "") -> str:
    """The brief for a photo channel: each frame by its format, placed at its time on the timeline."""
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    rel = episode.relative_to(root) if root in episode.parents else episode
    tools = store.APP_ROOT.name + "/tools"
    remarks = (f"Автор подивився кадри 1–{request['frames']} і просить виправити:\n{notes.strip()}\n\n"
               "Виправ потрібні кадри й перевір їх разом із сусідніми стиками.\n\n" if notes.strip() else "")
    if request.get("continuation_mode") == "handoff":
        remarks = f"Продовження зі збережених файлів:\n{notes.strip()}\n\n"
    return f"""Ти монтажер випуску в VideoKey Studio. План кадрів іде за озвучкою, автор натиснув «Почати створення ролика».

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка «{rel}», канал «{episode.parent.name}».
Запит: кадри студії 1–{request['frames']} з {request['total_frames']}, від {request['start']:.2f} до {request['end']:.2f} с озвучки.
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.
Службові JSON, плани, таймінги, запити й проміжні файли зберігай усередині VideoKey Studio. Папка випуску містить матеріали користувача та готові результати. План отримуй через API студії; зв’язок анімації через GET/POST /api/projects/<id>/razgon-link.

Спершу прочитай правила каналу {episode.parent / 'AGENTS.md'} (і {root / 'AGENTS.md'}, якщо він є): там стиль і що в якому форматі.
Великі документи студії (її AGENTS.md, CLAUDE.md, docs/) і сценарії інших випусків не читай: усе потрібне для цієї роботи нижче.
План кадрів по рядку на кадр (час, формат, ідея режисера, слова, ✓ зроблено): python3 "{tools}/studio.py" plan {project['id']} --frames 1-{request['frames']} --todo
Що вже стоїть на таймлайні і які проблеми: python3 "{tools}/studio.py" summary {project['id']} --issues.
Правила студії, які легко порушити: кожен кадр стоїть у свій час плану (place робить це сам); озвучку й плашку каналу не чіпай;
у кадрі одна головна картинка чи відео; стокове відео не коротше за кадр (place перевіряє); експорт запускає тільки автор.

{remarks}Твоє завдання: кадри 1–{request['frames']}, кожен за своїм форматом у плані і за змістом своїх слів.
Кадри, які вже стоять на таймлайні, не переробляй, якщо автор не просить правок саме до них.
1. Картинки автора першими: якщо автор сам поклав картинки чи відео в папку випуску (find "{rel}" -maxdepth 2 -type f),
   а вони пасують до кадру, бери їх.
2. Стокові фото й відео (формати stock_photo, stock_video): python3 "{tools}/studio.py" stock {project['id']} N "англійські слова" [--video]
   складає аркуш пронумерованих варіантів Pixabay для кадру N; подивись його (Read) і вибери за змістом слів кадру, без живих людей,
   а відео не коротше за кадр. Вибраний ставить кадром одна команда: python3 "{tools}/studio.py" stock-pick {project['id']} N <id> [--video].
   Нічого не підходить: інші слова, ще один аркуш.
3. Створені картинки (generated_photo, generated_video як картинка з рухом): малює Codex через термінал:
   промпт у файлі, потім python3 "{tools.rsplit('/', 1)[0]}/razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/tools/codex_image.py" --prompt <файл промпту> --out "{rel}/кадри/кадр_NNN.png".
   {PEOPLE}
4. Текстові кадри (text) робиш сам одним кроком: python3 "{tools}/studio.py" place {project['id']} all-text ставить слова кожного ще не
   поставленого текстового кадру на весь екран.
   Кадри 2D-анімації Razgon (razgon_2d) пишеш кодом, як у правилах каналу, без рендеру відео: якщо проєкту Razgon ще немає,
   python3 "{tools}/razgon_bridge.py" prepare --project-id {project['id']}; далі сцени шотів цих кадрів і
   python3 "{tools}/razgon_bridge.py" slots --razgon <проєкт Razgon>: блоки-код стануть лише на кадри формату razgon_2d.
   Кожну картинку чи відео ставиш на таймлайн у час кадру: python3 "{tools}/studio.py" place {project['id']} N <файл> [--motion zoom_in|zoom_out|none].
5. Перевірка: python3 "{tools}/studio.py" summary {project['id']} --frames 1-{request['frames']} --issues без проблем, і стоп-кадр
   кожного кадру (python3 "{tools}/studio.py" still {project['id']} fN --small: половинний розмір, учетверо дешевший на
   перегляд; повний розмір лише коли береш координати для акценту) ти переглядаєш очима: картинка відповідає словам кадру,
   люди лише стикмени, нічого не обрізано, текст читається. Кадр із вадою виправ (replace) і перевір ще раз.
{accents_step(project, tools)}

Помилилась команда монтажу: python3 "{tools}/studio.py" undo {project['id']}; кадр не той: remove {project['id']} N і place знову.
Не запускай експорт, не змінюй план і налаштування каналу, не чіпай кадри після {request['frames']}-го і нічого не публікуй.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською повним реченням, наприклад «Шукаю стокове фото для кадру 3.».
Довгі команди запускай на передньому плані з timeout до 600000 мс, без run_in_background.
Незалежні кадри можна робити паралельно помічниками (Agent), а ти збираєш їхню роботу.
Помічнику пиши в завданні все, що йому треба (стиль, герої, шляхи, команди, правила якості коротко), щоб він не перечитував
правила й навики заново: кожне таке читання з'їдає ліміт.
Наприкінці коротко напиши українською повними реченнями: які кадри готові, звідки картинки, що лишилося або не вдалося."""


def run(pid: str, cli: Path, notes: str = "") -> None:
    # The run always leaves ACTIVE, whatever fails on the way (a full disk while the request is written, a project
    # removed): otherwise the project read as «working» until the next restart and refused every new start.
    try:
        _run(pid, cli, notes)
    finally:
        with LOCK:
            ACTIVE.discard(pid)


def _run(pid: str, cli: Path, notes: str = "") -> None:
    fields = {}
    started = None
    try:
        with store.LOCK:
            project = store.load_project(pid)
            request = project["production_request"]
            if request.get('paused'):
                return
            log = run_log(pid, request)
            started = time.time()
            set_request(pid, status="in_progress", started_at=started, model=director.MODEL, effort=EFFORT, error=None, limit=False, paused=False)
        # Every continuation gets a fresh session and a compact disk checkpoint.
        # A cold resume after quota reset must not reload the entire old history.
        text = brief(project, request, notes) if store.project_animated(project) else photo_brief(project, request, notes)
        _, handoff = production_context.write(project, request, repair=bool(notes.strip()))
        text += production_context.instructions(handoff)
        code, answer = director.claude(cli, text, log, director.activity_path(pid, "production"), TIMEOUT,
                                       resume=None, effort=EFFORT)
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
    except (OSError, store.StudioError, KeyError) as error:
        fields.update(status="failed", error=str(error))
    except Exception:   # a bug must not leave the request «in work» with nobody working on it
        import traceback
        traceback.print_exc()
        fields.update(status="failed", error="Створення кадрів зупинилося через помилку студії. Спробуйте ще раз")
    finally:
        was_cancelled = director.cancelled(pid, "production")
        if started is not None and not was_cancelled:
            try:
                set_request(pid, finished_at=time.time(), **fields)
            except (OSError, store.StudioError):
                pass
            if fields.get("status") == "done":
                # the scenes may have brought new sound cues: the film's music and effects are laid again, without a
                # render (razgon_sound.py; only an animated film is due)
                razgon_sound.start(pid, "production")


def fix(pid: str, notes: str, *, handoff: bool = False) -> dict:
    """Repair or continue through a fresh session with the current disk checkpoint."""
    notes = str(notes or "").strip()
    if not notes:
        raise store.StudioError("Напишіть, що виправити")
    project = store.load_project(pid)
    request = project.get("production_request") or {}
    if request.get("status") not in {"done", "failed"}:
        raise store.StudioError("Агент ще працює над цими кадрами")
    task_notes = str(request.get("task_notes", request.get("notes", "")) or "") if handoff else notes[:4000]
    set_request(pid, status="requested", paused=False, continue_session=False,
                continuation_mode="handoff" if handoff else "repair", task_notes=task_notes,
                previous_session_id=request.get("session_id"),
                created_at=time.time(), notes=notes[:4000], fixes=int(request.get("fixes") or 0) + 1)
    start(pid, notes)
    return store.load_project(pid)


RESUME = ("Ліміт підписки оновився. Продовж роботу над цими кадрами з того місця, де зупинився: не переробляй уже готове, "
          "доведи решту кадрів до кінця з тією ж перевіркою якості й зроби крок 4 без рендеру відео.")


def resume(pid: str) -> dict:
    """Continue saved frames with a compact handoff, preserving completed work and author wishes."""
    with LOCK:
        if pid in ACTIVE:
            raise store.StudioError('Ще зупиняємо попередню роботу. Спробуйте за кілька секунд.',409)
    request = store.load_project(pid).get("production_request") or {}
    # a run stopped before the limit was marked keeps only the CLI's English note
    if request.get("status") != "failed" or not (request.get("paused") or request.get("limit") or director.limit_stop({"result": request.get("error")})):
        raise store.StudioError("Агент не стоїть на паузі")
    notes=("Автор просить продовжити після паузи. Продовж роботу з того місця, де зупинився. "
           "Збережи готові кадри й матеріали та закінчи решту без рендеру відео.") if request.get('paused') else RESUME
    return fix(pid, notes, handoff=True)


def pause(pid: str) -> dict:
    """Keep the project and the saved CLI session; stop only its active frame job."""
    project=store.load_project(pid)
    request=project.get('production_request') or {}
    if request.get('status') not in {'requested','in_progress'}:
        return project
    # A first run may not have returned its result yet. Its initial event already
    # identifies the persistent conversation that Resume must continue.
    session=request.get('session_id')
    log=run_log(pid, request)
    if not log.is_file():
        log=store.project_dir(pid)/f"production-{request['id']}.log"  # legacy repair runs shared this path
    if log.is_file():
        with log.open() as stream:
            for _,line in zip(range(20),stream):
                try:
                    event=json.loads(line)
                    if event.get('session_id'):
                        session=event['session_id'];break
                except ValueError:
                    continue
    director.stop(pid,'production')
    set_request(pid,status='failed',paused=True,limit=False,finished_at=time.time(),session_id=session,
                error='Призупинено на ваше прохання. Готові кадри збережені.')
    # Usually SIGTERM finishes immediately. Never let a quick Play silently lose
    # the request while the old worker still owns the project's active slot.
    until=time.monotonic()+2
    while pid in ACTIVE and time.monotonic()<until:
        time.sleep(.05)
    return store.load_project(pid)


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
