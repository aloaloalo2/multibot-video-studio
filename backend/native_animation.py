"""Place editable animation layers directly on the Studio timeline, without video encoding."""
from __future__ import annotations

import math
from pathlib import Path
from functools import lru_cache
from PIL import ImageColor, ImageFont
import font_catalog
import graphics
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
    background = str(spec.get('background') or '#000000')
    try:
        rgb = ImageColor.getrgb(background)
    except ValueError:
        raise store.StudioError('Невірний колір фону анімації', 400) from None
    prepared = []
    for part in parts:
        if not isinstance(part, dict):
            raise store.StudioError('Невірний шар анімації', 400)
        part = dict(part)
        foreground = part.pop('foreground', False)
        if type(foreground) is not bool:
            raise store.StudioError('foreground має бути увімкнено або вимкнено', 400)
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
        # A long layer anchored to the scene must not vanish one output frame before its background.
        # Keep intentional shorter events; hold the final pose of scene-spanning layers to the common seam.
        if local < .001 and length >= 1 and 0 < duration - length <= 1 / fps + 1e-6:
            length = duration
        part['_foreground'] = foreground or content == 'text'
        part.update(start=local, duration=length)
        store.validated_keyframes(part.get('keyframes', []), length)
        if content == 'text':
            default_font = getattr(ctx, 'accent_font' if part.get('text_role') in ('accent', 'label') else 'text_font', None)
            if default_font and (not part.get('font_family') or getattr(ctx, 'unified_font', False) and part.get('font_family') not in getattr(ctx, 'channel_fonts', set())):
                part['font_family'] = default_font
            validate_label(part, ctx.project, number, fps)
        prepared.append(part)
    # PNG props live to the frame's end in the channel's own motion, nothing comes in during its last second (asset_motion)
    import asset_motion
    ctx.report.extend(f'кадр {number}: {note}' for note in asset_motion.enliven_layers(ctx, frame, prepared, duration, start))
    camera = camera_move(spec.get('camera'))
    if camera:
        for part in prepared:
            apply_camera(part, camera, duration, fps)
        ctx.report.append(f'кадр {number}: камера {camera[0]} {round(camera[1] * 100)}%')
    for part in prepared:
        store.validated_keyframes(part.get('keyframes', []), float(part['duration']))
    # The generated backing colour alone never counts as a completed animation frame.
    # Validate each output frame before changing any timeline clips.
    for index in range(max(1, round(duration * fps))):
        moment = index / fps
        if not any(float(p['start']) <= moment < float(p['start']) + float(p['duration']) - 1e-8
                   and visible_opacity(p, moment - float(p['start'])) > .001 for p in prepared):
            raise store.StudioError(f'Кадр {number}: на {moment:.2f} с лишається тільки фон. Основний візуал має покривати весь кадр.', 400)
    # Text and explicitly marked label images stay above chart bars and decorative shapes.
    prepared.sort(key=lambda p: p.pop('_foreground', False))
    layer_id = ctx.project['tracks'][0]['id']
    backing = store.frame_background(layer_id, 0, duration, title='чорний фон')
    backgrounds = [backing]
    if rgb not in ((0, 0, 0), (0, 0, 0, 255)):
        backgrounds.append({**backing, 'color': background, 'title': 'фон', 'frame_background': False})
    # Add new layers before removing the old ones to preserve the scene group and its transitions.
    for index, part in enumerate(backgrounds + prepared):
        local = float(part.pop('start')); length = float(part.pop('duration'))
        title = f"K{number:03d} анімація {index} {part.pop('title', 'шар')}"
        payload = {**part, 'title': title, 'layer_id': layer_id,
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


# A gentle move of the whole frame, every layer together, so a still picture with animation on top never stands dead
# (user, 26 November 2026: «кадри… мертві, на місці стоять… трошечки якийсь рух постійно… приближення, віддалення…
# зліва направо… щоб це сильно не нагружало… по токенах і швидкості»). The agent names it in one word; the Studio
# recomputes each layer's keyframes, so a marker stays on its place in the picture. The frame's black backing stays.
CAMERA_MOVES = ('zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down')
CAMERA_AMOUNT = .05


def camera_move(value):
    if value in (None, False, '', 'none'):
        return None
    move, amount = (value.get('move'), value.get('amount', CAMERA_AMOUNT)) if isinstance(value, dict) else (value, CAMERA_AMOUNT)
    if move not in CAMERA_MOVES:
        raise store.StudioError('camera: ' + ', '.join(CAMERA_MOVES), 400)
    return move, store.finite_float(amount, .02, .12, 'Невірна сила руху камери')


def camera_at(camera, p):
    """Scale and shift of the whole frame at progress p (0…1): a pan keeps a margin of half its travel on each side."""
    move, a = camera
    if move == 'zoom_in':
        return 1 + a * p, 0., 0.
    if move == 'zoom_out':
        return 1 + a * (1 - p), 0., 0.
    shift = a / 2 - a * p          # from +a/2 to -a/2: the picture slides left as the camera pans right
    dx = shift if move == 'pan_right' else -shift if move == 'pan_left' else 0.
    dy = shift if move == 'pan_down' else -shift if move == 'pan_up' else 0.
    return 1 + a, dx, dy


def apply_camera(part, camera, duration, fps):
    import montage_ops
    local, length = float(part['start']), float(part['duration'])
    marks = {0.0, length} | {float(k['time']) for k in part.get('keyframes', [])}
    step = max(.25, length / 120)
    marks |= {round(i * step, 4) for i in range(int(length / step) + 1)}
    known = sorted({float(k['time']) for k in part.get('keyframes', [])})
    if part.get('easing', 'linear') != 'linear':          # an eased entrance keeps its curve, sampled every two frames
        for a, b in zip(known, known[1:]):
            n = min(12, max(1, int((b - a) * fps / 2)))
            marks |= {a + (b - a) * i / n for i in range(n + 1)}
    frames = []
    for t in sorted(m for m in marks if 0 <= m <= length + 1e-9):
        t = min(t, montage_ops.end_time(length))
        s, dx, dy = camera_at(camera, (local + t) / duration if duration else 0)
        x, y = (montage_ops.keyframe_value(part, k, t) for k in ('x', 'y'))
        frames.append({'time': round(t, 4), 'x': .5 + (x - .5) * s + dx, 'y': .5 + (y - .5) * s + dy,
                       'scale': montage_ops.keyframe_value(part, 'scale', t) * s,
                       'opacity': montage_ops.keyframe_value(part, 'opacity', t)})
    unique = {}
    for f in frames:
        unique[f['time']] = f
    part['keyframes'] = list(unique.values())[:200]
    part['easing'] = 'linear'


def visible_opacity(part, local):
    points = sorted((float(k['time']), float(k['opacity'])) for k in part.get('keyframes', []) if 'opacity' in k)
    base = float(part.get('opacity', 1))
    if not points: return base
    if points[0][0] > 0: points.insert(0, (0, base))
    if local <= points[0][0]: return points[0][1]
    for (a, av), (b, bv) in zip(points, points[1:]):
        if local < b:
            return av + (bv-av) * ((local-a)/(b-a))
    return points[-1][1]


@lru_cache(maxsize=64)
def label_font(family, weight, size):
    return ImageFont.truetype(str(font_catalog.font_path(family, weight)), size)


def value_at(part, key, moment, default):
    points=sorted((float(k['time']),float(k[key])) for k in part.get('keyframes',[]) if key in k)
    base=float(part.get(key,default))
    if not points:return base
    if points[0][0]>0:points.insert(0,(0,base))
    if moment<=points[0][0]:return points[0][1]
    for (a,av),(b,bv) in zip(points,points[1:]):
        if moment<b:return av+(bv-av)*(moment-a)/(b-a)
    return points[-1][1]


def validate_label(part, project, number, fps):
    """Cheap preflight at output-frame times; no model or video render is needed."""
    try:
        style=graphics.validate(part)
    except (ValueError,TypeError) as error:
        raise store.StudioError(str(error),400) from None
    size=store.finite_float(part.get('font_size',54),8,300)
    width=store.finite_float(part.get('width',1),.01,4)
    height=store.finite_float(part.get('height',1),.01,4)
    duration=float(part['duration'])
    peak=max([visible_opacity(part,0), *[float(k['opacity']) for k in part.get('keyframes',[]) if 'opacity' in k]])
    for index in range(max(1,math.ceil(duration*fps))):
        t=index/fps
        if visible_opacity(part,t)<max(.001,peak*.95):continue  # only the transient part of an actual fade may cross the edge
        x=value_at(part,'x',t,.5);y=value_at(part,'y',t,.5);scale=value_at(part,'scale',t,1)
        if x-width*scale/2 < -.001 or x+width*scale/2 > 1.001 or y-height*scale/2 < -.001 or y+height*scale/2 > 1.001:
            raise store.StudioError(f'Кадр {number}: текст виходить за екран на {t:.2f} с. Зменште або перемістіть його блок.',400)
    if part.get('text_words'):return
    font=label_font(project.get('font_family') or style.get('font_family','Arial'),style.get('font_weight',400),round(size))
    available=width*float(project.get('width') or 1920)
    lines=[]
    for paragraph in str(part.get('text','')).splitlines():
        current=''
        for word in paragraph.split():
            if font.getlength(word)>available:
                raise store.StudioError(f'Кадр {number}: слово не вміщується в текстовий блок. Збільште ширину або змініть текст.',400)
            candidate=word if not current else current+' '+word
            if current and font.getlength(candidate)>available:lines.append(current);current=word
            else:current=candidate
        lines.append(current)
    required=len(lines)*size*style.get('line_height',1.28)
    if required>height*float(project.get('height') or 1080)+1:
        raise store.StudioError(f'Кадр {number}: текст не вміщується по висоті. Збільште блок або скоротіть підпис.',400)
