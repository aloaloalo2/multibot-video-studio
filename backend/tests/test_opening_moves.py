import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import episode_ideas
import store


class OpeningMovesTest(unittest.TestCase):
    """Openings remember their way in, so later openings of every channel take other ways."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        p = patch.object(store, 'DATA_ROOT', Path(self.tmp.name)); p.start(); self.addCleanup(p.stop)
        for cid in ('a', 'b'):
            (Path(self.tmp.name) / 'channels' / cid).mkdir(parents=True)

    def test_the_brief_names_this_and_other_channels_recent_moves(self):
        for n in range(15):
            episode_ideas.remember_move('a', 'Канал А', f'хід {n}', 'Тема')
        episode_ideas.remember_move('b', 'Канал Б', 'число окремим реченням', 'Тема')
        episode_ideas.remember_move('b', 'Канал Б', '', 'Тема')   # an opening without a move is not recorded
        note = episode_ideas.variety_note('a')
        self.assertIn('хід 14', note)
        self.assertNotIn('хід 8;', note)   # only the last six of this channel
        self.assertIn('число окремим реченням (Канал Б)', note)
        self.assertEqual(len(store.read_json(episode_ideas.moves_path('a'))), episode_ideas.MOVES_KEPT)

    def test_a_channel_with_no_history_still_asks_for_variety(self):
        self.assertIn('move', episode_ideas.variety_note('a'))


if __name__ == '__main__':
    unittest.main()
