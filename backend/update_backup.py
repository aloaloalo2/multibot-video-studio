"""Local Git recovery points for an installation update. No project data is copied or removed."""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path


def exists(path):
    return os.path.lexists(path)


class UpdateBackup:
    def __init__(self, manager, target):
        self.manager = manager
        self.root = manager.root
        self.identity = str(time.time_ns()) + '-' + uuid.uuid4().hex[:8]
        self.ref = 'refs/studio-update-backups/' + self.identity
        folder = Path(manager.text('rev-parse', '--git-path', 'studio-update-backups'))
        folder = folder if folder.is_absolute() else self.root / folder
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        folder.chmod(0o700)
        self.folder = folder / self.identity
        self.folder.mkdir(mode=0o700)
        branch = manager.git('symbolic-ref', '--quiet', '--short', 'HEAD', check=False)
        main = manager.git('rev-parse', '--verify', 'refs/heads/main', check=False)
        self.data = {'id': self.identity, 'head': manager.text('rev-parse', 'HEAD'),
                     'branch': branch.stdout.decode().strip() if branch.returncode == 0 else None,
                     'main': main.stdout.decode().strip() if main.returncode == 0 else None,
                     'target': target, 'files': [], 'stash': None, 'checked_out': False, 'status': 'preparing'}
        manager.git('update-ref', self.ref + '/head', self.data['head'])
        if self.data['main']:
            manager.git('update-ref', self.ref + '/main', self.data['main'])
        self.write()

    def write(self):
        temp = self.folder / 'manifest.tmp'
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.folder / 'manifest.json')

    def save_tracked(self):
        m = self.manager
        if not m.git('status', '--porcelain=v1', '--untracked-files=no').stdout.strip():
            return
        before = m.git('rev-parse', '--verify', 'refs/stash', check=False).stdout.strip()
        try:
            # A normal installation needs no personal Git identity. Unrelated untracked files stay in place.
            m.git('-c', 'user.name=VideoKey Studio', '-c', 'user.email=studio@localhost',
                  'stash', 'push', '--quiet', '--message', 'VideoKey Studio update ' + self.identity, timeout=120)
        finally:
            after = m.git('rev-parse', '--verify', 'refs/stash', check=False).stdout.strip()
            if after and after != before:
                self.data['stash'] = after.decode()
                m.git('update-ref', self.ref + '/changes', self.data['stash'])
                self.write()

    def save_collisions(self):
        """Move only local paths a checkout would replace, including ignored files and symlink parents."""
        m = self.manager
        tracked = set(filter(None, m.git('ls-files', '-z').stdout.decode('utf-8', 'surrogateescape').split('\0')))
        targets = m.git('ls-tree', '-r', '--name-only', '-z', self.data['target']).stdout.decode('utf-8', 'surrogateescape').split('\0')
        collisions = set()
        for name in filter(None, targets):
            if name in tracked:
                continue
            parts = Path(name).parts
            for index in range(1, len(parts) + 1):
                relative = '/'.join(parts[:index])
                if relative in tracked:
                    break  # Git replaces its own old file or symlink without following it.
                path = self.root / relative
                if exists(path) and (path.is_symlink() or not path.is_dir() or index == len(parts)):
                    collisions.add(relative)
                    break
        for name in sorted(collisions, key=lambda item: (item.count('/'), item)):
            if any(name.startswith(parent + '/') for parent in self.data['files']):
                continue
            if m.protected(name):
                raise ValueError('Оновлення зачепило б особисті дані: ' + name)
            destination = self.folder / 'files' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.data['files'].append(name)
            self.write()  # The recovery manifest exists before moving the original.
            shutil.move(str(self.root / name), str(destination))

    def prepare(self):
        self.save_tracked()
        self.save_collisions()
        if (self.manager.text('rev-parse', 'HEAD') != self.data['head']
                or self.manager.git('status', '--porcelain=v1', '--untracked-files=no').stdout.strip()):
            raise ValueError('Код змінився під час підготовки оновлення. Резервну копію збережено.')
        self.data['status'] = 'ready'
        self.write()

    def checked_out(self):
        self.data['checked_out'] = True
        self.data['status'] = 'checking'
        self.write()

    def restore(self):
        """Rollback this transaction, retaining every saved Git object and any new conflicting local path."""
        m, d = self.manager, self.data
        current = m.text('rev-parse', 'HEAD')
        if d['checked_out']:
            if current != d['target']:
                raise ValueError('Git змінився після оновлення. Резервну копію збережено окремо.')
            if d['branch']:
                m.git('checkout', '-B', d['branch'], d['head'])
            else:
                m.git('checkout', '--detach', d['head'])
            if d['branch'] != 'main':
                if d['main']:
                    m.git('update-ref', 'refs/heads/main', d['main'], d['target'])
                else:
                    m.git('update-ref', '-d', 'refs/heads/main', d['target'])
        elif current != d['head']:
            raise ValueError('Git змінився під час підготовки. Резервну копію збережено окремо.')
        for name in reversed(d['files']):
            source, destination = self.folder / 'files' / name, self.root / name
            if not exists(source):
                continue
            if exists(destination):
                extra = self.folder / 'rollback-files' / name
                extra.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(extra))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
        if d['stash']:
            m.git('stash', 'apply', '--index', d['stash'], timeout=120)
        d['status'] = 'restored'
        self.write()

    def complete(self):
        self.data['status'] = 'updated'
        self.write()
