"""tools/doctor.py: one readable line per check and an exit code that says whether anything needed is missing."""
import io
import sys
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
        with patch.object(doctor.shutil, "which", side_effect=lambda name: None if name == "ffprobe" else real(name)), redirect_stdout(out):
            code = doctor.main([])
        text = out.getvalue()
        for part in ("Python і пакети", "Програми", "Розпізнавання озвучки", "Агенти", "2D-анімація Razgon", "Оновлення", "Перевірка запуску"):
            self.assertIn(part, text)
        self.assertIn("✗ ffprobe", text)
        self.assertIn("brew install ffmpeg", text)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
