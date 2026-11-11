"""Pure timeline validation and in-memory edits; no file or service access."""
from __future__ import annotations

import math
import uuid

from studio_errors import StudioError


def recompute_timeline(project: dict) -> None:
    t = 0.0
    for scene in project["scenes"]:
        scene["start"] = round(t, 3)
        t += float(scene["duration"])
    project["duration"] = round(t, 3)


def keep_overlays_on_top(project: dict) -> None:
    """The channel's logo and plate (layers whose clips all belong to scene groups with the role «overlay») stay the top
    layers, so a layer added after them never lands over them: the higher a layer, the higher its row and its place in
    the picture (user, 30 October 2026)."""
    overlay = {cid for group in project.get("scene_groups") or [] if group.get("role") == "overlay" for cid in group.get("clip_ids", [])}
    tracks = project.get("tracks", [])
    top = [layer.get("id") for layer in tracks if layer.get("clips") and all(clip.get("id") in overlay for clip in layer["clips"])]
    if top and [layer.get("id") for layer in tracks[-len(top):]] != top:
        project["tracks"] = [layer for layer in tracks if layer.get("id") not in top] + [layer for layer in tracks if layer.get("id") in top]


def recompute_universal_duration(project: dict) -> None:
    project["duration"] = round(max((float(clip.get("start", 0)) + float(clip.get("duration", 0)) for layer in project.get("tracks", []) for clip in layer.get("clips", [])), default=0), 3)
    keep_overlays_on_top(project)
    for index, layer in enumerate(project.get("tracks", [])):
        layer["z_index"] = index


def layer_by_id(project: dict, layer_id: str) -> dict:
    for layer in project.get("tracks", []):
        if layer.get("id") == layer_id and layer.get("type") == "universal":
            return layer
    raise StudioError("Шар не знайдено", 404)


def clip_by_id(project: dict, clip_id: str) -> tuple[dict, dict]:
    for layer in project.get("tracks", []):
        for clip in layer.get("clips", []):
            if clip.get("id") == clip_id:
                return layer, clip
    raise StudioError("Кліп не знайдено", 404)


def finite_float(value, minimum=None, maximum=None, message="Невірне число") -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise StudioError(message) from None
    if not math.isfinite(result) or minimum is not None and result < minimum or maximum is not None and result > maximum:
        raise StudioError(message)
    return result


def validated_keyframes(value, duration: float) -> list[dict]:
    if not isinstance(value, list) or len(value) > 200:
        raise StudioError("Невірні ключові кадри")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise StudioError("Невірний ключовий кадр")
        point = {"time": finite_float(item.get("time"), 0, duration, "Невірний час ключового кадру")}
        for key in ("x", "y"):
            if key in item:
                point[key] = finite_float(item[key], -2, 2, "Невірна позиція ключового кадру")
        if "scale" in item:
            point["scale"] = finite_float(item["scale"], .05, 8, "Невірний масштаб ключового кадру")
        if "opacity" in item:
            point["opacity"] = finite_float(item["opacity"], 0, 1, "Невірна прозорість ключового кадру")
        result.append(point)
    return sorted(result, key=lambda item: item["time"])


def validated_text_layout(value, text, duration):
    if not isinstance(value, list) or len(value) > 200:
        raise StudioError("Invalid timed text layout")
    result = []
    previous = -1
    for word in value:
        if not isinstance(word, dict) or not str(word.get("text", "")).strip():
            raise StudioError("Invalid timed text word")
        point = {"text": str(word["text"]), "start": finite_float(word.get("start"), 0, duration)}
        if 'end' in word:
            point['end'] = finite_float(word['end'], point['start'], duration)
        if point["start"] < previous:
            raise StudioError("Timed text words must be ordered")
        previous = point["start"]
        for key in ("x", "y", "width", "height"):
            point[key] = finite_float(word.get(key), 0, 1)
        if not point["width"] or not point["height"]:
            raise StudioError("Timed text words need a positive box")
        result.append(point)
    if result and " ".join(w["text"] for w in result).split() != str(text).split():
        raise StudioError("Timed text differs from clip text")
    return result


def validated_preset(name, duration, clip_duration: float) -> tuple[str | None, float]:
    if name in (None, "", "none"):
        return None, 0.0
    if name not in {"fade_in", "fade_out", "slide_in", "slide_out", "zoom_in", "pop"}:
        raise StudioError("Невідомий анімаційний прийом")
    length = finite_float(duration if duration is not None else min(.4, clip_duration), .05, clip_duration, "Невірна тривалість анімації")
    return str(name), round(length, 3)


def reconcile_scene_groups(project):
    existing={c['id'] for t in project['tracks'] for c in t.get('clips',[])}
    groups=[]
    for group in project.get('scene_groups',[]):
        group['clip_ids']=[cid for cid in group['clip_ids'] if cid in existing]
        if group['clip_ids']: groups.append(group)
    if 'scene_groups' in project: project['scene_groups']=groups


def apply_group_action(project, action, payload):
    groups=project.setdefault('scene_groups',[])
    clips={c['id']:c for t in project['tracks'] for c in t.get('clips',[])}
    if action=='group_clips':
        ids=payload.get('clip_ids')
        if ids is None and isinstance(payload.get('clip_titles'),list):
            # clips added earlier in the same batch have no id the caller knows: name them by title (the newest one not
            # yet in a group), so a clip and its frame group are one undo step (montage_ops.place)
            occupied={cid for g in groups for cid in g['clip_ids']}
            ids=[]
            for title in payload['clip_titles']:
                found=[c for t in project['tracks'] for c in t.get('clips',[]) if c.get('title')==title and c['id'] not in occupied and c['id'] not in ids]
                if not found:raise StudioError(f'Кліп «{title}» не знайдено')
                ids.append(found[-1]['id'])
        if not isinstance(ids,list) or not 1<=len(ids)<=200 or any(not isinstance(cid,str) for cid in ids) or len(set(ids))!=len(ids) or any(cid not in clips for cid in ids):
            raise StudioError('Invalid frame members')
        occupied={cid for g in groups for cid in g['clip_ids']}
        if occupied.intersection(ids):raise StudioError('A clip is already grouped')
        title=str(payload.get('title') or 'Кадр').strip()[:120]
        if not title:raise StudioError('Frame title is empty')
        role=payload.get('role','scene')
        if role not in {'scene','overlay'}:raise StudioError('Invalid frame role')
        groups.append(dict(id=uuid.uuid4().hex[:12],title=title,clip_ids=ids,role=role))
        return
    group=next((g for g in groups if g['id']==payload.get('group_id')),None)
    if not group:raise StudioError('Frame group not found',404)
    if action=='ungroup_clips':groups.remove(group)
    elif action=='update_group':
        title=str(payload.get('title','')).strip()[:120]
        if not title:raise StudioError('Frame title is empty')
        group['title']=title
    elif action=='move_group':
        members=[clips[cid] for cid in group['clip_ids']]
        first=min(float(c['start']) for c in members)
        offset=finite_float(payload.get('start'),0,36000)-first
        if any(float(c['start'])+offset<0 or float(c['start'])+offset+float(c['duration'])>36000 for c in members):raise StudioError('Frame exceeds timeline bounds')
        for clip in members:clip['start']=round(float(clip['start'])+offset,3)
    elif action=='delete_group':
        remove=set(group['clip_ids'])
        for track in project['tracks']:track['clips']=[c for c in track['clips'] if c['id'] not in remove]
        project['tracks']=[t for t in project['tracks'] if t['clips']] or [dict(id='layer-1',name='Шар 1',type='universal',clips=[])]
        groups.remove(group)



def scene_by_id(project: dict, sid: str) -> dict:
    for scene in project.get("scenes", []):
        if scene.get("id") == sid:
            return scene
    raise StudioError("Кадр не знайдено", 404)
