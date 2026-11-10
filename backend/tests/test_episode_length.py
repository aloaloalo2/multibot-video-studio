import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import episode_ideas as ideas
import store


class EpisodeLengthTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.projects = [{'id': name, 'name': name, 'created_at': stamp} for name, stamp in
                         [('old', 1), ('third', 2), ('second', 3), ('first', 4), ('empty', 5)]]
        self.saved = {name: {'id': name, 'name': name, 'voice_script': {'text': 'word ' * count}}
                      for name, count in [('old', 1200), ('third', 1802), ('second', 1999), ('first', 2201), ('empty', 0)]}
        self.saved['third']['voice_script']['text'] = ''
        for item in (patch.object(store, 'list_projects', return_value=self.projects),
                     patch.object(store, 'load_project', side_effect=lambda pid: self.saved[pid]),
                     patch.object(store, 'load_project_narration', side_effect=lambda pid:
                                  {'spoken_script': 'word ' * 1802} if pid == 'third' else None),
                     patch.object(store, 'get_channel_folder', return_value=self.root),
                     patch.object(ideas.author_rules, 'for_channel', return_value={})):
            item.start()
            self.addCleanup(item.stop)

    def test_latest_three_scripts_ignore_older_and_empty_projects_and_share_context(self):
        import agent_storage
        with patch.object(agent_storage, 'get_memory', return_value=''):
            ctx = ideas.context('channel')
        self.assertEqual([sample['title'] for sample in ctx['samples']], ['first', 'second', 'third'])
        self.assertEqual(ctx['target_words'], 2001)
        self.assertEqual(ctx['sample_count'], 3)
        self.assertEqual(ideas.recommended_length('channel'), {'target_words': 2001, 'sample_count': 3})

    def test_cached_ideas_refresh_length_without_rewriting_topics_or_drafts(self):
        path = self.root/'topics.json'
        saved = {'id': 'saved', 'ideas': [{'title': 'Keep this title', 'uk': ''}], 'target_words': 1700,
                 'day': ideas.today(), 'status': 'done'}
        path.write_text(json.dumps(saved))
        with patch.object(ideas, 'read', return_value=saved), patch.object(ideas, 'topics_path', return_value=path):
            result = ideas.catalog('channel')
        self.assertEqual(result['target_words'], 2001)
        self.assertEqual(result['sample_count'], 3)
        self.assertEqual(result['ideas'], saved['ideas'])
        self.assertEqual(json.loads(path.read_text()), saved)

    def test_missing_history_uses_available_scripts_then_default(self):
        with patch.object(store, 'list_projects', return_value=self.projects[3:]):
            self.assertEqual(ideas.recommended_length('channel'), {'target_words': 2201, 'sample_count': 1})
        with patch.object(store, 'list_projects', return_value=[]):
            self.assertEqual(ideas.recommended_length('channel'), {'target_words': 2000, 'sample_count': 0})
