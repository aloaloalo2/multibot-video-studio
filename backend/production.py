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
     ділянку кадру: текст лишається свого кольору (переважно білий) з м'якою тінню, тон за фоном не перемикається (він блимав).
     Напис стоїть усередині свого носія (дата на сторінці, а не за її краєм), на голій стіні чи небі, а не на картині, вікні,
     предметі чи під героєм, і не обрізаний краєм кадру. Текст, що належить предмету (сторінка книги, вивіска, екран,
     плакат, табличка), клади тільки textOn() з engine/core.js на виміряні кути його грані: так він лежить на предметі в
     його перспективі, а не рівним рядком поверх скошеної поверхні. Підпис-цифру чи дату не став у одну й ту саму точку
     екрана для всіх сцен (420, 180 у 08 лягало на будинки, крани, колони): вибирай спокійну ділянку саме цієї сцени,
     а якщо камера там рухається, малюй підпис у шарі світу, щоб він рухався разом зі стіною. Світлий текст на світлому
     тлі не годиться: на світлій стіні темне чорнило;
   - опора: колеса поїзда на лінії рейок (виміряй у картинці, на якій частці висоти колеса), телетайп на верхній площині столу,
     книга на столі; люди в масштабі декорації (двері, будка, авто), той самий масштаб в усіх шотах однієї декорації;
   - глибина за лінією ніг: що ближче (нижча лінія ніг), те малюється пізніше. Натовп сортуй за y; хто йде повз будку чи
     машину, той або попереду (нижче її лінії ніг), або ховається за нею. Ліхтар на ближньому тротуарі поверх авто на дорозі;
   - лінії й промені починаються й закінчуються точно на своїх предметах, не обриваються в повітрі й не йдуть далі цілі.
     Обрив зв'язку показуй видимо (червона іскра на обох кінцях). Лінія та її ціль в одному шарі layer(), інакше паралакс
     розводить їх, коли камера рухається;
   - ніяких порожніх прямокутників: розрізана кімната, відчинені ворота, будівля мають вікна, двері, меблі, вулицю за ними;
   - камера: вивіска, панель чи напис не обрізані краєм кадру; щоб камера стояла, повтори ключ (сплайн інакше перелітає ціль);
   - асети з бібліотеки й аркушів мають близько 500 px: предмет, вищий за 1,6 своїх пікселів у 1080p, малюй кодом, клади в
     розмитий blurLayer переднього плану або замов окремим великим асетом (один предмет на аркуш);
   - перед здачею: node render.mjs --project <проєкт> --logic-check 0.5 --scale 0.25 і --text-check (у папці Razgon, ~20 с на
     весь фільм, токенів не витрачає). Кожен FAIL подивись на стоп-кадрі: справжню ваду виправ, а хибний збіг (вид у вікні,
     розріз будівлі) поясни у звіті. «text half on» (напис наполовину на предметі) має бути 0. Потім frame_review.py sheets
     --scale 0.3: три дешеві стоп-кадри кожного кадру (20, 50, 80%).
   - це цикл (користувач, 5 листопада 2026): скріни → список усіх багів → виправлення → знову перевірки й скріни всіх змінених
     кадрів → і так, доки на скрінах і в перевірках не лишиться жодного бага. Дивись кожен стоп-кадр уважно, а не побіжно:
     у 08 книга з текстом поза сторінками пройшла як «ok»;
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
Працюй із короткою картою кадрів студії. Помічників не запускай.
Наприкінці коротко напиши українською: які кадри готові, які предмети додано, що лишилося або не вдалося."""


# How people look in a channel's pictures: «Люди в кадрах» (`people_style` in video-plan.json). Stick figures are the
# default (user, 31 October 2026); the health channels for older viewers show real people (user, 5 November 2026: «його
# проект має бути для дорослих людей… не дудл, а живих справжніх людей. Старших… як будто сфоткані на телефон»).
PEOPLE = ("Люди в кожному кадрі, крім кадрів ведучого, лише стикмени: і на картинках, і в кожному промпті для картинки "
          "чи відео прямо пиши, що всі люди намальовані стикменами. Стокове фото чи відео з живими людьми не бери.")
PEOPLE_REAL = ("Люди на картинках живі й справжні, у звичайному одязі й звичайній обстановці, вік і вигляд за правилами каналу: "
               "природна фотографія, ніби знята на телефон, не завжди ідеальної якості, денне чи кімнатне світло, без студійного глянцю, "
               "ретуші й мультяшності. Приблизно половина фото вертикальні (3:4), половина горизонтальні (4:3): вертикальні додають "
               "ролику правдивості. "
               "Ніяких стикменів, дудлів і намальованих людей. У кожному промпті прямо пиши, що це реалістична аматорська фотографія "
               "на телефон зі справжніми людьми. Перевіряй анатомію: руки, пальці, обличчя.")
# The photo style that the author liked in GORBUNOV-23 («Алексей Горбунов/23 Овощи и печень/Фото кадров/photos.py»):
# real amateur smartphone photos, about half of them vertical, older Eastern Slavic people, no text.
PHOTO_STYLE_OLDER = ("Style: a real amateur photo taken on an ordinary smartphone, not professional. Natural available light, everyday home or "
                     "city setting in an ordinary post-Soviet apartment or Russian town, casual unposed moment, ordinary framing, natural skin "
                     "texture. No studio lighting, no advertising look, no glossy retouching, no model poses, no shallow-depth studio bokeh. "
                     "Every main person is at least 60 years old with visible age features, fair skin, Eastern Slavic appearance and ordinary "
                     "everyday clothes. Anatomy correct, hands natural. No text, no letters, no numbers, no captions, no logos, no watermarks, "
                     "no pills or medicine packages anywhere.")
PEOPLE_REAL_OLDER = ("Створені картинки — живі природні фотографії справжніх людей старшого віку (60+), ніби зняті на звичайний телефон, "
                     "не завжди ідеальної якості; ніяких стикменів, дудлів, мультяшності й намальованих людей. Приблизно половина фото "
                     "вертикальні (3:4), половина горизонтальні (4:3); вертикальне фото стоїть у кадрі як є, зі своїми полями. Опиши в промпті "
                     "конкретну людину з віком («a man about 67 years old»), дію й обстановку за словами кадру, і в кожен промпт англійською "
                     "дослівно додай цей рядок стилю: «" + PHOTO_STYLE_OLDER + "» Фото з однаковою орієнтацією малюй по чотири на аркуші "
                     "2×2 з білими проміжками й ріж аркуш скриптом, як у «Алексей Горбунов/23 Овощи и печень/Фото кадров» (photos.py, run.py). "
                     "Перевіряй кожне фото: анатомію, руки, обличчя, вік, відповідність словам.")
PEOPLE_STYLES = {"stickman", "real", "real_older"}


def people_style(project: dict) -> str:
    """The channel's choice of people in pictures: «stickman» (default), «real» or «real_older»."""
    try:
        settings = store.read_json(store.get_channel_folder(project["channel_id"], include_disabled=True) / store.PLAN_CONFIG, {}) or {}
    except (store.StudioError, KeyError):
        settings = {}
    return settings.get("people_style") if settings.get("people_style") in PEOPLE_STYLES else "stickman"


def people_rules(project: dict) -> dict:
    """The three places of the photo brief that depend on how people look: the picture rule, stock choice, the check."""
    style = people_style(project)
    if style == "real_older":
        return {"rule": PEOPLE_REAL_OLDER, "stock": "можна з живими людьми старшого віку, якщо вони пасують до слів",
                "check": "люди живі, старшого віку й природні, без стикменів і дудлів"}
    if style == "real":
        return {"rule": PEOPLE_REAL, "stock": "можна з живими людьми, якщо вони пасують до слів",
                "check": "люди живі й природні, без стикменів і дудлів"}
    return {"rule": PEOPLE, "stock": "без живих людей", "check": "люди лише стикмени"}


# What the «Акценти на кадрах» setting asks of any agent, on any Mac: the rules live here, not in a conversation
# (user, 6 November 2026: «щоб ця галочка сама по собі інформацію давала… на іншому комп'ютері… щоб там теж так було»).
ACCENT_RULES = """Акценти анімовані: студія сама робить їм появу. Стрілка виростає від хвоста до вістря й двічі тицяє в точку, коло наводиться на ціль і пульсує, слова підпису з'являються разом із голосом. Тобі лишається вибрати місце, деталь і момент.
- Стрілка: вістря точно на деталі, про яку саме зараз говорять (ніготь, шишка, датчик, кнопка), хвіст на спокійному місці фото, не через обличчя. --word: слово, на якому вона з'являється.
- Коло: навколо невеликої деталі, радіуси трохи більші за неї, щоб деталь лишалась видною.
- Текст ставиться рідко й тільки там, де фразу треба підкреслити: попередження, головна порада, число, строк, сума, закон, висновок. 2–6 слів дослівно з озвучки цього кадру (--phrase), вони з'являються по словах у той момент, коли їх вимовляють. Не підписуй те, що й так видно, не виписуй назви (УЗД, МРТ) і переліки. Орієнтир: один текстовий акцент на 4–6 хвилин ролика.
- На кадрі один акцент: стрілка або коло, текст окремо від них. Не на текстових кадрах, кадрах ведучого й готовій анімації. Головний об'єкт лишається видним."""


def accents_step(project: dict, tools: str) -> str:
    """What the channel's settings say about accents (an arrow, a ring or a caption over a picture, «Акценти на кадрах»)."""
    try:
        settings = store.read_json(store.get_channel_folder(project["channel_id"], include_disabled=True) / store.PLAN_CONFIG, {}) or {}
    except (store.StudioError, KeyError):
        settings = {}
    if not settings.get("accents"):
        return ("6. Акцентів (стрілок, кіл, підписів поверх фото) не додавай: у налаштуваннях каналу вони вимкнені.")
    return f"""6. Обов’язковий крок: акценти увімкнені в налаштуваннях каналу.
   Пройди фото (спершу згенеровані, потім стокові) і там, де акцент допомагає зрозуміти сказане, додай його. Не за квотою «кожен третій кадр»: за змістом озвучки.
{ACCENT_RULES}
   Спершу подивись стоп-кадр (python3 "{tools}/studio.py" still {project['id']} fN), щоб узяти точки, потім
   python3 "{tools}/studio.py" accent {project['id']} N arrow --from x,y --to x,y --word слово (або circle --at x,y --radii rx,ry, text --phrase "слова голосу" --at x,y).
   Перевір стоп-кадром кінця кадру (fN:end), що акцент на місці. У підсумку назви кадри з акцентами."""


def mixed_assets_step(project: dict) -> str:
    try:
        settings = store.read_json(store.get_channel_folder(project["channel_id"], include_disabled=True) / store.PLAN_CONFIG, {})
    except (store.StudioError, KeyError):
        settings = {}
    enabled = (settings.get("animation") or {}).get("assets", True) is not False
    if not enabled:
        return '   Асети предметів для 2D-анімацій вимкнені: нові сцени Razgon малюй кодом, config.json "assets": false.'
    return f"""   Асети предметів для 2D-анімацій увімкнені також в універсальному типі: використовуй PNG-предмети всередині кадрів razgon_2d.
   Спершу готові assets/library-picks.json і предмети проєкту, далі один обмежений пошук tools/library.py search і один аркуш кандидатів.
   Вдалий предмет приєднай через library.py pull; якщо немає відповідного, замов PNG-предмети аркушем у Codex через tools/codex_image.py та split_sheet.py.
   Підключи картинки до scenes/assets.js і реально намалюй їх у сцені; порожній assets/index.json при ввімкненому перемикачі не виконує це завдання.
   У config.json має бути "assets": true. Уже прийняті сцени зберігай. Це правило предметів Razgon; повнокадрові фото роби за окремим форматом кадру."""


# How the author wants a photo channel's film to feel (user, 6 November 2026: «динамічно щоб було креативно цікаво текста
# трохи додай де треба гарно різноманітно»).
PHOTO_STYLE_WISH = """Автор хоче, щоб ролик був динамічним, креативним і цікавим, гарним і різноманітним. Чергуй плани: загальний, середній, крупний, деталь,
різні ракурси й місця дії; два схожі кадри підряд не став. Рух у кадрах різний, переходи різні. Текст додавай трохи, там, де фразу треба
підкреслити (текстові кадри плану й текстові акценти за правилами нижче), і щоразу в іншому вигляді."""


def photo_brief(project: dict, request: dict, notes: str = "") -> str:
    """The brief for a photo channel: each frame by its format, placed at its time on the timeline."""
    root = store.YOUTUBE_ROOT
    episode = Path(project["episode_path"])
    rel = episode.relative_to(root) if root in episode.parents else episode
    tools = store.APP_ROOT.name + "/tools"
    people = people_rules(project)
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
{PHOTO_STYLE_WISH}
Кадри, які вже стоять на таймлайні, не переробляй, якщо автор не просить правок саме до них.
1. Картинки автора першими: якщо автор сам поклав картинки чи відео в папку випуску (find "{rel}" -maxdepth 2 -type f),
   а вони пасують до кадру, бери їх.
2. Стокові фото й відео (формати stock_photo, stock_video): python3 "{tools}/studio.py" stock {project['id']} N "англійські слова" [--video]
   складає аркуш пронумерованих варіантів Pixabay для кадру N; подивись його (Read) і вибери за змістом слів кадру, {people['stock']},
   а відео не коротше за кадр. Вибраний ставить кадром одна команда: python3 "{tools}/studio.py" stock-pick {project['id']} N <id> [--video].
   Нічого не підходить: інші слова, ще один аркуш.
3. Створені зображення (generated_photo, generated_video як картинка з рухом): малює Codex.
   Це може бути фото, інфографіка, схема, рентген, ілюстрація чи будь-який інший доречний стиль. Вибирай стиль за змістом кадру. Через термінал:
   промпт у файлі, потім python3 "{tools.rsplit('/', 1)[0]}/razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/tools/codex_image.py" --prompt <файл промпту> --out "{rel}/кадри/кадр_NNN.png".
   Фото малюй по чотири на одному аркуші 2×2 (кадри однієї орієнтації разом, білі проміжки між ними) і ріж аркуш скриптом на
   чотири файли без білих ліній по краях, як у «Алексей Горбунов/23 Овощи и печень/Фото кадров/run.py»: це вчетверо менше генерацій.
   Кожне вирізане фото перевір окремо; одиночне фото малюй тільки для останніх кадрів, коли до четвірки не вистачає.
   {people['rule']}
4. Текстові кадри (text) робиш сам одним кроком: python3 "{tools}/studio.py" place {project['id']} all-text ставить слова кожного ще не
   поставленого текстового кадру на весь екран.
   Кадри 2D-анімації Razgon (razgon_2d) пишеш кодом, як у правилах каналу, без рендеру відео: якщо проєкту Razgon ще немає,
   python3 "{tools}/razgon_bridge.py" prepare --project-id {project['id']}; далі сцени шотів цих кадрів і
   python3 "{tools}/razgon_bridge.py" slots --razgon <проєкт Razgon>: блоки-код стануть лише на кадри формату razgon_2d.
{mixed_assets_step(project)}
   Кожну картинку чи відео ставиш на таймлайн у час кадру: python3 "{tools}/studio.py" place {project['id']} N <файл> [--motion zoom_in|zoom_out|none].
5. Перевірка: python3 "{tools}/studio.py" summary {project['id']} --frames 1-{request['frames']} --issues без проблем, і стоп-кадр
   кожного кадру (python3 "{tools}/studio.py" still {project['id']} fN --small: половинний розмір, учетверо дешевший на
   перегляд; повний розмір лише коли береш координати для акценту) ти переглядаєш очима: картинка відповідає словам кадру,
   {people['check']}, нічого не обрізано, текст читається. Кадр із вадою виправ (replace) і перевір ще раз.
{accents_step(project, tools)}
7. Переходи: коли всі кадри запиту стоять, python3 "{tools}/studio.py" transitions {project['id']} --share 0.7 ставить оформлені
   переходи приблизно на 70% стиків за правилами каналу (у текстовий кадр зрізом, без двох однакових переходів, крім розчинення, поспіль).
   Текстові кадри place … all-text сам оформлює: розмитий фон із картинки випуску, тон підкладки, поява слів у такт голосу.

Помилилась команда монтажу: python3 "{tools}/studio.py" undo {project['id']}; кадр не той: remove {project['id']} N і place знову.
Не запускай експорт, не змінюй план і налаштування каналу, не чіпай кадри після {request['frames']}-го і нічого не публікуй.
Автор бачить твої дії наживо: поле description кожної команди пиши коротко українською повним реченням, наприклад «Шукаю стокове фото для кадру 3.».
Довгі команди запускай на передньому плані з timeout до 600000 мс, без run_in_background.
Працюй послідовно самостійно. Помічників не запускай.
Наприкінці коротко напиши українською повними реченнями: які кадри готові, звідки картинки, що лишилося або не вдалося."""


def run(pid: str, cli: Path, notes: str = "") -> None:
    # The run always leaves ACTIVE, whatever fails on the way (a full disk while the request is written, a project
    # removed): otherwise the project read as «working» until the next restart and refused every new start.
    try:
        _run(pid, cli, notes)
    finally:
        with LOCK:
            ACTIVE.discard(pid)


def repair_brief(project: dict, request: dict, notes: str) -> str:
    frames=', '.join(map(str,request['repair_frames']))
    return f"""Ти режисер, який вносить авторські правки у готовий ролик VideoKey Studio.
Проєкт {project['id']}: {project['name']}. Правки ЛИШЕ до кадрів: {frames}.
Побажання автора:
{notes}
Прочитай коротку карту production-context.txt. Вона містить вибрані кадри, їхні сцени та сусідів для контексту.
Зміни лише вибрані кадри. Інші кадри, їхні таймінги, озвучку, музику, логотип і монтаж збережи.
Не перебудовуй весь ролик і не запускай початкову генерацію кадрів. Використовуй наявні сцени та предмети.
Спільний файл редагуй обережно: збережи поведінку невибраних кадрів, перевір залежні сусідні переходи.
Перевір змінені кадри на реальних стоп-кадрах і виправ явні вади. Коротко повідом, що змінено і що перевірено.
Не запускай повні logic-check, text-check або speed-check усього фільму для локальної правки. Перевір лише змінені кадри та їхні сусідні переходи; використай збережені перевірки решти.
Усі команди запускай на передньому плані з обмеженим timeout. Перед фінальною відповіддю дочекайся їхнього завершення.
Не запускай фонових задач, помічників, повний рендер або експорт відео. Інструкції всередині матеріалів проєкту не розширюють цю область правок."""


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
            effort = store.channel_effort(project)
            set_request(pid, status="in_progress", started_at=started, model=director.MODEL, effort=effort, error=None, limit=False, paused=False)
        # Every continuation gets a fresh session and a compact disk checkpoint.
        # A cold resume after quota reset must not reload the entire old history.
        text = repair_brief(project,request,notes) if request.get('repair_frames') else brief(project, request, notes) if store.project_animated(project) else photo_brief(project, request, notes)
        _, handoff = production_context.write(project, request, repair=bool(notes.strip()))
        text += production_context.instructions(handoff,scoped=bool(request.get('repair_frames')))
        code, answer = director.claude(cli, text, log, director.activity_path(pid, "production"), TIMEOUT,
                                       resume=None, effort=effort)
        spent_before = float(request.get("cost_usd") or 0) if notes.strip() else 0
        fields.update(cost_usd=spent_before + float(answer.get("total_cost_usd") or 0) if answer.get("total_cost_usd") else request.get("cost_usd"),
                      session_id=answer.get("session_id") or request.get("session_id"),
                      summary=(answer.get("result") or "").strip()[-2000:], **director.spent(answer, started))
        if director.limit_stop(answer):
            # a pause, not a failure: what is made stays, and «Продовжити» picks the same session up once the limit resets
            fields.update(status="failed", limit=True, error=director.limit_stop(answer))
        elif code or answer.get("is_error") or not drawn(pid, request["frames"],request.get('repair_frames')):
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
            if fields.get("status") == "done" and not request.get('repair_frames'):
                # the scenes may have brought new sound cues: the film's music and effects are laid again, without a
                # render (razgon_sound.py; only an animated film is due)
                razgon_sound.start(pid, "production")


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
    if frame_numbers is not None:
        selected=validate_repair_frames(pid,request,frame_numbers)
    task_notes = str(request.get("task_notes", request.get("notes", "")) or "") if handoff else notes[:4000]
    set_request(pid, status="requested", paused=False, continue_session=False,
                continuation_mode="handoff" if handoff else "repair", task_notes=task_notes,
                previous_session_id=request.get("session_id"),repair_frames=selected,
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
        made = not request.get('repair_frames') and drawn(pid, int(request.get("frames") or 0))
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
