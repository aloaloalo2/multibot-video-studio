"""tools/razgon_sync.py: the Razgon working copy follows the kit without losing the author's changes."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import razgon_sync  # noqa: E402


class RazgonSyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.kit, self.copy = base / "kit", base / "YOUTUBE" / "What If" / "razgon-2d-studio"
        for root in (self.kit, self.copy):
            (root / "engine").mkdir(parents=True)
            (root / "render.mjs").write_text("v1 render")
            (root / "engine" / "core.js").write_text("v1 core")
            (root / "engine" / "styles.js").write_text("v1 styles")
        (self.kit / "tools").mkdir()
        (self.kit / "tools" / "old.py").write_text("old tool")
        (self.copy / "projects" / "07").mkdir(parents=True)
        (self.copy / "projects" / "07" / "config.json").write_text("{}")

    def test_first_run_adds_missing_files_and_records_the_rest(self):
        report = razgon_sync.sync(self.copy, self.kit)
        self.assertEqual(report["added"], ["tools/old.py"])
        self.assertEqual(report["updated"] + report["kept"], [])
        self.assertEqual(set(json.loads((self.copy / razgon_sync.MANIFEST).read_text())), {"render.mjs", "engine/core.js", "engine/styles.js", "tools/old.py"})

    def test_a_kit_update_reaches_unchanged_files_and_spares_hand_changed_ones(self):
        razgon_sync.sync(self.copy, self.kit)
        (self.copy / "engine" / "styles.js").write_text("v1 styles + my own style")    # the author's change
        (self.kit / "engine" / "core.js").write_text("v2 core")
        (self.kit / "engine" / "styles.js").write_text("v2 styles")
        (self.kit / "tools" / "old.py").unlink()
        (self.kit / "tools" / "new.py").write_text("new tool")
        report = razgon_sync.sync(self.copy, self.kit)
        self.assertEqual(report["updated"], ["engine/core.js"])
        self.assertEqual(report["kept"], ["engine/styles.js"])
        self.assertEqual(report["added"], ["tools/new.py"])
        self.assertEqual(report["removed"], ["tools/old.py"])
        self.assertEqual((self.copy / "engine" / "core.js").read_text(), "v2 core")
        self.assertEqual((self.copy / "engine" / "styles.js").read_text(), "v1 styles + my own style")
        self.assertFalse((self.copy / "tools" / "old.py").exists())
        self.assertTrue((self.copy / "projects" / "07" / "config.json").is_file())   # projects are never touched
        # still the author's next time too
        self.assertEqual(razgon_sync.sync(self.copy, self.kit)["kept"], ["engine/styles.js"])

    def test_a_copy_that_differs_before_any_sync_is_left_alone(self):
        (self.copy / "render.mjs").write_text("the author's newer renderer")
        report = razgon_sync.sync(self.copy, self.kit)
        self.assertEqual(report["kept"], ["render.mjs"])
        self.assertEqual((self.copy / "render.mjs").read_text(), "the author's newer renderer")

    def test_dry_run_changes_nothing(self):
        (self.kit / "render.mjs").write_text("v2 render")
        razgon_sync.sync(self.copy, self.kit, dry=True)
        self.assertFalse((self.copy / "tools" / "old.py").exists())
        self.assertFalse((self.copy / razgon_sync.MANIFEST).exists())

    def test_working_copies_are_found_next_to_the_studio(self):
        self.assertEqual(razgon_sync.copies(self.copy.parents[1]), [self.copy])


if __name__ == "__main__":
    unittest.main()
