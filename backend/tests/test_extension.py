import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extension
import store


def sh(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class ExtensionTest(unittest.TestCase):
    def test_it_finds_multi_bot_updates_it_and_never_over_local_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            origin, folder = tmp / "origin", tmp / "flow-bot" / "heygen-grabber"
            origin.mkdir()
            sh("git", "init", "-q", "-b", "main", cwd=origin)
            sh("git", "config", "user.email", "a@b", cwd=origin); sh("git", "config", "user.name", "a", cwd=origin)
            (origin / "manifest.json").write_text(json.dumps({"name": "Multi Bot", "version": "2.88"}))
            sh("git", "add", ".", cwd=origin); sh("git", "commit", "-qm", "one", cwd=origin)
            sh("git", "clone", "-q", str(origin), str(folder), cwd=tmp)
            (origin / "manifest.json").write_text(json.dumps({"name": "Multi Bot", "version": "2.89"}))
            sh("git", "commit", "-qam", "two", cwd=origin)
            profile = tmp / "support" / "Google" / "Chrome" / "Default"
            profile.mkdir(parents=True)
            (profile / "Preferences").write_text(json.dumps({"extensions": {"settings": {
                "abc": {"manifest": {"name": "Multi Bot"}, "path": str(folder)}, "xyz": {"manifest": {"name": "Other"}, "path": str(tmp)}}}}))
            helper = tmp / "helper.py"
            helper.write_text("import pathlib; pathlib.Path(%r).write_text('ok')\n" % str(tmp / "helper-ran"))
            with mock.patch.object(extension, "SUPPORT", tmp / "support"), mock.patch.object(extension, "HELPER", helper):
                found = extension.state()
                self.assertEqual((found["path"], found["version"], found["behind"], found["dirty"]), (str(folder), "2.88", 1, []))
                (folder / "notes.txt").write_text("my own file")
                with self.assertRaises(store.StudioError):       # the author's own change is never overwritten
                    extension.update()
                (folder / "notes.txt").unlink()
                done = extension.update()
                self.assertEqual((done["version"], done["behind"]), ("2.89", 0))
                self.assertTrue((tmp / "helper-ran").is_file())


if __name__ == "__main__":
    unittest.main()
