"""The silence around and inside studio narration differs in every film (26 November 2026)."""
import hashlib
import unittest

from backend.tests import test_backend as support  # noqa: F401  (sys.path)
import channel_voice_lab
import narration_ending


class SilencePlanTest(unittest.TestCase):
    def test_lead_and_ending_vary_within_their_spans(self):
        plans = [narration_ending.silence_plan(hashlib.sha256(str(n).encode()).hexdigest()) for n in range(1, 40)]
        leads, endings = {p['lead'] for p in plans}, {p['ending'] for p in plans}
        self.assertTrue(all(0 <= v <= .03 for v in leads) and len(leads) > 5)
        self.assertTrue(all(1.0 <= v <= 2.2 for v in endings) and len(endings) > 5)
        self.assertEqual(narration_ending.silence_plan('a' * 64), narration_ending.silence_plan('a' * 64))   # one recording, one plan

    def test_breaths_inside_a_paragraph_and_sometimes_a_pause_after_one(self):
        breaks = [[i / 40, 'paragraph' if i % 4 == 0 else 'group'] for i in range(1, 40)]
        plan = narration_ending.silence_plan('b' * 64, breaks)
        kinds = dict((round(b[0], 6), b[1]) for b in breaks)
        groups = [s for share, s in plan['pauses'] if kinds[share] == 'group']
        paragraphs = [s for share, s in plan['pauses'] if kinds[share] == 'paragraph']
        self.assertEqual(len(groups), sum(1 for b in breaks if b[1] == 'group'))   # every join inside a paragraph breathes
        self.assertTrue(all(.02 <= s <= .05 for s in groups))
        self.assertTrue(all(.2 <= s <= .6 for s in paragraphs))
        self.assertLess(len(paragraphs), sum(1 for b in breaks if b[1] == 'paragraph'))   # only some paragraph ends

    def test_requests_are_automatic(self):
        self.assertEqual(channel_voice_lab.sentences_per_request({'provider': 'elevenlabs', 'eleven_sentences': 20}), 3)
        self.assertEqual(channel_voice_lab.sentences_per_request({'provider': 'heygen', 'heygen_model': 'heygen-voice-1-turbo-free', 'heygen_sentences': 2}),
                         channel_voice_lab.PARAGRAPH)
        self.assertFalse(channel_voice_lab.joins_paragraphs({'provider': 'heygen', 'heygen_join_paragraphs': True}))


if __name__ == '__main__':
    unittest.main()
