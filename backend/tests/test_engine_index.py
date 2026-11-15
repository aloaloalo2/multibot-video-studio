"""The frame agent's index of the Razgon engine is built from the engine files (user, 15 November 2026)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine_index


class EngineIndexTest(unittest.TestCase):
    def test_exports_carry_arguments_line_and_first_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'core.js').write_text('// colour mix\nexport function mix(a, b, k) {}\nexport const E = {};\nfunction hidden() {}\n')
            text = engine_index.build(folder)
        self.assertIn('core.js: mix(a, b, k) :2 — colour mix; E :3', text)
        self.assertNotIn('hidden', text)

    def test_brief_reads_the_real_engine_and_is_short(self):
        text = engine_index.brief()
        if not engine_index.engine_dir().is_dir():
            self.skipTest('no Razgon copy on this machine')
        self.assertIn('core.js:', text)
        self.assertLess(len(text), 20000)

    def test_missing_engine_gives_no_index(self):
        with patch.object(engine_index, 'engine_dir', lambda: Path('/nonexistent-razgon')):
            engine_index.CACHE.clear()
            self.assertEqual(engine_index.brief(), '')
        engine_index.CACHE.clear()


class ProjectIndexTest(unittest.TestCase):
    def test_scene_libraries_scripts_and_palette_are_listed(self):
        import store
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenes = root / 'razgon' / 'scenes'; (scenes / 'shots').mkdir(parents=True)
            (scenes / 'lib.js').write_text('// scenes/lib.js — shared helpers\nexport function word() {}\nexport const L = 1;\n')
            (scenes / 'shots' / 's001.js').write_text('')
            work = root / 'data' / 'work'; work.mkdir(parents=True)
            (work / 'grid.py').write_text('"""Contact sheet of props."""\n')
            (work / 'g1.png').write_bytes(b'')
            with patch('frame_progress.razgon_project', lambda project: root / 'razgon'), \
                 patch.object(store, 'project_dir', lambda pid: root / 'data'), \
                 patch.object(engine_index, 'style_palette', lambda style: 'neon: { ink: x }'), \
                 patch.object(store, 'read_channel_settings', lambda folder, default: {'animation': {'style': 'neon'}}), \
                 patch.object(store, 'get_channel_folder', lambda cid, include_disabled=True: root):
                text = engine_index.project_index({'id': 'p', 'channel_id': 'c'})
        self.assertIn('scenes/lib.js: shared helpers | експорт: word, L', text)
        self.assertIn('scenes/shots (1): s001', text)
        self.assertIn('work/grid.py: Contact sheet of props.', text)
        self.assertIn('1 PNG', text)
        self.assertIn('neon: { ink: x }', text)
