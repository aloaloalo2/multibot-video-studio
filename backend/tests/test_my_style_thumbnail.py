"""«Адаптувати під мій стиль»: the channel's own newest covers are the style the clone is written in."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import thumbnail_gen


class OwnThumbnailsTest(unittest.TestCase):
    def test_the_newest_other_covers_of_the_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = [{"id": "this", "updated_at": 9}, {"id": "old", "updated_at": 1}, {"id": "new", "updated_at": 5},
                        {"id": "bare", "updated_at": 7}]
            for pid in ("this", "old", "new"):
                (root / pid).mkdir()
                (root / pid / thumbnail_gen.PREVIEW).write_bytes(b"png")
            with patch.object(thumbnail_gen.store, "list_projects", return_value=projects), \
                 patch.object(thumbnail_gen, "keep_dir", side_effect=lambda pid: root / pid):
                found = thumbnail_gen.own_thumbnails({"id": "this", "channel_id": "c", "episode_path": tmp + "/c/e"})
        self.assertEqual([path.parent.name for path in found], ["new", "old"])   # newest first, never its own

    def test_a_cover_with_our_logo_laid_on_it_teaches_the_picture_before_the_logo(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "Превью v1.png").write_bytes(b"clean")
            (work / "Превью v2.png").write_bytes(b"with logo")
            (work / "Промпт прев'ю v2.txt").write_text("[Правка Превью v1.png] Логотип каналу (10% ширини)\n", encoding="utf-8")
            (work / thumbnail_gen.PREVIEW).write_bytes(b"with logo")
            with patch.object(thumbnail_gen, "keep_dir", return_value=work):
                self.assertEqual(thumbnail_gen.without_logo("p", work / thumbnail_gen.PREVIEW).name, "Превью v1.png")
                (work / thumbnail_gen.PREVIEW).write_bytes(b"clean")
                self.assertEqual(thumbnail_gen.without_logo("p", work / thumbnail_gen.PREVIEW).name, "Превью v1.png")

    def test_the_brief_keeps_the_idea_and_takes_our_look(self):
        text = thumbnail_gen.MY_STYLE.format(files="Наше прев'ю 1.png")
        self.assertIn("only the idea", text)
        self.assertIn("Наше прев'ю 1.png", text)


class PublicFiguresTest(unittest.TestCase):
    def test_every_prompt_writer_hears_that_real_people_are_refused(self):
        self.assertIn("REAL PEOPLE", thumbnail_gen.trending("T", "s", "", "x.png"))
        with patch("idea_reference.thumbnail_rules", return_value="R"):
            self.assertIn("REAL PEOPLE", thumbnail_gen.clone_brief("T", "", "x.png", []))


if __name__ == "__main__":
    unittest.main()
