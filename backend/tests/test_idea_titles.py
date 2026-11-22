import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import episode_ideas
import store


class IdeaTitlesTest(unittest.TestCase):
    """«Власна ідея»: five DeepSeek titles for the author's idea, the idea itself stays first in the window (22 November 2026)."""

    def test_titles_are_cleaned_and_bad_ones_dropped(self):
        answer = {'titles': [{'title': '1. Warum der Mond flieht', 'uk': 'Чому Місяць тікає'},
                             {'title': 'Mond: das Ende', 'uk': ''},                 # a colon is never a title
                             {'title': 'Die Erde verliert ihren Mond', 'uk': ''},
                             {'title': 'Was passiert mit dem Mond?', 'uk': ''},
                             {'title': 'Warum der Mond jedes Jahr wegzieht', 'uk': ''}]}
        with tempfile.TemporaryDirectory() as root, patch.object(store, 'DATA_ROOT', Path(root)), \
                patch.object(store, 'get_channel_folder', return_value=Path(root) / 'K'), \
                patch.object(store, 'read_channel_settings', return_value={}), \
                patch.object(episode_ideas.channel_topics, 'history', return_value=['Alt']), \
                patch.object(episode_ideas.agent_storage, 'get_memory', return_value=''), \
                patch.object(episode_ideas, 'deepseek', return_value=answer) as call:
            result = episode_ideas.idea_titles('c' * 16, '  Der Mond entfernt sich  ')
        self.assertEqual(result['idea'], 'Der Mond entfernt sich')
        self.assertEqual([row['title'] for row in result['titles']],
                         ['Warum der Mond flieht', 'Die Erde verliert ihren Mond', 'Was passiert mit dem Mond?', 'Warum der Mond jedes Jahr wegzieht'])
        self.assertIn('Der Mond entfernt sich', call.call_args.args[0])

    def test_an_empty_idea_is_refused(self):
        with self.assertRaises(ValueError):
            episode_ideas.idea_titles('c' * 16, ' ')


if __name__ == '__main__':
    unittest.main()
