import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import author_rules


class AuthorRulesTest(unittest.TestCase):
    """The studio's writers get the rules a Claude Code session works by (user, 8 November 2026)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_missing_checker_never_counts_as_passed(self):
        with mock.patch.object(author_rules, 'PROVERKA', self.tmp/'absent.py'):
            passed, report = author_rules.check('Text', self.tmp)
        self.assertIsNone(passed)
        self.assertIn('недоступна', report)

    def test_claude_md_includes_its_files(self):
        (self.tmp / "CLAUDE.md").write_text("@writing.md\n", encoding="utf-8")
        (self.tmp / "writing.md").write_text("# Правила письма\nБез тире.", encoding="utf-8")
        with mock.patch.object(author_rules, "CLAUDE_MD", self.tmp / "CLAUDE.md"):
            self.assertIn("Без тире.", author_rules.writing_rules())

    def test_only_script_sections_of_agents_md(self):
        path = self.tmp / "AGENTS.md"
        path.write_text("## Зачини ровно 10 речень\nчотири зачини\n\n## Монтаж кадрів\nзум 20%\n\n## Заборонені слова\nбез «стоит»\n", encoding="utf-8")
        text = author_rules.script_sections(path)
        self.assertIn("чотири зачини", text)
        self.assertIn("без «стоит»", text)
        self.assertNotIn("зум 20%", text)

    def test_memory_of_the_channel_and_of_all_channels_only(self):
        memory = self.tmp / "memory"
        memory.mkdir()
        note = "---\nname: x\n---\n{}"
        (memory / "antropov-ending.md").write_text(note.format("Сценарій закінчується «пока-пока»."), encoding="utf-8")
        (memory / "gorbunov-topics.md").write_text(note.format("Теми Горбунова, як у Антропова."), encoding="utf-8")
        (memory / "titles.md").write_text(note.format("Усі канали: тайтли без тире."), encoding="utf-8")
        (memory / "render.md").write_text(note.format("What If: рендер лише в експорті."), encoding="utf-8")
        with mock.patch.object(author_rules, "MEMORY", memory):
            text = author_rules.claude_memory("Григорий Антропов")
        self.assertIn("пока-пока", text)
        self.assertIn("тайтли без тире", text)
        self.assertNotIn("Теми Горбунова", text)
        self.assertNotIn("рендер", text)
        self.assertNotIn("name: x", text)


if __name__ == "__main__":
    unittest.main()
