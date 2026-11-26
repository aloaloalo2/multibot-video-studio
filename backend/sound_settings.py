"""Channel sound choices shared by settings, agents and the local audio mixer."""
from __future__ import annotations

import copy
import json
import sfx_library
import importlib.util
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT_AUDIO = ROOT / 'razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/audio'
# One SFX list for accents and animations, motion-design sounds first (user, 21 November 2026: «ефекти акцентів це те
# саме, що SFX для анімації… не мультяшні… щось появляється, щось крутиться, щелчки… накручування… тріщотка… вух має
# бути різні варіанти»). The cartoon and musical ones (a bell ding, a power-up, a freeze swell) left the list.
CATEGORIES = (
    ('appear', 'Поява елемента', ('appear',)),
    ('swoosh_in', 'Наліт', ('swoosh_in',)),
    ('swoosh_out', 'Відліт', ('swoosh_out',)),
    ('whoosh', 'М’який помах', ('whoosh',)),
    ('swish', 'Швидкий помах', ('swish',)),
    ('spin', 'Обертання', ('spin',)),
    ('slide', 'Ковзання', ('slide',)),
    ('ratchet', 'Тріскачка, накручування', ('ratchet',)),
    ('scramble', 'Перебір символів тексту', ('scramble',)),
    ('typing', 'Друк тексту', ('typing',)),
    ('click', 'Клік', ('ui_click', 'double_click')),
    ('tick', 'Клацання', ('tick',)),
    ('lock', 'Фіксація на місці', ('lock_in',)),
    ('counter', 'Підрахунок чисел', ('counter',)),
    ('rise', 'Коротке наростання', ('rise_short',)),
    ('movement', 'Короткий удар', ('hit',)),
    ('impact', 'Глибокий акцент', ('impact',)),
    ('glint', 'Відблиск', ('glint',)),
    ('digital', 'Цифровий збій', ('glitch',)),
    ('devices', 'Спалах і затвор', ('flash',)),
)
# A channel saved before this list (no "version"): its choices carry over by meaning, and the new motion sounds are on.
EFFECTS_VERSION = 2
OLD_CATEGORIES = {'appearance': 'appear', 'switch': 'click', 'sparkle': 'glint', 'tension': 'rise',
                  'notification': None, 'freeze': None, 'ambience': None}
NEW_IN_V2 = ('swoosh_in', 'swoosh_out', 'spin', 'slide', 'ratchet', 'scramble', 'typing', 'lock')
TRANSITIONS = (
    ('air', 'Повітряний whoosh'), ('silk', 'М’який шовковий'), ('snap', 'Сухий snap'),
)
# CapCut's trending sounds that suit a seam, offered among the transition sounds too (user, 25 November 2026: «ці SFX
# капкати… скопіюй і в звуки переходів… звук вух або звук затвору камери»): whooshes and swishes, camera shutters, glitches,
# a page turn and a bass hit. The file is the SFX library's own (sfx_library, levelled and at most 4 s); the key is «cc» and
# its CapCut id, its sound name «tr_cc…».
CAPCUT_TRANSITIONS = (
    '6940659030947792897', '6993230936988977154', '7385623662601701417', '7385623829542504489', '7527870971623393297',
    '7685955880517355521', '7685955939240839185', '7618787513914591233', '6817673392263530497', '6817674819585181698',
    '7380064362571548708', '7652550300482652177', '6830449581730301954', '6830449586222401538',
    '6839356087691380737', '6906958260398475265', '7380059953049389095', '7385629873921280019', '6830455909576083458',
    '7021300953584257026', '7065360142346225665', '6817155807902173185', '7380059090457413686', '7055113164392531970',
)
TRANSITION_IDS = {row[0] for row in TRANSITIONS} | {'cc' + key for key in CAPCUT_TRANSITIONS}


def capcut_transitions():
    """{sound name: SFX library row} of the CapCut transition sounds present on this Mac, in CAPCUT_TRANSITIONS order."""
    rows = {row['mixkit_id']: row for row in sfx_library.catalog() if row.get('source_group') == 'capcut'}
    return {'tr_cc' + key: rows[key] for key in CAPCUT_TRANSITIONS if key in rows}
RETIRED_TRANSITION_IDS = {'whip', 'camera', 'sweep', 'down', 'rise', 'reverse', 'bass', 'glitch', 'pixel', 'neon', 'warp', 'shimmer'}
# The channel's music style (kit audio/music.py STYLES); «whatif» is the original score (user, 17 November 2026: «в
# настройках хочу, щоб музику я міг вибрати… для What If ці звуки нравляться… для інших каналів… космічний стиль»).
MUSIC_STYLES = (('whatif', 'What If'), ('soft', 'М’який фон'), ('deep', 'Глибокий фон'), ('space', 'Космос'), ('piano', 'Піаніно'),
                ('cinematic', 'Кіно'), ('light', 'Легкий'))
MUSIC_STYLES = dict(MUSIC_STYLES)
IDS = {row[0] for row in CATEGORIES}
LOCK = threading.RLock()


def merge(current, patch):
    result = normalize(current)
    if not isinstance(patch, dict):
        raise ValueError('Невірні налаштування звуку')
    for key, value in patch.items():
        result[key] = {**result.get(key, {}), **value} if isinstance(value, dict) else value
    return normalize(result)


def normalize(value=None):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - {'music', 'effects', 'transitions', 'library'}:
        raise ValueError('Невірні налаштування звуку')
    result = {}
    for key, flags in (('music', {'enabled': True, 'generate': True}), ('effects', {'enabled': True})):
        part = value.get(key, {})
        if not isinstance(part, dict) or set(part) - (set(flags) | ({'categories', 'version'} if key == 'effects' else {'style'})):
            raise ValueError('Невірні налаштування ' + key)
        result[key] = {}
        for flag, default in flags.items():
            current = part.get(flag, default)
            if type(current) is not bool:
                raise ValueError('Вибір звуку має бути увімкнено або вимкнено')
            result[key][flag] = current
    style = value.get('music', {}).get('style', 'whatif')
    if style not in MUSIC_STYLES:
        raise ValueError('Невідомий стиль музики')
    result['music']['style'] = style
    effects = value.get('effects', {})
    categories = effects.get('categories', [row[0] for row in CATEGORIES])
    if not isinstance(categories, list) or len(set(categories)) != len(categories):
        raise ValueError('Невідома або повторена категорія звуку')
    if any(isinstance(key, str) and key in OLD_CATEGORIES for key in categories) or (effects.get('version') != EFFECTS_VERSION and 'categories' in effects):
        # a choice from the list before 21 November 2026: the same choice by meaning; a channel saved then gets the new
        # motion sounds on as well
        carried = [OLD_CATEGORIES.get(key, key) for key in categories if isinstance(key, str)]
        carried = [key for key in carried if key is not None]
        if effects.get('version') != EFFECTS_VERSION and carried:   # an empty choice stays empty
            carried += [key for key in NEW_IN_V2 if key not in carried]
        if any(key not in IDS for key in carried):
            raise ValueError('Невідома або повторена категорія звуку')
        categories = [row[0] for row in CATEGORIES if row[0] in set(carried)]
    if any(not isinstance(key, str) or key not in IDS for key in categories):
        raise ValueError('Невідома або повторена категорія звуку')
    result['effects']['categories'] = list(categories)
    result['effects']['version'] = EFFECTS_VERSION
    transition = value.get('transitions', {})
    if not isinstance(transition, dict) or set(transition) - {'enabled', 'styles'}:
        raise ValueError('Невірні налаштування звуків переходів')
    enabled = transition.get('enabled', False)
    styles = transition.get('styles', [row[0] for row in TRANSITIONS])
    if type(enabled) is not bool or not isinstance(styles, list) or any(not isinstance(k, str) or k not in TRANSITION_IDS | RETIRED_TRANSITION_IDS for k in styles) or len(set(styles)) != len(styles):
        raise ValueError('Невідомий звук переходу або некоректний вибір')
    result['transitions'] = {'enabled': enabled, 'styles': [key for key in styles if key in TRANSITION_IDS]}
    if 'library' in value:
        library = value['library']
        if not isinstance(library, dict) or set(library) - {'enabled', 'ids'} or type(library.get('enabled', True)) is not bool:
            raise ValueError('Невірний вибір SFX для анімацій')
        result['library'] = {'enabled': library.get('enabled', True)}
        if 'ids' in library:
            ids = library['ids']
            # Stable IDs survive channel transfer even when this computer has no library installed.
            if (not isinstance(ids, list) or len(ids) > 1000
                    or any(not isinstance(key, str) or not re.fullmatch(r'[0-9]{1,20}', key) for key in ids)
                    or len(set(ids)) != len(ids)):
                raise ValueError('Невідомий або повторений SFX')
            result['library']['ids'] = list(ids)
    return result


def saved_for_project(project):
    import store
    try:
        settings = store.read_channel_settings(store.get_channel_folder(project['channel_id'], include_disabled=True), {})
    except (store.StudioError, OSError, KeyError):
        settings = {}
    return settings.get('sound')


def for_project(project):
    return normalize(saved_for_project(project))


def allowed_names(sound):
    selected = sound['effects']['categories'] if sound['effects']['enabled'] else []
    return [name for key, _, names in CATEGORIES if key in selected for name in names]


def transition_names(sound):
    selected = sound['transitions']['styles'] if sound['transitions']['enabled'] else []
    return ['tr_' + key for key, _ in TRANSITIONS if key in selected] + [name for name in capcut_transitions() if name[3:] in selected]


def apply_config(config, value, *, animated=False):
    """A copy, so channel switches never destroy the director's saved cues or music file."""
    result = copy.deepcopy(config)
    if value is None:
        return result
    sound = normalize(value)
    result['music'] = {**(result.get('music') or {}), **sound['music']}
    library = sfx_library.allowed(sound)   # one SFX list in every project (21 November 2026)
    result['sfx'] = {**(result.get('sfx') or {}), 'enabled': sound['effects']['enabled'] or bool(library) or (sound['transitions']['enabled'] and not animated), 'allowed_names': allowed_names(sound) + library + ([] if animated else transition_names(sound))}
    return result


def filter_story(story, config):
    """Also supports a working kit that has not been updated yet."""
    result = copy.deepcopy(story)
    sfx = config.get('sfx') or {}
    if not sfx.get('enabled', True) or 'allowed_names' in sfx:
        allowed = set(sfx.get('allowed_names', [])) if sfx.get('enabled', True) else set()
        result['sfx'] = [cue for cue in result.get('sfx', []) if cue.get('name') in allowed]
        for shot in result.get('shots', []):
            shot['sfx'] = [cue for cue in shot.get('sfx', []) if cue.get('name') in allowed]
            if (shot.get('amb') or {}).get('name') not in allowed:
                shot.pop('amb', None)
    return result


def catalog():
    return [{'id': key, 'label': label, 'names': list(names), 'preview_url': f'/api/sound-effects/{key}.wav?v=5'} for key, label, names in CATEGORIES]


def transition_catalog():
    return ([{'id': key, 'label': label, 'name': 'tr_' + key, 'preview_url': f'/api/transition-sounds/{key}.wav?v=5', 'source_group': 'studio'}
             for key, label in TRANSITIONS]
            + [{'id': name[3:], 'label': row['label'], 'name': name, 'preview_url': row['preview_url'], 'source_group': 'capcut'}
               for name, row in capcut_transitions().items()])


def audio_module(name):
    # Load the checked-in kit, without requiring a renderer or changing a working project.
    with LOCK:
        key = '_videokey_audio_' + name
        if key not in sys.modules:
            spec = importlib.util.spec_from_file_location(key, KIT_AUDIO / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[key] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(key, None)
                raise
        return sys.modules[key]


def preview(category, *, transition=False):
    import store
    rows = [(key, label, ('tr_' + key,)) for key, label in TRANSITIONS] if transition else CATEGORIES
    row = next((row for row in rows if row[0] == category), None)
    if row is None:
        raise store.StudioError('Звук не знайдено', 404)
    # v3: the whole sound, as the film lays it (user, 21 November 2026: «навіть в настройках каналу… звуки якісь обрізані»)
    path = store.DATA_ROOT / 'cache' / 'sound-previews-v5' / (('transition-' if transition else '') + category + '.wav')
    with LOCK:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            module = audio_module('sfx')
            # the whole sound at the common SFX loudness, as the film lays it; every preview sounds equally loud
            module.write_wav(str(path), module.take(row[2][0]))
    return path


def music_catalog():
    return [{'id': key, 'label': label, 'preview_url': f'/api/music-styles/{key}.mp3?v=2'} for key, label in MUSIC_STYLES.items()]


def music_preview(style):
    """Twenty seconds of the style, the same two moods for every style so they compare by ear; made once, locally."""
    import store, subprocess
    if style not in MUSIC_STYLES:
        raise store.StudioError('Стиль музики не знайдено', 404)
    folder = store.DATA_ROOT / 'cache' / 'music-style-previews-v2'
    path = folder / (style + '.mp3')
    with LOCK:
        if not path.is_file():
            folder.mkdir(parents=True, exist_ok=True)
            module = audio_module('music')
            plan = [{'start': 0, 'end': 10, 'mood': 'wonder', 'intensity': .6}, {'start': 10, 'end': 20, 'mood': 'mystery', 'intensity': .6}]
            samples = module.render_score(plan, 20, seed=7, style=style)
            wav = path.with_suffix('.wav')
            module.write_wav(str(wav), samples)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(wav), '-b:a', '160k', str(path)], check=True)
            wav.unlink(missing_ok=True)
    return path


def instructions(project, *, scoped=False, include_workflow=True):
    sound = for_project(project)
    music = sound['music']
    text = '\nЗВУК РОЛИКА. Актуальний вибір автора для цього каналу:\n'
    text += ('Музика вимкнена. Не створюй і не додавай фонову музику.\n' if not music['enabled'] else
             'Використовуй фонову музику. Її можна створити локально.\n' if music['generate'] else
             'Використовуй лише вже додану музику. Нову музику не генеруй.\n')
    import store
    animated = store.project_animated(project)
    downloaded = sfx_library.instructions(sound)
    names = allowed_names(sound)
    # one SFX list for accents and animations: the synthesized motion sounds and the author's files together
    text += ('SFX (одна добірка для акцентів і анімацій): ' + ', '.join(names) + '. Це звуки моушн-дизайну під видиму подію: '
             'поява (appear, swoosh_in), відліт (swoosh_out), обертання (spin), ковзання (slide), накручування й перебір тексту '
             '(ratchet, scramble, typing), кліки й фіксація (ui_click, double_click, tick, lock_in), числа (counter), удари. '
             'Чергуй варіанти, не мультяшно, кожен звук цілий (до 4 с), гучність студія вирівнює сама; голос лишається чітким.\n'
             if names else '') + (downloaded or ('' if names else 'Звукові ефекти й атмосферу вимкнено. Не додавай їх.\n'))
    if 'library' in sound and not downloaded and not names:
        text += 'У добірці SFX для анімацій немає дозволених доступних звуків. Файли цієї добірки не додавай.\n'
    transitions = [] if animated else transition_names(sound)
    text += ('Окремі звуки переходів: ' + ', '.join(transitions) + '. Обирай лише доречні стики, чергуй типи. Більшість м’яких склейок залишай тихими.\n' if transitions else 'Звуки переходів вимкнено. Монтажні акценти мають окремий вибір.\n')
    if scoped:
        return text + 'Це правка кадрів: наявний звук збережи, заново його не створюй.\n'
    if not include_workflow or not project.get('id'):
        return text
    if not animated:
        # the studio voices what comes on screen itself, from the code (event_sounds.py, 25 November 2026): an agent's
        # guessed times doubled it and missed the picture
        text += ('Звуки на появу тексту й картинок і на письмо (олівець, клавіатура) у кадрах Razgon, текстових вставках і '
                 'моушн-коді студія кладе сама після створення кадрів: вона читає момент кожної події з коду кадру. '
                 'Не пиши для них cues. Окремі cues став лише на фізичні події, яких немає серед цих: удар, вибух, клацання '
                 'механізму, спалах, не частіше одного на кадр.\n')
        text += 'Операція transitions озвучує вибрані доречні стики. Для авторського вибору передай sound_frames з номерами вхідних кадрів; порожній список лишає всі переходи тихими. Операція transition_sounds оновлює тільки звук на існуючих стиках. Не дублюй ці події окремими cues.\n'
    create_music = music['enabled'] and music['generate']
    cues = names + (sfx_library.allowed(sound) if downloaded else [])
    if not create_music and not cues:
        return text + 'Нову музику й акценти всередині кадру створювати не потрібно. Окрему доріжку для них не генеруй.\n'
    example = json.dumps({'op': 'soundtrack', 'music': create_music, 'mood': 'calm',
                          'cues': [{'name': cues[0], 't': 12.5}] if cues else []}, ensure_ascii=False)
    text += ('Для Razgon запиши ці обмеження в config.json: music.enabled, music.generate, sfx.enabled і sfx.allowed_names; '
             'cue та amb мають використовувати тільки дозволені імена. Вимкнений пункт не потребує генерування.\n'
             'Для звичайного монтажу після створення кадрів один раз використай /ops операцію soundtrack: '
             + example + '. Постав події за реальними таймінгами свого пакета кадрів. '
             'Передай music:true лише коли музика дозволена до генерації та її ще немає; cues містять лише потрібні події. '
             'Це локальний синтез звуку, без платного API й без рендеру відео. Наявний звук не дублюй.\n')
    return text


# A transition sounds like what it does (user, 25 November 2026: «звук у цього переходу… гліч… має відповідати глічу
# переходу. Не може бути плавний перехід і звук переходу гліч»): each transition and each transition sound has a character.
# Each CapCut transition by what it does on the screen, watched on its own sample (25 November 2026; the names misled: a
# white burst called «Спотворення прискорення» took a glitch sound, user: «перехід, який не мечиться з звуком гліч. Ніколи
# їх не мечі»). A transition not listed moves (a slide, a turn, a cube, a door, a zoom).
TRANSITION_CHARACTER = {
    # «Пиловий вихор» (capcut_t23) is no soft one: its 2 s whirl pressed into a 0.7 s seam swirls with drive (user, 26
    # November 2026, Andromeda 83→84: «на ведучому не може появлятися. Це драйвовий перехід»), so it moves
    "crossfade": "soft", "capcut_t10": "soft", "capcut_t25": "soft", "capcut_t34": "soft",
    "capcut_t08": "glitch",   # a film-burn flash with a grainy double exposure; the author hears it as a glitch (25 November 2026)
    "capcut_t17": "glitch", "capcut_t24": "glitch", "capcut_t29": "glitch", "capcut_t31": "glitch",
    "capcut_t03": "flash", "capcut_t04": "flash", "capcut_t06": "flash", "capcut_t07": "flash", "capcut_t12": "flash", "capcut_t13": "flash",
    "capcut_t19": "flash", "capcut_t22": "flash", "capcut_t26": "flash", "capcut_t27": "flash", "capcut_t32": "flash", "capcut_t38": "flash",
}
SOUND_CHARACTER = {
    "tr_silk": "soft", "tr_cc7685955880517355521": "soft", "tr_cc7385623662601701417": "soft", "tr_cc7385623829542504489": "soft",
    "tr_cc6817674819585181698": "soft", "tr_cc6817673392263530497": "soft",
    "tr_cc7021300953584257026": "glitch", "tr_cc7065360142346225665": "glitch",
    "tr_snap": "flash", "tr_cc6839356087691380737": "flash", "tr_cc6906958260398475265": "flash", "tr_cc7380059953049389095": "flash",
    "tr_cc7385629873921280019": "flash", "tr_cc6830455909576083458": "flash", "tr_cc7055113164392531970": "flash",
}


def transition_character(kind):
    """soft, glitch, flash or motion (a slide, a zoom, a turn, a portal)."""
    if kind.startswith("cin_"):
        return "soft"
    return TRANSITION_CHARACTER.get(kind, "motion")


def sound_character(name):
    return SOUND_CHARACTER.get(name, "motion")


def sounds_for(character, chosen):
    """The transition sounds of a character: the channel's own first, else every one the studio has."""
    own = [name for name in chosen if sound_character(name) == character]
    if own:
        return own
    every = ['tr_' + key for key, _ in TRANSITIONS] + list(capcut_transitions())
    return [name for name in every if sound_character(name) == character]
