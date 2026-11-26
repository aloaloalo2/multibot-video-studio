"""Making the first N frames of an episode, started by «Почати створення ролика» on the plan of any channel.

A photo channel's frames (stock photos and videos, pictures Codex draws, the author's own pictures from the episode
folder, text frames and Razgon frames of a mixed episode) are made by the same agent with photo_brief: it places each
frame on the timeline with tools/studio.py place, and the run is done when each of the requested frames has its clip
(store.made_frames). An animated film's frames follow below.

The production request (store.request_production) hands the frames to the channel-selected model and effort through Claude
Code on the user's subscription, in the YOUTUBE folder, as the channel rules' step 7 asks: scenes of the shots behind
those frames, props from the library or drawn by Codex (tools/codex_image.py), checks on contact sheets. The frames stay
«Кадр N» code blocks on the timeline that the live preview draws: nothing is rendered until the author presses «Експорт
MP4», which renders the blocks (razgon_export.py; user, 30 October 2026: «має показати мені код, і коли я нажимаю
експорт, тоді починається рендер»). No final film and nothing published. The run counts as done only when every one of
those frames has its scene written and stands on the timeline as a code block. Its state lives in the project's request.
"""
from __future__ import annotations

import json, re, subprocess, threading, time
from pathlib import Path

import director
import motion_direction
import asset_motion
import frame_progress
import channel_hero
import logo_layer
import production_context
import production_sessions
import razgon_sound
import os
import store
import job_timing
import production_quality
import montage_context

TIMEOUT = 6 * 3600
# New frame runs use the author-selected channel effort; high is only the CLI fallback.
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
    if fields.get("status") == "done":
        import auto_pipeline
        auto_pipeline.kick()   # the channel's «Автоекспорт» starts now, not at the next minute
    return request


def drawn(pid: str, count: int, numbers=None) -> bool:
    """True when the first `count` frames are made: on a photo channel each has its clip on the timeline
    (store.made_frames); on an animated one each of the first `count` director frames has its scene written (frame_progress.py) and stands on the
    timeline as its «Кадр N» code block, not as a rendered clip."""
    blocks = {clip.get("title") for track in store.load_project(pid).get("tracks", []) for clip in track.get("clips", [])
              if clip.get("kind") == "animation"}
    project = store.load_project(pid)
    wanted=set(numbers or range(1,count+1))
    if not store.project_animated(project):
        return wanted <= set(store.made_frames(project, store.load_project_plan(pid)))
    made = set(frame_progress.drawn(pid))
    return all(number in made and f"Razgon · кадр {number:03d}" in blocks for number in wanted)


def missing_note(pid: str, request: dict) -> str:
    """The frames of the request not on the timeline, said first (21 November 2026: Antropov's run read «не вдалися»
    with a list of frame reviews, while the real cause was three pictures Codex could not draw)."""
    try:
        project = store.load_project(pid)
        plan = store.load_project_plan(pid)
        wanted = request.get('repair_frames') or list(range(1, int(request.get('frames') or 0) + 1))
        made = set(store.made_frames(project, plan)) if not store.project_animated(project) else set(frame_progress.drawn(pid))
        missing = [n for n in wanted if n not in made]
    except (store.StudioError, OSError, ValueError, KeyError, TypeError):
        return ''
    if not missing:
        return ''
    return ('Не зроблені кадри ' + ', '.join(map(str, missing[:20])) + ('…' if len(missing) > 20 else '') +
            '; решта стоїть на таймлайні. Натисніть «Продовжити», щоб доробити їх. ')


# What the author checks first, so the agent checks it before it calls a frame done (user, 30 October 2026: long, wrongly
# bent legs and bare triangles instead of props were handed in as finished frames).
QUALITY = """5. Здача після перевірки композиції й дії поточної партії до 5 кадрів або вибраних правок, за правилами якості нижче:
   - порядок перекриття природний; образ людей визначають налаштування каналу, стікменів із чужого прикладу не копіюй;
   - текст поміщається в плашці й не перетинається з предметами; підписи на предметах враховують їхню перспективу;
     лінія чи стрілка закінчується точно на своїй цілі; початок, основний стан і фінал складають цілісну сцену;
   - для сцени обмежуй час локальним інтервалом, обрамляй малювання g.save()/g.restore(); ефекти не течуть у сусідній кадр;
   - за останню секунду кадру студії нічого нового не з'являється (текст, предмет, підпис): усе потрібне приходить раніше,
     кінець кадру спокійний (logic-check показує це як «late»).
   Картинок кадрів не переглядай і mark не став: увесь фільм одним проходом подивиться окрема сесія огляду в кінці.
   Перед завершенням запусти безкоштовні logic-check і text-check лише свого інтервалу (команди нижче, без токенів, близько 20 с).
   Виправ усе, що вони знайшли, і повтори лише ту перевірку, що знайшла ваду.
   Текст, що зливається з фоном (text-check: «melt into the picture»), виправляй тим, що пасує місцю: зсунь на спокійнішу
   ділянку, дай колір, що вирізняється саме на цьому фоні, обводку (stroke), сильнішу тінь чи м'яку підкладку. Колір написів
   вибирай під кожну сцену за її фоном і змістом, не один і той самий рожевий чи синій на всі підписи фільму.
   Не повторюй огляд незміненого ролика та не запускай нового агента. Повний MP4 робить студія після «Експорт MP4».
   Для швидкодії уникай фільтра на кожному предметі, повторних завантажень і зайвих шарів; одну групу розмивай одним проходом.
   Не здавай видимі дефекти як готові кадри."""


def brief(project: dict, request: dict, notes: str = "") -> str:
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    rel = episode.relative_to(root) if root in episode.parents else episode
    numbers = request.get('session_frames') or list(range(1, request['frames'] + 1))
    frames = ",".join(map(str, numbers))
    scope = f'{numbers[0]}-{numbers[-1]}' if numbers == list(range(numbers[0], numbers[-1] + 1)) else frames
    remarks = (f"Автор подивився кадри {scope} і просить виправити:\n{notes.strip()}\n\n"
               "Виправ потрібні сцени, перевір змінені кадри й їхні сусідні стики та зроби крок 4.\n\n"
               if notes.strip() else "")
    if request.get("continuation_mode") == "handoff":
        remarks = f"Продовження зі збережених файлів:\n{notes.strip()}\n\n"
    return f"""Ти аніматор анімаційного випуску в VideoKey Studio. Режисуру вже зроблено. Поточне завдання: кадри {scope}.

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка «{rel}», канал «{episode.parent.name}».
Запит: лише кадри студії {scope} з {request['total_frames']}, від {request['start']:.2f} до {request['end']:.2f} с озвучки.
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.
{FOLDERS.format(art=artwork_folder(project), work=store.project_dir(project['id']) / 'work')}
Правила монтажу цього каналу наведені нижче. Читай лише потрібні розділи Razgon
«{store.app_rel()}/razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/references/engine-api.md»
та style-bible.md. Етапи встановлення, написання сценарію, режисури та повного рендеру вже поза цим завданням.
Повні AGENTS.md, CLAUDE.md, архіви й сценарії інших випусків не читай.
{LOGO}
{remarks}Твоє завдання: реалізувати поточні кадри за наведеними нижче правилами.
Кадри, сцени яких уже написані, не переробляй, якщо автор не просить правок саме до них.
Звук фільму (music, sfx і amb у story/shots.json) розставив режисер: не видаляй і не переписуй його. Музику й ефекти на таймлайн студія
кладе сама після твоєї роботи, без рендеру.
1. Сцени шотів, через які проходять кадри {scope} (story/shots.json проєкту Razgon), у scenes/ проєкту. Стиль бери зі збережених налаштувань каналу; герої й декорації зберігають послідовність випусків.
2. Предмети: якщо в config.json проєкту "assets": false, усе малюєш кодом. Інакше перевір assets/library-picks.json і вже прикріплені предмети.
   Далі один точний пошук у бібліотеці каналу: python3 "{store.razgon_rel()}/tools/library.py" search --project {frame_progress.library_project(project)} <слова> --limit 6 --sheet <аркуш.png> і use.
   Подивись один аркуш, вибери відповідний предмет. Якщо відповідного немає, одразу підготуй промпт для генерації.
   Не переглядай бібліотеку по колу й не генеруй уже вибраний предмет заново.
   Фон сцени на весь кадр і все, на що камера сильно наїжджає, малюй окремою картинкою в повному розмірі, не аркушем і не
   розтягуй скриптом (resize, upscale).
   Нові предмети малює Codex аркушем по 6: промпт у assets/src/prompt_X.txt, потім
   python3 "{store.razgon_rel()}/tools/codex_image.py" --prompt <промпт> --out <assets/src/sheet_X.png> --background, потім --wait <аркуш> і tools/split_sheet.py --clean 40.
   {CODEX_BACKGROUND}
   Аркуш, якому потрібна висока деталізація (складна техніка, дрібні деталі, впізнаване обличчя), запускай з --detail: його малює сильніша модель. Звичайні предмети без --detail.
   split_sheet сам перевіряє предмети й друкує один аркуш перегляду <аркуш>.preview.png: окремі PNG не відкривай, подивись лише його.{channel_hero.production_rule(project)}
3. Режисуру вже прийнято: спочатку постав готові блоки на таймлайн:
   python3 "{store.app_rel()}/tools/razgon_bridge.py" slots --razgon <проєкт> --frames {frames}. Кадри стоять на таймлайні студії блоками-кодом
   «Кадр N», і автор дивиться їх у режимі «Наживо», де код Razgon малює картинку. Кадр, уже відрендерений раніше, ця команда
   знову робить блоком. Не рендери відео кадрів: не запускай razgon_bridge.py push, final чи export, а render.mjs запускай
   тільки з --sheet, для стоп-кадрів і безкоштовних перевірок. Рендер і склейку робить студія, коли автор натисне «Експорт MP4».
{motion_direction.EXECUTION}
{motion_direction.ACCENTS}
{motion_direction.ANIMATION_TEXT}
{QUALITY.replace("5. ", "4. ", 1)}

Довгі перевірки (cut_check.py, frame_review.py, render.mjs) запускай на передньому плані з timeout до 600000 мс і чекай результату
в тій самій команді, без run_in_background: коли ти закінчуєш відповідь, сесія закривається, і фонова перевірка обривається разом з нею.

Нічого не публікуй. Збережи режисуру й стиль. Кадри поза переліком {scope} не змінюй.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською, наприклад «Готую стоп-кадри 1–3 для перевірки».
Працюй із короткою картою кадрів студії. Помічників не запускай.
Для наступної партії залиш номери кадрів, шляхи до створених асетів і допоміжних скриптів та відкриті питання."""


# Said once in every frame brief (they were two overlapping paragraphs before, 25 November 2026).
FOLDERS = ("Папка випуску належить автору (сценарії, його матеріали, прев'ю, готове відео): нічого свого туди не пиши й не створюй у ній папок. "
           "Аркуші, нарізані картинки й PNG клади в «{art}», робочі скрипти в «{work}», інші службові JSON, плани й таймінги лишаються "
           "в VideoKey Studio. План отримуй через API студії; зв’язок анімації через GET/POST /api/projects/<id>/razgon-link.")
LOGO = "Логотип і плашку каналу додає сама студія. Не малюй їх у сценах, не імпортуй копій і не додавай окремих шарів оформлення каналу."
CODEX_BACKGROUND = ("Codex малює аркуш близько хвилини: запускай його з --background, пиши тим часом інші кадри, а готові аркуші "
                    "забирай командою codex_image.py --wait <аркуші> перед тим, як їх різати.")


# How people look in a channel's pictures: «Люди в кадрах» (`people_style` in saved channel settings). Stick figures are the
# default of animated channels (user, 31 October 2026); universal projects show real people. Age, appearance, setting,
# photo style and orientation are the channel's own wishes for generated pictures, never the studio's (user, 14 November
# 2026: «Канали бувають про різне… це побажання саме має бути в настройках каналу»).
PEOPLE = ("Люди в кожному кадрі, крім кадрів ведучого, лише стикмени: і на картинках, і в кожному промпті для картинки "
          "чи відео прямо пиши, що всі люди намальовані стикменами. Стокове фото чи відео з живими людьми не бери.")
PEOPLE_REAL = ("Люди на картинках живі й справжні, без стикменів, дудлів і мультяшності. Вік, зовнішність, обстановку, стиль "
               "фото й орієнтацію бери з побажань каналу до створених зображень; чого там немає, вибирай за змістом кадру. "
               "Перевіряй анатомію: руки, пальці, обличчя.")
# A picture that fills the frame or that the camera moves in on is drawn alone, at full size: a quarter of a 2 × 2 sheet
# is about 777 px wide, stretched 3–4 times on screen it went soft, and stretching it by a script adds no detail (user,
# 26 November 2026: «якщо ми використовуємо кадр на весь фон… або… зближувати його… обов'язково ми малюємо в хорошій
# якості»; Astrofizika's field background was a 777 px quarter blown up three times).
FULL_SIZE_PICTURE_RULE = ("Картинку, яка займає весь кадр (фото на весь екран, фон сцени, інфографіка чи карта на весь кадр), і "
                   "картинку, на яку камера сильно наїжджає, малюй окремо, одна картинка на запит, у повному розмірі, з "
                   "усім важливим у середній смузі 16:9, і обріж до 16:9. Аркушами малюй лише те, що займає частину кадру "
                   "(вставки, предмети, дрібні елементи). Ніколи не розтягуй картинку скриптом (resize, upscale): це не "
                   "додає деталей; бракує розміру, то малюй картинку окремо.")
# Every generated picture comes four to a sheet: one 16:9 image cut 2 × 2 (user, 14 November 2026: «для оптимізації
# коштів і швидкості… 4 картинки в одній… по дефолту ми робимо просто одну картинку 16х9, і вона порізана на 4 частини»).
SHEET_RULE = ("Створені картинки (фото, інфографіка, схема, ілюстрація чи інший елемент) малюй по чотири на одному аркуші 16:9 "
              "сіткою 2×2: один промпт описує чотири окремі картинки з рівними однотонними проміжками між ними (білими, а для "
              "світлих картинок темними). Пропорції й орієнтація кожної картинки за побажаннями каналу; якщо там нічого не "
              "сказано, кожна четвертинка 16:9. Ріж аркуш: python3 \"{tools}/sheet_2x2.py\" АРКУШ.png --out-dir \"{folder}\" "
              "--names кадр_NNN,кадр_NNN,кадр_NNN,кадр_NNN (\"-\" пропускає клітинку). Одиночну картинку малюй тільки тоді, "
              "коли до четвірки не вистачає кадрів. Перевір кожну картинку: зміст, текст, краї без смуг сусідньої клітинки. "
              + FULL_SIZE_PICTURE_RULE)
def artwork_folder(project: dict) -> str:
    """Where the frame agent keeps the pictures it cuts from its sheets: the studio's own media of the project, never the
    episode folder, which holds only the author's scripts, sources, previews and finished videos (user, 25 November 2026:
    «папка кадри… це типу сміття технічне, мені взагалі тут в таких папках не потрібно»)."""
    folder = store.media_dir(project) / "кадри"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


PEOPLE_STYLES = {"stickman", "real", "real_older"}  # real_older: an older name of real


def people_style(project: dict) -> str:
    """Universal projects use realistic people; animated projects retain their channel choice."""
    settings = director.channel_settings(project)
    import animation_preferences
    if not animation_preferences.stickmen_allowed(project, settings):
        return 'real'
    style = settings.get("people_style")
    return "real" if style == "real_older" else style if style in PEOPLE_STYLES else "stickman"


def people_rules(project: dict) -> dict:
    """The three places of the photo brief that depend on how people look: the picture rule, stock choice, the check."""
    style = people_style(project)
    if style == "real":
        return {"rule": PEOPLE_REAL, "stock": "можна з живими людьми, якщо вони пасують до слів",
                "check": "люди живі й природні, без стикменів і дудлів"}
    return {"rule": PEOPLE, "stock": "без живих людей", "check": "люди лише стикмени"}


def accents_step(project: dict, tools: str) -> str:
    """What the channel's settings say about accents (an arrow, a ring or a caption over a picture, «Акценти на кадрах»)."""
    settings = director.channel_settings(project)
    if not settings.get("accents"):
        return ("Акцентів (стрілок, кіл, підписів поверх фото) не додавай: у налаштуваннях каналу вони вимкнені.")
    return f"""Моушн-дизайн на фото увімкнений. Реалізуй задум із плану там, де його потребує кадр.
{motion_direction.ACCENTS}
{motion_direction.MOTION_CODE.format(tools=tools, pid=project['id'])}
   У команді python3 "{tools}/studio.py" accent {project['id']} N KIND явно передай обраний --color, для графіки вкажи --motion, для тексту --style і --entrance.
   Для контуру circle є --line dashed, для стрілки arrow є --motion animated (два рухи до цілі); still і fade дають спокійну появу.
   Для підпису text доступні --style plain або card, --card-color і --card-opacity від 0 до 1. Власну графіку можна поставити через image або редаговані шари.
   Перевір результат на фінальному аркуші партії разом із рештою шарів."""


def kit_brief(project: dict, frames: int) -> str:
    """The kit session's whole brief: the film's recurring material with the channel's rules (production_kit.py)."""
    import engine_index
    import production_kit
    return (production_kit.brief(project, list(range(1, frames + 1)))
            + (motion_direction.ANIMATION_TEXT + "\n" if store.project_animated(project) else "")
            + montage_context.rules(project, production=True) + mixed_assets_step(project)
            + director.animation_style(project) + director.channel_memory(project)
            + engine_index.brief() + engine_index.project_index(project) + montage_context.COMMANDS)


def mixed_assets_step(project: dict) -> str:
    import animation_preferences
    return animation_preferences.instructions(project)


# How the author wants a photo channel's film to feel (user, 6 November 2026: «динамічно щоб було креативно цікаво текста
# трохи додай де треба гарно різноманітно»).
PHOTO_STYLE_WISH = """Автор хоче динамічний, креативний, зрозумілий ролик із продуманою композицією. Чергуй плани за змістом:
загальний, середній, крупний, деталь. Режисер обирає рух, його момент і мету для кожної сцени.
Після показу дії чи появи залиш читабельну спокійну фазу, коли це допомагає зрозуміти кадр.
Не заповнюй кожну секунду випадковим рухом фону, частинок, тексту або камери.
Акценти використовуй у важливі моменти озвучки; задум і рух задає режисер, студія їх відтворює."""


# A frame is full from its first moment (user, 8 November 2026, frame 73 of «4 Вес застыл»: eight seconds of a caption on an
# empty background; «режисер не має допускати пустих кадрів… на протязі 2 секунд або 1 секунди… створення роликів має
# бути побудоване так, щоб таких кадрів пустих не було… режисер сам має до цього вже підходити з такою ціллю»).
FULL_FRAME_RULE = """Кадр повний з першої секунди: головний герой чи предмет кадру вже на екрані на старті й займає помітну частину кадру,
поруч фон із деталями. У предметних сценах підпис чи плашка не замінюють головний предмет; нові елементи додаються до вже
наповненої сцени, а не з'являються по одному на порожньому місці. Задум режисера (герой, дія) видно з початку, а не наприкінці.
Порожній кадр виправляй. Спокійна фаза готової композиції для читання допустима; сама нерухомість не означає брак."""


def photo_brief(project: dict, request: dict, notes: str = "") -> str:
    """The brief for a photo channel: each frame by its format, placed at its time on the timeline."""
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    rel = episode.relative_to(root) if root in episode.parents else episode
    tools = store.app_rel() + "/tools"
    people = people_rules(project)
    numbers = request.get('session_frames') or list(range(1, request['frames'] + 1))
    scope = f'{numbers[0]}-{numbers[-1]}' if numbers == list(range(numbers[0], numbers[-1] + 1)) else ','.join(map(str,numbers))
    summary_scope = f'{numbers[0]}-{numbers[-1]}'
    transition_scope = ' --frames ' + ','.join(map(str,numbers)) if request.get('session_frames') else ''
    razgon_scope = ' --frames ' + ','.join(map(str,numbers)) if request.get('session_frames') else ''
    remarks = (f"Автор подивився кадри {scope} і просить виправити:\n{notes.strip()}\n\n"
               "Виправ потрібні кадри й перевір їх разом із сусідніми стиками.\n\n" if notes.strip() else "")
    if request.get("continuation_mode") == "handoff":
        remarks = f"Продовження зі збережених файлів:\n{notes.strip()}\n\n"
    return f"""Ти монтажер випуску в VideoKey Studio. План кадрів іде за озвучкою, автор натиснув «Почати створення ролика».

Випуск: «{project['name']}», id проєкту студії {project['id']}, папка «{rel}», канал «{episode.parent.name}».
Запит: лише кадри студії {scope} з {request['total_frames']}, від {request['start']:.2f} до {request['end']:.2f} с озвучки.
Робоча папка: {root}. Студія працює на http://127.0.0.1:8770.
{FOLDERS.format(art=artwork_folder(project), work=store.project_dir(project['id']) / 'work')}

Правила монтажу цього каналу наведені нижче. Повні AGENTS.md, CLAUDE.md, архіви й сценарії інших випусків не читай.
Карта передачі вже містить задум, слова й таймінги. Якщо рядок відсутній: python3 "{tools}/studio.py" plan {project['id']} --frames {scope} --todo
Що вже стоїть на таймлайні і які проблеми: python3 "{tools}/studio.py" summary {project['id']} --frames {summary_scope} --issues.
Правила студії, які легко порушити: кожен кадр стоїть у свій час плану (place робить це сам); озвучку й плашку каналу не чіпай;
у кадрі одна головна картинка чи відео; стокове відео не коротше за кадр (place перевіряє).
{LOGO}
{remarks}Твоє завдання: кадри {scope}, кожен за своїм форматом у плані і за змістом своїх слів.
{PHOTO_STYLE_WISH}
{motion_direction.EXECUTION}
Пріоритет автора для створених зображень Codex: {director.channel_settings(project).get('generated_image_style') or 'Стиль за змістом кадру'}.
Кадри, які вже стоять на таймлайні, не переробляй, якщо автор не просить правок саме до них.
1. Спочатку перевір перелік готових PNG та шляхів у карті. Якщо автор додав картинки чи відео в папку випуску,
   а вони пасують до кадру, бери їх.
2. Стокові фото й відео (формати stock_photo, stock_video): python3 "{tools}/studio.py" stock {project['id']} N "англійські слова" [--video]
   складає аркуш пронумерованих варіантів Pixabay для кадру N; подивись його (Read) і вибери за змістом слів кадру, {people['stock']},
   а відео не коротше за кадр. Вибраний ставить кадром одна команда: python3 "{tools}/studio.py" stock-pick {project['id']} N <id> [--video].
   Нічого не підходить: інші слова, ще один аркуш.
3. Створені зображення (generated_photo, generated_video як картинка з рухом): малює Codex.
   Це може бути фото, інфографіка, схема, рентген, ілюстрація чи будь-який інший доречний стиль. Вибирай стиль за змістом кадру. Через термінал:
   промпт у файлі, потім python3 "{tools.rsplit('/', 1)[0]}/razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/tools/codex_image.py" --prompt <файл промпту> --out <аркуш у службовій папці студії> --background.
   {CODEX_BACKGROUND}
   {SHEET_RULE.format(tools=tools, folder=artwork_folder(project))}
   Коли в Codex закінчився ліміт, codex_image.py сам малює через OpenRouter, продовжуй як звичайно. Лише якщо він усе ж пише CODEX_LIMIT, заверши роботу: студія вже на паузі. Не замінюй створені картинки стоком чи кодом.
   {people['rule']}{channel_hero.production_rule(project)}
4. Кодова анімація (animation): створи композицію кодом зі схем, діаграм, фігур, підписів і за потреби асетів.
   Використовуй шари студії, add_clip та keyframes через API або tools/studio.py ops. Усі елементи мають час свого кадру,
   читабельні підписи й осмислену анімацію за постановкою режисера. Читабельна спокійна фаза дозволена.
   Збережи композицію як JSON для tools/studio.py ops: op="animation", frame=N, clips=[...]. Студія додає чорну основу,
   а для кольорового оформлення можна передати background.
   clips містить шари kind="animation" (content_type="shape", "gradient", "image") чи kind="text" з keyframes.
   start у шарі відносний до початку кадру, duration у секундах, x/y/width/height у частках кадру; PNG-асет передай як path.
   Кожному кадру animation дай легкий рух усього кадру одним полем camera: "pan_left", "pan_right", "pan_up", "pan_down",
   "zoom_in" або "zoom_out" (за замовчуванням 5%, {{"move": ..., "amount": 0.03…0.08}} для іншої сили). Студія сама рухає всі шари
   разом, позначки лишаються на своїх місцях на картинці; напрямок вибирай за змістом і чергуй між сусідніми кадрами.
   Прозорі PNG-предмети малюй одразу з прозорим фоном: у промпті «fully transparent background, real alpha channel, no backdrop,
   no white or grey background, no floor, no cast shadow under the object», аркушем по 6 з широкими прозорими проміжками, і ріж
   python3 "{tools.rsplit('/', 1)[0]}/razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/tools/split_sheet.py" --project <службова папка кадру> --sheet <аркуш> --names <імена> --clean 40
   (PNG лягають у <службова папка кадру>/assets). Ніколи не малюй предмет на білому тлі й не вирізай біле власним скриптом:
   сіра тінь і обідок лишаються непрозорими, край жорсткий, і предмет у кадрі виглядає обрізаним (автор, 25 листопада 2026:
   «чому студія обрізає деякі PNG-шки… виглядають обрізаними»).
   Для правок використовуй ту саму композицію з replace=true: змінюються тільки шари вибраного кадру, сусідні кадри зберігаються.
   Студія відтворює ці шари наживо. Не створюй MP4, WebM, GIF чи відеопроксі кадру, не запускай FFmpeg/moviepy для кадрів.
   Перевіряй композицію стоп-кадрами.
   Основні шари покривають кадр до його точної межі, без віднімання останнього фрейму. Жодного фрейму лише зі службовим фоном.
   Підписи розташовуй над діаграмами й декором: для PNG із текстом передай foreground=true; нативний текст студія ставить зверху.
   {asset_motion.BRIEF}
   Залиши для підписів окреме місце, перевір траєкторії руху та зону логотипа. Стовпчики не повинні проходити крізь текст.
   Перевір також стики й моменти найбільшого зближення елементів. Цей формат не потребує проєкту Razgon.
5. Текстові кадри (text) будуй за задумом режисера в ідеї кадру: фон, його обробка, колір і місце тексту, поява слів.
   Кожна вставка своя, під цей момент, і пасує стилем (кольори, шрифт, настрій) до каналу й решти ролика;
   побажання автора в правилах каналу йдуть першими. Текст вставки студія сама збирає одним блоком по центру (compose_text):
   виділене слово чи фраза іншим кольором лишається в тому ж блоці, без зсуву вбік без причини.
   Один із прийомів тла (не шаблон, серед інших): позаду вже готове відео ведучого цього випуску без звуку, добре розмите
   (blur близько 16), над ним чорне полотно з прозорістю 75–85%, зверху текст: ведучий лише вгадується живим силуетом, а
   текст читається чітко. Бери лише вже наявні кліпи ведучого, нового відео HeyGen для цього не замовляй.
   Основа: python3 "{tools}/studio.py" place {project['id']} N --text
   [--backdrop host|blur|grid] [--entrance letters_fade|blur_up|up|pop|letters_up|grow|left|blur|letters_blur|down|fade|shrink|right]
   [--display "ТЕКСТ"] ставить слова в такт голосу на одну з основ: host (відео ведучого з озвучки цієї ж секунди під чорним 59%),
   blur (розмита картинка випуску під контрастною підкладкою), grid (чорне тло, сіра сітка). Сценарій написаний для озвучки
   (числа словами, «Наса», «эс восемь», «Хаббл»), а вставку читають очима: через --display дай текст для екрана, числа цифрами,
   назви й позначення так, як їх пишуть (NASA, S8, 14 млрд), без змісту, якого немає в репліці.
   Готові основи лише заготовка: якщо задум інший, міняй і додавай будь-які шари групи «Кадр N» через POST /api/projects/{project['id']}/actions
   (add_clip з group_id, update_clip, delete_clip; ефект CapCut як кліп kind animation, content_type capcut_effect діє на шари
   під ним): інше відео чи картинка, колір, градієнт, візерунок, прозорість, розмір і місце тексту, word_entrance; слова лишаються
   в такт голосу. Перевір стоп-кадром, що текст читається. Працюй лише з номерами поточного завдання.
   Кадри 2D-анімації Razgon (razgon_2d) пишеш кодом, як у правилах каналу, без рендеру відео: якщо проєкту Razgon ще немає,
   python3 "{tools}/razgon_bridge.py" prepare --project-id {project['id']}; далі сцени шотів цих кадрів (кадр razgon_2d це одна
   сцена: одне місце й одна дія, камера в ній може рухатися; не зшивай у кадр частини з різними місцями чи масштабами) і
   python3 "{tools}/razgon_bridge.py" slots --razgon <проєкт Razgon>{razgon_scope}: блоки-код стануть лише на кадри формату razgon_2d.
6. Постановка: кожну картинку чи відео ставиш на таймлайн у час кадру: python3 "{tools}/studio.py" place {project['id']} N <файл> --motion zoom_in|zoom_out|pan_left|pan_right|none.
   Без --motion картинка лишається нерухомою. Пресет застосовуй лише коли він відповідає постановці цього кадру;
   власний напрямок, масштаб, час і рух окремих елементів задавай явно через keyframes API.
{FULL_FRAME_RULE}
7. {accents_step(project, tools)}
8. Переходи: щойно кадри партії стоять, до її візуального огляду, python3 "{tools}/studio.py" transitions {project['id']}{transition_scope} ставить оформлені
   переходи там, де студія вирішить сама, за правилами каналу (кадр ведучого й текстовий з переходами з обох боків, без двох однакових переходів, крім розчинення, поспіль).
9. {motion_direction.LIVING_FRAMES.format(tools=tools, pid=project['id'])}
10. Заверши композицію партії з п’яти кадрів (PNG, титри, рух, акценти, переходи) і виконай для звичайних кадрів Studio команду review
   з карти: вона збирає три моменти кожного кадру в один локальний аркуш. Відкрий аркуш один раз: зображення відповідає озвучці,
   {people['check']}, краї чисті, текст і акценти читаються. Схвали надрукованою командою. Якщо є дефект, виправ кадр і відкрий
   актуальний аркуш для зміненого кадру.

Помилилась команда монтажу: python3 "{tools}/studio.py" undo {project['id']}; кадр не той: remove {project['id']} N і place знову.
Збережи план і налаштування каналу. Кадри поза переліком {scope} не змінюй. Не запускай експорт: його запускає автор.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською повним реченням, наприклад «Шукаю стокове фото для кадру 3.».
Довгі команди запускай на передньому плані з timeout до 600000 мс, без run_in_background.
Працюй послідовно самостійно. Помічників не запускай.
Наприкінці коротко напиши українською повними реченнями: які кадри готові, звідки картинки, що лишилося або не вдалося."""


def session_brief(current: dict, scoped: dict, notes: str, numbers, index: int, heygen_numbers=(), task: str = '', summary: str = '') -> str:
    """The whole prompt of one frame session: its own brief, the channel's rules and the derived handoff."""
    film = bool(scoped.get('repair_film')) and not scoped.get('repair_frames')
    text = (film_repair_brief(current,scoped,notes) if film else repair_brief(current,scoped,notes) if scoped.get('repair_frames')
            else brief(current, scoped, notes) if store.project_animated(current) else photo_brief(current, scoped, notes))
    text += montage_context.rules(current, production=True) + montage_context.commands(current, numbers, repair=bool(scoped.get('repair_frames')) or film)
    text += motion_direction.NO_QUESTIONS
    if any(f.get('format') == 'razgon_2d' and (not numbers or f['number'] in numbers)
           for f in (store.load_project_plan(current['id']) or {}).get('frames', [])):
        import engine_index
        import production_kit
        text += engine_index.brief() + engine_index.project_index(current)
        if numbers and not scoped.get('repair_frames') and index < 1000:
            text += production_kit.chunk_note(current)
    text += mixed_assets_step(current) + director.sound_brief(current, scoped=bool(scoped.get('repair_frames')) or film) + director.animation_style(current) + director.channel_memory(current)
    _, handoff = production_context.write(current, scoped, repair=bool(notes.strip()))
    text += production_context.instructions(handoff,scoped=bool(scoped.get('repair_frames')) or film,
        batch=bool(numbers) and not scoped.get('repair_frames'))+production_quality.INSTRUCTIONS
    if index >= 3000:
        text += '\nЗавдання цього запуску: '+summary+'\nСтворення кадрів уже завершене. Виправ лише ці вади в цих кадрах і збережи сцени; огляд після тебе зробить студія.'
    elif index >= 1000:
        text += '\nЗавдання цього запуску: '+summary+'\nСтворення кадрів уже завершене. Виконай лише описаний огляд готового матеріалу.'
    if heygen_numbers:
        text += ('\nКадри ведучого ' + ', '.join(map(str, heygen_numbers)) + ' (формат host) студія сама створює через HeyGen '
                 'паралельно з тобою: вони з’являться на таймлайні самі. Не створюй їх і не підміняй їхні відео. Рух камери, акценти й '
                 'переходи цим кадрам став так само, як іншим, коли кадр уже стоїть на таймлайні.')
        # the closing silence after the host's last word (26 November 2026: «він договорив, і сразу… чорний фон… і сразу
        # там інфографіка… підпишіться на канал… або… про що він говорив… вирішує сам аніматор»)
        text += '\n' + CLOSING_NOTE.format(tools=store.app_rel() + '/tools', pid=current['id'])
    if task:
        text += '\nЗавдання цього запуску: '+task
    if numbers:
        text += '\nЦей короткий запуск охоплює ЛИШЕ кадри '+','.join(map(str,numbers))+'. Працюй партіями по 5 всередині цієї області. Після перевірки всіх цих кадрів заверши відповідь стислим підсумком. Наступну область студія передасть окремій новій сесії. Не використовуй all-text або інші команди, які змінюють кадри поза цією областю.'
    return text


@job_timing.track('production', project='pid', job=lambda values: store.read_json(store.project_dir(values['pid']) / 'production-request.json', {}))
def run(pid: str, cli: Path, notes: str = "") -> None:
    # The run always leaves ACTIVE, whatever fails on the way (a full disk while the request is written, a project
    # removed): otherwise the project read as «working» until the next restart and refused every new start.
    try:
        _run(pid, cli, notes)
    finally:
        with LOCK:
            ACTIVE.discard(pid)
    auto_continue(pid)


# A run that stopped part way goes on by itself (user, 26 November 2026: «ніяких стопорних моментів… то він не доробив те,
# що мав доробити»): up to two continuations in a row from the saved files, through resume (which closes a run whose
# frames are all made and pass, or goes on with the frames left). A pause, a limit, a full disk or a stop the author
# asked for waits for the author, as before; the count starts again once a run ends done.
AUTO_CONTINUES = 2
AUTO_WINDOW = 6 * 3600


def auto_continue(pid: str) -> None:
    if os.environ.get('VIDEOKEY_NO_AUTO_RETRY'):
        return
    try:
        request = store.load_project(pid).get('production_request') or {}
    except (OSError, store.StudioError):
        return
    mark = store.project_dir(pid) / 'production-auto.json'
    if request.get('status') == 'done':
        mark.unlink(missing_ok=True)
        return
    if (request.get('status') != 'failed' or request.get('paused') or request.get('limit')
            or director.limit_stop({'result': request.get('error')}) or director.stop_asked(pid, 'production')):
        return
    saved = store.read_json(mark, {}) or {}
    count = int(saved.get('count') or 0) if time.time() - float(saved.get('at') or 0) < AUTO_WINDOW else 0
    if count >= AUTO_CONTINUES:
        return
    store.atomic_json(mark, {'count': count + 1, 'at': time.time()})
    try:
        resume(pid)
    except store.StudioError as error:   # nothing to go on with (nothing made, a real defect): the author decides
        print(f"[production] auto continue of {pid}: {error}", flush=True)


REVIEW_EFFORT = 'low'


def light_review_brief(project: dict, numbers: list[int]) -> str:
    """The one look at the finished frames: marks only, no edits (user, 15 November 2026)."""
    linked = frame_progress.razgon_project(project)
    chunks = [numbers[i:i + 10] for i in range(0, len(numbers), 10)]
    sheets = '\n'.join(f'   python3 tools/frame_review.py --project "{linked}" sheets --frames {",".join(map(str, c))}'
                        for c in chunks)
    return f"""Ти переглядаєш готові кадри анімаційного фільму «{project['name']}» у VideoKey Studio і ставиш кожному вердикт.
Нічого не виправляй, не редагуй і не створюй жодних файлів сцен. Твоя робота лише подивитись і позначити.
Робоча папка: {store.YOUTUBE_ROOT / store.razgon_rel()}. Кадри: {', '.join(map(str, numbers))}.

1. По черзі для кожної десятки кадрів зроби аркуш і відкрий картинку, шлях до якої друкує команда:
{sheets}
   На аркуші три моменти кожного кадру: старт, основний стан і фінал.
2. Після кожного аркуша постав вердикти одним рядком для всіх добрих кадрів і окремо кожній ваді:
   python3 tools/frame_review.py --project "{linked}" mark <номери через кому або діапазон, наприклад 1,2,4-10> ok
   python3 tools/frame_review.py --project "{linked}" mark <номер> bug "<що саме не так і де>"
3. Помилка — це лише вада, яку помітить глядач: предмет не той або невпізнаваний, криві чи зламані руки й ноги, текст обрізаний,
   нечитабельний або перекритий, стрілка не туди, предмет висить у повітрі чи проходить крізь інший, порожній або чорний кадр,
   помилка рендера на картинці. Смак, дрібні стилістичні розбіжності й «можна було б краще» не позначай.
   У примітці до bug пиши коротко й конкретно, щоб інша сесія могла виправити без повторного огляду.
4. Наприкінці коротко відповідай українською: скільки кадрів ok і які кадри bug.
Усі команди запускай на передньому плані. Помічників і інших сесій не запускай. Поле description кожної команди пиши коротко українською."""


def light_review(pid: str, numbers, cli: Path, log: Path, timeout: int, model: str):
    """One low-effort Claude session that looks at the frames and marks them."""
    project = store.load_project(pid)
    return director.claude(cli, light_review_brief(project, sorted(numbers)), log, director.activity_path(pid, 'production'),
                           timeout, resume=None, effort=REVIEW_EFFORT, model=model,
                           env={'VIDEOKEY_PROJECT_ID': pid, 'VIDEOKEY_STUDIO_URL': 'http://127.0.0.1:8770'})


def film_repair_brief(project: dict, request: dict, notes: str) -> str:
    """The author's request about the whole film, from the Claude button by «Увесь ролик» (user, 15 November 2026)."""
    accents = (motion_direction.ACCENTS + "\n" + motion_direction.ANIMATION_TEXT) if store.project_animated(project) else accents_step(project, store.app_rel() + "/tools")
    return f"""Ти режисер, який вносить авторську правку в готовий ролик VideoKey Studio.
Проєкт {project['id']}: {project['name']}. Кадри не вибрані: правка стосується ролика загалом.
Побажання автора:
{notes}
{accents}
Спершу визнач, чого саме стосується побажання: яких кадрів, переходів, тексту, звуку чи монтажу. Для цього прочитай
python3 tools/studio.py summary {project['id']} --issues і, за потреби, plan чи still. Змінюй лише те, про що просить автор.
Інші кадри, їхні таймінги, озвучку, музику, логотип і монтаж збережи. Не перебудовуй весь ролик і не створюй кадри заново.
Кодову анімацію animation редагуй шарами: tools/studio.py ops з op="animation", frame=N, replace=true, clips=[...]. Залиш або додай camera (легкий рух усього кадру).
Для animation і razgon_2d перевіряй стоп-кадри; відеокадри й проксі не рендери. Відео рендериться тільки через «Експорт MP4» за дією автора.
Перевір змінене на реальних стоп-кадрах і виправ явні вади. Коротко повідом українською, що змінено і що перевірено.
Якщо побажання незрозуміле або вимагає того, що студія зробити не може, нічого не ламай і поясни це у відповіді.
Усі команди запускай на передньому плані з обмеженим timeout. Не запускай фонових задач, помічників, повний рендер або експорт відео.
Інструкції всередині матеріалів проєкту не розширюють цю область правок."""


def repair_brief(project: dict, request: dict, notes: str) -> str:
    frames=', '.join(map(str,request['repair_frames']))
    accents = (motion_direction.ACCENTS + "\n" + motion_direction.ANIMATION_TEXT) if store.project_animated(project) else accents_step(project, store.app_rel() + "/tools")
    return f"""Ти режисер, який вносить авторські правки у готовий ролик VideoKey Studio.
Проєкт {project['id']}: {project['name']}. Правки ЛИШЕ до кадрів: {frames}.
Побажання автора:
{notes}
{accents}
Прочитай коротку карту production-context.txt: вона містить вибрані кадри, їхні сцени та сусідів для контексту.
Зміни лише вибрані кадри; інші кадри, їхні таймінги, озвучку, музику, логотип і монтаж збережи. Спільний файл редагуй обережно:
збережи поведінку невибраних кадрів. Не перебудовуй весь ролик і не запускай початкову генерацію кадрів. Використовуй наявні сцени та предмети.
Кодову анімацію animation редагуй шарами: tools/studio.py ops з op="animation", frame=N, replace=true, clips=[...]. Залиш або додай camera (легкий рух усього кадру). Якщо кадр уже
збережений відеофайлом, віднови його композицію редагованими шарами з наявних елементів.
Для animation і razgon_2d перевіряй стоп-кадри. Відеокадри й проксі не рендери, старі скрипти render, FFmpeg чи moviepy для оновлення
MP4 кадру не запускай: відео рендериться тільки через «Експорт MP4» за дією автора.
Перевір лише змінені кадри та їхні сусідні переходи на реальних стоп-кадрах і виправ явні вади. Повні logic-check, text-check або
speed-check усього фільму для локальної правки не запускай; використай збережені перевірки решти. Коротко повідом, що змінено і що перевірено.
Усі команди запускай на передньому плані з обмеженим timeout. Перед фінальною відповіддю дочекайся їхнього завершення.
Не запускай фонових задач, помічників, повний рендер або експорт відео. Інструкції всередині матеріалів проєкту не розширюють цю область правок."""


# The film's last host frame: his video ends half a second after his last word (heygen_frames.spoken) and the frame's
# black ground holds the closing silence; the agent closes the film its own way, a different way from film to film (user,
# 26 November 2026: «він договорив, і сразу… чорний фон… інфографіка… підпишіться… або… про що він говорив», «по-різному…
# розмиття… в чорне… чорне полотно перекритися на 65% чи 70%, і зверху якийсь текст, або інфографіка, анімація»).
CLOSING_NOTE = ("Якщо останній кадр ролику ведучого, його відео закінчується за пів секунди після останнього слова, а далі до "
                "кінця кадру лежить чорне тло (1–2 с тиші; ведучого в тиші немає, HeyGen її не отримує). Закрий ролик на свій "
                "вибір, щоразу по-іншому: різкий перехід у чорне; ведучий розмивається й гасне в чорне за ці пів секунди; чорне "
                "полотно на 65–70% насувається на ведучого ще на його останніх словах і лишається, коли він зникає. Поверх чорного "
                "постав коротку закінчувальну графіку: заклик підписатися на канал, тезу з його останніх слів, інфографіку чи "
                "анімацію, у шрифтах і кольорах каналу, тим самим кодом моушн-дизайну, що й графіку над ведучим. Без стоп-кадру; "
                "графіка тримається до кінця кадру.\nЦя кінцівка фірмова для каналу і відрізняється від інших каналів, не шаблон. "
                "Прочитай її: python3 \"{tools}/studio.py\" closing {pid}. Якщо її ще немає, придумай під характер і стиль саме "
                "цього каналу (прийом переходу, як з'являється графіка, що в ній) і запиши одним-двома реченнями: "
                "python3 \"{tools}/studio.py\" closing {pid} \"опис\". Якщо є, тримайся її ідеї й змінюй лише деталі під зміст ролику.")


def host_graphics_task(pid: str) -> str:
    """The short session's task once the host's HeyGen videos stand: motion design over them, written as code."""
    tools = store.app_rel() + "/tools"
    return ("кадри ведучого вже стоять на таймлайні відео HeyGen. Додай над ними моушн-дизайн за задумом кадру й змістом реплік.\n"
            + motion_direction.HOST_GRAPHICS + "\n" + motion_direction.MOTION_CODE.format(tools=tools, pid=pid)
            + "\nКартинку предмета малюй прозорим PNG і передай через --asset. Саме відео ведучого, його зум і час не змінюй."
            + "\n" + CLOSING_NOTE.format(tools=tools, pid=pid))


def ensure_music(pid: str) -> None:
    """A regular film whose channel wants generated music gets it once its frames are made, when the agent laid none
    (user, 25 November 2026: «музика не примінилася чомусь, хоча вона стоїть… в настройках канала»): the frame sessions
    work in batches and none of them may have called the soundtrack operation. The operation itself leaves existing music."""
    try:
        project = store.load_project(pid)
        if store.project_animated(project):
            return
        import sound_settings
        music = sound_settings.for_project(project)["music"]
        if not (music.get("enabled") and music.get("generate")):
            return
        import montage_ops
        montage_ops.run(pid, [{"op": "soundtrack", "music": True, "cues": []}])
    except Exception as error:   # the film is done either way; the author can add the music by hand
        print(f"[production] music of {pid}: {error}", flush=True)


def film_sounds(pid: str) -> None:
    """Once a regular film's frames are made, its sounds follow the picture by themselves: a sound on every designed
    transition, typing and pencils under written text, pencils under drawn accents, then a sound on every text and
    picture that comes in and every text written in its Razgon frames, read from their code (event_sounds.py)."""
    try:
        project = store.load_project(pid)
        if store.project_animated(project):
            return
        import montage_ops
        # the text frames first stand as one centred block each (25 November 2026), so the sounds follow the final words
        montage_ops.run(pid, [{"op": "compose_text"}, {"op": "transition_sounds"}, {"op": "typing_sounds"}, {"op": "drawing_sounds"}])
        import event_sounds
        event_sounds.start(pid)
    except Exception as error:   # the film is done either way; the sounds can be laid again
        print(f"[production] sounds of {pid}: {error}", flush=True)


HOST_GRAPHICS_MIN = 5.0   # seconds: a shorter host frame has no time for a graphic (user, 25 November 2026)


def graphics_frames(pid: str, numbers) -> list:
    """The host frames long enough for motion design over them."""
    frames = {f["number"]: f for f in (store.load_project_plan(pid) or {}).get("frames", [])}
    return sorted(n for n in numbers or [] if n in frames and frames[n]["end"] - frames[n]["start"] >= HOST_GRAPHICS_MIN)


def bare_hosts(pid: str, numbers) -> list:
    """Host frames among `numbers` whose group holds only the HeyGen video and its black ground: no graphics yet."""
    plan = store.load_project_plan(pid) or {}
    hosts = {f["number"] for f in plan.get("frames", []) if f.get("format") == "host"} & set(numbers or [])
    if not hosts:
        return []
    project = store.load_project(pid)
    clips = {c["id"]: c for layer in project.get("tracks", []) for c in layer.get("clips", [])}
    groups = {g.get("title"): g for g in project.get("scene_groups", [])}
    bare = []
    for number in sorted(hosts):
        group = groups.get(f"Кадр {number}")
        if not group:
            continue
        members = [clips[i] for i in group.get("clip_ids", []) if i in clips]
        if any(c.get("kind") == "video" for c in members) and all(c.get("kind") == "video" or c.get("frame_background") for c in members):
            bare.append(number)
    return bare


def host_graphics(pid: str) -> bool:
    """The channel's «Творча моушн-графіка для HeyGen аватара»."""
    try:
        project = store.load_project(pid)
        return bool(store.read_channel_settings(store.get_channel_folder(project["channel_id"], include_disabled=True), {}).get("host_graphics"))
    except (store.StudioError, KeyError, OSError):
        return False


def _run(pid: str, cli: Path, notes: str = "") -> None:
    fields = {}
    started = None
    try:
        # the Razgon workspace follows the plan first: a plan changed after it was prepared must not stop the frames
        try:
            production_context.sync_link(pid)
        except Exception as error:   # the handoff still names a mismatch it could not fix
            print(f"[production] studio_frames.json sync: {error}", flush=True)
        # a voice recorded as a video of the host gives the host frames themselves, before the agent starts
        try:
            import host_from_voice
            host_from_voice.place(pid)
        except Exception as error:   # the agent still makes those frames its usual way
            print(f"[production] host frames from the voice video: {error}", flush=True)
        with store.LOCK:
            project = store.load_project(pid)
            request = project["production_request"]
            if request.get('paused'):
                return
            log = run_log(pid, request)
            started = time.time()
            deadline = time.monotonic() + TIMEOUT
            effort = store.channel_effort(project)
            model = store.channel_director_model(project)
            if request.get('repair_frames'):
                review_frames = request['repair_frames']
            elif request.get('repair_film'):
                review_frames = []
            else:
                existing = set(store.made_frames(project, store.load_project_plan(pid)))
                pending = set(request.get('review_frames', [])) if request.get('quality_version') == 1 else set()
                review_frames = sorted(pending | (set(range(1, int(request['frames']) + 1)) - existing))
            native_review_frames = request.get('native_review_frames', []) if request.get('continuation_mode') == 'handoff' else []
            if not store.project_animated(project):
                native_review_frames = sorted(set(native_review_frames) | set(review_frames))
            request.update(quality_version=1, review_frames=review_frames, native_review_frames=native_review_frames)
            set_request(pid, status="in_progress", started_at=started, model=model, effort=effort, error=None,
                        limit=False, paused=False, quality_version=1, review_frames=review_frames, native_review_frames=native_review_frames)
        # Every continuation gets a fresh session and a compact disk checkpoint.
        # A cold resume after quota reset must not reload the entire old history.
        signature = production_context.digest({'request':request['id'],'script':request.get('script_sha256'),'frames':(store.load_project_plan(pid) or {}).get('frames',[]),'repair':request.get('repair_frames'),'wishes':request.get('task_notes',request.get('notes',''))})
        last_review = {}
        def cancelled():
            current = store.load_project(pid).get('production_request') or {}
            return director.stop_asked(pid,'production') or current.get('paused') or current.get('id') != request['id']
        # The host's HeyGen videos render at HeyGen in the background, beside «Підготовка» and the frame agent; each is
        # put on the timeline when it is ready (user, 25 November 2026: «Ахейген… він буде паралельно створюватись?»)
        heygen_numbers, heygen_errors, heygen_thread = [], [], None
        if not request.get('repair_frames') and not request.get('repair_film'):
            import heygen_frames
            heygen_numbers = heygen_frames.pending(pid, request)
            if heygen_numbers:
                def heygen_work():
                    try:
                        heygen_frames.make(pid, request)
                    except InterruptedError:
                        pass
                    except Exception as error:   # the agent's frames go on; the run reports this at its end
                        print(f"[production] HeyGen host frames of {pid}: {error}", flush=True)
                        heygen_errors.append(error)
                heygen_thread = threading.Thread(target=heygen_work, name=f'heygen-{pid}', daemon=True)
                heygen_thread.start()
        reviews = threading.local()   # two sessions verify side by side: each reads back its own review
        def verify(numbers):
            nonlocal last_review
            reviews.last = {}
            if not drawn(pid,request['frames'],numbers):
                return False
            last_review = reviews.last = production_quality.check(store.load_project(pid),{**request,'review_frames':numbers})
            return last_review['passed']
        def checkpoint(receipt):
            with store.LOCK:
                if cancelled():raise InterruptedError('Створення кадрів зупинено')
                set_request(pid,session_checkpoint={**receipt,'signature':signature})
        def launch(numbers,summary,index,task=''):
            nonlocal last_review
            last_review = {}
            current=store.load_project(pid)
            scoped={**request,**({'session_frames':numbers,'summary':summary} if numbers else {})}
            if numbers:
                selected=[f for f in (store.load_project_plan(pid) or {}).get('frames',[]) if f['number'] in numbers]
                if selected:
                    scoped.update(start=min(f['start'] for f in selected),end=max(f['end'] for f in selected))
            if numbers and scoped.get('repair_frames'):scoped['repair_frames']=numbers
            text = session_brief(current, scoped, notes, numbers, index, heygen_numbers, task, summary)
            session_log=log.with_name(log.stem+f'-session-{index:02d}.log') if index else log
            if cancelled():raise InterruptedError('Створення кадрів зупинено')
            remaining = deadline - time.monotonic()
            if remaining <= 0:raise subprocess.TimeoutExpired(str(cli), TIMEOUT)
            return director.claude(cli,text,session_log,director.activity_path(pid,'production'),max(1,int(remaining)),resume=None,effort=effort,model=model,
                                  env={'VIDEOKEY_PROJECT_ID':pid,'VIDEOKEY_STUDIO_URL':'http://127.0.0.1:8770'})
        previous=request.get('session_checkpoint') or {}
        if previous.get('signature') != signature or request.get('continuation_mode') != 'handoff':
            previous = {}
        # A pause can occur after the first five were approved, before the ten-frame
        # session returned. Only a real visual receipt can recover that partial batch.
        if request.get('continuation_mode') == 'handoff' and not request.get('repair_frames') and not request.get('task_notes'):
            import native_review
            current = store.load_project(pid)
            plan = store.load_project_plan(pid) or {}
            made = set(store.made_frames(current, plan))
            pending = made.intersection(request.get('review_frames') or [])
            razgon = [f['number'] for f in plan.get('frames',[]) if f['number'] in pending and f.get('format') == 'razgon_2d']
            recovered = production_quality.approved_razgon(current,razgon)
            numbers = made.intersection(request.get('native_review_frames') or [])
            candidates = [f for f in plan.get('frames',[]) if f['number'] in numbers and f.get('format') != 'razgon_2d']
            if candidates and native_review.folder(current).is_dir():
                recovered.update({f['number'] for f in candidates} - set(native_review.missing(current,candidates)))
            if recovered:
                previous = {**previous,'completed_frames':sorted(recovered | set(previous.get('completed_frames') or []))}
        targets = [n for n in (request.get('repair_frames') or request.get('review_frames') or []) if n not in heygen_numbers]
        kit_answer = None
        import production_kit
        if not request.get('repair_frames') and not request.get('repair_film') and production_kit.needed(store.load_project(pid), targets):
            # The film's shared kit is made once before the parallel sessions (production_kit.py).
            current = store.load_project(pid)
            production_kit.seed(current)
            kit_text = kit_brief(current, int(request['frames']))
            if cancelled():raise InterruptedError('Створення кадрів зупинено')
            if deadline - time.monotonic() <= 0:raise subprocess.TimeoutExpired(str(cli), TIMEOUT)
            # the card and the plan read «Підготовка» while the kit is made (user, 15 November 2026)
            set_request(pid, stage='kit')
            try:
                with job_timing.separate('kit', pid) as kit_timing:   # «Підготовка» has its own row in «Час роботи»
                    with production_sessions.STUDIO_SESSIONS:
                        kit_code, kit_answer = director.claude(cli, kit_text, log.with_name(log.stem + f'-session-{production_kit.KIT_INDEX}.log'),
                            director.activity_path(pid, 'production'), max(1, int(deadline - time.monotonic())), resume=None,
                            effort=effort, model=model, env={'VIDEOKEY_PROJECT_ID': pid, 'VIDEOKEY_STUDIO_URL': 'http://127.0.0.1:8770'})
                    if production_kit.ready(store.load_project(pid)):
                        kit_timing['status'] = 'complete'
            finally:
                try:
                    set_request(pid, stage=None)
                except (OSError, store.StudioError):
                    pass
            production_kit.record_cost(store.load_project(pid), kit_answer)
            if director.limit_stop(kit_answer):
                fields.update(status="failed", limit=True, error=director.limit_stop(kit_answer),
                              cost_usd=float(request.get("cost_usd") or 0) + float(kit_answer.get("total_cost_usd") or 0))
                return
            # A kit that did not finish never stops the film: the sessions then work as before, without a shared kit.
        locked = production_kit.lock(store.load_project(pid)) if production_kit.ready(store.load_project(pid)) and len(targets) > production_sessions.SESSION_FRAMES else []
        try:
            if request.get('repair_film') and not request.get('repair_frames'):
                # one session for the whole film: Claude itself finds what the request concerns
                with production_sessions.STUDIO_SESSIONS:
                    code, answer = launch([], '', 0)
            else:
                code, answer = production_sessions.run(targets,launch,verify,checkpoint,cancelled,director.limit_stop,previous=previous, pending_review=lambda:getattr(reviews,'last',{}).get('pending_review',[]))
        finally:
            if locked:
                production_kit.unlock(store.load_project(pid))
        if heygen_thread:
            heygen_thread.join()   # the agent is done: the film waits for the host's videos still rendering at HeyGen
        # every host frame of this run long enough for it and still without graphics, whether its HeyGen video came now
        # or was kept from before (user, 26 November 2026: the kept videos of Astrofizika never got any: «що значить новий
        # кадр?… галочка… мало би використовуватись»); a whole-film repair leaves the hosts to its own agent
        scope = request.get('repair_frames') or ([] if request.get('repair_film') else range(1, int(request['frames']) + 1))
        long_hosts = graphics_frames(pid, bare_hosts(pid, scope))
        if long_hosts and host_graphics(pid) and not heygen_errors and not director.limit_stop(answer) and not cancelled():
            # the host's videos stand now: one short session puts the motion graphics over the long ones
            graphics_code, graphics_answer = launch(long_hosts, '', 900, task=host_graphics_task(pid))
            answer = production_sessions.merge_answers(answer, graphics_answer)
        if kit_answer:
            answer = production_sessions.merge_answers(kit_answer, answer)
        if last_review and not last_review['passed']:
            fields['quality'] = last_review
            answer['result'] = ' '.join(last_review.get('errors') or [answer.get('result','')])[:1600]
        spent_before = float(request.get("cost_usd") or 0) if notes.strip() else 0
        fields.update(cost_usd=spent_before + float(answer.get("total_cost_usd") or 0) if answer.get("total_cost_usd") else request.get("cost_usd"),
                      session_id=answer.get("session_id") or request.get("session_id"),
                      summary=(answer.get("result") or "").strip()[-2000:], **director.spent(answer, started))
        if director.limit_stop(answer):
            # A continuation preserves verified work and opens a fresh scoped session from its checkpoint.
            fields.update(status="failed", limit=True, error=director.limit_stop(answer))
        elif heygen_errors:
            fields.update(status="failed", error=str(heygen_errors[0])[:600])
        elif code or answer.get("is_error") or not drawn(pid, request["frames"],request.get('repair_frames')):
            missing = ("Не всі кадри намальовані й стоять на таймлайні студії блоками-кодом" if store.project_animated(project)
                       else "Не всі вибрані кадри стоять на таймлайні студії")
            fields.update(status="failed", error=(answer.get("result") or missing)[-600:])
        else:
            try:
                logo_layer.place(pid)   # the channel logo from the settings goes over the new frames
            except (OSError, store.StudioError):
                pass
            review_failed = False
            final_request = {**request,'review_frames':request.get('repair_frames') or list(range(1,int(request['frames'])+1))}
            review = production_quality.check(store.load_project(pid), final_request)
            if review.get('pending_review'):
                # fresh stills first, free: an unchanged picture keeps its verdict and needs no Claude session
                production_quality.refresh_stills(store.load_project(pid), review['pending_review'])
                review = production_quality.check(store.load_project(pid), final_request)
            review_code, review_answer = 0, {}
            formats = {f['number']: f.get('format') for f in (store.load_project_plan(pid) or {}).get('frames', [])}
            razgon_pending = [n for n in review.get('pending_review') or [] if formats.get(n) == 'razgon_2d']
            if razgon_pending:
                # One look at the whole film at the end, at a low effort: it only marks ok or bug. The frames it marks
                # as a bug are fixed in fresh sessions at the channel's effort, then looked at once more (user,
                # 15 November 2026: «це робити окремою сесією в кінці ролика. на еформ лоу»).
                def look(numbers, index):
                    nonlocal answer
                    code, raw = light_review(pid, numbers, cli, log.with_name(log.stem + f'-session-{index}.log'),
                                             max(1, int(deadline - time.monotonic())), model)
                    answer = production_sessions.merge_answers(answer, raw)
                    return code, raw
                review_code, review_answer = look(razgon_pending, 2500)
                found = production_quality.bugs(store.load_project(pid), razgon_pending)
                if found and not (review_code or review_answer.get('is_error') or director.limit_stop(review_answer)):
                    bug_notes = '; '.join(f'кадр {n}: {note}' for n, note in sorted(found.items()))   # not `notes`: that is the author's wish
                    fix_code, fix_answer = production_sessions.run(
                        sorted(found), lambda ns, _, index: launch(ns, 'Огляд знайшов вади, виправ лише їх: ' + bug_notes, 3000 + index),
                        verify, lambda receipt: None, cancelled, director.limit_stop)
                    answer = production_sessions.merge_answers(answer, fix_answer)
                    if not (fix_code or fix_answer.get('is_error') or director.limit_stop(fix_answer)):
                        production_quality.refresh_stills(store.load_project(pid), sorted(found))
                        review_code, review_answer = look(sorted(found), 2600)
                        left = production_quality.bugs(store.load_project(pid), sorted(found))
                        if left and not (review_code or review_answer.get('is_error') or director.limit_stop(review_answer)):
                            # what the second look still finds is fixed once more here, and the film ends: the author
                            # wants the finished video, not frames to look at or a button to press (17 November 2026:
                            # «я взагалі не хочу нічого переглядати мені треба просто результат готове відео»)
                            left_notes = '; '.join(f'кадр {n}: {note}' for n, note in sorted(left.items()))
                            fix_code, fix_answer = production_sessions.run(
                                sorted(left), lambda ns, _, index: launch(ns, 'Повторний огляд ще бачить вади, виправ лише їх: ' + left_notes, 3100 + index),
                                verify, lambda receipt: None, cancelled, director.limit_stop)
                            answer = production_sessions.merge_answers(answer, fix_answer)
                            if not (fix_code or fix_answer.get('is_error')):
                                production_quality.refresh_stills(store.load_project(pid), sorted(left))
                            if director.limit_stop(fix_answer):
                                review_code, review_answer = fix_code, fix_answer
                    else:
                        review_code, review_answer = fix_code, fix_answer
                fields.update(cost_usd=spent_before+float(answer.get('total_cost_usd') or 0),
                              session_id=answer.get('session_id'), **director.spent(answer,started))
                review = production_quality.check(store.load_project(pid), final_request)
                left = production_quality.bugs(store.load_project(pid), final_request['review_frames'])
                if left and not review['passed'] and all(e.startswith('Перевірка кадрів Razgon не підтверджена:') for e in review['errors']):
                    # what the second look still dislikes goes to the author to look at, it never stops the film
                    review = {**review, 'pending_review': sorted(set(review.get('pending_review') or []) | set(left))}
                if director.limit_stop(review_answer):
                    fields.update(limit=True)
            native_pending = [n for n in review.get('pending_review') or [] if formats.get(n) != 'razgon_2d']
            if native_pending and not fields.get('limit'):
                # A later batch may invalidate an earlier dependency. Finish that
                # review here, while the same worker still owns the production job.
                review_code, review_answer = production_sessions.finish_review(
                    native_pending, launch, verify, cancelled, director.limit_stop)
                answer = production_sessions.merge_answers(answer, review_answer)
                fields.update(cost_usd=spent_before+float(answer.get('total_cost_usd') or 0),
                              session_id=answer.get('session_id'), **director.spent(answer,started))
                review = production_quality.check(store.load_project(pid), final_request)
                if review_code or review_answer.get('is_error'):
                    review_failed = True
                    review = {**review,'passed':False,'errors':review.get('errors') or [review_answer.get('result') or 'Не завершено огляд кадрів']}
                    if director.limit_stop(review_answer):
                        fields.update(limit=True)
            # Frames that are all drawn and only wait for a fresh look never stop the film (user, 15 November 2026:
            # «щоб зупинено ніколи не було»): the run is done and the frames are named for the author to look at.
            look_only = not review['passed'] and not review_failed and not fields.get('limit') and not director.limit_stop(answer) \
                and bool(review.get('pending_review')) and drawn(pid, request["frames"], request.get('repair_frames'))
            # the frames are drawn and only the check could not run (the disk was full, a saved layer unreadable): the
            # film is made, its frames wait for a look; never «Кадри 1–134 не вдалися» for a check that did not happen
            # (user, 25 November 2026)
            unchecked = review.get('check_failed') and not review_failed and not fields.get('limit') and not director.limit_stop(answer) \
                and drawn(pid, request["frames"], request.get('repair_frames'))
            if unchecked:
                review = {**review, 'passed': True, 'look_later': final_request['review_frames'], 'review_unavailable': review['errors'][:1]}
            elif look_only:
                review = {**review, 'passed': True, 'look_later': review['pending_review']}
            elif not review['passed'] and not fields.get('limit') and not director.limit_stop(answer) \
                    and drawn(pid, request["frames"], request.get('repair_frames')):
                review = bugs_to_fix(store.load_project(pid), final_request, review) or review
            fields.update(quality=review, status='done' if review['passed'] else 'failed')
            if not review['passed']:
                # A provider pause is the actionable cause; keep the local review
                # details in quality without replacing the quota reset message.
                missing = missing_note(pid, request)
                fields['error'] = director.limit_stop(answer) or (missing + ' '.join(review['errors']))[:1600]
                if missing and not fields.get('limit'):
                    # the made frames stay and the round «Продовжити» finishes the rest, as after a restart
                    fields.update(paused=True, paused_by='incomplete')
    except subprocess.TimeoutExpired:
        try:
            made = drawn(pid, request["frames"], request.get('repair_frames'))
        except (OSError, store.StudioError, KeyError, ValueError):
            made = False
        if made:
            # every frame is drawn and only the look at them ran out of time: the film is done (17 November 2026 audit:
            # a finished film read «не вклалося в 6 годин» and could not be resumed)
            fields.update(status="done", error=None, quality={'passed': True, 'errors': [], 'look_later': [], 'review_timed_out': True})
        else:
            fields.update(status="failed", error="Створення кадрів не вклалося в 6 годин")
    except (OSError, store.StudioError, KeyError) as error:
        if getattr(error, 'errno', None) == 28:   # ENOSPC: the Mac's disk is full, nothing about the frames
            fields.update(status="failed", paused=True, paused_by="disk", error=DISK_FULL)
        else:
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
            if fields.get("status") == "done" and not request.get('repair_frames'):
                try:
                    import production_kit
                    production_kit.harvest(store.load_project(pid))   # the channel library takes what this film added
                except (OSError, store.StudioError):
                    pass
                # the scenes may have brought new sound cues: the film's music and effects are laid again, without a
                # render (razgon_sound.py; only an animated film is due)
                razgon_sound.start(pid, "production")
                ensure_music(pid)
                film_sounds(pid)


def validate_repair_frames(pid,request,frame_numbers):
    valid={f['number'] for f in (store.load_project_plan(pid) or {}).get('frames',[])
           if f['number']<=int(request.get('frames') or 0)}
    if (not isinstance(frame_numbers,list) or not frame_numbers or len(frame_numbers)>200
            or any(type(n) is not int or n not in valid for n in frame_numbers)):
        raise store.StudioError('Виберіть наявні кадри для правок',400)
    return sorted(set(frame_numbers))


def fix(pid: str, notes: str, *, handoff: bool = False, frame_numbers=None) -> dict:
    """Repair or continue through a fresh session with the current disk checkpoint."""
    notes = str(notes or "").strip()
    if not notes:
        raise store.StudioError("Напишіть, що виправити")
    project = store.load_project(pid)
    request = project.get("production_request") or {}
    if request.get("status") not in {"done", "failed"}:
        raise store.StudioError("Агент ще працює над цими кадрами")
    selected=request.get('repair_frames') if handoff else None
    # a whole-film edit stopped by a limit or a pause goes on as a whole-film edit: the continuation used to drop it,
    # run no session and read «done», losing the author's wish (17 November 2026 audit)
    film = (frame_numbers == [] and not handoff) or (handoff and bool(request.get('repair_film')))
    if frame_numbers is not None and not film:
        selected=validate_repair_frames(pid,request,frame_numbers)
    task_notes = str(request.get("task_notes", request.get("notes", "")) or "") if handoff else notes[:4000]
    set_request(pid, status="requested", paused=False, continue_session=False,
                continuation_mode="handoff" if handoff else "repair", task_notes=task_notes,
                previous_session_id=request.get("session_id"),repair_frames=selected,repair_film=film,
                created_at=time.time(), notes=notes[:4000], fixes=int(request.get("fixes") or 0) + 1)
    start(pid, notes)
    return store.load_project(pid)


RESUME = ("Ліміт підписки оновився. Продовж роботу над цими кадрами з того місця, де зупинився: не переробляй уже готове, "
          "доведи решту кадрів до кінця з тією ж перевіркою якості й зроби крок 4 без рендеру відео.")


def partly_made(pid: str, project: dict, request: dict) -> bool:
    """Some of the requested frames are made and some are not."""
    try:
        wanted = set(request.get('repair_frames') or range(1, int(request.get('frames') or 0) + 1))
        made = set(store.made_frames(project, store.load_project_plan(pid))) & wanted
    except (store.StudioError, OSError, ValueError, KeyError, TypeError):
        return False
    return bool(made) and made != wanted


def resume(pid: str) -> dict:
    """Continue saved frames with a compact handoff, preserving completed work and author wishes."""
    with LOCK:
        if pid in ACTIVE:
            raise store.StudioError('Ще зупиняємо попередню роботу. Спробуйте за кілька секунд.',409)
    project = store.load_project(pid)
    request = project.get("production_request") or {}
    review_pending = False
    saved_review = request.get('quality') or {}
    failed = request.get('status') == 'failed'
    if failed and saved_review.get('frames'):
        review_pending = bool(production_quality.check(project, {**request, 'review_frames': saved_review['frames']}).get('pending_review'))
    if failed and drawn(pid,int(request.get('frames') or 0),request.get('repair_frames')):
        # every frame is made: the run closes here when they pass, or goes on only to look at the ones waiting for a look
        final_review=production_quality.check(project,{**request,'review_frames':request.get('repair_frames') or list(range(1,int(request['frames'])+1))})
        if final_review.get('passed'):
            set_request(pid,status='done',error=None,paused=False,limit=False,quality=final_review,finished_at=time.time())
            if not request.get('repair_frames'):
                razgon_sound.start(pid, "production")   # the bed a pause stopped is laid now
            return store.load_project(pid)
        review_pending = review_pending or bool(final_review.get('pending_review'))
    # A run stopped part way with frames made and frames left goes on from its saved files (user, 26 November 2026: the
    # card stood at «Зупинено · 67 з 72» and «Продовжити» answered «Агент не стоїть на паузі»: «не має вставати
    # намертво»). A run that made nothing, or whose made frames have a real defect, still waits for the author.
    unfinished = failed and partly_made(pid, project, request)
    if not failed or not (review_pending or unfinished or request.get("paused") or request.get("limit") or director.limit_stop({"result": request.get("error")})):
        raise store.StudioError("Агент не стоїть на паузі")
    notes=("Заверши актуальний візуальний огляд готових кадрів і продовж решту зі збережених файлів. "
           "Збережи готові сцени й матеріали, без повторного створення схвалених кадрів і без рендеру відео.") if review_pending else (
           "Автор просить продовжити після паузи. Продовж роботу з того місця, де зупинився. "
           "Збережи готові кадри й матеріали та закінчи решту без рендеру відео.") if request.get('paused') else (
           "Попередній запуск зупинився, не довівши всі кадри. Не переробляй готові: доведи до кінця лише незроблені кадри "
           "зі збережених файлів, з тією ж перевіркою якості, без рендеру відео.") if unfinished and not request.get('limit') else RESUME
    return fix(pid, notes, handoff=True)


def codex_limit_note(reset: str | None, no_funds: bool = False) -> str:
    """The pause note when Codex ran out of its limit mid-production (user, 14 November 2026: «нехай просто… на паузу
    ставиться обробка кадрів… не хочу, щоб створювались кадри… без PNG»)."""
    reset = re.sub(r"[^0-9A-Za-zА-Яа-яІіЇїЄєҐґ:.,\s-]", "", str(reset or ""))[:60].strip()
    return ("Закінчився ліміт Codex" + (f", він оновиться {reset}" if reset else "") +
            (". На балансі OpenRouter замало вільних коштів, щоб малювати замість Codex" if no_funds else "") +
            ". Готові кадри збережені; натисніть «Продовжити», коли ліміт оновиться" +
            (" або поповніть OpenRouter" if no_funds else "") + ".")


def pause(pid: str, note: str | None = None) -> dict:
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
    import razgon_sound   # the music and effects of this film stop too; they are laid again after the frames
    razgon_sound.stop(pid)
    set_request(pid,status='failed',paused=True,paused_by='user' if note is None else 'limit',limit=False,finished_at=time.time(),session_id=session,
                error=note or 'Призупинено на ваше прохання. Готові кадри збережені.')
    # Usually SIGTERM finishes immediately. Never let a quick Play silently lose
    # the request while the old worker still owns the project's active slot.
    until=time.monotonic()+2
    while pid in ACTIVE and time.monotonic()<until:
        time.sleep(.05)
    return store.load_project(pid)


def start_from_plan(pid: str) -> dict:
    """Continue the author's one-step creation once direction is complete, without replaying frame jobs."""
    import episode_pause
    if episode_pause.note(pid, "production"):
        return store.load_project(pid)   # the episode is paused: «Продовжити» starts the frames
    with store.LOCK:
        project = store.load_project(pid)
        plan = store.load_project_plan(pid) or {}
        request = project.get('production_request') or {}
        if pid in ACTIVE or request.get('status') in {'requested', 'in_progress'}:
            return project
        count = len(plan.get('frames') or [])
        if count and set(range(1, count + 1)) <= set(store.made_frames(project, plan)):
            return project
        same_script = request.get('script_sha256') == plan.get('script_sha256')
        # a run cut by a restart for an older script never blocks the frames of the new one
        held = request.get('paused') and (same_script or request.get('paused_by') != 'restart')
        if held or request.get('status') == 'failed' and same_script and (request.get('limit') or director.limit_stop({"result": request.get("error")})):
            raise store.StudioError('Створення кадрів призупинено. Продовжіть збережену роботу кнопкою продовження.', 409)
        if request.get('status') == 'failed' and same_script:
            # a run that failed (no pause, no limit) is not resumed by «Продовжити»: a new start goes on from the first
            # frame not made, which the automation does not buy by itself (16 November 2026 stability pass: the old
            # answer sent the author to a resume that refused with «Агент не стоїть на паузі»)
            raise store.StudioError('Попереднє створення кадрів зупинилося з помилкою. Готові кадри збережено. Натисніть «Продовжити створення ролика» в блоці «Створення ролика»: робота піде з першого незробленого кадру.', 409)
        project = store.request_production(pid, count)
    start(pid)
    # A corrected explicit retry replaces the previous handoff error in the shared process status.
    direction = director.state(pid) or {}
    if direction.get('creation_error'):
        direction.pop('creation_error')
        director.save(pid, direction)
    return project


PRODUCTION_MIN_FREE = 3 * 1024 ** 3


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
        # frames write pictures, motion-code renders and stills: on a full disk every frame failed at once (25 November
        # 2026, «Кадри 1–134 не вдалися… No space left on device»); the request waits for the author instead
        import shutil
        free = shutil.disk_usage(store.DATA_ROOT).free
        if free < PRODUCTION_MIN_FREE:
            set_request(pid, status="failed", error=f"Мало місця на диску: вільно {free / 1024 ** 3:.1f} ГБ, для створення кадрів "
                                                    f"потрібно хоча б {PRODUCTION_MIN_FREE // 1024 ** 3} ГБ. Звільніть місце й натисніть «Продовжити».")
            return
        ACTIVE.add(pid)
    try:
        threading.Thread(target=run, args=(pid, cli, notes), daemon=True).start()
    except Exception:
        try:
            set_request(pid, status='failed', error='Не вдалося запустити створення кадрів', finished_at=time.time())
        finally:
            with LOCK:
                ACTIVE.discard(pid)
        raise


# A request just written waits this long for its run to start before it can read as stale.
START_GRACE = 30


REVIEW_ONLY = ('Перевірка кадрів Razgon не підтверджена:', 'Потрібен огляд готової композиції кадрів Studio:')


def bugs_to_fix(project: dict, request: dict, review: dict) -> dict | None:
    """A review that failed only on the look at frames that are all drawn: the film is done (17 November 2026: 131 of
    131 frames made, 9 with bugs, read as «Кадри 1–131 не вдалися»; 21 November 2026, the Jupiter film: frames whose
    look a parallel session's change of shared files undid, and a stale render line, read «Кадри 1–71 не вдалися», and
    the user: «всі кадри мають вдаватися… не може видавати проект, де кадри не вдались»). Bugs the look saw stay in
    `fix_later`, frames still waiting for a look in `look_later`, both for the record; the author is not asked to look.
    The caller checks the frames are drawn. None for any other failure."""
    if review.get('passed') or not review.get('errors') or not all(str(error).startswith(REVIEW_ONLY) for error in review['errors']):
        return None
    frames = request.get('review_frames') or request.get('repair_frames') or list(range(1, int(request.get('frames') or 0) + 1))
    found = production_quality.bugs(project, frames)
    waiting = sorted({int(n) for error in review['errors'] for line in str(error).splitlines()
                      if line.strip().startswith(('not reviewed:', 'changed frames needing fresh stills:', 'missing cached stills:'))
                      or line.startswith(REVIEW_ONLY[1]) for n in re.findall(r'\d+', line.split(':', 1)[1])})
    return {**review, 'passed': True, 'look_later': sorted(set(review.get('pending_review') or []) | set(waiting)),
            'fix_later': {str(n): note for n, note in sorted(found.items())}}


def settle(pid: str, project: dict | None = None) -> dict | None:
    """A request that says the agent works while no agent of this Studio runs (a restart, a run that never started:
    31 October 2026 a finished film read «Створюємо кадри» for good) is put right: done when every requested frame is
    made, otherwise stopped, so the button can be pressed again. Returns the request as it stands."""
    project = project or store.load_project(pid)
    request = project.get("production_request") or {}
    if review_only_failure(request) and pid not in ACTIVE:
        return settle_review_failure(pid, project, request)
    if request.get("status") not in {"requested", "in_progress"} or pid in ACTIVE:
        return request or None
    if request["status"] == "requested" and time.time() - float(request.get("created_at") or 0) < START_GRACE:
        return request
    try:
        made = not request.get('repair_frames') and drawn(pid, int(request.get("frames") or 0))
    except (store.StudioError, OSError, ValueError, KeyError):
        made = False
    # a run cut by a restart or a crash goes on from its frames with the round play, like a pause (16 November 2026:
    # «Кадри 1–96 не вдалися» while 91 of 96 were made)
    fields = {"status": "done", "error": None} if made else {
        "status": "failed", "paused": True, "paused_by": "restart",
        "error": "Студію перезапущено посеред роботи. Готові кадри збережені, натисніть «Продовжити»."}
    if made and request.get('quality_version') == 1:
        review = production_quality.check(project, request)
        review = bugs_to_fix(project, request, review) or review
        fields.update(quality=review, status='done' if review['passed'] else 'failed',
                      error=None if review['passed'] else ' '.join(review['errors'])[:1600])
    saved = set_request(pid, finished_at=time.time(), **fields)
    if fields.get('status') == 'done':
        razgon_sound.start(pid, "production")
        film_sounds(pid)
    return saved




def review_only_failure(request: dict) -> bool:
    """A run an older Studio marked failed only because the last look at its frames was not confirmed (frames to look
    at again, or bugs the look still saw): the frames themselves are made."""
    errors = (request.get('quality') or {}).get('errors') if isinstance(request.get('quality'), dict) else None
    return (request.get('status') == 'failed' and not request.get('paused') and not request.get('limit')
            and not request.get('review_settle_tried')
            and bool(errors) and all(str(error).startswith(REVIEW_ONLY) for error in errors))


def settle_review_failure(pid: str, project: dict, request: dict) -> dict:
    """Such a run is done now, as the end of a run decides it today (user, 17 November 2026: «у дівчини пише не вдались
    кадри» on a film whose frames were all made): frames waiting for a look and bugs the look still saw stay in the
    record, the author is not asked to look at them. Not drawn frames keep the run failed."""
    try:
        if not drawn(pid, int(request.get('frames') or 0), request.get('repair_frames')):
            return set_request(pid, review_settle_tried=True)   # looked at once, not on every read of the project
        final = {**request, 'review_frames': request.get('repair_frames') or list(range(1, int(request['frames']) + 1))}
        review = production_quality.check(project, final)
    except (store.StudioError, OSError, ValueError, KeyError):
        return request
    if not review.get('passed'):
        review = bugs_to_fix(project, final, review) or review
    if not review.get('passed'):
        return set_request(pid, review_settle_tried=True)
    saved = set_request(pid, status='done', error=None, quality=review)
    if not request.get('repair_frames'):
        razgon_sound.start(pid, "production")
        film_sounds(pid)
    return saved


DISK_FULL = ("На диску Mac закінчилось місце, тому створення кадрів зупинилось. Готові кадри збережені. Звільніть місце "
             "(кнопка «Звільнити місце» в загальних налаштуваннях студії або видаліть зайві файли) і натисніть «Продовжити».")


SOUND_BED = 'Razgon · музика й ефекти'


def missing_bed(pid: str) -> bool:
    """A finished animated film whose music and effects were stopped or broken and never laid again (user, 15 November
    2026: «для корбина где музика? чому не сталось» — a pause stopped the bed, the frames finished another way)."""
    project = store.load_project(pid)
    request = project.get('production_request') or {}
    if request.get('repair_frames') or not razgon_sound.due(project):
        return False
    # with music switched on a film always has it (user, 16 November 2026: «Якщо галочка стоїть, значить має бути
    # музика все»): once the director's plan follows the voice, not only after the frames
    plan = store.load_project_plan(pid) or {}
    directed = ((plan.get('timing') or {}).get('status') == 'audio_synced' and plan.get('frame_source') == 'razgon-direction'
                and not plan.get('director_stale'))
    if request.get('status') != 'done' and not directed:
        return False
    if any(t.get('name') == SOUND_BED for t in project.get('tracks', [])):
        return False
    return (razgon_sound.state(pid) or {}).get('status') in {None, 'cancelled', 'failed'}


def reset_interrupted() -> None:
    """At start-up: a request left in work by a restart is settled (done if its frames are made, else stopped), and a
    finished film that lost its music bed gets it again (two at a time at most: each mix takes a few GB)."""
    beds = 0
    for item in store.list_projects():
        try:
            settle(item["id"])
            if beds < 2 and item["id"] not in razgon_sound.ACTIVE and missing_bed(item["id"]):
                beds += razgon_sound.start(item["id"], "production")
        except (store.StudioError, OSError):
            continue
