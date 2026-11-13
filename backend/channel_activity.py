"""Compact channel completion notices, derived only from work observed running."""
import threading
import time


class Notices:
    def __init__(self):
        self.lock = threading.RLock()
        self.running = {}
        self.finished = {}

    def update(self, active_channels, tasks, outcome):
        with self.lock:
            active = set(active_channels)
            for task in tasks:
                cid = task.get('channel_id')
                if not cid:
                    continue
                key = (task.get('project_id'), task['kind'], task.get('job_id'), task.get('language'))
                self.running.setdefault(cid, {})[key] = dict(task)
            for cid in list(self.running):
                if cid in active:
                    continue
                results = []
                for task in self.running[cid].values():
                    try:
                        results.append(outcome(task))
                    except Exception:
                        # An unreadable receipt must never become a success checkmark.
                        results.append(None)
                self.finished[cid] = {
                    'id': str(time.time_ns()),
                    'status': 'done' if results and all(value in {'done', 'complete', 'completed', 'ready'} for value in results) else 'stopped',
                }
                del self.running[cid]
            return {cid: dict(value) for cid, value in self.finished.items()}


notices = Notices()
