"""tools/doctor.py: one readable line per check and an exit code that says whether anything needed is missing."""
import io
import subprocess
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import doctor  # noqa: E402


class DoctorTest(unittest.TestCase):
    def test_every_part_is_checked_and_a_missing_program_is_named_with_its_fix(self):
        out = io.StringIO()
        real = doctor.shutil.which
        # the update check asks GitHub and the start check imports the whole server in a new Python (about 15 s on a busy
        # Mac): both answer here at once, the report's lines are what this test reads
        updater = types.SimpleNamespace(Updater=lambda root: types.SimpleNamespace(refresh=lambda: {"status": "current"}))
        started = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(doctor.shutil, "which", side_effect=lambda name: None if name == "ffprobe" else real(name)), \
             patch.dict(sys.modules, {"updater": updater}), patch.object(doctor, "run", return_value=started), redirect_stdout(out):
            code = doctor.main([])
        text = out.getvalue()
        for part in ("Python і пакети", "Програми", "Розпізнавання озвучки", "Агенти", "2D-анімація Razgon", "Оновлення", "Перевірка запуску"):
            self.assertIn(part, text)
        self.assertIn("✗ ffprobe", text)
        self.assertIn("brew install ffmpeg", text)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
