import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production
import razgon_sound
import store


class MissingBedTest(unittest.TestCase):
    def check(self, project, sound):
        with patch.object(store, 'load_project', return_value=project), patch.object(razgon_sound, 'due', return_value={'project': '/x'}), \
             patch.object(razgon_sound, 'state', return_value=sound):
            return production.missing_bed('a' * 24)

    def test_a_finished_film_whose_bed_was_stopped_gets_it_again(self):
        done = {'production_request': {'status': 'done'}, 'tracks': []}
        self.assertTrue(self.check(done, {'status': 'cancelled'}))
        self.assertTrue(self.check(done, None))
        self.assertFalse(self.check(done, {'status': 'done'}))
        self.assertFalse(self.check({**done, 'tracks': [{'name': production.SOUND_BED}]}, {'status': 'cancelled'}))
        self.assertFalse(self.check({'production_request': {'status': 'failed'}, 'tracks': []}, {'status': 'cancelled'}))
        self.assertFalse(self.check({'production_request': {'status': 'done', 'repair_frames': [3]}, 'tracks': []}, None))


if __name__ == '__main__':
    unittest.main()
