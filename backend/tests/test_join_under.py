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

    def test_an_accent_above_the_other_frame_puts_its_group_on_top(self):
        # frame 4 of the fennel film: its photo under frame 5, its caption above it (user, 22 November 2026: «перехід
        # використовує групи, а не кожен слой»); the group fades at its top layer's place, so frame 4 fades out over 5
        project = self.project(0, 1)
        project['tracks'].append({'id': 'l2', 'clips': [{'id': 'caption', 'kind': 'text', 'start': 0, 'duration': 4}]})
        project['scene_groups'][0]['clip_ids'].append('caption')
        clips = self.rendered(project)
        self.assertFalse(clips['a']['join_out']['under'])
        self.assertTrue(clips['b']['join_in']['under'])
        self.assertEqual(clips['a']['join_out']['group'], clips['caption']['join_out']['group'])

    def test_a_layer_gone_before_the_seam_does_not_decide_the_side_on_top(self):
        # Astéroïde 86→87 (27 November 2026): a lead-in of frame 86 on the top layer ended 2.8 s before the seam; counting
        # it put 86 «on top», its group fade lay under 87 and 87 was drawn whole over it, a plain cut
        project = self.project(0, 1)
        project['tracks'].append({'id': 'l2', 'clips': [{'id': 'lead', 'kind': 'text', 'start': 0, 'duration': 1.2}]})
        project['scene_groups'][0]['clip_ids'].append('lead')
        clips = self.rendered(project)
        self.assertTrue(clips['a']['join_out']['under'])
        self.assertFalse(clips['b']['join_in']['under'])

    def test_a_layer_of_the_next_frame_that_comes_after_the_transition_does_not_either(self):
        project = self.project(1, 0)
        project['tracks'].append({'id': 'l2', 'clips': [{'id': 'late', 'kind': 'image', 'start': 6, 'duration': 2}]})
        project['scene_groups'][1]['clip_ids'].append('late')
        clips = self.rendered(project)
        self.assertFalse(clips['a']['join_out']['under'])
        self.assertTrue(clips['b']['join_in']['under'])

    def test_a_dissolve_without_a_length_is_the_studios_shorter_one(self):
        project = self.project(0, 1)
        project['join_transitions'] = []
        joins.set_transition(project, {'from_ref': 'group:ga', 'to_ref': 'group:gb', 'type': 'crossfade'})
        self.assertAlmostEqual(project['join_transitions'][0]['duration'], .30)


if __name__ == '__main__':
    unittest.main()
