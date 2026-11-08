"""One channel preference for PNG objects in both editable animation formats."""
import store


def instructions(project, *, planning=False):
    try:
        settings=store.read_json(store.get_channel_folder(project['channel_id'],include_disabled=True)/store.PLAN_CONFIG,{}) or {}
    except (store.StudioError, KeyError, OSError):
        settings={}
    enabled=(settings.get('animation') or {}).get('assets',True) is not False
    if not enabled:
        return '\nPNG асети вимкнені для animation та razgon_2d. Предмети нових анімацій малюй кодом; не підмінюй це PNG-предметами. Повнокадрові фото мають окремий формат. Наявні прийняті кадри зберігай.\n'
    text='\nPNG асети увімкнені. Це обов’язкова вимога для обох форматів: кодової анімації animation і 2D-анімації razgon_2d, також в універсальному проєкті. Для предметів, органів, людей та інших конкретних об’єктів використовуй доречні готові PNG асети. Геометрію, графіки, схеми й написи можна малювати кодом. Не зводь усі кадри до геометричних замінників предметів.\n'
    if planning:
        return text+'У задумі відповідних кадрів вкажи, який предмет показати PNG асетом, а які частини зробити кодом. На етапі плану лише запиши рішення; створення зображень виконує агент кадрів.\n'
    return text+'''Спершу використай збережені picks і відповідні предмети проєкту, далі один обмежений пошук tools/library.py search і один аркуш кандидатів.
Вдалий предмет підключи через library.py pull; якщо відповідного немає, створи PNG предмет у Codex. Не переглядай бібліотеку повторними довгими колами.
Для animation додай PNG як окремий редагований шар через op=animation, clips з kind=image і path, рух через keyframes. Для PNG підписів передай foreground=true.
Для razgon_2d підключи PNG у scenes/assets.js, реально намалюй їх у сцені й залиш config.json assets=true. Самі завантажені файли без використання в кадрі не виконують вимогу.
Зафіксуй, які PNG взято з бібліотеки або створено й у яких кадрах вони використані. Уже прийняті сцени зберігай.\n'''
