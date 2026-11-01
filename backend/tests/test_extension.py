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
            (origin / "manifest.json").write_text(json.dumps({"name": "Multi Bot", "version": "2.88", "permissions": ["tabs"]}))
            (origin / "popup.html").write_text("<html><head><style>\n body{}\n  </style></head><body>\n  <div>Meet</div>\n  <script src=\"popup.js\"></script>\n</body></html>\n")
            (origin / "popup.js").write_text("// meet search\n")
            sh("git", "add", ".", cwd=origin); sh("git", "commit", "-qm", "one", cwd=origin)
            sh("git", "config", "receive.denyCurrentBranch", "updateInstead", cwd=origin)
            sh("git", "clone", "-q", str(origin), str(folder), cwd=tmp)
            (origin / "manifest.json").write_text(json.dumps({"name": "Multi Bot", "version": "2.89", "permissions": ["tabs"]}))
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
                with mock.patch.object(extension, "add_item") as add:
                    unsaved = extension.update()                 # unsaved work: the item only, no pull, no commit
                    add.assert_called_once_with(folder, in_git=False)
                self.assertEqual((unsaved["version"], unsaved["behind"]), ("2.88", 1))
                (folder / "notes.txt").unlink()
                done = extension.update()
                # the newer version came in, then the «VideoKey Studio» item went on top of it, one step up
                self.assertEqual((done["version"], done["behind"], done["item"], done["ahead"]), ("2.90", 0, True, 0))
                self.assertTrue((tmp / "helper-ran").is_file())
                html = (folder / "popup.html").read_text()
                self.assertIn("Meet", html)                          # the private version's own features stay
                self.assertLess(html.index('id="studioOpen"'), html.index('<script src="popup.js">'))
                self.assertIn("nativeMessaging", json.loads((folder / "manifest.json").read_text())["permissions"])
                self.assertIn("VideoKey Studio item", subprocess.run(["git", "log", "-1", "--format=%s"], cwd=origin, capture_output=True, text=True).stdout)
                self.assertIsNone(extension.add_item(folder, True))  # once only


if __name__ == "__main__":
    unittest.main()
