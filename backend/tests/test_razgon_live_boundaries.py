import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import razgon_live

class MixedPlayerTest(unittest.TestCase):
    def test_patch_preserves_the_outgoing_frame_until_its_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"engine").mkdir()
            live=root/"live.html";live.write_text("const f = Math.round(t * fps);")
            player=root/"engine/player.js";player.write_text("const tr = shot.in || { type: 'cut' };")
            razgon_live.patch_mixed_player(root)
            self.assertIn("Math.floor(t * fps + 1e-8)",live.read_text())
            self.assertIn("!getShot(E.shots[i - 1].id)",player.read_text())
            original=player.read_text();razgon_live.patch_mixed_player(root)
            self.assertEqual(player.read_text(),original)
