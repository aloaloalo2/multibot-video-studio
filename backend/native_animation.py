"""Place editable animation layers directly on the Studio timeline, without video encoding."""
from __future__ import annotations

import math
from pathlib import Path
from PIL import ImageColor
import store


def place(ctx, spec: dict) -> None:
    number = int(spec['frame'])
    frame = next((f for f in (ctx.plan or {}).get('frames', []) if f['number'] == number), None)
    if not frame or frame.get('format') != 'animation':
        raise store.StudioError('Оберіть кадр формату animation', 400)
    parts = spec.get('clips')
    if not isinstance(parts, list) or not 1 <= len(parts) <= 150:
        raise store.StudioError('Передайте від 1 до 150 шарів анімації', 400)
    if 'replace' in spec and not isinstance(spec['replace'], bool):
        raise store.StudioError('Оберіть, чи замінити шари кадру', 400)
    existing = next((f for f in ctx.frames if f['number'] == number), None)
    if existing and not spec.get('replace'):
        raise store.StudioError('Кадр уже створений. Для правок передайте replace: true.', 409)
    marker = f'Кадр {number}'
    if marker in ctx.groups.values() or number in getattr(ctx, '_native_frames', set()):
        raise store.StudioError('Кадр повторюється в одному запиті', 400)
    fps = int(ctx.project.get('fps') or 25)
    snap = lambda t: math.floor(float(t) * fps + .5 + 1e-8) / fps
    start, end = snap(frame['start']), snap(frame['end'])
    duration = round(end - start, 6)
    background = str(spec.get('background') or '#101114')
    try:
        ImageColor.getrgb(background)
    except ValueError:
        raise store.StudioError('Невірний колір фону анімації', 400) from None
    prepared = [{'kind': 'animation', 'content_type': 'shape', 'color': background, 'start': 0,
                 'duration': duration, 'title': 'фон', 'width': 1, 'height': 1}]
    for part in parts:
        if not isinstance(part, dict):
            raise store.StudioError('Невірний шар анімації', 400)
        part = dict(part)
        kind = part.get('kind', 'animation')
        content = part.get('content_type', 'shape') if kind == 'animation' else kind
        if kind not in {'animation', 'image', 'text'} or content not in {'shape', 'gradient', 'image', 'text'}:
            raise store.StudioError('Анімація використовує шари, текст і зображення. Відеофайл для неї не потрібний.', 400)
        part['kind'] = kind
        if kind == 'animation':
            part['content_type'] = content
        if content == 'image':
            if part.get('path'):
                path = Path(part.pop('path')).expanduser()
                if store.media_kind(path) != 'image':
                    raise store.StudioError('Асетом анімації може бути зображення', 400)
                part['asset_id'] = ctx.asset_for(path)
            else:
                asset = next((a for a in ctx.project.get('assets', []) if a['id'] == part.get('asset_id')), None)
                if not asset or asset.get('kind') != 'image':
                    raise store.StudioError('Оберіть зображення для шару анімації', 400)
        elif part.get('asset_id') or part.get('path'):
            raise store.StudioError('Файли додавайте лише до шару зображення', 400)
        local = store.finite_float(part.get('start', 0), 0, duration)
        length = store.finite_float(part.get('duration', duration - local), .001, duration)
        if local + length > duration + .001:
            raise store.StudioError('Шар виходить за межі кадру', 400)
        part.update(start=local, duration=length)
        store.validated_keyframes(part.get('keyframes', []), length)
        prepared.append(part)
    # Add new layers before removing the old ones to preserve the scene group and its transitions.
    for index, part in enumerate(prepared):
        local = float(part.pop('start')); length = float(part.pop('duration'))
        title = f"K{number:03d} анімація {index} {part.pop('title', 'шар')}"
        payload = {**part, 'title': title, 'layer_id': ctx.project['tracks'][0]['id'],
                   'start': round(start + local, 3), 'duration': round(length, 3),
                   'easing': part.get('easing', 'linear')}
        if existing:
            payload['group_id'] = existing['group']['id']
        else:
            ctx.groups[title] = marker
        ctx.actions.append({'type': 'add_clip', 'payload': payload})
    if existing:
        ctx.actions.extend({'type': 'delete_clip', 'payload': {'clip_id': c['id']}} for c in existing['clips'])
    ctx._native_frames = getattr(ctx, '_native_frames', set()) | {number}
    ctx.report.append(f'кадр {number}: анімація наживо, {len(parts)} шарів, без рендеру відео')
