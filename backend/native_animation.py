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
            validate_label(part, ctx.project, number, fps)
        prepared.append(part)
    # The generated backing colour alone never counts as a completed animation frame.
    # Validate each output frame before changing any timeline clips.
    for index in range(max(1, round(duration * fps))):
        moment = index / fps
        if not any(float(p['start']) <= moment < float(p['start']) + float(p['duration']) - 1e-8
                   and visible_opacity(p, moment - float(p['start'])) > .001 for p in prepared[1:]):
            raise store.StudioError(f'Кадр {number}: на {moment:.2f} с лишається тільки фон. Основний візуал має покривати весь кадр.', 400)
    # Text and explicitly marked label images stay above chart bars and decorative shapes.
    prepared = [prepared[0]] + sorted(prepared[1:], key=lambda p: p.pop('_foreground', False))
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
    for index in range(max(1,math.ceil(duration*fps))):
        t=index/fps
        if visible_opacity(part,t)<.95:continue  # a deliberate fade-in/out may cross the screen edge
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
