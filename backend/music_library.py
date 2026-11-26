"""The studio's music library: real tracks from the YouTube Audio Library (licence «без зазначення автора»), one shared
library above the SFX, and each channel ticks the tracks it uses (user, 26 November 2026: «бібліотека музики має бути в
над SFX. І там просто галочками маємо відбирати»).

A film's music is laid from the channel's ticked tracks by moments: the director may give a frame a «music» mark (a
category, «тиша», «тихіше», «гучніше», «ледь чутно»); frames of one category share a track, the tracks change with
crossfades, a stretch may have no music at all, and the level moves a little up or down, more so down (user: «інколи без
музики може бути якийсь етап… в деяких моментах… тихіше… голосніше… різниця… 2%… може бути більше… вниз»). The bed is
rendered into one file the timeline plays as one music clip; the tracks used go to the film's description.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import store

CATEGORIES = ['дуже спокійна', 'спокійна', 'лоуфай', 'натхненна', 'драйвова', 'драматична', 'темна', 'сумна']
LEVELS = {'тихіше': .67, 'гучніше': 1.33, 'ледь чутно': .33, 'тиша': 0.0}   # the music clip's 6% then reads 4%, 8%, 2%, 0
RATE = 48000
TARGET_LUFS = -20.0   # every track brought to one loudness, so a change of track is no jump
RAMP = 1.5            # seconds a change of level takes
FADE = 2.0            # seconds a track fades in and out, and two tracks cross
RECENT = 4            # the channel's last films whose tracks a new film does not take again
SOURCE = 'YouTube Audio Library'


def root() -> Path:
    return store.DATA_ROOT / 'music-library'


def catalog() -> list[dict]:
    rows = store.read_json(root() / 'catalog.json', []) or []
    return [row for row in rows if isinstance(row, dict) and row.get('id') and (root() / row.get('file', '')).is_file()]


def public() -> list[dict]:
    """The library for the channel's settings: a row a track, grouped by category in their order."""
    order = {name: index for index, name in enumerate(CATEGORIES)}
    rows = [{key: row.get(key) for key in ('id', 'title', 'artist', 'category', 'seconds', 'vocals')} | {'preview_url': f'/api/music-library/{row["id"]}.mp3'}
            for row in catalog()]
    return sorted(rows, key=lambda row: (order.get(row['category'], 99), row['title']))


def track_path(track_id: str) -> Path:
    row = next((row for row in catalog() if row['id'] == track_id), None)
    if not row:
        raise store.StudioError('Трек не знайдено', 404)
    return root() / row['file']


def selected(sound: dict) -> list[dict]:
    """The channel's ticked tracks, without vocals."""
    ids = set(((sound or {}).get('music') or {}).get('tracks') or [])
    return [row for row in catalog() if row['id'] in ids and not row.get('vocals')]


def loudness(path: Path) -> float | None:
    done = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', str(path), '-af', 'ebur128', '-f', 'null', '-'],
                          capture_output=True, text=True, timeout=300)
    found = re.findall(r'I:\s+(-?\d+(?:\.\d+)?) LUFS', done.stderr)
    return float(found[-1]) if found else None


def import_folder(folder: Path, pick: list[dict]) -> dict:
    """Copies the downloaded tracks named «Title - Artist.mp3» that are in `pick` (the rows chosen in the YouTube Audio
    Library: id, title, artist, cat, moods, genres) into the library, measured once."""
    target = root() / 'files'
    target.mkdir(parents=True, exist_ok=True)
    rows = {row['id']: row for row in (store.read_json(root() / 'catalog.json', []) or []) if isinstance(row, dict)}
    added, missing = [], []
    files = {p.stem.casefold(): p for p in Path(folder).glob('*.mp3')}
    for item in pick:
        name = f"{item['title']} - {item['artist']}".casefold()
        source = files.get(name) or next((p for stem, p in files.items() if stem.startswith(item['title'].casefold() + ' - ')), None)
        if source is None:
            missing.append(item['title'])
            continue
        file = target / f"{item['id']}.mp3"
        if not file.exists():
            shutil.copy2(source, file)
        rows[item['id']] = {**rows.get(item['id'], {}), 'id': item['id'], 'title': item['title'], 'artist': item['artist'],
                            'category': item.get('cat') if item.get('cat') in CATEGORIES else 'спокійна',
                            'moods': item.get('moods', []), 'genres': item.get('genres', []), 'file': f"files/{item['id']}.mp3",
                            'seconds': round(store.media_duration(file) or float(item.get('sec') or 0), 2),
                            'lufs': rows.get(item['id'], {}).get('lufs') or loudness(file), 'source': SOURCE,
                            'license': 'YouTube Audio Library, без зазначення автора'}
        added.append(item['id'])
    store.atomic_json(root() / 'catalog.json', list(rows.values()))
    return {'added': len(added), 'missing': missing, 'total': len(rows)}


def remove_vocal_tracks() -> list[str]:
    """Takes the tracks found with a voice out of the library, file and all: the background under the narration has no
    voice of its own (user, 26 November 2026: «що з голосом прибери взагалі»). Returns their titles."""
    rows = store.read_json(root() / 'catalog.json', []) or []
    gone = [row for row in rows if row.get('vocals')]
    store.atomic_json(root() / 'catalog.json', [row for row in rows if not row.get('vocals')])
    for row in gone:
        (root() / row['file']).unlink(missing_ok=True)
    return [row['title'] for row in gone]


def mark_vocals(track_id: str, vocals: bool) -> None:
    rows = store.read_json(root() / 'catalog.json', []) or []
    for row in rows:
        if row.get('id') == track_id:
            row['vocals'] = bool(vocals)
    store.atomic_json(root() / 'catalog.json', rows)


def frame_marks(plan: dict | None) -> list[tuple[float, float, str | None, float]]:
    """(start, end, category or None, level) of every plan frame from its «music» mark."""
    out, category = [], None
    for frame in (plan or {}).get('frames') or []:
        mark = str(frame.get('music') or '').strip().lower()
        level = 1.0
        if mark in CATEGORIES:
            category = mark
        elif mark in LEVELS:
            level = LEVELS[mark]
        out.append((float(frame['start']), float(frame['end']), category, level))
    return out


def lay_out(project: dict, plan: dict | None, total: float, tracks: list[dict]) -> list[dict]:
    """The film's music as segments [{start, end, track, level}], track None for silence. Frames of one category share a
    track; a film the director gave no marks plays its channel's tracks in turn by stretches of a few minutes, one short
    quiet stretch now and then; never a track the channel's last films played, never one track twice in a film."""
    rng = random.Random(int(hashlib.sha256(project['id'].encode()).hexdigest()[:16], 16))
    history = [row for row in (store.read_json(history_path(project), []) or []) if isinstance(row, dict) and row.get('project') != project['id']]
    recent = {tid for row in history[-RECENT:] for tid in row.get('tracks', [])}
    by_category: dict[str, list[dict]] = {}
    for row in tracks:
        by_category.setdefault(row['category'], []).append(row)
    for rows in by_category.values():
        rng.shuffle(rows)
    used: set[str] = set()

    def take(category: str | None) -> dict | None:
        pools = [by_category.get(category, [])] if category else []
        pools.append([row for rows in by_category.values() for row in rows])
        for pool in pools:
            for fresh in (lambda r: r['id'] not in used and r['id'] not in recent, lambda r: r['id'] not in used, lambda r: True):
                found = [row for row in pool if fresh(row)]
                if found:
                    used.add(found[0]['id'])
                    return found[0]
        return None

    marks = frame_marks(plan)
    if not any(category for _, _, category, _ in marks):
        # no marks: a stretch of a few minutes per track, and in some films one quiet frame past the middle
        marks = [(start, end, None, level) for start, end, _, level in marks] or [(0.0, total, None, 1.0)]
        if total > 240 and not any(level == 0 for *_, level in marks) and rng.random() < .6:
            middle = [i for i, (start, end, *_) in enumerate(marks) if .5 * total < start < .78 * total and 8 <= end - start <= 45]
            if middle:
                i = rng.choice(middle)
                marks[i] = (*marks[i][:3], 0.0)
    segments, current, track_start = [], None, 0.0
    for start, end, category, level in marks:
        key = category or 'auto'
        # a new track where the category changes, or every few minutes when the director left the film to the studio
        change = current is None or current['key'] != key or (key == 'auto' and start - track_start > rng.uniform(150, 260))
        # a track that would end inside the stretch hands over to the next of the same character, never starts over
        change = change or bool(current['track'] and end - track_start > float(current['track'].get('seconds') or 1e9) + .01)
        if change:
            track = take(category)
            current = {'key': key, 'track': track}
            track_start = start
        segments.append({'start': start, 'end': end, 'track': current['track']['id'] if current['track'] else None,
                         'level': level, 'from': round(start - track_start, 3)})
    if segments:
        segments[-1]['end'] = max(segments[-1]['end'], total)
    return segments


def history_path(project: dict) -> Path:
    return store.DATA_ROOT / 'channels' / str(project.get('channel_id') or 'none') / 'music-library-history.json'


def remember(project: dict, segments: list[dict]) -> None:
    ids = list(dict.fromkeys(s['track'] for s in segments if s['track']))
    path = history_path(project)
    rows = [row for row in (store.read_json(path, []) or []) if isinstance(row, dict) and row.get('project') != project['id']]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        store.atomic_json(path, (rows + [{'project': project['id'], 'tracks': ids}])[-40:])
        store.atomic_json(store.project_dir(project['id']) / 'music-tracks.json', ids)
    except OSError:
        pass


def _decode(path: Path):
    import numpy as np
    raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-f', 'f32le', '-ac', '2', '-ar', str(RATE), '-'],
                         capture_output=True, timeout=300)
    if raw.returncode:
        raise RuntimeError('Не вдалося прочитати трек: ' + path.name)
    return np.frombuffer(raw.stdout, dtype='<f4').reshape(-1, 2)


def render(segments: list[dict], total: float, output: Path) -> None:
    """One stereo file of the film's music: each track at one loudness from where its stretch starts in it (looped when
    the stretch is longer), faded in and out and crossed with the next, its level following the segments with gentle
    ramps. Written block by block into a temporary file on disk, never the whole film in memory twice."""
    import numpy as np
    rows = {row['id']: row for row in catalog()}
    n = int(round(total * RATE))
    work = output.with_suffix('.pending.f32')
    bed = np.lib.format.open_memmap(str(work), mode='w+', dtype=np.float32, shape=(n, 2))
    try:
        # runs of one track: (track, first sample, last sample, offset in the track)
        runs = []
        for seg in segments:
            if runs and runs[-1][0] == seg['track']:
                runs[-1][2] = seg['end']
            else:
                runs.append([seg['track'], seg['start'], seg['end'], seg.get('from', 0.0)])
        fade = int(FADE * RATE)
        for track, start, end, offset in runs:
            if not track or track not in rows:
                continue
            audio = _decode(root() / rows[track]['file'])
            if not len(audio):
                continue
            gain = 10 ** ((TARGET_LUFS - float(rows[track].get('lufs') or TARGET_LUFS)) / 20)
            a, b = max(0, int(start * RATE) - fade // 2), min(n, int(end * RATE) + fade // 2)
            first = int(offset * RATE) % len(audio)
            for begin in range(a, b, 10 * RATE):
                stop = min(b, begin + 10 * RATE)
                idx = (np.arange(begin - a, stop - a) + first) % len(audio)
                part = audio[idx] * gain
                pos = np.arange(begin, stop)
                env = np.minimum(1.0, np.minimum((pos - a) / max(1, fade), (b - pos) / max(1, fade))).clip(0, 1)
                bed[begin:stop] += part * env[:, None]
        # the level of each segment, ramped over RAMP seconds
        level = np.ones(n, dtype=np.float32)
        ramp = int(RAMP * RATE)
        previous = 1.0
        for seg in segments:
            a, b = int(seg['start'] * RATE), min(n, int(seg['end'] * RATE))
            if b <= a:
                continue
            target = 0.0 if not seg['track'] else float(seg['level'])
            level[a:b] = target
            r = min(ramp, b - a)
            level[a:a + r] = np.linspace(previous, target, r, dtype=np.float32)
            previous = target
        for begin in range(0, n, 10 * RATE):
            stop = min(n, begin + 10 * RATE)
            bed[begin:stop] *= level[begin:stop, None]
        bed.flush()
        pending = output.with_suffix('.pending.flac')
        encoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'f32le', '-ar', str(RATE), '-ac', '2', '-i', '-',
                                    '-af', 'alimiter=limit=0.95:level=false', '-c:a', 'flac', '-compression_level', '5', str(pending)],
                                   stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        for begin in range(0, n, 10 * RATE):
            encoder.stdin.write(np.ascontiguousarray(bed[begin:min(n, begin + 10 * RATE)]).tobytes())
        _, error = encoder.communicate(timeout=900)
        if encoder.returncode:
            raise RuntimeError('Не вдалося зібрати музику: ' + error.decode(errors='replace')[-300:])
        pending.replace(output)
    finally:
        del bed
        work.unlink(missing_ok=True)
        output.with_suffix('.pending.flac').unlink(missing_ok=True)


def credits(project: dict) -> list[str]:
    """«Назва — виконавець» of the tracks the film's music used, for its description."""
    ids = store.read_json(store.project_dir(project['id']) / 'music-tracks.json', []) or []
    rows = {row['id']: row for row in catalog()}
    return [f"{rows[i]['title']}, {rows[i]['artist']}" for i in ids if i in rows]


def plan_key(segments: list[dict], total: float) -> str:
    return hashlib.sha256(json.dumps([segments, round(total, 3), TARGET_LUFS], sort_keys=True).encode()).hexdigest()[:16]
