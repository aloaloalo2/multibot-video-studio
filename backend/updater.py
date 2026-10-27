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

    def _inspect(self):
        if not (self.root / '.git').exists():
            return {'status': 'not_configured'}
        upstream = self.git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}', check=False)
        if upstream.returncode:
            return {'status': 'not_configured'}
        if not upstream.stdout.decode('utf-8', 'replace').strip().startswith('origin/'):
            return {'status': 'not_configured'}
        if self.git('status', '--porcelain', '--untracked-files=all').stdout:
            return {'status': 'local_changes'}
        local = self.text('rev-parse', 'HEAD')
        remote = self.text('rev-parse', '@{upstream}')
        if local == remote:
            return {'status': 'current'}
        if self.git('merge-base', '--is-ancestor', 'HEAD', '@{upstream}', check=False).returncode != 0:
            return {'status': 'diverged'}
        changed = self.git('diff', '--name-only', '-z', 'HEAD', '@{upstream}').stdout.split(b'\0')
        tracked = set(self.git('ls-files', '-z').stdout.split(b'\0'))
        for raw in filter(None, changed):
            name = os.fsdecode(raw)
            if name == 'backend/data' or name.startswith('backend/data/'):
                return {'status': 'unsafe_update'}
            if raw not in tracked and (self.root / name).exists():
                return {'status': 'unsafe_update'}
        return {'status': 'available', 'revision': remote}

    def refresh(self):
        with self.lock:
            try:
                if not (self.root / '.git').exists() or self.git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}', check=False).returncode:
                    self.state = {'status': 'not_configured'}
                else:
                    self.git('fetch', '--quiet', '--no-tags', 'origin', timeout=30)
                    self.state = self._inspect()
            except UpdateError:
                self.state = {'status': 'offline'}
            return dict(self.state)

    def apply(self):
        with self.lock:
            state = self._inspect()
            if state['status'] != 'available':
                raise UpdateError('Оновлення недоступне або є незбережені зміни програми.')
            self.git('merge', '--ff-only', '--no-edit', state['revision'])
            self.state = {'status': 'current'}

    def public_state(self):
        with self.lock:
            return {'status': self.state['status']}


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
        elif outcome in {'local_changes', 'diverged', 'unsafe_update'}:
            print('Оновлення пропущено: локальні файли або дані потребують перевірки.')
