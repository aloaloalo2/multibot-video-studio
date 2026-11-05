import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store
import technical_files


class TechnicalFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.episode = self.base / 'Episode'
        self.episode.mkdir()
        self.folder = self.base / 'Studio' / ('a' * 24)
        self.folder.mkdir(parents=True)
        self.project = {'id': 'a' * 24, 'episode_path': str(self.episode), 'revision': 42, 'tracks': [{'clips': [{'start': 0, 'duration': 8}]}]}
        for name, value in [('project_dir', lambda pid: self.folder), ('load_project', lambda pid: copy.deepcopy(self.project)), ('save_project', self.save), ('find_razgon_project', lambda pid: None)]:
            patcher = patch.object(store, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def save(self, project):
        self.project = copy.deepcopy(project)

    def test_legacy_files_are_backed_up_exactly_and_read_internally(self):
        link = {'project': str(self.base / 'animation'), 'razgon_root': str(self.base)}
        request = {'status': 'paused', 'frames': 3}
        self.project['production_request'] = request
        sources = {'razgon.json': link, 'План видео.json': {'obsolete': True}, 'Запит на створення.json': request}
        original = {}
        for name, data in sources.items():
            path = self.episode / name
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            original[name] = path.read_bytes()
        before = copy.deepcopy(self.project)
        self.assertEqual(len(technical_files.migrate(self.project['id'])), 3)
        self.assertEqual(self.project, before)  # No montage, revision, or active-plan changes.
        self.assertEqual(store.razgon_link(self.project), link)
        self.assertEqual(store.read_json(self.folder / 'production-request.json'), request)
        for name, content in original.items():
            self.assertFalse((self.episode / name).exists())
            self.assertEqual(next((self.folder / 'technical-history').glob('*/' + name)).read_bytes(), content)
        self.assertEqual(technical_files.migrate(self.project['id']), [])

    def test_external_active_plan_moves_without_changing_montage(self):
        old = self.episode / 'План видео.json'
        old.write_text('{"frames": [{"start": 0, "end": 8}]}')
        self.project['plan_source'] = str(old)
        before = copy.deepcopy(self.project)
        with patch.object(store, 'validate_plan', side_effect=lambda value: value):
            technical_files.migrate(self.project['id'])
        self.assertEqual(self.project, dict(before, plan_source=str(self.folder / 'imported-plan.json')))
        self.assertEqual(store.read_json(self.folder / 'imported-plan.json')['frames'][0]['end'], 8)

    def test_internal_plan_remains_authoritative_and_invalid_legacy_stays(self):
        target = self.folder / 'imported-plan.json'
        target.write_text('{"new": true}')
        self.project['plan_source'] = str(target)
        (self.episode / 'План видео.json').write_text('{"old":true}')
        technical_files.migrate(self.project['id'])
        self.assertEqual(target.read_text(), '{"new": true}')
        bad = self.episode / 'razgon.json'
        bad.write_text('{invalid')
        with self.assertRaises(ValueError):
            technical_files.migrate(self.project['id'])
        self.assertTrue(bad.is_file())

    def test_api_link_validates_identity_and_never_writes_to_episode(self):
        root = self.base / 'razgon'
        project = root / 'projects' / 'film'
        (project / 'story').mkdir(parents=True)
        (root / 'render.mjs').write_text('')
        frames = project / 'story/studio_frames.json'
        frames.write_text(json.dumps({'project_id': self.project['id']}))
        data = {'razgon_root': str(root), 'project': str(project)}
        self.assertEqual(technical_files.save_link(self.project['id'], data), data)
        self.assertFalse((self.episode / 'razgon.json').exists())
        frames.write_text('{"project_id":"other"}')
        with self.assertRaises(store.StudioError):
            technical_files.save_link(self.project['id'], data)
        self.assertEqual(store.read_json(self.folder / 'razgon-link.json'), data)


if __name__ == '__main__':
    unittest.main()
