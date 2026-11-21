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
        project = {"fps": 25, "assets": [{"id": "v", "kind": kind, "path": __file__}]}
        with patch.object(store, "load_project", return_value=project), patch.object(store, "load_project_plan", return_value=PLAN), \
                patch.object(store, "made_frames", return_value=list(made)), patch.object(montage_ops, "run") as run:
            placed = host_from_voice.place("p")
        return placed, (run.call_args[0][1] if run.called else [])

    def test_host_frames_take_the_voice_video_at_their_own_time(self):
        placed, ops = self.run_with("video", made=[4])
        self.assertEqual(placed, [1, 3])                       # frame 4 is made already, frame 2 is no host frame
        self.assertEqual([(op["frame"], op["asset_id"], op["trim_start"]) for op in ops], [(1, "v", 0.0), (3, "v", 9.0)])
        self.assertEqual([op["motion"] for op in ops], ["zoom_in", "zoom_out"])

    def test_a_voice_cut_out_of_a_video_finds_that_video(self):
        """The recognition cuts the sound out of a video voice; the plan keeps only that sound's hash (the Jupiter
        episode, 21 November 2026: host pictures were drawn though the voice was a video of the host)."""
        import json, tempfile
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "analysis" / "j").mkdir(parents=True)
            (Path(root) / "analysis" / "j" / "result.json").write_text(json.dumps(
                {"source": {"asset_id": "v", "kind": "video"}, "audio": {"asset_id": "a", "sha256": "s"}}))
            project = {"id": "p", "assets": [{"id": "v", "kind": "video", "path": __file__},
                                             {"id": "a", "kind": "audio", "path": __file__}]}
            with patch.object(store, "project_dir", return_value=Path(root)):
                self.assertEqual(host_from_voice.voice_video(project, {"timing": {"audio": {"sha256": "s"}}})["id"], "v")
                self.assertIsNone(host_from_voice.voice_video(project, {"timing": {"audio": {"sha256": "other"}}}))

    def test_redo_takes_off_drawn_host_frames_first(self):
        project = {"fps": 25, "assets": [{"id": "v", "kind": "video", "path": __file__}]}
        with patch.object(store, "load_project", return_value=project), patch.object(store, "load_project_plan", return_value=PLAN), \
                patch.object(store, "made_frames", return_value=[1, 2]), patch.object(montage_ops, "run") as run:
            self.assertEqual(host_from_voice.place("p", redo=True), [1, 3, 4])
        self.assertEqual(run.call_args_list[0][0][1], [{"op": "remove", "frame": 1}])

    def test_an_audio_voice_leaves_the_host_frames_to_the_agent(self):
        self.assertEqual(self.run_with("audio"), ([], []))


if __name__ == "__main__":
    unittest.main()
