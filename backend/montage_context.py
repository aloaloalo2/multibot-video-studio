"""Stage-specific standing rules, with no script archives or automatic CLI memory."""
import re
import shlex
from pathlib import Path

import author_rules
import store

# Exclude only recognisable text-authoring/history sections. Unknown rules stay intact.
WRITING = re.compile(r'авторы|авторів|выбор автора|автора сценар|удержан|подач|речь|драматург|лайк|польз|сут[ьиі]|згадк|объём|обсяг|сценар|зачин|тайтл|заголов|\bтем[аиыуі]|темы|теми|архив|архів|метадан|тег[иів]|описани|опису|публикац|публікац|thumbnail|превью|прев.ю', re.I)
VISUAL = re.compile(r'монтаж|кадр|анимац|анімац|фото|png|зображ|изображ|ілюстр|иллюстр|плашк|екран|экран|рендер|render|расказ|раскадр|розкадр|стик|стык|звук|audio|відео|видео|студі|studio|таймін|тайминг|whisper|персонаж|логотип|движ|рух|геометр|пропорц|склей|переход|zoom|зум', re.I)


# Production receives an accepted script, voice and timed plan. These known upstream
# headings otherwise send historical author selection and planning steps every session.
UPSTREAM = re.compile(
    r'^(?:короткий технічний маршрут режисера|план ролика тільки після озвучки|карта ролика только после озвучки|'
    r'(?:попередня )?карта ролика (?:в|у) videokey studio|готовий перевірений сценарій до студії|'
    r'тільки opus|только opus|четыре автора для всех каналов|захватывающий полезный рассказ|'
    r'перевірка кожного кадру|'   # the look at the pictures is one review at the end (15 November 2026), not in each session
    r'не раскрывать главный ответ|уникальность выпусков|повторы между каналами|'
    r'[1-9][0-9]*\. (?:написать полный сценарий|проверить и показать сценарий|подготовить превью|'
    r'получить финальную озвучку|подготовить выпуск к публикации))', re.I)


# Frame production gets an accepted script, voice and plan; these standing rules govern other stages, the Studio itself
# or the author's chat, and only made every step of every frame session reread them (user, 15 November 2026: «ліміти
# витрачаються швидко… почисти»).
NOT_FRAMES = re.compile(
    r'перезапуск студії|whisper|числа цифрами|прямий запуск інструментів|усилие claude|запрет слов|заборонені слова|'
    r'слово «душа»|кликбейт|собственный браузер|google flow|цель при создании|без слышимого звука|'
    r'объединение коротких фраз|смысловое объединение|восьмисекундное вступление|сверка каждой расшифровки|'
    r'ориентиры индивидуального стиля|план кадрів тільки після|кроки випуску й одна команда|место на диске|'
    r'ещё не определено|медичні стилі|одна пауза на випуск|план кадрів зі сценарію паралельно|'
    # replaced by later rules: the director sets every move, `place` without --motion stays still (8 November 2026)
    r'непрерывный зум каждой фотографии', re.I)
# Grouping sentences into frames is the director's work: the planning brief keeps these, the frame sessions do not.
PLANNING = re.compile(r'объединение коротких фраз|смысловое объединение', re.I)
# «Прямое указание пользователя только для Алексея Горбунова и Валентина Чичваркина: …» names its channels in the first
# sentence of the body, not in the heading.
FOR_WHOM = re.compile(r'^[^:\n]{0,200}?\b(?:только|тільки|лише)?\s*для\s+([^:\n]{0,160})', re.I)
# Rules written for named channels go only to those channels.
NAMED = {'алексе': 'горбунов', 'олекс': 'горбунов', 'горбунов': 'горбунов', 'валентин': 'чичвар', 'чичвар': 'чичвар',
         'карл': 'karl', 'karl': 'karl', 'антропов': 'антропов', 'ветров': 'ветров'}
PHOTO_ONLY = re.compile(r'фото|красивый текст по озвучке|кадрирован|изображения из интернета|последовательная дорожка|инфографик|картинок на одном', re.I)


def for_frames(heading, channel, animated, body='', planning=False):
    """Whether a standing rule section belongs in the brief of the frame agent (or, with planning, the director)."""
    if NOT_FRAMES.search(heading) and not (planning and PLANNING.search(heading)):
        return False
    low, name = heading.lower(), channel.lower()
    named = {target for key, target in NAMED.items() if key in low}
    if not named:
        first = next((line for line in body.splitlines()[1:] if line.strip()), '')
        whom = FOR_WHOM.match(first)
        if whom and not re.search(r'всех|всіх|усіх', whom.group(1), re.I):
            named = {target for key, target in NAMED.items() if key in whom.group(1).lower()}
    if named and not any(target in name for target in named):
        return False
    return not (animated and PHOTO_ONLY.search(heading))


def sections(text, *, production=False):
    """Keep whole relevant sections, including unknown/general rules and their preamble."""
    kept = []
    for part in re.split(r'(?m)^(?=#{1,3} )', text):
        heading = part.splitlines()[0] if part.strip() else ''
        if production and UPSTREAM.match(heading.lstrip('# ').strip()):
            continue
        if WRITING.search(heading) and not VISUAL.search(heading):
            continue
        kept.append(part.strip())
    return '\n\n'.join(p for p in kept if p)


def rules(project, *, production=False, planning=False):
    """The standing rules of this stage: the frame sessions (production) and the director (planning) get the sections
    that govern their work, without the other stages', other channels' and replaced ones."""
    channel = Path(project['episode_path']).parent
    sources = [store.YOUTUBE_ROOT / 'AGENTS.md', store.channel_rules_source(channel)]
    seen, blocks = set(), []
    animated = store.project_animated(project)
    staged = production or planning
    for path in sources:
        text = sections(author_rules._read(path), production=staged)
        if staged:
            text = '\n\n'.join(part.strip() for part in re.split(r'(?m)^(?=#{1,3} )', text)
                                 if part.strip() and for_frames(part.splitlines()[0], channel.name, animated, part, planning))
        for paragraph in re.split(r'\n\s*\n', text):
            key = paragraph.strip()
            if key and key not in seen:
                seen.add(key)
                blocks.append(key)
    fonts=store.read_channel_settings(channel,{}).get('typography') or {}
    if fonts.get('font_family'):
        blocks.append('Шрифти текстових вставок та окремих монтажних елементів Studio: основний текст '+fonts['font_family']+
                      ', акценти й підписи '+fonts.get('accent_font_family',fonts['font_family'])+
                      '. Шрифти сцен Razgon визначає animation.title_font.')
        extra=[f for f in (fonts.get('second_font_family'),fonts.get('extra_font_family')) if f and f!=fonts['font_family']]
        if extra:
            blocks.append('Інші шрифти каналу для комбінацій у моушн-дизайні, підписах і текстових вставках: '+', '.join(extra)+
                          ' (передавай font_family). Поєднуй їх з основним для ієрархії, наприклад заголовок і підпис, не більше двох шрифтів в одному кадрі.')
    return ('\nЧинні загальні та канальні правила для режисури й монтажу. '
            'Сценарій та озвучка вже прийняті. Поточний запит, налаштування каналу і наведений нижче '
            'порядок Studio мають пріоритет над історичними кроками випуску.\n' + '\n\n'.join(blocks) + '\n')


COMMANDS = '''
Пиши українською. Не використовуй антитези й довге тире у власних текстах.
Команди виконуй по одній, без cd, &&, ;, конвеєрів, shell-змінних та перенаправлення виводу.
Використовуй абсолютні шляхи в лапках. Файли змінюй через Write/Edit; для довшої логіки
збережи короткий Python-скрипт через Write і виконай його однією командою python3.
Текст читай через Read з offset/limit. Не повторюй відхилену складну shell-команду.
Код студії (backend/*.py, tools/*.py) для довідки не читай: команди, ops і шари описані тут; якщо команда відмовила,
її повідомлення каже, що виправити.
Це зберігає звичайні перевірки дозволів; не змінюй дозволи CLI.
'''


def commands(project, numbers, *, repair=False):
    plan = store.load_project_plan(project['id']) or {}
    formats = {f['number']: f.get('format', 'razgon_2d') for f in plan.get('frames', [])}
    linked = __import__('frame_progress').razgon_project(project)
    tools = store.APP_ROOT / 'tools'
    guide = [COMMANDS, 'Команди для кожної партії після розміщення всіх PNG, шарів, підписів, акцентів і руху.']
    for start in range(0, len(numbers), 5):
        batch = numbers[start:start+5]
        native = [n for n in batch if n in formats and formats[n] != 'razgon_2d']
        razgon = [n for n in batch if formats.get(n) == 'razgon_2d']
        scope = ','.join(map(str,razgon))
        if razgon and linked:
            tool = store.YOUTUBE_ROOT / store.razgon_rel() / 'tools/frame_review.py'
            base = f'python3 {shlex.quote(str(tool))} --project {shlex.quote(str(linked))}'
            guide.append(f'python3 {shlex.quote(str(tools/"razgon_bridge.py"))} slots --razgon {shlex.quote(str(linked))} --frames {scope}')
        if native and not repair:
            guide.append(f'python3 {shlex.quote(str(tools/"studio.py"))} transitions {project["id"]} --frames {",".join(map(str,batch))} --share 0.7')
        if native:
            guide.extend([f'python3 {shlex.quote(str(tools/"studio.py"))} review {project["id"]} --frames {",".join(map(str,native))}',
                          'Відкрий повернений аркуш. Схвали готові номери надрукованою командою. Для дефекту виключи його номер зі схвалення й виправ лише цей кадр.'])
        if razgon and linked:
            # the pictures are looked at once, at the end of the film (production.light_review); here only the free checks
            times = [(f.get('start'), f.get('end')) for f in plan.get('frames', []) if f['number'] in razgon]
            span = (f' --from {min(t[0] for t in times):.2f} --to {max(t[1] for t in times):.2f}'
                    if times and all(isinstance(t[0], (int, float)) and isinstance(t[1], (int, float)) for t in times) else '')
            render = f'nice -n 10 node {shlex.quote(str(store.YOUTUBE_ROOT / store.razgon_rel() / "render.mjs"))} --project {shlex.quote(str(linked))}'
            guide.extend([f'{render} --logic-check{span}', f'{render} --text-check{span}', f'{render} --jump-check{span}',
                          'Виправ лише те, що вони знайшли. Картинок кадрів не переглядай і mark не став.'])
    return '\n'.join(guide) + '\n'
