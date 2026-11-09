"""Summary diagnostics must distinguish intentional backing from an exposed canvas."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_view


class BackingTest(unittest.TestCase):
    picture = {"start": 10., "duration": 5.}
    field = {"kind": "animation", "content_type": "shape", "title": "K001 фон",
             "start": 10., "duration": 5., "width": 1., "height": 1., "color": "#101114"}

    def test_opaque_full_frame_field_covers_the_picture(self):
        self.assertTrue(agent_view._solid_backing(self.field, self.picture))
        self.assertTrue(agent_view._solid_backing({**self.field, "start": 0., "duration": 20.}, self.picture))

    def test_incomplete_or_transparent_backing_does_not_hide_an_exposed_edge(self):
        for change in ({"start": 10.04}, {"duration": 4.96}, {"opacity": .5}, {"color": "#10111400"},
                       {"x": .6}, {"scale": .95}, {"rotation": 5}, {"mask": "rounded"},
                       {"keyframes": [{"time": 0., "opacity": 0.}]}):
            with self.subTest(change=change):
                self.assertFalse(agent_view._solid_backing({**self.field, **change}, self.picture))
