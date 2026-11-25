"""One HeyGen price by the avatar's kind (user, 25 November 2026: «одну ціну»)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import heygen_avatars
import store


class AvatarRateTest(unittest.TestCase):
    def rate(self, kind, calls):
        def read(path):
            calls.append(path)
            return {'data': {'id': 'L', 'avatar_type': kind}}
        with patch.object(heygen_avatars, '_read', side_effect=read):
            return heygen_avatars.look_rate('L')

    def test_photo_avatar_costs_099_and_the_kind_is_asked_once(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'DATA_ROOT', Path(tmp)):
            calls = []
            self.assertEqual(self.rate('photo_avatar', calls)['usd_per_minute'], .99)
            self.assertEqual(self.rate('photo_avatar', calls)['usd_per_minute'], .99)
            self.assertEqual(len(calls), 1)

    def test_digital_twin_costs_060(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'DATA_ROOT', Path(tmp)):
            self.assertEqual(self.rate('digital_twin', [])['usd_per_minute'], .60)

    def test_an_unknown_kind_is_priced_as_the_dearer_one(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, 'DATA_ROOT', Path(tmp)):
            self.assertEqual(self.rate('', [])['usd_per_minute'], .99)


if __name__ == '__main__':
    unittest.main()
