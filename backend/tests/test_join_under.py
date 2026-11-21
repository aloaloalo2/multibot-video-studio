import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joins


class JoinUnderTest(unittest.TestCase):
    """A dissolve fades only the side on top; the side under it stays whole (user, 21 November 2026: «переходи… в
    чорноту, а потім різко появляється наступний кадр»: both halves faded over black, the middle at 75%)."""

    def project(self, a_layer, b_layer):
        a = {'id': 'a', 'kind': 'image', 'start': 0, 'duration': 4}
        b = {'id': 'b', 'kind': 'image', 'start': 4, 'duration': 4}
        tracks = [{'id': 'l0', 'clips': []}, {'id': 'l1', 'clips': []}]
        tracks[a_layer]['clips'].append(a)
        tracks[b_layer]['clips'].append(b)
        return {'fps': 25, 'tracks': tracks, 'scene_groups': [{'id': 'ga', 'clip_ids': ['a']}, {'id': 'gb', 'clip_ids': ['b']}],
                'join_transitions': [{'id': 'j', 'from_ref': 'group:ga', 'to_ref': 'group:gb', 'type': 'crossfade', 'duration': .5, 'seam': 4}]}

    def rendered(self, project):
        layers = [{'id': t['id'], 'clips': [dict(c) for c in t['clips']]} for t in project['tracks']]
        joins.transport(project, layers)
        return {c['id']: c for layer in layers for c in layer['clips']}

    def test_the_lower_side_stays_whole(self):
        clips = self.rendered(self.project(0, 1))            # the outgoing frame lies under the incoming one
        self.assertTrue(clips['a']['join_out']['under'])
        self.assertFalse(clips['b']['join_in']['under'])
        clips = self.rendered(self.project(1, 0))            # the incoming frame lies under
        self.assertFalse(clips['a']['join_out']['under'])
        self.assertTrue(clips['b']['join_in']['under'])


if __name__ == '__main__':
    unittest.main()
