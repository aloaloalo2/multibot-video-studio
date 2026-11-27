"""tools/ must never shadow a backend module of the same name (27 November 2026: tools/music_library.py, a CLI wrapper,
took the place of backend/music_library.py once app.py had put tools/ first, and a film's music failed)."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ToolsPathTest(unittest.TestCase):
    def test_backend_module_wins_after_studio_start(self):
        code = ("import sys; sys.path[:0] = ['backend', 'engine']; import app; app.razgon_kit_at_start(); "
                "import motion_code; motion_code._modules(); import music_library; "
                "print(music_library.__file__); print(hasattr(music_library, 'selected'))")
        out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=120)
        lines = out.stdout.strip().splitlines()
        self.assertEqual(lines[-1], 'True', out.stdout + out.stderr)
        self.assertIn('backend', lines[-2])


if __name__ == '__main__':
    unittest.main()
