import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

TOOL = Path(__file__).resolve().parents[2] / "razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit/tools/library.py"
spec = importlib.util.spec_from_file_location("asset_library", TOOL)
library = importlib.util.module_from_spec(spec); spec.loader.exec_module(library)


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "props").mkdir()
        self.catalog = {"props": [{"name": "rocket" if n == 0 else f"rocket_{n:02d}", "description": "space capsule",
                                   "projects": ["old"], "sha256": "hash"} for n in range(30)]}
        for p in (patch.object(library, "load", return_value=self.catalog), patch.object(library, "LIBRARY", self.root)):
            p.start(); self.addCleanup(p.stop)

    def test_default_search_is_six_text_candidates_with_exact_name_first(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(Image, "open") as opened:
            library.search(["rocket"])
        self.assertTrue(out.getvalue().splitlines()[0].startswith("rocket "))
        self.assertEqual(len(out.getvalue().splitlines()), 7)
        opened.assert_not_called()

    def test_one_small_sheet_for_candidates(self):
        for p in self.catalog["props"][:6]:
            Image.new("RGBA", (800, 500), (255, 0, 0, 128)).save(self.root / "props" / (p["name"] + ".png"))
        with contextlib.redirect_stdout(io.StringIO()):
            library.search(["rocket"], sheet=self.root / "sheet.png")
        with Image.open(self.root / "sheet.png") as image:
            self.assertEqual(image.size, (720, 400))

    def test_selected_asset_is_persisted_and_not_copied_again(self):
        source = self.root / "props/rocket.png"; source.write_bytes(b"same")
        self.catalog["props"][0]["sha256"] = library.digest(source)
        project = self.root / "project"
        with contextlib.redirect_stdout(io.StringIO()), patch.object(library, "add_project"), \
             patch.object(library, "clone", wraps=library.clone) as clone:
            library.use(project, ["rocket"])
            library.use(project, ["rocket"])
        self.assertEqual(clone.call_count, 1)
        picks = json.loads((project / "assets/library-picks.json").read_text())
        self.assertEqual(picks["rocket"]["sha256"], self.catalog["props"][0]["sha256"])


class ChannelLibraryTest(unittest.TestCase):
    """Each channel keeps its own props; a project without a channel keeps the shared library."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.shared = Path(self.tmp.name) / "library"
        p = patch.object(library, "LIBRARY", self.shared); p.start(); self.addCleanup(p.stop)

    def project(self, name, channel=None):
        project = Path(self.tmp.name) / "projects" / name
        (project / "assets").mkdir(parents=True)
        (project / "config.json").write_text(json.dumps({"title": name, **({"channel": channel} if channel else {})}))
        Image.new("RGBA", (40, 40), (len(name) * 20 % 255, 0, 0, 255)).save(project / "assets" / "rocket.png")
        return project

    def test_a_new_prop_goes_to_its_channels_library_only(self):
        with contextlib.redirect_stdout(io.StringIO()):
            library.add_project(self.project("a", "chan1"))
            library.add_project(self.project("old"))
        own = library.load(self.shared / "channels" / "chan1")["props"]
        self.assertEqual([p["projects"] for p in own], [["a"]])
        self.assertTrue((self.shared / "channels/chan1/props/rocket.png").is_file())
        self.assertEqual([p["projects"] for p in library.load(self.shared)["props"]], [["old"]])

    def test_search_and_use_stay_inside_the_channel(self):
        with contextlib.redirect_stdout(io.StringIO()):
            library.add_project(self.project("a", "chan1"))
        other = self.project("b", "chan2")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            library.search(["rocket"], lib=library.library_for(other))
        self.assertIn("Показано 0 із 0", out.getvalue())
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            library.use(other, ["rocket-2"])
        self.assertEqual(library.library_for(channel="chan1"), self.shared / "channels" / "chan1")
        self.assertEqual(library.library_for(channel="../x"), self.shared)   # not a path out of the library


if __name__ == "__main__":
    unittest.main()
