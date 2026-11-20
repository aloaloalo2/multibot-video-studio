"""An episode published on YouTube, read from the blue Finder tag on its folder and kept by the studio.

The user's ChatGPT marks an episode folder with Finder's blue tag once the video is on YouTube (user, 16 November 2026:
«синій кружочок біля папки… відмічає ролики, які опубліковані… відмітити другою галочкою… навіть якщо я видалю ту
папку… щоб та друга галочка нікуди не зникла»). The studio notices the tag and writes published.json in the project,
so the mark stays when the folder is gone or the tag is removed.
"""
from __future__ import annotations

import plistlib
import subprocess
import time
from pathlib import Path

import store

BLUE = 4                       # Finder's colour number of the blue tag, whatever its name in the system language
_SEEN: dict[str, tuple] = {}   # folder -> (its change time, blue?) so the list does not ask Finder every few seconds


def path(pid: str) -> Path:
    return store.project_dir(pid) / 'published.json'


def blue(folder: Path) -> bool:
    try:
        stamp = folder.stat().st_ctime_ns   # setting a tag changes the folder's change time
    except OSError:
        return False
    cached = _SEEN.get(str(folder))
    if cached and cached[0] == stamp:
        return cached[1]
    found = False
    try:
        raw = subprocess.run(['xattr', '-px', 'com.apple.metadata:_kMDItemUserTags', str(folder)],
                             capture_output=True, text=True, timeout=5)
        if raw.returncode == 0:
            tags = plistlib.loads(bytes.fromhex(''.join(raw.stdout.split())))
            found = isinstance(tags, list) and any(str(tag).rsplit('\n', 1)[-1] == str(BLUE) for tag in tags if '\n' in str(tag))
    except Exception:   # an odd tag from another app never breaks the project list
        found = False
    if not found:
        # Finder also keeps a folder's colour in its FinderInfo flags (bits 1-3 of byte 9): the blue dot the user saw
        # was written that way, with no tag at all (16 November 2026)
        try:
            info = subprocess.run(['xattr', '-px', 'com.apple.FinderInfo', str(folder)], capture_output=True, text=True, timeout=5)
            raw = bytes.fromhex(''.join(info.stdout.split())) if info.returncode == 0 else b''
            found = len(raw) > 9 and (raw[9] >> 1) & 7 == BLUE
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    _SEEN[str(folder)] = (stamp, found)
    return found


def check(item: dict) -> dict | None:
    """The saved mark of a listed project, written once when its folder first shows the blue tag."""
    saved = store.read_json(path(item['id']), None)
    if isinstance(saved, dict) and saved.get('at'):
        return saved
    folder = item.get('episode_path')
    if folder and blue(Path(folder)):
        saved = {'at': time.time(), 'source': 'finder-blue-tag'}
        try:
            store.atomic_json(path(item['id']), saved)
        except OSError:
            pass
        return saved
    return None


STARTING_MINUTES = 10   # a session opened by the button has this long to start waiting before another is opened


def queue_path() -> Path:
    return store.DATA_ROOT / 'youtube-queue.json'


def queue() -> list:
    """The episodes waiting for the publishing session. A project deleted while it waited leaves the queue by itself
    (user, 20 November 2026: «я видалив проект а спинер… крутиться в черзі на публікацію»)."""
    rows = store.read_json(queue_path(), [])
    rows = rows if isinstance(rows, list) else []
    alive = [row for row in rows if isinstance(row, dict) and row.get('project')
             and (store.PROJECTS_ROOT / str(row['project']) / 'project.json').exists()]
    if len(alive) != len(rows):
        store.atomic_json(queue_path(), alive)
    return alive


def listener() -> bool:
    """A publishing session on this Mac waits with tools/youtube_publish.py wait: its process is alive. Another Mac has
    none until the author starts one (user, 19 November 2026: «а на іншому комп'ютері… може не буде така сесія»)."""
    import os
    pid = (store.read_json(store.DATA_ROOT / 'youtube-listener.json', {}) or {}).get('pid')
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    # the pid must still be the waiting script, and its session must still be there: a session closed while it waited
    # left the script running under launchd (pid 1), and «Опублікувати» queued episodes nobody took and opened no new
    # session (user, 20 November 2026: «нажав опубликувати але в клод тепер не перекинуло»)
    return waiting_script(int(pid))


def waiting_script(pid: int) -> bool:
    import os
    import signal
    import subprocess

    def row(p: int) -> tuple[int, str]:
        out = subprocess.run(['ps', '-o', 'ppid=,command=', '-p', str(p)], capture_output=True, text=True, timeout=5).stdout.strip()
        parent, _, command = out.partition(' ')
        return (int(parent) if parent.strip().isdigit() else 0), command
    try:
        parent, command = row(pid)
        if 'youtube_publish.py' not in command or 'wait' not in command:
            return False   # the pid was reused by another program
        shell = parent
        if shell <= 1 or row(shell)[0] <= 1:
            os.kill(pid, signal.SIGTERM)   # an orphan: its session is gone, nobody would act on what it hears
            return False
    except (OSError, ValueError, subprocess.SubprocessError):
        return True   # cannot tell: keep the old behaviour
    return True


def in_progress() -> bool:
    """A publishing session is uploading an episode right now (tools/youtube_publish.py prepare, no «done» yet)."""
    for marker in store.PROJECTS_ROOT.glob('*/publishing.json'):
        try:
            item = store.listed_project(marker.parent / 'project.json')
        except (OSError, ValueError, store.StudioError):
            continue
        if publishing({**item, 'id': marker.parent.name, 'published': store.read_json(path(marker.parent.name), None)}) == 'publishing':
            return True
    return False


def session_task(project: dict) -> str:
    root = store.APP_ROOT
    return (f"Опублікуй на YouTube випуски з черги студії по одному, першим «{project.get('name')}» (проєкт студії {project['id']}). "
            f"Порядок і правила: {root}/docs/YOUTUBE_PUBLISH.md, інструмент: python3 \"{root}/tools/youtube_publish.py\". "
            "Якщо цей випуск уже є в «Контенті» каналу чернеткою, продовж її, а не завантажуй удруге. "
            "Після публікації стань сесією публікації: запусти у фоні (Bash, run_in_background) wait і, коли він закінчиться, "
            "публікуй наступний випуск з черги так само.")


def open_claude(project: dict) -> bool:
    """A new Claude Code session with the task filled in, opened by the studio on this Mac itself (`open claude://…`): a
    link from the page made the browser ask «Відкрити Claude?» every time (user, 19 November 2026: «я такого не хотів»).
    The author presses Enter in it."""
    import subprocess
    import urllib.parse
    link = 'claude://code/new?source=desktop_action&prompt=' + urllib.parse.quote(session_task(project))
    try:
        return subprocess.run(['open', link], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def enqueue(pid: str) -> dict:
    """«Опублікувати» on the card: the episode waits for the publishing session, which listens with
    `tools/youtube_publish.py wait` (user, 19 November 2026: «просто відправити в Клод, щоб він опублікував»)."""
    project = store.load_project(pid)
    if (store.read_json(path(pid), {}) or {}).get('at'):
        raise store.StudioError('Цей випуск уже опубліковано', 409)
    (store.project_dir(pid) / 'publishing.json').unlink(missing_ok=True)   # a stopped attempt starts again
    rows = [row for row in queue() if row.get('project') != pid]
    rows.append({'project': pid, 'channel_id': project.get('channel_id'), 'at': time.time()})
    store.atomic_json(queue_path(), rows)
    # One publishing session at a time: a new one is opened only when none waits, none is publishing and none was opened
    # in the last minutes. Three episodes sent at once wait in the queue for that one session, which publishes them in
    # turn (they would otherwise fight over the file server's port).
    working = listener() or in_progress()
    starting = store.DATA_ROOT / 'youtube-session-opened.json'
    # a session opened in the last minutes is still starting only while other episodes wait for it: with this one alone
    # in the queue nothing is waiting for that session (it was cancelled or its episode deleted), so a new one opens
    # (user, 20 November 2026: «нажав але не перекинуло в клод» after «Скасувати» and «Опублікувати» again)
    others = len(rows) > 1
    recent = others and time.time() - float((store.read_json(starting, {}) or {}).get('at') or 0) < STARTING_MINUTES * 60
    open_session = not working and not recent
    if open_session:
        store.atomic_json(starting, {'at': time.time()})
        open_session = open_claude(project)
    return {'queued': True, 'position': len(rows), 'listener': working, 'open_session': open_session,
            'studio_root': str(store.APP_ROOT)}


STALE_MINUTES = 15   # a publishing session that marks no step for this long has stopped (a lost connection, a refusal)


def cancel(pid: str) -> dict:
    """«Скасувати» on a card waiting or being published (user, 20 November 2026: «нажав випадково… щоб я міг відмінити
    в студії»): the episode leaves the queue; a session already at work finds the mark at its next step
    (tools/youtube_publish.py step/endscreen/done) and stops without scheduling the video."""
    store.load_project(pid)
    rows = queue()
    was_queued = any(row.get('project') == pid for row in rows)
    store.atomic_json(queue_path(), [row for row in rows if row.get('project') != pid])
    marker = store.project_dir(pid) / 'publishing.json'
    state = store.read_json(marker, {}) or {}
    working = bool(state.get('at'))
    store.atomic_json(marker, {'cancelled': time.time(), **({'was': state} if state else {})})
    if not queue():
        (store.DATA_ROOT / 'youtube-session-opened.json').unlink(missing_ok=True)   # nothing waits for that session now
    return {'cancelled': True, 'was_queued': was_queued, 'was_publishing': working}


def publishing(item: dict) -> str | None:
    """'queued' while the episode waits for the publishing session; 'publishing' while tools/youtube_publish.py marks its
    steps; 'stopped' when the session said it failed or went quiet (user, 19 November 2026: «публікація зупинилась… я б
    це мав би в студії бачити»); None otherwise or once it is on YouTube."""
    if (item.get('published') or {}).get('at'):
        return None
    if any(row.get('project') == item['id'] for row in queue()):
        return 'queued'
    state = store.read_json(store.project_dir(item['id']) / 'publishing.json', {}) or {}
    if not state.get('at'):
        return None
    if state.get('failed'):
        return 'stopped'
    last = float(state.get('updated') or state.get('at') or 0)
    if time.time() - last < STALE_MINUTES * 60:
        return 'publishing'
    return 'stopped' if time.time() - float(state['at']) < 7 * 86400 else None


def stopped_note(pid: str) -> str:
    state = store.read_json(store.project_dir(pid) / 'publishing.json', {}) or {}
    return state.get('failed') or (f"Остання дія: {state['step']}" if state.get('step') else '')


def active_projects() -> dict:
    """{project id: channel id} of the episodes in the YouTube queue or being published (user, 19 November 2026: their
    channel's spinner turns and counts them). A publication never blocks a studio restart: it runs in its own session."""
    found = {row['project']: row.get('channel_id') for row in queue() if row.get('project')}
    for marker in store.PROJECTS_ROOT.glob('*/publishing.json'):
        pid = marker.parent.name
        try:
            item = store.listed_project(marker.parent / 'project.json')
        except (OSError, ValueError, store.StudioError):
            continue
        if publishing({**item, 'id': pid, 'published': store.read_json(path(pid), None)}) == 'publishing':
            found[pid] = item.get('channel_id')
    return {pid: cid for pid, cid in found.items() if cid}


def active_channels() -> set:
    return set(active_projects().values())


STALL_SECONDS = 60


def ensure_session() -> bool:
    """Episodes wait in the queue and nobody takes them (a session that stopped and did not wait again, the app restarted):
    the studio opens one new publishing session itself (user, 19 November 2026: «у черзі на публікацію висить… і нічого
    не відбувається»). Called with the studio's status, so within seconds; at most one session per STARTING_MINUTES."""
    rows = queue()
    if not rows or time.time() - float(rows[0].get('at') or 0) < STALL_SECONDS or listener() or in_progress():
        return False
    starting = store.DATA_ROOT / 'youtube-session-opened.json'
    if time.time() - float((store.read_json(starting, {}) or {}).get('at') or 0) < STARTING_MINUTES * 60:
        return False
    try:
        project = store.load_project(rows[0]['project'])
    except store.StudioError:
        store.atomic_json(queue_path(), rows[1:])   # a deleted episode leaves the queue
        return False
    store.atomic_json(starting, {'at': time.time()})
    return open_claude(project)
