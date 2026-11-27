"""Validated transitions attached to actual touching scene/clip boundaries."""
import os
import re
import uuid
import json
from pathlib import Path

GRAPHIC_PRESETS=json.loads((Path(__file__).resolve().parents[1]/'frontend'/'graphic-transitions.json').read_text())
# transitions taken out of the library (engine/retired-graphic-transitions.json) stay valid on a seam that has one
OFFERED=set(GRAPHIC_PRESETS)
GRAPHIC_PRESETS={**json.loads((Path(__file__).resolve().parents[1]/'engine'/'retired-graphic-transitions.json').read_text()),**GRAPHIC_PRESETS}
CAPCUT=json.loads((Path(__file__).resolve().parents[1]/'frontend'/'capcut-catalog.json').read_text())['transitions']
MAX_TRANSITION=0.7   # seconds: no transition lasts longer (user, 25 November 2026: «всі переходи, які довго… скоротити…
# a plain dissolve, 15% shorter than the former 0.35 s (user, 27 November 2026, Astéroïde 84→85: «зроби його на 15%
# коротшим, бо він зазвичай довго… працює… в самій студії»): 0.30 s, whole frames at 25 and 30 fps
CROSSFADE = .30
                     # швидкість мені не подобається»); 30% off the ones over 1.2 s still left 1.0–1.4 s
def capcut_duration(kind):
    """How long a CapCut transition lasts on a seam: its own length, at most MAX_TRANSITION. The engine plays the
    animation faster over the shorter seam; the catalog keeps the animation's own length (engine/capcut_fx.py «comp»)."""
    own=float(CAPCUT[kind].get('default_duration',1.0))
    return round(min(own,MAX_TRANSITION),2)
TYPES={'cut','crossfade','slide_left','slide_right','slide_up','slide_down','zoom_in','zoom_out'}|set(GRAPHIC_PRESETS)|set(CAPCUT)
# what the library, the channel's «Переходи» and the montage may pick
CHOICES=(TYPES-set(GRAPHIC_PRESETS)-{'cut'})|OFFERED
def members(project,ref):
    clips={c['id']:c for t in project.get('tracks',[]) for c in t.get('clips',[])}
    if isinstance(ref,str) and ref.startswith('group:'):
        group=next((g for g in project.get('scene_groups',[]) if g['id']==ref[6:] and g.get('role')!='overlay'),None)
        if not group:raise ValueError('Scene not found')
        result=[clips[cid] for cid in group['clip_ids'] if cid in clips]
    elif isinstance(ref,str) and ref.startswith('clip:') and ref[5:] in clips:result=[clips[ref[5:]]]
    else:raise ValueError('Invalid transition endpoint')
    if not result or any(c['kind']=='audio' for c in result):raise ValueError('A transition requires visual clips')
    return result

def boundary(project,left,right):
    if not isinstance(left,str) or not isinstance(right,str) or left==right or left.split(':')[0]!=right.split(':')[0]:raise ValueError('Choose two adjacent frames')
    a,b=members(project,left),members(project,right)
    start=min(c['start'] for c in a);seam=max(c['start']+c['duration'] for c in a);following=min(c['start'] for c in b);end=max(c['start']+c['duration'] for c in b)
    if abs(seam-following)>1/max(1,project.get('fps',25))+.001:raise ValueError('Transitions can only be dropped onto touching frame edges')
    return seam,min(seam-start,end-following),a,b

def set_transition(project,payload):
    kind=payload.get('type')
    if kind not in TYPES:raise ValueError('Unknown transition')
    seam,maximum,a,b=boundary(project,payload.get('from_ref'),payload.get('to_ref'))
    duration=min(float(payload.get('duration',CROSSFADE if kind=='crossfade' else .35)),MAX_TRANSITION)   # no transition longer than MAX_TRANSITION
    if kind!='cut' and not .05<=duration<=min(2,maximum):raise ValueError('Transition is longer than an adjacent frame')
    old=project.get('join_transitions',[])
    project['join_transitions']=[j for j in old if j['id']!=payload.get('move_from') and j['from_ref']!=payload['from_ref'] and j['to_ref']!=payload['to_ref']]
    if kind!='cut':project['join_transitions'].append(dict(id=uuid.uuid4().hex[:12],from_ref=payload['from_ref'],to_ref=payload['to_ref'],type=kind,duration=duration,seam=seam))

def _video_spare(project, clip):
    """Seconds of the clip's own video after its end on the timeline; None when unknown."""
    import store
    asset = next((a for a in project.get('assets', []) if a.get('id') == clip.get('asset_id')), None)
    if not asset or not asset.get('path'):
        return None
    total = store.media_duration(Path(asset['path']))
    if not total:
        return None
    return total - float(clip.get('trim_start', 0)) - float(clip['duration'])


def ends_at_seam(project, join):
    """A transition out of a video with no frames left after its edge (a HeyGen host clip as long as its voice) ends on
    the seam instead of starting there: the video plays its own last moments under the transition and the next frame
    comes in over it a little early, instead of a held last picture (user, 25 November 2026: «стоп-кадр відео дивиться
    дуже дивно і як будто це баг»; «любий кадр можна підтягнути… накласти на ведучого»)."""
    if join.get('type') in (None, 'cut'):
        return False
    try:
        _, _, outgoing, _ = boundary(project, join['from_ref'], join['to_ref'])
    except (ValueError, KeyError, TypeError):
        return False
    need = float(join['duration'])
    for clip in outgoing:
        if clip.get('kind') != 'video' or abs(float(clip['start']) + float(clip['duration']) - float(join['seam'])) > .05:
            continue
        spare = _video_spare(project, clip)
        if spare is not None and spare + .02 < need:
            return True
    return False


_HITS = None


def transition_hit(kind):
    """Where in its length a transition hits (0..1): its strongest change of picture, measured on the transition's own
    video for the CapCut ones (backend/transition_hits.json); the middle for a dissolve, a slide or a zoom."""
    global _HITS
    if _HITS is None:
        try:
            _HITS = json.loads((Path(__file__).resolve().parent / 'transition_hits.json').read_text())
        except (OSError, ValueError):
            _HITS = {}
    return min(.95, max(.05, float(_HITS.get(kind, .5))))


_FRAME_TEXT = re.compile(r'^K\d{3} кадр\b')


def _text_out(project, join) -> bool:
    """The outgoing side of the seam is a full-frame text."""
    try:
        _, _, outgoing, _ = boundary(project, join['from_ref'], join['to_ref'])
    except (ValueError, KeyError, TypeError):
        return False
    # a full-frame text, or the frame's own lines of text («K020 кадр 1», «K020 кадр 2»…), not an accent's caption
    return any(c.get('kind') == 'text' and (c.get('text_role') == 'full_frame' or _FRAME_TEXT.match(str(c.get('title') or '')))
               for c in outgoing)


def _spares(project, join):
    """(seconds of the outgoing videos after their edge, seconds of the incoming videos before their start); None where
    the side has no video (a picture, a text or a Razgon frame is drawn as long as it is asked)."""
    try:
        _, _, outgoing, incoming = boundary(project, join['from_ref'], join['to_ref'])
    except (ValueError, KeyError, TypeError):
        return None, None
    seam, after, before = float(join['seam']), None, None
    for clip in outgoing:
        if clip.get('kind') == 'video' and abs(float(clip['start']) + float(clip['duration']) - seam) <= .05:
            spare = _video_spare(project, clip)
            if spare is not None:
                after = spare if after is None else min(after, spare)
    for clip in incoming:
        if clip.get('kind') == 'video' and abs(float(clip['start']) - seam) <= .05:
            head = float(clip.get('trim_start', 0))
            before = head if before is None else min(before, head)
    return after, before


def lead_seconds(project, join):
    """How long before its seam a transition starts: so that its hit lands on the seam, where the words change (user,
    25 November 2026: «я вже на 11-му фреймі, а воно показує… що я ще на 10-му… переходи… то спішать, то запізнюються»).
    A video with no frames after its edge makes it end on the seam, an incoming video with no frames before its start
    keeps it from starting earlier than it has pictures: no side ever holds a still picture."""
    if join.get('type') in (None, 'cut'):
        return 0.0
    length = float(join['duration'])
    fps = max(1, int(project.get('fps') or 25))
    # out of a text frame the transition starts on the seam, never before it: the seam is where the next sentence begins,
    # and every word stays readable until then (user, 25 November 2026: «текстова вставка має закінчитись аж там, де
    # починається наступне речення… щоб його ще встигли люди прочитати»)
    if _text_out(project, join):
        return 0.0
    after, before = _spares(project, join)
    low = max(0.0, length - after - .02) if after is not None else 0.0
    high = min(length, before) if before is not None else length
    want = length * transition_hit(join['type'])
    value = min(max(want, low), high) if low <= high else low
    return round(round(value * fps) / fps, 6)


def anchor(project):
    """Mark each transition with how long before its seam it starts (`lead`; `anchor: end` when it ends on the seam),
    the one rule the preview, the export and the sounds all read."""
    for join in project.get('join_transitions', []):
        value = lead_seconds(project, join)
        join['lead'] = value
        if value >= float(join.get('duration', 0)) - 1e-6 and value > 0:
            join['anchor'] = 'end'
        else:
            join.pop('anchor', None)
    return project


def lead_of(join):
    if isinstance(join.get('lead'), (int, float)):
        return float(join['lead'])
    return float(join['duration']) if join.get('anchor') == 'end' else 0.0


def window(join):
    """(start, end) of the transition on the film's clock."""
    seam, length = float(join['seam']), float(join['duration'])
    begin = seam - lead_of(join)
    return begin, begin + length


def reconcile(project):
    valid=[]
    for join in project.get('join_transitions',[]):
        try:seam,maximum,_,_=boundary(project,join['from_ref'],join['to_ref'])
        except (ValueError,KeyError,TypeError):continue
        if join['duration']<=maximum:valid.append({**join,'seam':seam})
    if 'join_transitions' in project:project['join_transitions']=valid
    anchor(project)

HELD_KEEP = 3 * 24 * 3600   # a held copy no export asked for in three days goes (a new edit makes a new one)


HELD_LIMIT = 1024 ** 3   # the held copies of a project together; the least recently used go first


def _prune_held(folder):
    """Copies no export asked for in HELD_KEEP go, and the folder never grows past HELD_LIMIT (it reached 24 GB on
    25 November 2026): the least recently used go first, a later edit makes again the one it needs."""
    import time
    now = time.time()
    kept = []
    for item in folder.iterdir():
        try:
            if not item.is_file():
                continue
            stat = item.stat()
            if now - stat.st_mtime > HELD_KEEP or item.name.endswith(".part.mp4"):
                item.unlink()
            else:
                kept.append((stat.st_mtime, stat.st_size, item))
        except OSError:
            pass
    total = sum(size for _, size, _ in kept)
    for _, size, item in sorted(kept):
        if total <= HELD_LIMIT:
            break
        try:
            item.unlink()
            total -= size
        except OSError:
            pass


_ALPHA = {}


def _has_alpha(path, stat):
    """Whether the video carries transparency, asked of ffprobe once a file version: asked anew for 28 host clips it took
    1.1 s of every manifest, so of every still, CapCut preview and export (25 November 2026)."""
    import subprocess
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _ALPHA:
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt",
                                "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60)
        _ALPHA[key] = any(tag in probe.stdout.strip() for tag in ("yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya8", "ya16"))
    return _ALPHA[key]


def _padded(folder, source, seconds, at_start):
    """A copy of the video with its first (at_start) or last frame held `seconds` longer, made once in `folder`; a
    transparent layer (motion code as ProRes 4444) keeps its alpha: an H.264 copy turned it into an opaque black picture
    over the whole frame (25 November 2026, the host frames of «Космос PRO» went black under the graphics). Local FFmpeg,
    nothing paid; the video itself when the copy cannot be made."""
    import hashlib, subprocess
    path = Path(source)
    stat = path.stat()
    side = 'head' if at_start else 'tail'
    key = hashlib.sha256(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{side}|{seconds:.3f}".encode()).hexdigest()[:24]
    folder.mkdir(parents=True, exist_ok=True)
    alpha = _has_alpha(path, stat)
    if alpha or path.parent.name == "motion-code":
        # a transparent layer (motion code: HEVC with alpha, drawn with a margin for transitions) is not copied: each copy of a whole clip took 1.4 GB and 17 of them
        # filled the Mac's disk (25 November 2026); a graphic over the frame comes in at its own start instead
        return source
    target = folder / f"{key}.mp4"
    if target.is_file():
        os.utime(target)   # in use: the prune below keeps it
        return str(target)
    _prune_held(folder)
    part = target.with_suffix(".part" + target.suffix)
    codec = (["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"] if alpha else
             ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"])
    pad = f"tpad=start_mode=clone:start_duration={seconds:.3f}" if at_start else f"tpad=stop_mode=clone:stop_duration={seconds:.3f}"
    result = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(path), "-vf", pad, "-an", *codec, str(part)],
                            capture_output=True, timeout=600)
    if result.returncode or not part.is_file():
        part.unlink(missing_ok=True)
        return source
    part.replace(target)
    return str(target)


def held_source(project, source, needed):
    """The video itself when it lasts `needed` seconds, else a copy holding its last frame to that length."""
    import store
    available = store.media_duration(Path(source)) or 0
    if available + .02 >= needed:
        return source
    return _padded(store.cache_dir(project) / "held-tails", source, needed - available + .2, False)


def held_head(folder, source, seconds):
    """A copy of the video that shows its first frame `seconds` before it starts (an incoming frame that comes in early,
    under a transition that ends on its seam)."""
    return _padded(Path(folder), source, seconds, True)


def lead(clip, seconds, folder=None):
    """The incoming clip starts `seconds` earlier with its picture unchanged from its own start on: keyframes and timed
    words move with it, a motion still running at its start runs on backwards (as an outgoing clip runs on, below),
    a video plays earlier frames it has, else holds its first one."""
    clip['start'] = float(clip['start']) - seconds
    clip['duration'] = float(clip['duration']) + seconds
    clip['lead'] = round(float(clip.get('lead', 0)) + seconds, 6)
    points = clip.get('keyframes') or []
    if points:
        moved = [{**point, 'time': float(point['time']) + seconds} for point in points]
        first = {'time': 0.0}
        for prop in ('x', 'y', 'scale', 'opacity'):
            known = sorted((point for point in points if prop in point), key=lambda point: float(point['time']))
            if not known or float(known[0]['time']) > 1e-9:
                known = [{'time': 0, prop: clip.get(prop, 1 if prop in {'scale', 'opacity'} else .5)}] + known
            head = known[0]
            after = known[1] if len(known) > 1 else head
            span = float(after['time']) - float(head['time'])
            value = float(head[prop]) - ((float(after[prop]) - float(head[prop])) / span * seconds if span > 1e-9 else 0)
            first[prop] = max(0, min(1, value)) if prop == 'opacity' else value
        clip['keyframes'] = [first, *moved]
    for word in clip.get('text_words') or []:
        for key in ('start', 'end'):
            if isinstance(word.get(key), (int, float)):
                word[key] = float(word[key]) + seconds
    if clip.get('type') == 'video' and clip.get('source'):
        trim = float(clip.get('trim_start', 0))
        if trim >= seconds - 1e-6:
            clip['trim_start'] = trim - seconds
        elif folder is not None:
            clip['source'] = held_head(folder, clip['source'], seconds - trim)
            clip['trim_start'] = 0.0
    return clip


def transport(project,layers):
    rendered={c['id']:c for layer in layers for c in layer['clips']}
    protected_text_ids=set()
    overlay_ids={cid for group in project.get('scene_groups',[]) if group.get('role')=='overlay' for cid in group['clip_ids']}
    brand_index=next((i for i,layer in enumerate(layers) if any(c['id'] in overlay_ids for c in layer['clips'])),len(layers))
    level={c['id']:i for i,layer in enumerate(layers) for c in layer['clips']}
    for join in project.get('join_transitions',[]):
        _,_,outgoing,incoming=boundary(project,join['from_ref'],join['to_ref'])
        ahead=lead_of(join) if 'lead' in join or join.get('anchor')=='end' else lead_seconds(project,join)
        early=ahead>1e-6
        after=max(0.0,float(join['duration'])-ahead)   # how long the outgoing side lasts past its edge
        begin=float(join['seam'])-ahead
        effect={'type':join['type'],'duration':join['duration'],'seam':begin}
        # a dissolve fades only the side on top; the side under it stays whole (user, 21 November 2026: «переходи, які в
        # чорноту переходить, а потім різко появляється наступний кадр»): both fading over black left the middle at 75%
        # only the clips on screen in the transition count: a lead-in that left the frame seconds before its end put the
        # outgoing frame «on top» while its group lay under the next one, and the next frame was drawn whole over it, a
        # plain cut with a blue glow (user, 27 November 2026, Astéroïde 86→87: «переходу цього… візуально ніяк не працює»)
        seam_at=float(join['seam'])
        out_levels=[level[c['id']] for c in outgoing if c['id'] in level and abs(float(c['start'])+float(c['duration'])-seam_at)<=.05]
        in_levels=[level[c['id']] for c in incoming if c['id'] in level and float(c['start'])<seam_at+float(join['duration'])]
        # a fading group is drawn at its top layer's place (engine/render.py group_key), so the group whose top layer is
        # higher lies on top even when an accent of the other one sits above some of its layers
        out_under=bool(out_levels and in_levels and max(out_levels)<max(in_levels));in_under=bool(out_levels and in_levels and max(in_levels)<max(out_levels))
        capcut=join['type'] in CAPCUT
        if early:
            # the incoming frame comes in early over the outgoing video's own last moments; only clips that start on the
            # seam (an accent later in the frame keeps its time)
            import store
            try:heads=store.cache_dir(project)/'held-tails'
            except (KeyError,store.StudioError):heads=None
            for source in incoming:
                if source['id'] in rendered and abs(float(source['start'])-float(join['seam']))<=.05:
                    lead(rendered[source['id']],ahead,heads)
        for source in incoming:
            if source['id'] not in rendered or capcut:continue
            if source.get('kind')=='text' and source.get('text_role')=='full_frame':
                protected_text_ids.add(source['id'])
            # the frame group fades as one picture (user, 22 November 2026: «перехід використовує групи, а не кожен
            # слой»): every clip of a side carries the same `group`, and the engine composites them before the fade
            else:rendered[source['id']]['join_in']={**effect,'under':in_under,'group':f"{join.get('id','')}:in"}
        for source in outgoing:
            if source['id'] not in rendered or abs(source['start']+source['duration']-join['seam'])>.05:continue
            clip=rendered[source['id']]
            # a CapCut transition draws both sides itself (engine/capcut_fx.py): the outgoing clip only goes on under it
            if not capcut:clip['join_out']={**effect,'under':out_under,'group':f"{join.get('id','')}:out"}
            if after<=1e-6:continue   # the transition ends on the edge: nothing to add after it
            old=clip['duration'];clip['native_duration']=old;clip['duration']=old+after
            if clip.get('type')=='video' and clip.get('source'):
                # a video with no frames left for the transition (the host's HeyGen clip is as long as its frame) holds
                # its last picture through it (user, 25 November 2026: «просто кадр… на 0,8 секунд довший зробити»)
                clip['source']=held_source(project,clip['source'],float(clip.get('trim_start',0))+clip['duration'])
            points=clip.get('keyframes',[])
            if points:
                # a clip still moving at its end keeps the speed of its last keyframe segment through the transition
                # (frontend/transitions.js); one that stopped earlier, or has a single keyframe, holds its picture
                extra={'time':clip['duration']}
                for prop in ('x','y','scale','opacity'):
                    known=sorted((p for p in points if prop in p),key=lambda p:float(p['time']))
                    if not known or float(known[0]['time'])>1e-9:known=[{'time':0,prop:clip.get(prop,1 if prop in {'scale','opacity'} else .5)}]+known
                    last=known[-1];previous=known[-2] if len(known)>1 else last
                    span=float(last['time'])-float(previous['time'])
                    moving=span>1e-9 and float(last['time'])>=old-.05
                    value=float(last[prop])+((float(last[prop])-float(previous[prop]))/span if moving else 0)*(clip['duration']-float(last['time']))
                    extra[prop]=max(0,min(1,value)) if prop=='opacity' else value
                clip['keyframes']=[*points,extra]
        if capcut:
            members={c['id'] for c in outgoing+incoming}
            top=max((float(layer.get('z',0)) for layer in layers if any(c['id'] in members and c.get('content_type')!='capcut_effect' for c in layer['clips'])),default=brand_index-1)
            layers.append(dict(id='capcut-'+join['id'],z=min(top+.5,brand_index-.5),clips=[dict(id='capcut-'+join['id'],type='animation',content_type='capcut_transition',capcut_type=join['type'],start=begin,duration=join['duration'],trim_start=0,x=.5,y=.5,width=1.,height=1.,opacity=1,volume=0,easing='linear',capcut_a_drop=[c['id'] for c in incoming],capcut_b_drop=[c['id'] for c in outgoing],capcut_exclude=sorted(overlay_ids))]))
        if join['type'] in GRAPHIC_PRESETS:
            layers.append(dict(id='graphic-'+join['id'],z=brand_index-.5,clips=[dict(id='graphic-'+join['id'],type='animation',content_type='graphic_transition',graphic_style=join['type'],start=begin,duration=join['duration'],trim_start=0,x=.5,y=.5,width=1.,height=1.,opacity=1,volume=0,easing='linear')]))
    for layer in list(layers):
        moved=[clip for clip in layer['clips'] if clip['id'] in protected_text_ids]
        if moved:
            layer['clips']=[clip for clip in layer['clips'] if clip['id'] not in protected_text_ids]
            layers.append(dict(id='transition-text-'+layer.get('id','layer'),z=brand_index-.25,clips=moved))
