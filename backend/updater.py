"""Safe Git-based updates for the local Studio installation."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path


class UpdateError(Exception):
    pass


class Updater:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.state = {'status': 'not_configured'}
        self.failed = None   # a GitHub version that did not load here: offered again only when a newer one comes

    def git(self, *arguments, check=True, timeout=30):
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
        try:
            result = subprocess.run(['git', *arguments], cwd=str(self.root), env=env,
                                    capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UpdateError('Не вдалося перевірити оновлення.') from exc
        if check and result.returncode:
            raise UpdateError('Не вдалося отримати оновлення. Перевірте доступ до GitHub.')
        return result

    def text(self, *arguments):
        return self.git(*arguments).stdout.decode('utf-8', 'replace').strip()

    def _changed_files(self):
        """Files of the studio folder that differ from Git or are not in it (ignored ones aside)."""
        out = self.git('status', '--porcelain=v1', '-z', '--untracked-files=all').stdout.split(b'\0')
        names, skip = [], False
        for entry in out:
            if skip:          # the old name of a renamed file
                skip = False
                continue
            if len(entry) > 3:
                names.append(os.fsdecode(entry[3:]))
                skip = entry[:1] in (b'R', b'C')
        return names

    def _off_main(self):
        """The branch the folder stands on when it is not main and GitHub's main has commits it lacks: such a
        folder never receives the new versions (an agent switched it to its own branch and left it there)."""
        branch = self.text('rev-parse', '--abbrev-ref', 'HEAD')
        if branch == 'main' or self.git('rev-parse', '--verify', '--quiet', 'origin/main', check=False).returncode:
            return None
        if self.git('merge-base', '--is-ancestor', 'origin/main', 'HEAD', check=False).returncode == 0:
            return None
        return branch

    def _inspect(self):
        """What an update would do now. A blocked update says why: the files in the way, or the branch."""
        if not (self.root / '.git').exists():
            return {'status': 'not_configured'}
        upstream = self.git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}', check=False)
        if upstream.returncode or not upstream.stdout.decode('utf-8', 'replace').strip().startswith('origin/'):
            branch = self._off_main()
            return {'status': 'other_branch', 'branch': branch} if branch else {'status': 'not_configured'}
        local = self.text('rev-parse', 'HEAD')
        remote = self.text('rev-parse', '@{upstream}')
        if local == remote:
            branch = self._off_main()
            return {'status': 'other_branch', 'branch': branch} if branch else {'status': 'current'}
        changed = self._changed_files()
        if changed:
            return {'status': 'local_changes', 'files': changed}
        if self.git('merge-base', '--is-ancestor', 'HEAD', '@{upstream}', check=False).returncode != 0:
            return {'status': 'diverged'}
        changed = self.git('diff', '--name-only', '-z', 'HEAD', '@{upstream}').stdout.split(b'\0')
        tracked = set(self.git('ls-files', '-z').stdout.split(b'\0'))
        for raw in filter(None, changed):
            name = os.fsdecode(raw)
            if name == 'backend/data' or name.startswith('backend/data/'):
                return {'status': 'unsafe_update', 'files': [name]}
            if raw not in tracked and (self.root / name).exists():
                return {'status': 'unsafe_update', 'files': [name]}
        if remote == self.failed:
            return {'status': 'update_failed', 'error': self.state.get('error', '')}
        return {'status': 'available', 'revision': remote}

    def refresh(self):
        # the fetch runs outside the lock: on a slow network the page asking for the state must not wait 30 s for it
        try:
            if not (self.root / '.git').exists() or self.git('remote', 'get-url', 'origin', check=False).returncode:
                state = {'status': 'not_configured'}
            else:
                self.git('fetch', '--quiet', '--no-tags', 'origin', timeout=30)
                with self.lock:
                    state = self._inspect()
        except UpdateError:
            state = {'status': 'offline'}
        with self.lock:
            self.state = state
            return dict(self.state)

    def starts(self):
        """None when the studio's code in the folder loads (every module and package it needs is there), otherwise the
        tail of the error. A folder without the studio's server (tests of the updater itself) always passes."""
        if not (self.root / 'backend' / 'app.py').is_file():
            return None
        check = 'import sys; sys.path[:0] = ["backend", "engine"]; import app'
        try:
            result = subprocess.run([sys.executable, '-c', check], cwd=str(self.root), capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return str(exc)
        return None if result.returncode == 0 else result.stderr.decode('utf-8', 'replace').strip()[-600:]

    def apply(self):
        """Move the folder to GitHub's version; a version that does not load on this Mac is taken back at once, so the
        studio always starts (31 October 2026: a new package missing on the Mac would otherwise leave it dead)."""
        with self.lock:
            state = self._inspect()
            if state['status'] != 'available':
                raise UpdateError('Оновлення недоступне або є незбережені зміни програми.')
            before = self.text('rev-parse', 'HEAD')
            self.git('merge', '--ff-only', '--no-edit', state['revision'])
            problem = self.starts()
            if problem:
                self.git('reset', '--keep', before)
                self.failed = state['revision']
                self.state = {'status': 'update_failed', 'error': problem}
                raise UpdateError('Нова версія студії не запускається на цьому комп’ютері, тому студія лишилась на попередній.')
            self.state = {'status': 'current'}

    def public_state(self):
        """The status for the page; a blocked update also names up to eight files in the way, or the branch."""
        with self.lock:
            state = {'status': self.state['status']}
            if self.state.get('files'):
                state.update(files=self.state['files'][:8], more=max(0, len(self.state['files']) - 8))
            if self.state.get('branch'):
                state['branch'] = self.state['branch']
            if self.state.get('error'):
                state['error'] = self.state['error'][-400:]
            return state


def update_at_start(root):
    manager = Updater(root)
    status = manager.refresh()['status']
    if status == 'available':
        try:
            manager.apply()
            return 'updated'
        except UpdateError:
            return 'error'
    return status


if __name__ == '__main__':
    if sys.argv[1:] == ['--at-start']:
        outcome = update_at_start(Path(__file__).resolve().parents[1])
        if outcome == 'updated':
            print('Студію оновлено.')
        elif outcome == 'error':
            print('Нова версія не запускається на цьому комп’ютері: студія лишилась на попередній. Причину показує кнопка у студії.')
        elif outcome in {'local_changes', 'diverged', 'unsafe_update', 'other_branch'}:
            print('Оновлення пропущено: причину показує кнопка «Оновлення зупинене» у студії.')
