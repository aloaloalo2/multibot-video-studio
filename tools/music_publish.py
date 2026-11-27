#!/usr/bin/env python3
"""Publish this Mac's new music-library tracks to https://github.com/aloaloalo2/videokey-music-library, so every other
Mac's studio downloads them at its next start (backend/music_sync.py). Needs `gh` signed in with write access.

  python3 tools/music_publish.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import music_sync  # noqa: E402

if __name__ == "__main__":
    print(music_sync.push())
