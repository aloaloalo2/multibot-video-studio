import os
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[2] / "razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit"
sys.path.insert(0, str(KIT / "tools"))
import project_lock  # noqa: E402


class ProjectLockTest(unittest.TestCase):
    def test_a_relative_path_from_another_folder_makes_no_folders_there(self):
        # user, 15 November 2026: an empty «projects/<slug>/build» appeared in the YouTube folder
        here = Path(tempfile.mkdtemp())
        old = os.getcwd()
        os.chdir(here)
        try:
            with self.assertRaises(SystemExit):
                with project_lock.project_files("projects/some-episode"):
                    pass
        finally:
            os.chdir(old)
        self.assertEqual(list(here.iterdir()), [])

    def test_a_real_project_gets_its_lock(self):
        project = Path(tempfile.mkdtemp())
        (project / "story").mkdir()
        with project_lock.project_files(project):
            self.assertTrue((project / "build" / ".files.lock").is_file())


if __name__ == "__main__":
    unittest.main()
