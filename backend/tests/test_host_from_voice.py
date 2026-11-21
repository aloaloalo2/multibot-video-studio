import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_from_voice
import montage_ops
import store

PLAN = {"timing": {"audio": {"asset_id": "v"}},
        "frames": [{"number": 1, "format": "host", "start": 0.0, "end": 4.0},
                   {"number": 2, "format": "stock_photo", "start": 4.0, "end": 9.0},
                   {"number": 3, "format": "host", "start": 9.013, "end": 14.0},
                   {"number": 4, "format": "host", "start": 14.0, "end": 18.0}]}


class HostFromVoiceTest(unittest.TestCase):
    """A voice recorded as a video of the host gives the host frames, from their own second (21 November 2026)."""

    def run_with(self, kind, made=()):
        project = {"fps": 25, "assets": [{"id": "v", "kind": kind, "path": "/tmp/voice.mp4"}]}
        with patch.object(store, "load_project", return_value=project), patch.object(store, "load_project_plan", return_value=PLAN), \
                patch.object(store, "made_frames", return_value=list(made)), patch.object(montage_ops, "run") as run:
            placed = host_from_voice.place("p")
        return placed, (run.call_args[0][1] if run.called else [])

    def test_host_frames_take_the_voice_video_at_their_own_time(self):
        placed, ops = self.run_with("video", made=[4])
        self.assertEqual(placed, [1, 3])                       # frame 4 is made already, frame 2 is no host frame
        self.assertEqual([(op["frame"], op["asset_id"], op["trim_start"]) for op in ops], [(1, "v", 0.0), (3, "v", 9.0)])
        self.assertEqual([op["motion"] for op in ops], ["zoom_in", "zoom_out"])

    def test_an_audio_voice_leaves_the_host_frames_to_the_agent(self):
        self.assertEqual(self.run_with("audio"), ([], []))


if __name__ == "__main__":
    unittest.main()
