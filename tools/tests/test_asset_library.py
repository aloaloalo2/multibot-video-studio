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


if __name__ == "__main__":
    unittest.main()
