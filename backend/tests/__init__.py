"""Backend tests. Some modules import their fixtures as `test_backend` and the studio's modules by name: the test folder
and the backend folder go on the path, so `python3 -m unittest backend.tests.test_x` (CLAUDE.md) loads every module
instead of failing on 12 of them (25 November 2026)."""
import sys
from pathlib import Path

for folder in (Path(__file__).resolve().parent, Path(__file__).resolve().parents[1]):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
