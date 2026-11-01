import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import razgon_bridge

BRIDGE = Path(razgon_bridge.__file__)


class FakeStudio:
    """Applies the timeline actions the bridge sends, the way the Studio's batch does for these few."""
    def __init__(self, project):
        self.project_data, self.sent = project, []

    def batch(self, project, actions):
        self.sent += actions
        clips = self.project_data["tracks"][0]["clips"]
        for action in actions:
            payload = action["payload"]
            if action["type"] == "delete_clip":
                clips[:] = [clip for clip in clips if clip["id"] != payload["clip_id"]]
            elif action["type"] == "add_clip":
                clips.append({**payload, "id": f"new{len(self.sent)}"})
            elif action["type"] == "group_clips":
                self.project_data["scene_groups"].append({"clip_ids": payload["clip_ids"], "title": payload["title"]})
        return self.project_data


class FrameSlotsTest(unittest.TestCase):
    def test_reset_frames_go_back_from_a_rendered_clip_to_a_code_block(self):
        link = {"project_id": "p" * 24, "fps": 25, "duration": 10.0,
                "frames": [{"number": 1, "start": 0.0, "end": 4.0}, {"number": 2, "start": 4.0, "end": 10.0}]}
        rendered = lambda n, start, end: {"id": f"v{n}", "kind": "video", "title": f"Razgon · кадр {n:03d}", "start": start, "duration": end - start}
        project = {"id": "p" * 24, "tracks": [{"id": "t1", "clips": [rendered(1, 0.0, 4.0), rendered(2, 4.0, 10.0)]}], "scene_groups": []}
        studio = FakeStudio(project)
        with patch.object(razgon_bridge, "ensure_overlay", side_effect=lambda studio, razgon, project, duration: project):
            razgon_bridge.ensure_frame_slots(studio, Path("/tmp/razgon"), link, project)
            self.assertEqual(studio.sent, [])                                   # without --frames nothing is touched
            razgon_bridge.ensure_frame_slots(studio, Path("/tmp/razgon"), link, project, frozenset({2}))
        kinds = {clip["title"]: clip["kind"] for clip in project["tracks"][0]["clips"]}
        self.assertEqual(kinds, {"Razgon · кадр 001": "video", "Razgon · кадр 002": "animation"})
        block = next(clip for clip in project["tracks"][0]["clips"] if clip["kind"] == "animation")
        self.assertEqual((block["start"], block["duration"], block["content_type"]), (4.0, 6.0, "shape"))

    def test_an_agent_of_the_studio_cannot_render_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            for command in ("push", "final"):
                extra = ["--out", str(Path(folder) / "film.mp4")] if command == "final" else []
                run = subprocess.run([sys.executable, str(BRIDGE), command, "--razgon", folder, *extra], capture_output=True, text=True,
                                     env={**os.environ, "MULTIBOT_RENDER_ON_EXPORT": "1"}, timeout=60)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("«Експорт MP4»", run.stderr)


class RenderMemoryTest(unittest.TestCase):
    """Frames start side by side only while the RAM holds them (31 October 2026: 6 Chromiums froze a 16 GB Mac)."""

    def run_frames(self, used_gb, jobs=5):
        """The most renders running at once. The memory reading stays at used_gb: renders younger than RAMP are not in
        a reading yet, and render_many counts them itself."""
        frames = [{"number": n, "start": n * 10.0, "end": n * 10.0 + 5} for n in range(1, 5)]
        lock, state = threading.Lock(), {"now": 0, "most": 0}

        def render(razgon, frame, fps, workers):
            with lock:
                state["now"] += 1
                state["most"] = max(state["most"], state["now"])
            time.sleep(0.2)
            with lock:
                state["now"] -= 1

        memory = (lambda: None) if used_gb is None else (lambda: (used_gb * 1e9, 16e9))
        done = []
        with patch.object(razgon_bridge, "render_frame", render), patch.object(razgon_bridge, "memory", memory), \
                patch.object(razgon_bridge, "RAMP", 60.0), patch.object(razgon_bridge, "RAM_LIMIT", 0.8):
            razgon_bridge.render_many(Path("."), frames, 25, None, jobs, done.append)
        self.assertEqual(sorted(f["number"] for f in done), [1, 2, 3, 4])
        return state["most"]

    def test_as_many_frames_as_fit_under_the_limit(self):
        # 8 GB in use on 16 GB: 80 % is 12.8 GB, so two Chromiums of 2.2 GB fit and the third would not
        self.assertEqual(self.run_frames(8), 2)

    def test_the_first_frame_starts_even_when_memory_is_short(self):
        self.assertEqual(self.run_frames(15), 1)

    def test_without_a_memory_reading_the_job_limit_holds(self):
        self.assertEqual(self.run_frames(None, jobs=3), 3)



class PictureFingerprintTest(unittest.TestCase):
    """A rendered frame stays fresh until something it is drawn from changes, and only then."""

    def test_one_changed_scene_makes_only_its_frames_stale(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); razgon = root / "projects" / "07"
            for folder in ("engine", "projects/07/scenes", "projects/07/story", "projects/07/assets", "projects/07/timeline"):
                (root / folder).mkdir(parents=True)
            (root / "engine" / "core.js").write_text("core")
            (root / "render.mjs").write_text("render")
            (razgon / "config.json").write_text(json.dumps({"style": "dusk", "music": "calm"}))
            shots = [{"id": f"e0{n}", "start": 5.0 * (n - 1), "end": 5.0 * n} for n in range(1, 5)]
            (razgon / "story" / "shots.json").write_text(json.dumps({"shots": shots}))
            for n in range(1, 5):
                (razgon / "scenes" / f"s{n}.js").write_text(f"take('e0{n}', () => draw{n}())")
            (razgon / "scenes" / "helpers.js").write_text("export const glow = 1")
            frames = [{"number": n, "start": 5.0 * (n - 1), "end": 5.0 * n} for n in range(1, 5)]
            before = razgon_bridge.picture_fingerprints(razgon, frames)
            (razgon / "scenes" / "s4.js").write_text("take('e04', () => drawBetter())")
            after = razgon_bridge.picture_fingerprints(razgon, frames)
            # frame 4 shows it; frame 3 too, through the transition into it; frames 1 and 2 stay fresh
            self.assertEqual([before[n] == after[n] for n in range(1, 5)], [True, True, False, False])
            config = json.loads((razgon / "config.json").read_text()); config["music"] = "dark"
            (razgon / "config.json").write_text(json.dumps(config))
            self.assertEqual(razgon_bridge.picture_fingerprints(razgon, frames), after)   # sound only: no frame stale
            (razgon / "scenes" / "helpers.js").write_text("export const glow = 2")
            changed = razgon_bridge.picture_fingerprints(razgon, frames)
            self.assertTrue(all(changed[n] != after[n] for n in range(1, 5)))           # a shared helper: every frame

if __name__ == "__main__":
    unittest.main()
