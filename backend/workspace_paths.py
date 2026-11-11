"""Shared location of channel folders for the server and standalone Studio tools."""

import json
import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YOUTUBE_ROOT = APP_ROOT.parent


def youtube_root() -> Path:
    data = Path(os.environ.get('MULTIBOT_STUDIO_DATA', str(APP_ROOT / 'backend' / 'data'))).expanduser().resolve()
    try:
        settings = json.loads((data / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        settings = {}
    value = settings.get('youtube_root') if isinstance(settings, dict) else None
    if isinstance(value, str) and value.strip() and '\x00' not in value:
        folder = Path(value).expanduser()
        if folder.is_absolute():
            # Keep an unplugged drive selected. Falling back could save new files in another workspace.
            return folder.resolve()
    return DEFAULT_YOUTUBE_ROOT


def app_relative_to(root: Path) -> str:
    return Path(os.path.relpath(APP_ROOT, root)).as_posix()
