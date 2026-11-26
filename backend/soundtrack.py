"""Place a locally synthesized soundtrack through ordinary, undoable timeline actions."""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

import sound_settings
import sfx_library
import store

# The music sits this far under the voice, whose standard is audio_level.TARGET_LUFS (−16): measured, not a fixed share.
# A fixed 35% left a synthesized bed only 13 dB under Gorbunov's voice and loud in every pause (user, 15 November 2026:
# «чому музика так голосно? чому немає якоїсь нормалізації»).
MUSIC_UNDER_VOICE_DB = 30.0   # 22 dB was still loud (user, 15 November 2026: «всеодно голосно»); Antropov's liked bed sits ~32 dB under
MUSIC_FALLBACK_VOLUME = 0.12


def music_volume(path) -> float:
    import audio_level
    level = audio_level.measure(Path(path))
    if not level or not math.isfinite(level.get('lufs', float('nan'))):
        return MUSIC_FALLBACK_VOLUME
    db = audio_level.TARGET_LUFS - MUSIC_UNDER_VOICE_DB - level['lufs']
    return round(max(0.02, min(0.5, 10 ** (db / 20))), 3)


PREFIX = 'Звук ролика · '
TRANSITION_PREFIX = 'Звук переходу · '
TYPING_PREFIX = 'Звук друку · '
DRAWING_PREFIX = 'Звук олівця · '
APPEAR_PREFIX = 'Звук появи · '
SFX_PREFIX = PREFIX + 'SFX · '
# every effect file is levelled to the same loudness of its loudest 400 ms (−18 dB); at this volume it sits about 14 dB
# under the voice's −16 LUFS, the same for a click, a whoosh and an impact
SFX_VOLUME = .07   # universal projects, the author's level (25 November 2026: «краще на 6% сфх для універсальних проектів… або 7»); it was .25, then .14


_PEAKS: dict = {}
_PEAKS_LOADED = False
PEAKS_FILE = 'sfx-peaks-v1.json'   # in store.DATA_ROOT / 'cache', kept between starts of the studio


def _peak(path) -> float:
    """Seconds from a sound file's start to its loudest 50 ms (kit audio/sfx.py peak_time), measured once a file version
    and kept on disk: every start of the studio decoded every effect of every project again before (25 November 2026)."""
    global _PEAKS_LOADED
    path = Path(path)
    try:
        stat = path.stat()
        key = f'{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}'
    except OSError:
        key = None
    cache = store.DATA_ROOT / 'cache' / PEAKS_FILE
    with sound_settings.LOCK:
        if not _PEAKS_LOADED:
            _PEAKS.update(store.read_json(cache, {}) or {})
            _PEAKS_LOADED = True
        if key in _PEAKS:
            return _PEAKS[key]
    import numpy as np
    raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'f32le', '-ac', '2', '-ar', '48000', '-'],
                         capture_output=True).stdout
    samples = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2) if raw else np.zeros((1, 2), np.float32)
    peak = peak_time(samples)
    if key and raw:
        with sound_settings.LOCK:
            _PEAKS[key] = peak
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                store.atomic_json(cache, _PEAKS)
            except OSError:
                pass
    return peak


def peak_time(samples) -> float:
    """The kit's audio/sfx.py peak_time without importing the kit (its scipy took 4 s at the first sound pass): seconds
    from the start to the middle of the loudest 50 ms of 48 kHz stereo samples."""
    import numpy as np
    power = (np.asarray(samples, dtype=np.float32).astype(np.float64) ** 2).sum(axis=1)
    return float(np.argmax(np.convolve(power, np.ones(2400), 'same'))) / 48000


_DIGESTS: dict = {}


def _digest(path: Path) -> str:
    """The first 12 hex of a library file's SHA-256, read once a file version (it was read whole for every cue)."""
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _DIGESTS:
        _DIGESTS[key] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return _DIGESTS[key]


def _library_copy(folder: Path, row) -> tuple[Path, Path]:
    """(the project's file of a library effect, the shared levelled file it is a copy of). The project keeps its own file
    (the timeline plays only files of the project), as an APFS clone of the levelled one: no second copy on the disk."""
    path = folder / ('mixkit-' + row['mixkit_id'] + '-' + _digest(Path(row['name'])) + '-v4.wav')
    shared = sfx_library.leveled_path(row)
    if path.exists():
        return path, shared if shared.is_file() else path
    shared = sfx_library.leveled(row)
    if not path.exists():
        part = path.with_name(path.stem + '.part.wav')
        part.unlink(missing_ok=True)
        store.clone_or_copy(shared, part)
        part.replace(path)
    return path, shared


def full_take(module, name: str, seed: int = 7):
    """A synthesized effect whole and at the common SFX loudness (kit audio/sfx.py take: never cut short, at most 4 s;
    user, 21 November 2026: «ніколи не обрізай ті звукові ефекти», «нема норми звуків по громкості»)."""
    samples = module.take(name, seed=seed)
    return samples, len(samples) / module.SR


# Every film its own score (user, 26 November 2026: «музика та сама… в кожному ролику… щоб YouTube не блокував мої ролики,
# щоб він давав монетизацію»): the sound (the kit's style), the mood, the key, the tempo and the seed are picked for the
# film, never a combination the channel's last films had; one seed and one mood made every film of a channel the same.
MUSIC_MOODS = ('calm', 'wonder', 'mystery', 'hopeful', 'playful', 'sad')   # moods that sit under a voice
MUSIC_KEYS = ('C', 'D', 'Eb', 'E', 'F', 'G', 'Ab', 'A', 'Bb', 'B')
MUSIC_RECENT = 4   # the channel's last films whose sound and mood a new film does not repeat


def music_kit(channel: str, module) -> dict:
    """The channel's own music, made for it once on this computer from a random seed: two sounds (the kit's styles),
    three moods, four keys and a tempo of its own, unlike the other channels' kits as far as the sounds allow (user, 26
    November 2026: «для нового каналу… по-іншому вже музика генерується… щоб вона кардинально відрізнялася… в каналі
    самому вже відрізнятися воно може не так сильно»). Its films vary inside it (music_pick)."""
    import random
    import secrets
    path = store.DATA_ROOT / 'channels' / channel / 'music-kit.json'
    saved = store.read_json(path, None)
    styles = [x for x in getattr(module, 'STYLES', {}) or ['whatif']]
    if isinstance(saved, dict) and set(saved.get('styles') or []) <= set(styles) and saved.get('styles'):
        return saved
    rng = random.Random(f"{channel}:{secrets.token_hex(16)}")
    # the sounds the other channels lead with are taken last, so two channels rarely share their sound
    taken = {}
    for other in (store.DATA_ROOT / 'channels').glob('*/music-kit.json'):
        kit = store.read_json(other, None)
        if isinstance(kit, dict) and other.parent.name != channel:
            for rank, sid in enumerate(kit.get('styles') or []):
                taken[sid] = taken.get(sid, 0) + (2 if rank == 0 else 1)
    order = sorted(styles, key=lambda sid: (taken.get(sid, 0), rng.random()))
    kit = {'styles': order[:2], 'moods': rng.sample([m for m in MUSIC_MOODS if m in module.MOODS], 3),
           'keys': rng.sample(MUSIC_KEYS, 4), 'tempo': round(rng.uniform(.9, 1.1), 2)}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        store.atomic_json(path, kit)
    except OSError:
        pass
    return kit


def music_pick(project: dict, module, mood: str | None = None) -> dict:
    """The film's music inside its channel's kit, picked once and kept with the project (the soundtrack laid again sounds
    the same), never the sound and mood of the channel's last films."""
    import random
    mine = store.project_dir(project['id']) / 'music-pick.json'
    saved = store.read_json(mine, None)
    if isinstance(saved, dict) and saved.get('seed') and (mood is None or saved.get('mood') == mood):
        return saved
    channel = project.get('channel_id') or 'none'
    kit = music_kit(channel, module) if project.get('channel_id') else {
        'styles': ['whatif'], 'moods': ['calm'], 'keys': ['Eb'], 'tempo': 1.0}
    history_path = store.DATA_ROOT / 'channels' / channel / 'music-history.json'
    history = [row for row in (store.read_json(history_path, []) or []) if isinstance(row, dict) and row.get('project') != project['id']]
    recent = history[-MUSIC_RECENT:]
    rng = random.Random(int(hashlib.sha256(project['id'].encode()).hexdigest()[:16], 16))
    moods = [mood] if mood else list(kit['moods'])
    combos = [(st, md) for st in kit['styles'] for md in moods]
    rng.shuffle(combos)
    used = {(row.get('style'), row.get('mood')) for row in recent}
    style, chosen = ([c for c in combos if c not in used] or combos)[0]
    keys = [k for k in kit['keys'] if k != (recent[-1].get('key') if recent else None)] or list(kit['keys'])
    pick = {'style': style, 'mood': chosen, 'key': rng.choice(keys),
            'tempo': round(min(1.15, max(.85, float(kit['tempo']) + rng.uniform(-.04, .04))), 2),
            'seed': rng.randrange(1, 1_000_000)}
    if project.get('channel_id'):
        try:
            store.atomic_json(mine, pick)
            history_path.parent.mkdir(parents=True, exist_ok=True)
            store.atomic_json(history_path, (history + [{**pick, 'project': project['id']}])[-40:])
        except OSError:
            pass
    return pick


def music_arc(count: int, seed: int) -> list:
    """The intensity of each minute of the score: quiet under the start, rising to the film's own peak (somewhere past
    the middle) and settling before the end, with a little life of its own; always low enough to sit under the voice."""
    import random
    rng = random.Random(seed)
    peak = rng.uniform(.55, .8)
    low, high = rng.uniform(.24, .28), rng.uniform(.34, .40)
    out = []
    for i in range(count):
        x = (i + .5) / count
        rise = 1 - abs(x - peak) / max(peak, 1 - peak)
        out.append(round(min(.42, max(.22, low + (high - low) * rise + rng.uniform(-.02, .02))), 3))
    return out


def place(ctx, spec, *, transition=False, typing=False, drawing=False, appear=False):
    sound = sound_settings.for_project(ctx.project)
    music = spec.get('music', False)
    if type(music) is not bool:
        raise ValueError('music має бути увімкнено або вимкнено')
    cues = spec.get('cues', [])
    if not isinstance(cues, list) or len(cues) > 400:
        raise ValueError('Передайте до 400 звукових подій')
    total = max([float(f.get('end', 0)) for f in (ctx.plan or {}).get('frames', [])] +
                [float(c.get('start', 0)) + float(c.get('duration', 0)) for l in ctx.project['tracks'] for c in l['clips']] + [0])
    if not math.isfinite(total) or not .1 <= total <= 36000:
        raise ValueError('Спочатку додайте озвучку або кадри з тривалістю')
    allowed = set(sound_settings.transition_names(sound) if transition else sound_settings.allowed_names(sound))
    # the downloaded SFX belong to every project now, one SFX list with the synthesized ones (21 November 2026)
    library = {row['name']: row for row in sfx_library.catalog()} if not transition else sound_settings.capcut_transitions()
    allowed.update(sfx_library.allowed(sound) if library and not transition else [])
    # any effect of the kit stays known, so cues written with a sound that left the list still lay
    known = set(library) | {'tr_' + key for key, _ in sound_settings.TRANSITIONS} | set(sound_settings.capcut_transitions())
    is_known = lambda name: name in known or isinstance(name, str) and name in sound_settings.audio_module('sfx').LIB
    events = []
    for cue in cues:
        if not isinstance(cue, dict) or not is_known(cue.get('name')):
            raise ValueError('Невідомий звуковий ефект')
        at, duration = float(cue.get('t', 0)), float(cue.get('dur', .7))   # dur is kept for old cues; the sound plays whole
        if not math.isfinite(at) or not math.isfinite(duration) or not 0 <= at <= total - .1 or not .1 <= duration <= 6:
            raise ValueError('Невірний час звукового ефекту')
        # the studio's own passes (typing, pencil, appearances) check the channel's choice themselves and may take any
        # sound of a kind the channel allows: every pencil that writes, not only the one ticked (user, 25 November 2026:
        # «щоб не один звук там брався, що пише, а там різні звуки»)
        if cue['name'] in allowed or transition and cue.get('required') and is_known(cue['name']) \
                or (typing or drawing or appear) and cue['name'] in library:
            gain = float(cue.get('gain', -8))
            if not math.isfinite(gain) or not -60 <= gain <= 6:
                raise ValueError('Невірна гучність SFX')
            events.append({**({'gain': gain} if cue['name'] in library else {}), 'name': cue['name'], 't': round(at, 3), 'dur': min(duration, total - at),
                           **({'join': cue['join']} if transition or typing or drawing or appear else {}),
                           **({'from_start': True} if appear and cue.get('from_start') else {}),
                           **({'hit': min(float(cue['hit']), total - .05)} if transition and isinstance(cue.get('hit'), (int, float)) else {})})
    use_music = music and sound['music']['enabled'] and sound['music']['generate']
    by_title = {}
    for layer in ctx.project['tracks']:
        for c in layer['clips']:
            by_title.setdefault(c.get('title', ''), c)
    existing = set(by_title)
    existing.update(a['payload'].get('title', '') for a in ctx.actions if a['type'] == 'add_clip')
    if any(c.get('kind') == 'audio' and ('муз' in c.get('title', '').lower() or 'music' in c.get('title', '').lower())
           for layer in ctx.project['tracks'] for c in layer['clips']):
        use_music = False
    if getattr(ctx, 'dry_run', False):
        ctx.report.append(f'звук: музика {int(use_music)}, дозволених подій {len(events)}')
        return
    folder = store.media_dir(ctx.project) / 'soundtrack'
    folder.mkdir(parents=True, exist_ok=True)
    anchor = ctx.project['tracks'][0]['id']

    assets = {}

    def add(path, title, start, duration, volume):
        if title in existing:
            old = by_title.get(title)
            if not (transition or typing or drawing or appear) or old is None or (abs(float(old['start']) - start) < .001 and abs(float(old['duration']) - duration) < .001):
                # music laid before the measured level gets the measured one on the next pass
                if old is not None and title.startswith(PREFIX + 'музика') and abs(float(old.get('volume', 1)) - volume) > .005:
                    ctx.actions.append({'type': 'set_clip_volume', 'payload': {'clip_id': old['id'], 'volume': volume}})
                return
            ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': old['id']}})
        if path not in assets:
            assets[path] = store.asset_record(path, ctx.project['id'])['id'] if path in getattr(ctx, 'files', []) else ctx.asset_for(path)
        ctx.actions.append({'type': 'add_clip', 'payload': {'layer_id': anchor, 'kind': 'audio', 'title': title,
                            'asset_id': assets[path], 'start': start, 'duration': duration, 'volume': volume}})
        existing.add(title)

    if use_music:
        module = sound_settings.audio_module('music')
        if spec.get('mood') is not None and spec['mood'] not in module.MOODS:
            raise ValueError('Невідомий настрій музики')
        pick = music_pick(ctx.project, module, spec.get('mood'))
        # One piece over the whole film (user, 21 November 2026: «чому музика порізана… це ж має бути одна»): a new
        # section about every minute, crossfaded inside the score with its own seed; its intensity rises and falls like a
        # story with its own peak (music_arc), so no two films share one curve
        count = max(1, math.ceil(total / 60.0))
        step = total / count
        arc = music_arc(count, pick['seed'])
        plan = [{'start': i * step, 'end': (i + 1) * step, 'mood': pick['mood'], 'intensity': arc[i]} for i in range(count)]
        # FLAC: the same samples in about half the space of the WAV (262 MB for a 24-minute film before)
        path = folder / f"music-v4-{pick['style']}-{pick['mood']}-{pick['key']}-{pick['tempo']}-{pick['seed']}-{total:.3f}.flac"
        with sound_settings.LOCK:
            if not path.exists():
                samples = module.render_score(plan, total, seed=pick['seed'], key=pick['key'], tempo=pick['tempo'], style=pick['style'])
                wav = path.with_suffix('.pending.wav')
                module.write_wav(str(wav), samples[:module.secs(total)])
                del samples
                try:
                    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(wav), '-c:a', 'flac', '-compression_level', '8',
                                    str(path.with_suffix('.pending.flac'))], check=True, capture_output=True, timeout=600)
                    path.with_suffix('.pending.flac').replace(path)
                finally:
                    wav.unlink(missing_ok=True)
                    path.with_suffix('.pending.flac').unlink(missing_ok=True)
        ctx.report.append(f"музика: {pick['style']}, {pick['mood']}, тональність {pick['key']}, темп ×{pick['tempo']}")
        add(path, PREFIX + 'музика', 0.0, total, music_volume(path))
    for cue in events:
        key = hashlib.sha256(json.dumps(cue, sort_keys=True).encode()).hexdigest()[:16]
        row = library.get(cue['name'])
        if row:
            path, measured = _library_copy(folder, row)   # levelled and at most 4 s, like the synthesized ones
        else:
            path = measured = folder / f'sfx-v5-{cue["name"]}.wav'
            with sound_settings.LOCK:
                if not path.exists():
                    module = sound_settings.audio_module('sfx')
                    module.write_wav(str(path), full_take(module, cue['name'])[0])
        # the whole file, never shorter: only the film's own end can stop it
        length = float(row['duration_seconds']) if row else (store.media_duration(path) or cue['dur'])
        title = (TRANSITION_PREFIX + cue['join'] + ' · ' + cue['name'] if transition else
                 TYPING_PREFIX + cue['join'] + ' · ' + (row['label'] if row else cue['name']) if typing else
                 DRAWING_PREFIX + cue['join'] + ' · ' + (row['label'] if row else cue['name']) if drawing else
                 APPEAR_PREFIX + cue['join'] + ' · ' + (row['label'] if row else cue['name']) if appear else
                 SFX_PREFIX + row['label'] + ' ' + key if row else SFX_PREFIX + cue['name'] + ' ' + key)
        if not row and not transition and not typing and not drawing and not appear:
            # the same cue laid before under its old name, cut to 0.7 s, goes: the whole one takes its place
            for layer in ctx.project['tracks']:
                for clip in layer['clips']:
                    if clip.get('title') == PREFIX + cue['name'] + ' ' + key:
                        ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': clip['id']}})
        # the loudest moment of the sound lands on its event (user, 21 November 2026: «переходи часто не в момент
        # переходів»): on a seam, the middle of the transition; on any other cue, the cue's own time
        # typing has no single peak: it starts with the first letter
        hit = cue['t'] if typing or drawing or cue.get('from_start') else (cue['hit'] if 'hit' in cue else cue['t'] + (cue['dur'] / 2 if transition else 0)) - _peak(measured)
        start = round(max(0.0, min(hit, total - .1)), 3)
        add(path, title, start, max(.1, min(length, total - start)), min(1.5, SFX_VOLUME * 10 ** ((cue.get('gain', -8) + 8) / 20)))
    ctx.report.append(f'звук: музика {int(use_music)}, дозволених подій {len(events)}')


def transition_hit(kind: str) -> float:
    import joins
    return joins.transition_hit(kind)


def transitions(ctx, spec=None):
    """Choose restrained sound accents for designed joins in universal projects only."""
    if store.project_animated(ctx.project) or sound_settings.saved_for_project(ctx.project) is None:
        return
    settings = sound_settings.for_project(ctx.project)
    pool = sound_settings.transition_names(settings)
    spec = spec or {}
    scope = spec.get('frames')
    scoped_labels = set()
    wanted_frames = spec.get('sound_frames')
    if wanted_frames is not None and (not isinstance(wanted_frames, list) or any(type(n) is not int for n in wanted_frames)):
        raise ValueError('sound_frames має містити номери кадрів')
    joins = {(j['from_ref'], j['to_ref']): j for j in ctx.project.get('join_transitions', [])}
    for action in ctx.actions:
        if action['type'] == 'set_join_transition':
            p = action['payload']; key = (p['from_ref'], p['to_ref'])
            if p['type'] == 'cut': joins.pop(key, None)
            else: joins[key] = p
    # Every transition of the film has its sound, and one kind of transition always the same sound through the film
    # (user, 25 November 2026: «звуки мають дорівнювати цим переходам завжди на протязі цілого ролика… якщо в ролику є
    # якийсь перехід, то в нього є свій звук… любого переходу»). A sound only where a transition really is: a cut has none,
    # the host's and a text frame's way out included (user, 25 November 2026: «озвучку переходів ставити там, де дійсно
    # переход»); their way out always has a transition anyway (montage_ops._host_or_text).
    sounds = list(pool) or ['tr_snap', 'tr_air', 'tr_silk']
    seams, kinds = [], []
    for a, b in zip(ctx.frames, ctx.frames[1:]):
        key = ('group:' + a['group']['id'], 'group:' + b['group']['id'])
        join = joins.get(key)
        # into the host no sound: the host's transitions sound only where he goes out (user, 25 November 2026: «для хейгена
        # лише для аута. Для іна не став звуковий ефект»; «in переход має бути обов'язковий. Просто що без озвучки»)
        if (b.get('plan') or {}).get('format') == 'host' and (a.get('plan') or {}).get('format') not in ('host', 'text'):
            continue
        if not join or join.get('type') == 'cut':
            continue
        seams.append((a, b, join))
        if join['type'] not in kinds:
            kinds.append(join['type'])
    # the order of first appearance in the whole film, so a scoped run gives a seam the same sound as the full one; each kind
    # takes a sound of its own character (a glitch a glitch, a dissolve a soft one), the kinds of one character in turn
    sound_of, taken = {}, {}
    for kind in kinds:
        character = 'flash' if kind == 'cut' else sound_settings.transition_character(kind)
        fitting = sound_settings.sounds_for(character, list(pool)) or sounds
        sound_of[kind] = fitting[taken.get(character, 0) % len(fitting)]
        taken[character] = taken.get(character, 0) + 1
    events, wanted = [], set()
    for a, b, join in seams:
        label = f'{a["number"]} → {b["number"]}'
        if scope is not None:
            if b['number'] not in scope:
                continue
            scoped_labels.add(label)
        name = sound_of[join['type']]
        length = float(join.get('duration', .35))
        # the sound's loudest moment lands on the transition's own hit (its flash, jolt or switch, measured on its video:
        # TRANSITION_HITS), inside the transition's real window, which ends on the seam for a video with no tail
        # (user, 25 November 2026: «звук підставляється неточно… то лівіше, то правіше»); a cut sounds on the seam
        import joins as joins_module
        ahead = joins_module.lead_seconds(ctx.project, {**join, 'seam': b['start']}) if join.get('type') != 'cut' else 0.0
        begin = b['start'] - ahead
        hit = b['start'] if join.get('type') == 'cut' else begin + length * transition_hit(join['type'])
        events.append({'name': name, 't': round(max(0.0, begin), 3), 'dur': max(.1, min(.7, length)), 'join': label,
                       'required': True, 'hit': round(max(0.0, hit), 3)})
        wanted.add(TRANSITION_PREFIX + label + ' · ' + name)
    for layer in ctx.project['tracks']:
        for clip in layer['clips']:
            title = clip.get('title','')
            if scope is not None:
                # a seam into a frame of the scope: its sound goes with its transition, even when that became a cut
                label = title.removeprefix(TRANSITION_PREFIX).split(' · ', 1)[0]
                try:
                    into = int(label.split(' → ')[1])
                except (IndexError, ValueError):
                    into = None
                if label not in scoped_labels and into not in scope:
                    continue
            if title.startswith(TRANSITION_PREFIX) and title not in wanted:
                ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': clip['id']}})
    place(ctx, {'cues': events}, transition=True)


TYPING_GAIN = -12   # the keys sit under the voice, quieter than an accent


WORD_GAP = 1.0      # seconds between two words that end one run of writing and start another
LAST_WORD = .45     # how long the last word of a run is written when its end is not known


def writing_runs(words, begin: float) -> list:
    """[(start, end)] of the stretches in which words keep coming, each from its first word to the end of its last."""
    rows = sorted((begin + float(w.get('start', 0)), begin + float(w['end']) if w.get('end') is not None else None) for w in words)
    runs = []
    for at, end in rows:
        stop = end if end is not None and end > at else at + LAST_WORD
        if runs and at - runs[-1][1] <= WORD_GAP:
            runs[-1][1] = max(runs[-1][1], stop)
        else:
            runs.append([at, stop])
    return [tuple(r) for r in runs]


def chain(pool, start: float, length: float, used: dict, last=None) -> tuple:
    """Sounds one after another from `start` that fill `length`, each whole (never cut): a long writing gets a long sound,
    or several different ones in a row (user, 25 November 2026: «якщо довго пише, то довго звук… щоб не один звук там
    брався… а різні звуки»). The least used sound that still fits goes first, never the same twice in a row."""
    out, t, rest = [], start, length
    while rest > .3:
        others = [s for s in pool if s[0] != last] or list(pool)
        fit = [s for s in others if s[1] <= rest + .35]
        if not fit:
            if out:
                break
            fit = [min(others, key=lambda s: (s[1], s[0]))]
        name, seconds = min(fit, key=lambda s: (used.get(s[0], 0), -s[1], s[0]))
        out.append((name, round(t, 3), seconds))
        used[name] = used.get(name, 0) + 1
        last, t, rest = name, t + seconds, rest - seconds
    return out, last


LETTER_ENTRANCES = ('letters_fade', 'letters_up', 'letters_blur')   # entrances that type a text letter by letter
KEYS_DELAY = .2   # seconds after the first letter the keys start: they followed the letters a moment too early


def typing(ctx, spec=None):
    """A typing sound under every text typed letter by letter and a pencil under every text written word by word or by
    motion code (user, 25 November 2026: «якщо ми друкуємо текст… озвучка має бути друкування тексту», «часто щось
    пишуть, і там нема… звука писання»): for as long as the words keep coming, different sounds one after another, each
    whole, two texts never sounding over each other. Only where the channel's sound settings allow such a sound;
    otherwise the old ones go."""
    if store.project_animated(ctx.project) or sound_settings.saved_for_project(ctx.project) is None:
        return
    spec = spec or {}
    scope = spec.get('frames')
    keys, pencils = typing_pool(ctx), writing_pool(ctx)
    events, wanted = [], set()
    total = max([float(f['end']) for f in ctx.frames] + [0])
    runs = []
    for frame in ctx.frames if (keys or pencils) else []:
        if frame.get('number') is None or scope is not None and frame['number'] not in scope:
            continue
        for clip in frame['clips']:
            entrance = (clip.get('word_entrance') or {}).get('type', '')
            # keys only under a text that comes in letter by letter, a little after its first letter; a text that
            # comes in word by word or whole is not typed and has no keys (user, 26 November 2026: «клацання
            # клавіатурою… засильно рано… Там воно не друкується. Коли по буквах появляється, тоді да. Але трошки з
            # затримкою»); a pencil only where a hand, a pen or chalk writes on screen
            if clip.get('kind') == 'text' and clip.get('text_words'):
                if entrance not in LETTER_ENTRANCES:
                    continue
                words, pool = clip['text_words'], keys
            elif clip.get('content_type') == 'code' and clip.get('code_words') and HAND.search(str(clip.get('code') or '')):
                # code_words are the voice's words the code times itself by; only those it really writes on screen (its
                # own quoted text) sound like writing (Andromeda 118, 25 November 2026)
                words, pool = written_words(clip), pencils
            else:
                continue
            if not pool:
                continue
            begin, end = float(clip['start']), min(float(clip['start']) + float(clip['duration']), total - .1)
            for a, b in writing_runs(words, begin):
                if begin <= a < end:
                    # the keys follow the letters a moment behind, the whole run shifted (user, 26 November 2026)
                    lag = KEYS_DELAY if pool is keys else 0.0
                    runs.append((a + lag, min(b + lag, end), pool, frame['number']))
    used, busy, last = {}, -1.0, None
    for a, b, pool, number in sorted(runs, key=lambda r: r[0]):
        a = max(a, busy)
        if b - a < .3:
            continue
        sounds, last = chain(pool, a, b - a, used, last)
        for name, at, seconds in sounds:
            label = f"K{number:03d} {at:.2f}"
            events.append({'name': name, 't': at, 'dur': max(.1, min(seconds, 6.0)), 'join': label, 'gain': TYPING_GAIN})
            row = sfx_library.find(name)
            wanted.add(TYPING_PREFIX + label + ' · ' + (row['label'] if row else name))
            busy = at + seconds
    for layer in ctx.project['tracks']:
        for clip in layer['clips']:
            title = clip.get('title', '')
            if not title.startswith(TYPING_PREFIX) or title in wanted:
                continue
            if scope is not None:
                try:
                    if int(title.removeprefix(TYPING_PREFIX)[1:4]) not in scope:
                        continue
                except ValueError:
                    continue
            ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': clip['id']}})
    if events:
        place(ctx, {'cues': events}, typing=True)
    else:
        ctx.report.append('звук друку: ' + ('немає тексту, що друкується' if keys or pencils else 'вимкнено в налаштуваннях звуку каналу'))


def _plain(word: str) -> str:
    return re.sub(r'[^\w]+', '', str(word).lower().replace('ё', 'е'))


def written_words(clip) -> list:
    """The words of a motion-code clip that its code writes: a spoken word found in the code's own quoted text."""
    code = str(clip.get('code') or clip.get('motion_code') or '')
    if not re.search(r'fillText|strokeText', code):
        return []
    quoted = ' '.join(_plain(q) for q in re.findall(r"'([^'\n]*)'|\"([^\"\n]*)\"|`([^`\n]*)`", code) for q in q if q)
    return [w for w in clip.get('code_words') or [] if len(_plain(w.get('text', ''))) > 2 and _plain(w.get('text', '')) in quoted]


def _kind(row) -> str:
    return sound_settings.OLD_CATEGORIES.get(row['category'], row['category'])


# code that shows a pen, a pencil, chalk or a quill writing or drawing: only there a written text sounds like a pencil.
# The tool and the writing come together (Andromeda 23: «the hand with a dip pen writes the next rows»); a bare «hand»
# is a camera's shake or an arm laid along a gap, a bare «marker» a point on a map
TOOL = r'(?<![a-z])(?:pens?|pencils?|chalk|quill|stylus|nib)(?![a-z])|олів|крейд|ручк|перо(?![а-я])'
VERB = r'writ|draw|scribbl|пиш|пише|напис|малю'
HAND = re.compile(rf'(?:{TOOL})[^\n]{{0,60}}(?:{VERB})|(?:{VERB})[^\n]{{0,60}}(?:{TOOL})', re.I)


WRITES = re.compile(r'пише|write|writing|запис|штрих|шкряб|scratch', re.I)
NOT_WRITING = re.compile(r'коло|circle|трикутник|triangle|хрестик|cross|пряма|straight|округла|round|зафарбов|paint|риска', re.I)


def writing_pool(ctx) -> list:
    """Every pencil of the library that writes, (name, seconds) each, when the channel allows a pencil sound at all."""
    if not drawing_sounds(ctx):
        return []
    return sorted((r['name'], float(r['duration_seconds'])) for r in sfx_library.catalog()
                  if _kind(r) == 'drawing' and WRITES.search(f"{r['label']} {r.get('original_title') or ''}")
                  and not NOT_WRITING.search(f"{r['label']} {r.get('original_title') or ''}"))


def typing_pool(ctx) -> list:
    """Every keyboard of the library, when the channel allows a typing sound; else the synthesized one."""
    sound = sound_settings.for_project(ctx.project)
    if not sound['effects']['enabled'] and 'library' not in sound:
        return []
    allowed = set(sfx_library.allowed(sound))
    rows = [r for r in sfx_library.catalog() if _kind(r) == 'typing']
    if any(r['name'] in allowed for r in rows):
        return sorted((r['name'], float(r['duration_seconds'])) for r in rows)
    if 'typing' in sound_settings.allowed_names(sound):
        return [('typing', full_take(sound_settings.audio_module('sfx'), 'typing')[1])]
    return []


DRAWN = {"стрілка", "коло", "риска"}   # accents that are drawn on screen: an arrow grows, a ring is traced, a line is drawn


def drawing_sounds(ctx) -> list:
    """The channel's pencil sounds (category «drawing»), when its SFX allow them: (name, seconds) each."""
    sound = sound_settings.for_project(ctx.project)
    names = set(sfx_library.allowed(sound))
    return [(r['name'], float(r['duration_seconds'])) for r in sfx_library.catalog()
            if r['name'] in names and sound_settings.OLD_CATEGORIES.get(r['category'], r['category']) == 'drawing']


def drawing(ctx, spec=None):
    """A pencil under every accent that is drawn (user, 25 November 2026: «звук писання олівця на дошці… включив теж
    додай де треба його»): from its first moment, the pencil sound closest to the drawing's length, played whole. Only
    where the channel's sound settings allow the pencil; otherwise the old ones go."""
    if store.project_animated(ctx.project) or sound_settings.saved_for_project(ctx.project) is None:
        return
    import montage_ops
    spec = spec or {}
    scope = spec.get('frames')
    sounds = drawing_sounds(ctx)
    events, wanted = [], set()
    total = max([float(f['end']) for f in ctx.frames] + [0])
    for frame in ctx.frames if sounds else []:
        if frame.get('number') is None or scope is not None and frame['number'] not in scope:
            continue
        for clip in frame['clips']:
            if not montage_ops.is_entrance(clip) or montage_ops.accent_kind(clip) not in DRAWN:
                continue
            at, length = float(clip['start']), float(clip['duration'])
            if not 0 <= at < total - .1:
                continue
            name, seconds = min(sounds, key=lambda s: (abs(s[1] - length), s[0]))
            label = f"K{frame['number']:03d} {at:.2f}"
            events.append({'name': name, 't': round(at, 3), 'dur': max(.1, min(seconds, 4.0)), 'join': label, 'gain': TYPING_GAIN})
            row = sfx_library.find(name)
            wanted.add(DRAWING_PREFIX + label + ' · ' + (row['label'] if row else name))
    for layer in ctx.project['tracks']:
        for clip in layer['clips']:
            title = clip.get('title', '')
            if not title.startswith(DRAWING_PREFIX) or title in wanted:
                continue
            if scope is not None:
                try:
                    if int(title.removeprefix(DRAWING_PREFIX)[1:4]) not in scope:
                        continue
                except ValueError:
                    continue
            ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': clip['id']}})
    if events:
        place(ctx, {'cues': events}, drawing=True)
    else:
        ctx.report.append('звук олівця: ' + ('немає акцентів, що малюються' if sounds else 'вимкнено в налаштуваннях звуку каналу'))


# ---------------------------------------------------------------------------------------------------------------------
# Sounds on what really comes on screen in Razgon frames (user, 25 November 2026: «появляється щось, звук появляється
# відповідний… щось пише, появляється звук, типу, що пише щось»). The events are read from the scenes' own drawing
# (razgon render.mjs --events, backend/event_sounds.py), not guessed by an agent: a line of text that comes in, a picture
# that comes in, a text written letter by letter for as long as it is written.
APPEAR_GAP = 1.2        # seconds between two appearance sounds: a scene that brings in five labels does not rattle
NEAR_OTHER = .5          # no appearance sound this close to a transition, typing or an agent's own effect
APPEAR_GAIN = {'text': -16, 'picture': -14}
COMIC = re.compile(r'кумедн|діти|павич|губ|парасольк|ура|лампочк|funny|kids|peacock|lips|umbrella', re.I)
TEXT_KINDS = ('appear', 'glint', 'click', 'tick')
# a line of text that comes in is not a mouse, a key or a menu: those sounds stay for scenes about such devices
DEVICE = re.compile(r'миш|mouse|механічн|mechanical|меню|menu|клік-клік|клавіш|keyboard|клацання|snap|вибір|select', re.I)
PICTURE_KINDS = ('swoosh_in', 'whoosh', 'swish', 'movement')


def appear_pools(ctx) -> dict:
    """{'text': [...], 'picture': [...], 'write': [...]}: the channel's own sounds of each kind, (name, seconds) each."""
    sound = sound_settings.for_project(ctx.project)
    allowed = set(sfx_library.allowed(sound))
    rows = [r for r in sfx_library.catalog() if r['name'] in allowed and not COMIC.search(f"{r['label']} {r.get('original_title') or ''}")]
    pick = lambda kinds, longest, extra=None: sorted((r['name'], float(r['duration_seconds'])) for r in rows
                                                     if (_kind(r) in kinds or extra and extra.search(r['label'])) and float(r['duration_seconds']) <= longest
                                                     and not (kinds is TEXT_KINDS and DEVICE.search(f"{r['label']} {r.get('original_title') or ''}")))
    # a text written letter by letter is a keyboard; a pencil only when a hand or a pen writes it on screen
    return {'text': pick(TEXT_KINDS, 1.6, re.compile(r'^Поява', re.I)), 'picture': pick(PICTURE_KINDS, 1.8), 'write': typing_pool(ctx),
            'hand': writing_pool(ctx)}


def razgon_blocks(ctx) -> list:
    """(frame number, start, end) of every frame drawn by Razgon code on this timeline."""
    out = []
    for frame in ctx.frames:
        if frame.get('number') is None:
            continue
        if any(str(c.get('title', '')).startswith('Razgon · кадр') for c in frame['clips']):
            out.append((frame['number'], float(frame['start']), float(frame['end'])))
    return out


def appear(ctx, spec=None):
    """Lay a sound on every event of the Razgon frames: {'events': [{'t', 'kind': 'text'|'picture'|'write', 'dur'}],
    'frames': [numbers]} (the scope; without it the whole film). Old appearance sounds of the scope go first."""
    if store.project_animated(ctx.project) or sound_settings.saved_for_project(ctx.project) is None:
        return
    spec = spec or {}
    scope = spec.get('frames')
    raw = spec.get('events') or []
    if not isinstance(raw, list) or len(raw) > 6000:
        raise ValueError('Передайте до 6000 подій')
    blocks = [b for b in razgon_blocks(ctx) if scope is None or b[0] in scope]
    pools = appear_pools(ctx)
    # what already sounds there: a transition, a typing or pencil run, an agent's own effect (start, end of its body)
    others = [(float(c['start']), float(c['start']) + min(float(c['duration']), 1.5)) for layer in ctx.project['tracks'] for c in layer['clips']
              if c.get('kind') == 'audio' and str(c.get('title', '')).startswith((TRANSITION_PREFIX, SFX_PREFIX, TYPING_PREFIX, DRAWING_PREFIX))]
    near = lambda t: any(a - NEAR_OTHER <= t <= b for a, b in others)
    cues, wanted, used, last = [], set(), {}, {}
    busy, previous = -1.0, -9.0
    for event in sorted((e for e in raw if isinstance(e, dict)), key=lambda e: float(e.get('t', 0))):
        t, kind = float(event.get('t', 0)), event.get('kind')
        if not math.isfinite(t) or kind not in ('text', 'picture', 'write'):
            continue
        frame = next((b for b in blocks if b[1] + .15 <= t <= b[2] - .15), None)
        if frame is None or kind != 'write' and not pools[kind]:
            continue
        if kind == 'write':
            pool = 'hand' if event.get('hand') and pools['hand'] else 'write'
            if not pools[pool]:
                continue
            # a text the scan saw grow letter by letter is typed: its keys come a little after the first letter
            start = t + (KEYS_DELAY if pool == 'write' else 0.0)
            a = max(start, busy)
            length = min(start + float(event.get('dur', 0) or 0) - a, frame[2] - a)
            if length < .3:
                continue
            sounds, last[pool] = chain(pools[pool], a, length, used, last.get(pool))
            for name, at, seconds in sounds:
                label = f"K{frame[0]:03d} {at:.2f}"
                cues.append({'name': name, 't': at, 'dur': max(.1, min(seconds, 6.0)), 'join': label, 'gain': TYPING_GAIN, 'from_start': True})
                busy = at + seconds
            previous = t
            continue
        if t - previous < APPEAR_GAP or t < busy or near(t):
            continue
        pool = [s for s in pools[kind] if s[0] != last.get(kind)] or pools[kind]
        name, seconds = min(pool, key=lambda s: (used.get(s[0], 0), s[0]))
        used[name] = used.get(name, 0) + 1
        last[kind], previous = name, t
        cues.append({'name': name, 't': round(t, 3), 'dur': max(.1, min(seconds, 6.0)), 'join': f"K{frame[0]:03d} {t:.2f}", 'gain': APPEAR_GAIN[kind]})
    if spec.get('prune_guessed'):
        # an agent's own effect inside a Razgon frame whose loudest moment falls on no event of the picture was guessed:
        # it goes (user, 25 November 2026: «щоб все відповідало дійсно тому, що треба»); one on a real event stays
        moments = [float(e.get('t', 0)) for e in raw if isinstance(e, dict)]
        rows = {r['mixkit_id']: r for r in sfx_library.catalog()}
        for layer in ctx.project['tracks']:
            for clip in layer['clips']:
                if clip.get('kind') != 'audio' or not str(clip.get('title', '')).startswith(SFX_PREFIX):
                    continue
                try:
                    path = store.resolve_asset(ctx.project, clip['asset_id'])['path']
                except (store.StudioError, OSError, KeyError, ValueError):
                    continue
                # only sounds of appearing: an impact or a move is a physical event the scan does not see
                found = re.search(r'mixkit-(\d+)-', Path(path).name)
                row = rows.get(found.group(1)) if found else None
                if row is None or _kind(row) not in TEXT_KINDS + PICTURE_KINDS[:3] + ('drawing', 'typing', None):
                    continue
                try:
                    peak = float(clip['start']) + _peak(path)
                except (OSError, ValueError):
                    continue
                if any(b[1] <= peak <= b[2] for b in blocks) and not any(abs(peak - m) <= .5 for m in moments):
                    ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': clip['id']}})
                    ctx.report.append(f"прибрано вгаданий звук «{clip.get('title')}» на {peak:.1f} с: там нічого не з'являється")
    for cue in cues:
        row = sfx_library.find(cue['name'])
        wanted.add(APPEAR_PREFIX + cue['join'] + ' · ' + (row['label'] if row else cue['name']))
    for layer in ctx.project['tracks']:
        for clip in layer['clips']:
            title = clip.get('title', '')
            if not title.startswith(APPEAR_PREFIX) or title in wanted:
                continue
            if scope is not None:
                try:
                    if int(title.removeprefix(APPEAR_PREFIX)[1:4]) not in scope:
                        continue
                except ValueError:
                    continue
            ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': clip['id']}})
    if cues:
        place(ctx, {'cues': cues}, appear=True)
    ctx.report.append(f'звуки появи: {len(cues)} з {len(raw)} подій')

