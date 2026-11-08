"""Small, versioned read-only project cache for bursts of preview media requests."""
from collections import OrderedDict
import threading
import store

_LOCK = threading.RLock()
_PROJECTS = OrderedDict()
_MAX_PROJECTS = 4


def resolve(pid, aid):
    # Timeline/asset edits and deletion change the project file atomically. Read
    # its stamp on every request; never reuse a project from a different version.
    stat = store.project_path(pid).stat()
    version = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    with _LOCK:
        hit = _PROJECTS.get(pid)
        if hit is None or hit[0] != version:
            project = store.load_project(pid)
            _PROJECTS[pid] = (version, project)
        else:
            project = hit[1]
        _PROJECTS.move_to_end(pid)
        while len(_PROJECTS) > _MAX_PROJECTS:
            _PROJECTS.popitem(last=False)
        try:
            # Still validate the actual path on each request, including symlinks
            # and retained audio. Cached metadata never grants file access.
            asset = store.resolve_asset(project, aid)
        except store.StudioError as error:
            if error.status != 404 or hit is None:
                raise
            # A new derived channel-logo ID can appear without a timeline edit.
            project = store.load_project(pid)
            _PROJECTS[pid] = (version, project)
            asset = store.resolve_asset(project, aid)
    return project, asset
