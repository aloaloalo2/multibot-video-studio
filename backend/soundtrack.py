"""Place a locally synthesized soundtrack through ordinary, undoable timeline actions."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

import sound_settings
import sfx_library
import store

PREFIX = 'Звук ролика · '
TRANSITION_PREFIX = 'Звук переходу · '


def place(ctx, spec, *, transition=False):
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
    library = {row['name']: row for row in sfx_library.catalog()} if store.project_animated(ctx.project) and not transition else {}
    allowed.update(sfx_library.allowed(sound) if library else [])
    known = set(library) | {name for _, _, names in sound_settings.CATEGORIES for name in names} | {'tr_' + key for key, _ in sound_settings.TRANSITIONS}
    events = []
    for cue in cues:
        if not isinstance(cue, dict) or cue.get('name') not in known:
            raise ValueError('Невідомий звуковий ефект')
        at, duration = float(cue.get('t', 0)), float(cue.get('dur', .7))
        if not math.isfinite(at) or not math.isfinite(duration) or not 0 <= at <= total - .1 or not .1 <= duration <= 6:
            raise ValueError('Невірний час звукового ефекту')
        if cue['name'] in allowed:
            gain = float(cue.get('gain', -8))
            if not math.isfinite(gain) or not -60 <= gain <= 6:
                raise ValueError('Невірна гучність SFX')
            events.append({**({'gain': gain} if cue['name'] in library else {}), 'name': cue['name'], 't': round(at, 3), 'dur': min(duration, total - at),
                           **({'join': cue['join']} if transition else {})})
    use_music = music and sound['music']['enabled'] and sound['music']['generate']
    existing = {c.get('title', '') for layer in ctx.project['tracks'] for c in layer['clips']}
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
            old = next((c for layer in ctx.project['tracks'] for c in layer['clips'] if c.get('title') == title), None)
            if not transition or old is None or (abs(float(old['start']) - start) < .001 and abs(float(old['duration']) - duration) < .001):
                return
            ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': old['id']}})
        if path not in assets:
            assets[path] = store.asset_record(path, ctx.project['id'])['id'] if path in getattr(ctx, 'files', []) else ctx.asset_for(path)
        ctx.actions.append({'type': 'add_clip', 'payload': {'layer_id': anchor, 'kind': 'audio', 'title': title,
                            'asset_id': assets[path], 'start': start, 'duration': duration, 'volume': volume}})
        existing.add(title)

    if use_music:
        module = sound_settings.audio_module('music')
        mood = spec.get('mood', 'calm')
        if mood not in module.MOODS:
            raise ValueError('Невідомий настрій музики')
        # Bounded memory and reusable material, even for an hour-long film.
        count = max(1, math.ceil(total / 60.0))
        length = max(4.0, total / count)
        path = folder / f'music-v1-{mood}-{length:.3f}.wav'
        with sound_settings.LOCK:
            if not path.exists():
                samples = module.render_score([{'start': 0, 'end': length, 'mood': mood, 'intensity': .3}], length, seed=7)
                module.write_wav(str(path), samples[:module.secs(length)])
        for index in range(count):
            at = index * length
            add(path, PREFIX + f'музика {index + 1}', at, min(length, total - at), .35)
    module = sound_settings.audio_module('sfx') if any(c['name'] not in library for c in events) else None
    for cue in events:
        key = hashlib.sha256(json.dumps(cue, sort_keys=True).encode()).hexdigest()[:16]
        row = library.get(cue['name'])
        if row:
            source = Path(row['name'])
            path = folder / ('mixkit-' + row['mixkit_id'] + '-' + hashlib.sha256(source.read_bytes()).hexdigest()[:12] + '.wav')
            if not path.exists():
                shutil.copy2(source, path)
        else:
            path = folder / f'sfx-v1-{cue["name"]}-{cue["dur"]:.3f}.wav'
            with sound_settings.LOCK:
                if not path.exists():
                    module.write_wav(str(path), module.make(cue['name'], dur=cue['dur'], seed=7))
        title = (PREFIX + 'SFX · ' + row['label'] + ' ' + key) if row else (TRANSITION_PREFIX + cue['join'] + ' · ' + cue['name'] if transition else PREFIX + cue['name'] + ' ' + key)
        add(path, title, cue['t'], min(cue['dur'], row['duration_seconds']) if row else cue['dur'], min(1.5, .12 * 10 ** ((cue.get('gain', -8) + 8) / 20)))
    ctx.report.append(f'звук: музика {int(use_music)}, дозволених подій {len(events)}')


def transitions(ctx, spec=None):
    """Choose restrained sound accents for designed joins in universal projects only."""
    if store.project_animated(ctx.project) or sound_settings.saved_for_project(ctx.project) is None:
        return
    settings = sound_settings.for_project(ctx.project)
    pool = sound_settings.transition_names(settings)
    spec = spec or {}
    wanted_frames = spec.get('sound_frames')
    if wanted_frames is not None and (not isinstance(wanted_frames, list) or any(type(n) is not int for n in wanted_frames)):
        raise ValueError('sound_frames має містити номери кадрів')
    joins = {(j['from_ref'], j['to_ref']): j for j in ctx.project.get('join_transitions', [])}
    for action in ctx.actions:
        if action['type'] == 'set_join_transition':
            p = action['payload']; key = (p['from_ref'], p['to_ref'])
            if p['type'] == 'cut': joins.pop(key, None)
            else: joins[key] = p
    events, wanted, previous = [], set(), None
    limit = max(1, math.ceil(len(joins) * .4))
    for a, b in zip(ctx.frames, ctx.frames[1:]):
        key = ('group:' + a['group']['id'], 'group:' + b['group']['id'])
        join = joins.get(key)
        if not join or not pool:
            continue
        kind = join['type']
        if wanted_frames is not None:
            if b['number'] not in wanted_frames: continue
        elif kind == 'crossfade' or len(events) >= limit or (events and b['start'] - events[-1]['t'] < 8):
            continue
        preferred = (['tr_warp', 'tr_bass', 'tr_rise', 'tr_reverse'] if 'zoom' in kind else
                     ['tr_air', 'tr_whip', 'tr_sweep', 'tr_down', 'tr_silk'] if 'slide' in kind else
                     ['tr_silk', 'tr_shimmer', 'tr_air'] if kind == 'crossfade' else
                     ['tr_neon', 'tr_glitch', 'tr_pixel', 'tr_camera', 'tr_snap'])
        choices = [name for name in preferred if name in pool] or pool
        different = [name for name in choices if name != previous] or [name for name in pool if name != previous]
        choices = different or choices
        name = choices[len(events) % len(choices)]
        label = f'{a["number"]} → {b["number"]}'
        events.append({'name': name, 't': b['start'], 'dur': max(.1, min(.7, float(join.get('duration', .35)))), 'join': label})
        wanted.add(TRANSITION_PREFIX + label + ' · ' + name)
        previous = name
    for layer in ctx.project['tracks']:
        for clip in layer['clips']:
            if clip.get('title', '').startswith(TRANSITION_PREFIX) and clip['title'] not in wanted:
                ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': clip['id']}})
    place(ctx, {'cues': events}, transition=True)
