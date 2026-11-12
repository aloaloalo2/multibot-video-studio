"""Safe Git-based updates for the local Studio installation."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from update_backup import UpdateBackup


class UpdateError(Exception):
    pass


class Updater:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.state = {'status': 'not_configured'}
        self.failed = None   # A failed version stays available for an explicit retry after fixing dependencies.

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

    @staticmethod
    def protected(name):
        parts = Path(name).parts
        normalized = '/'.join(parts).casefold()
        return (normalized == 'backend' or normalized == 'backend/data' or normalized.startswith('backend/data/')
                or any(part.casefold() == '.env' or (part.casefold().startswith('.env.')
                       and part.casefold() not in {'.env.example', '.env.sample', '.env.template'})
                       or part.casefold().endswith(('.key', '.pem')) for part in parts))

    def _inspect(self):
        """Offer new main commits; local code is preserved automatically when applying them."""
        if not (self.root / '.git').exists():
            return {'status': 'not_configured'}
        if self.git('rev-parse', '--verify', '--quiet', 'origin/main', check=False).returncode:
            return {'status': 'not_configured'}
        local = self.text('rev-parse', 'HEAD')
        remote = self.text('rev-parse', 'origin/main')
        if local == remote or self.git('merge-base', '--is-ancestor', remote, 'HEAD', check=False).returncode == 0:
            return {'status': 'current'}
        changed = self.git('diff', '--name-only', '-z', 'HEAD', remote).stdout.split(b'\0')
        for raw in filter(None, changed):
            name = os.fsdecode(raw)
            if self.protected(name):
                return {'status': 'unsafe_update', 'files': [name]}
        if remote == self.failed:
            return {'status': 'update_failed', 'revision': remote, 'error': self.state.get('error', '')}
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
            with tempfile.TemporaryDirectory(prefix='videokey-import-check-') as cache:
                # Read fresh source without leaving new bytecode behind for a possible rollback.
                result = subprocess.run([sys.executable, '-B', '-X', 'pycache_prefix=' + cache, '-c', check],
                                        cwd=str(self.root), capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return str(exc)
        return None if result.returncode == 0 else result.stderr.decode('utf-8', 'replace').strip()[-600:]

    def apply(self):
        """Move the folder to GitHub's version; a version that does not load on this Mac is taken back at once, so the
        studio always starts (31 October 2026: a new package missing on the Mac would otherwise leave it dead)."""
        with self.lock:
            state = self._inspect()
            if state['status'] not in {'available', 'update_failed'}:
                raise UpdateError('Оновлення зараз недоступне.')
            backup = None
            try:
                backup = UpdateBackup(self, state['revision'])
                backup.prepare()
                self.git('checkout', '-B', 'main', state['revision'])
                backup.checked_out()
                problem = self.starts()
                if problem:
                    raise UpdateError(problem)
                backup.complete()
            except Exception as error:
                problem = str(error)
                if backup:
                    try:
                        backup.restore()
                    except Exception:
                        problem += '\nНе вдалося автоматично повернути всі файли. Резервна копія: ' + str(backup.folder)
                self.failed = state['revision']
                self.state = {'status': 'update_failed', 'error': problem, 'backup': str(backup.folder) if backup else None}
                raise UpdateError('Не вдалося оновити студію. Попередні файли збережено; можна спробувати ще раз.') from error
            self.failed = None
            self.state = {'status': 'current', 'backup': str(backup.folder)}

    def public_state(self):
        """Compact readiness, genuine failures, protected paths and the local recovery point."""
        with self.lock:
            state = {'status': self.state['status']}
            if self.state.get('files'):
                state.update(files=self.state['files'][:8], more=max(0, len(self.state['files']) - 8))
            if self.state.get('branch'):
                state['branch'] = self.state['branch']
            if self.state.get('error'):
                state['error'] = self.state['error'][-400:]
            if self.state.get('backup'):
                state['backup'] = self.state['backup']
            return state


def update_at_start(root):
    manager = Updater(root)
    status = manager.refresh()['status']
    if status in {'available', 'update_failed'}:
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
        elif outcome == 'unsafe_update':
            print('Оновлення зачіпає особисті дані або ключі. Файли залишено на місці.')
