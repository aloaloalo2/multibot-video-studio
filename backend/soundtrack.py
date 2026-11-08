"""Place a locally synthesized soundtrack through ordinary, undoable timeline actions."""
from __future__ import annotations

import hashlib
import json
import math

import sound_settings
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
    allowed = set(sound_settings.allowed_names(sound))
    known = {name for _, _, names in sound_settings.CATEGORIES for name in names}
    events = []
    for cue in cues:
        if not isinstance(cue, dict) or cue.get('name') not in known:
            raise ValueError('Невідомий звуковий ефект')
        at, duration = float(cue.get('t', 0)), float(cue.get('dur', .7))
        if not math.isfinite(at) or not math.isfinite(duration) or not 0 <= at <= total - .1 or not .1 <= duration <= 6:
            raise ValueError('Невірний час звукового ефекту')
        if cue['name'] in allowed:
            events.append({'name': cue['name'], 't': round(at, 3), 'dur': min(duration, total - at),
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
    module = sound_settings.audio_module('sfx') if events else None
    for cue in events:
        key = hashlib.sha256(json.dumps(cue, sort_keys=True).encode()).hexdigest()[:16]
        path = folder / f'sfx-v1-{cue["name"]}-{cue["dur"]:.3f}.wav'
        with sound_settings.LOCK:
            if not path.exists():
                module.write_wav(str(path), module.make(cue['name'], dur=cue['dur'], seed=7))
        title = TRANSITION_PREFIX + cue['join'] + ' · ' + cue['name'] if transition else PREFIX + cue['name'] + ' ' + key
        add(path, title, cue['t'], cue['dur'], .12)
    ctx.report.append(f'звук: музика {int(use_music)}, дозволених подій {len(events)}')


def transitions(ctx):
    """Sound follows actual designed joins; repeating this operation leaves existing matching cues in place."""
    if sound_settings.saved_for_project(ctx.project) is None:
        return
    settings = sound_settings.for_project(ctx.project)
    allowed = set(sound_settings.allowed_names(settings))
    pool = [name for name in ('whoosh', 'swish', 'flash', 'blip', 'tick', 'pop', 'ding', 'counter',
                             'shimmer', 'hit', 'impact', 'glitch', 'powerup', 'freeze', 'riser') if name in allowed]
    joins = {(j['from_ref'], j['to_ref']): j for j in ctx.project.get('join_transitions', [])}
    for action in ctx.actions:
        if action['type'] == 'set_join_transition':
            p = action['payload']; key = (p['from_ref'], p['to_ref'])
            if p['type'] == 'cut': joins.pop(key, None)
            else: joins[key] = p
    events, wanted = [], set()
    for a, b in zip(ctx.frames, ctx.frames[1:]):
        key = ('group:' + a['group']['id'], 'group:' + b['group']['id'])
        join = joins.get(key)
        if not join or not pool:
            continue
        name = pool[len(events) % len(pool)]
        label = f'{a["number"]} → {b["number"]}'
        # A join begins at the incoming frame; its sound occupies that same interval.
        events.append({'name': name, 't': b['start'], 'dur': max(.1, min(.7, float(join.get('duration', .35)))), 'join': label})
        wanted.add(TRANSITION_PREFIX + label + ' · ' + name)
    for layer in ctx.project['tracks']:
        for clip in layer['clips']:
            if clip.get('title', '').startswith(TRANSITION_PREFIX) and clip['title'] not in wanted:
                ctx.actions.append({'type': 'delete_clip', 'payload': {'clip_id': clip['id']}})
    place(ctx, {'cues': events}, transition=True)
