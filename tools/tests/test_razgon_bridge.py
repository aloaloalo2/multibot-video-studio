import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
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
    def test_reused_scene_configuration_takes_current_channel_style_and_all_fonts(self):
        old={'style':'neon','styleDef':{'old':True},'fonts':{'title':'Fredoka','ui':'Nunito'},'duration':10,'music':{'gainDb':-17}}
        current={'style':'care','title_font':'Noto Serif','assets':False}
        result=razgon_bridge.channel_style(old,current)
        self.assertEqual(result['style'],'care')
        self.assertNotIn('styleDef',result)
        self.assertEqual(set(result['fonts'].values()),{'Noto Serif'})
        self.assertFalse(result['assets'])
        self.assertEqual(result['music'],old['music'])
        self.assertEqual(old['style'],'neon')

    def test_custom_style_keeps_its_definition_and_missing_style_does_not_silently_fallback(self):
        style={'id':'custom-mint','def':{'ink':'#123456'}}
        result=razgon_bridge.channel_style({'style':'neon'},{'style':'custom-mint'},styles=[style])
        self.assertEqual(result['styleDef'],style['def'])
        self.assertTrue(result['style_approved'])
        with self.assertRaises(razgon_bridge.BridgeError):
            razgon_bridge.channel_style({}, {'style':'custom-missing'})
        self.assertEqual(razgon_bridge.channel_style({}, {'style':'care'},'dusk')['style'],'dusk')

    def test_channel_plate_already_grouped_by_studio_is_not_grouped_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "plate.png").write_bytes(b"fixture")
            (root / "config.json").write_text(json.dumps({"overlay": "plate.png"}))
            initial = {"id": "p", "tracks": [], "scene_groups": []}
            layer = {"id": "t", "name": razgon_bridge.OVERLAY_TITLE, "clips": []}
            added_layer = {**initial, "tracks": [layer]}
            clip = {"id": "c", "title": razgon_bridge.OVERLAY_TITLE, "start": 0, "duration": 10}
            grouped = {**initial, "tracks": [{**layer, "clips": [clip]}],
                       "scene_groups": [{"id": "managed", "role": "overlay", "clip_ids": ["c"]}]}
            studio = SimpleNamespace(import_file=Mock(return_value={"id": "a"}), project=Mock(return_value=initial),
                                     batch=Mock(side_effect=[added_layer, grouped]))
            self.assertIs(razgon_bridge.ensure_overlay(studio, root, initial, 10), grouped)
            self.assertEqual(studio.batch.call_count, 2)
            self.assertFalse(any(a["type"] == "group_clips" for call in studio.batch.call_args_list for a in call.args[1]))

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


class SoundStudio:
    """The few Studio calls of `razgon_bridge.py sound`, applied the way the Studio's store does: add_layer at an index,
    add_clip into an empty layer (a full one gets a new layer on top), delete_clip with its layer, imports as assets."""
    def __init__(self, project, plan):
        self.data, self.plan_data, self.sent, self.imported, self.calls = project, plan, [], [], []

    def project(self, pid):
        return json.loads(json.dumps(self.data))

    def plan(self, pid):
        return self.plan_data

    def import_file(self, pid, path):
        copy = Path(path).with_name(f"imported-{len(self.imported)}{Path(path).suffix}")
        shutil.copy(path, copy)
        asset = {"id": f"a{len(self.imported)}", "kind": "audio", "path": str(copy)}
        self.imported.append(asset)
        self.data["assets"].append(asset)
        self.data["revision"] += 1
        return asset

    def batch(self, project, actions):
        if project.get("revision") != self.data["revision"]:
            raise razgon_bridge.BridgeError("Студія відповіла 409 на POST /actions: Проєкт змінився")
        tracks = self.data["tracks"]
        for action in actions:
            self.sent.append(action)
            payload = action["payload"]
            if action["type"] == "add_layer":
                tracks.insert(payload["to_index"], {"id": f"L{len(self.sent)}", "name": payload["name"], "clips": []})
            elif action["type"] == "add_clip":
                layer = next(t for t in tracks if t["id"] == payload["layer_id"])
                if layer["clips"]:
                    layer = {"id": f"L{len(self.sent)}", "name": payload["title"], "clips": []}
                    tracks.append(layer)
                layer["clips"].append({**payload, "id": f"c{len(self.sent)}"})
            elif action["type"] == "delete_clip":
                layer = next(t for t in tracks if any(c["id"] == payload["clip_id"] for c in t["clips"]))
                layer["clips"] = [c for c in layer["clips"] if c["id"] != payload["clip_id"]]
                tracks.remove(layer)
        self.data["revision"] += 1
        return self.project(self.data["id"])

    def call(self, method, path, body=None):
        self.calls.append((method, path))
        return {}


class SoundTest(unittest.TestCase):
    """Music and effects reach the timeline without a render (5 November 2026: episode 07 had the voice alone)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.razgon = Path(self.tmp.name) / "projects" / "07"
        (self.razgon / "story").mkdir(parents=True)
        (self.razgon / "build" / "studio").mkdir(parents=True)
        frames = [{"number": 1, "start": 0.0, "end": 2.0, "format": "razgon_2d"}, {"number": 2, "start": 2.0, "end": 4.0, "format": "razgon_2d"}]
        self.link = {"project_id": "p" * 24, "fps": 25, "duration": 4.0, "studio_url": "http://studio", "frames": frames,
                     "script_sha256": "s1", "audio_sha256": "v1"}
        (self.razgon / "story" / "studio_frames.json").write_text(json.dumps(self.link))
        (self.razgon / "story" / "shots.json").write_text(json.dumps(
            {"duration": 4.0, "shots": [{"id": "e01", "start": 0.0, "end": 4.0}], "sfx": [{"t": 1.0, "name": "ding"}]}))
        (self.razgon / "config.json").write_text(json.dumps({"fps": 25}))
        voice = {"id": "voice", "kind": "audio", "title": "Озвучка", "start": 0, "duration": 4.0, "volume": 1}
        frame = lambda n: {"id": f"f{n}", "kind": "animation", "title": f"Razgon · кадр {n:03d}", "start": 2.0 * (n - 1), "duration": 2.0}
        plate = {"id": "logo", "kind": "image", "title": "Логотип каналу", "start": 0, "duration": 4.0, "channel_logo": True}
        project = {"id": "p" * 24, "revision": 3, "assets": [],
                   "tracks": [{"id": "t0", "name": "Шар 1", "clips": [voice]}, {"id": "t1", "name": "Кадр 1", "clips": [frame(1)]},
                              {"id": "t2", "name": "Кадр 2", "clips": [frame(2)]}, {"id": "t3", "name": "Плашка каналу", "clips": [plate]}],
                   "scene_groups": [{"id": "g", "title": "Плашка каналу", "clip_ids": ["logo"], "role": "overlay"}]}
        self.studio = SoundStudio(project, {"script_sha256": "s1", "timing": {"audio": {"sha256": "v1"}}})
        self.tone = 440

    def bed(self, razgon):
        """A short WAV in place of Razgon's mix (render_bed is checked against the kit's mix below)."""
        path = razgon / "build" / "studio" / "music_sfx.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={self.tone}:duration=4:sample_rate=48000",
                        "-ac", "2", str(path)], check=True)
        return path

    def run_sound(self):
        args = SimpleNamespace(razgon=str(self.razgon), studio_url=None)
        output = io.StringIO()
        with patch.object(razgon_bridge, "Studio", lambda url: self.studio), patch.object(razgon_bridge, "render_bed", self.bed), \
                patch.object(razgon_bridge, "renders_running", lambda: 0), contextlib.redirect_stdout(output):
            razgon_bridge.sound(args)
        return output.getvalue()

    def beds(self):
        return [(index, track, clip) for index, track in enumerate(self.studio.data["tracks"]) for clip in track["clips"]
                if clip.get("title") == razgon_bridge.BED_TITLE]

    def test_the_bed_goes_on_its_own_layer_under_the_plate_and_replaces_the_old_one(self):
        self.studio.data["tracks"].insert(1, {"id": "old", "name": "x", "clips": [
            {"id": "oldbed", "kind": "audio", "title": razgon_bridge.BED_TITLE, "start": 0, "duration": 4.0, "volume": 1, "asset_id": "gone"}]})
        self.run_sound()
        found = self.beds()
        self.assertEqual(len(found), 1)                                               # the old clip went with its layer
        index, track, clip = found[0]
        self.assertEqual((clip["kind"], clip["start"], clip["duration"], clip["volume"]), ("audio", 0, 4.0, 1))
        self.assertEqual((track["name"], len(track["clips"])), (razgon_bridge.BED_TITLE, 1))
        self.assertEqual(index, len(self.studio.data["tracks"]) - 2)                  # right under the plate
        self.assertEqual(self.studio.data["tracks"][-1]["clips"][0]["id"], "logo")    # the plate stays on top
        self.assertNotIn("old", [t["id"] for t in self.studio.data["tracks"]])
        bed = Path(self.studio.imported[0]["path"])
        self.assertEqual(bed.suffix, ".m4a")
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,bit_rate:format=duration", "-of", "json", str(bed)],
                               capture_output=True, text=True, check=True)
        info = json.loads(probe.stdout)
        self.assertEqual(info["streams"][0]["codec_name"], "aac")
        self.assertAlmostEqual(float(info["format"]["duration"]), 4.0, delta=0.03)
        self.assertIn(("POST", f"/api/projects/{'p' * 24}/tidy"), self.studio.calls)

    def test_an_unchanged_bed_is_left_and_a_new_one_replaces_it(self):
        self.run_sound()
        sent = len(self.studio.sent)
        self.assertIn("не змінилися", self.run_sound())
        self.assertEqual((len(self.studio.sent), len(self.studio.imported)), (sent, 1))  # nothing imported or sent again
        self.tone = 330                                                                    # new cues: a new bed
        self.run_sound()
        self.assertEqual(len(self.studio.imported), 2)
        self.assertEqual([clip["asset_id"] for _, _, clip in self.beds()], ["a1"])

    def test_an_edit_meanwhile_is_met_with_a_fresh_project(self):
        batch = self.studio.batch
        def once_stale(project, actions):
            if not getattr(self, "edited", False):
                self.edited = True
                self.studio.data["revision"] += 1                                       # the author edits right then
            return batch(project, actions)
        self.studio.batch = once_stale
        self.run_sound()
        self.assertEqual(len(self.beds()), 1)
        self.assertEqual(len([t for t in self.studio.data["tracks"] if t["name"] == razgon_bridge.BED_TITLE]), 1)

    def test_a_mixed_episode_and_a_changed_plan_are_refused(self):
        self.link["frames"][1]["format"] = "stock_photo"
        (self.razgon / "story" / "studio_frames.json").write_text(json.dumps(self.link))
        with self.assertRaisesRegex(razgon_bridge.BridgeError, "змішаного"):
            self.run_sound()
        self.link["frames"][1]["format"] = "razgon_2d"
        (self.razgon / "story" / "studio_frames.json").write_text(json.dumps(self.link))
        self.studio.plan_data = {"script_sha256": "s2", "timing": {"audio": {"sha256": "v1"}}}
        with self.assertRaisesRegex(razgon_bridge.BridgeError, "prepare"):
            self.run_sound()
        self.assertEqual(self.beds(), [])

    def test_the_agents_may_lay_the_sound(self):
        run = subprocess.run([sys.executable, str(BRIDGE), "sound", "--razgon", self.tmp.name], capture_output=True, text=True,
                             env={**os.environ, "MULTIBOT_RENDER_ON_EXPORT": "1"}, timeout=60)
        self.assertNotIn("«Експорт MP4»", run.stderr)                                 # not refused like push and final

    def test_the_mix_waits_while_razgon_renders(self):
        running = iter([2, 1, 0])
        with patch.object(razgon_bridge, "renders_running", lambda: next(running)), patch.object(razgon_bridge.time, "sleep") as sleep, \
                contextlib.redirect_stdout(io.StringIO()):
            razgon_bridge.wait_for_renders()
        self.assertEqual(sleep.call_count, 2)


class KitBedTest(unittest.TestCase):
    """render_bed sums the kit mix's own parts: the same bed as the whole mix less the voice, without whole-film copies."""

    def test_the_bed_from_the_parts_equals_the_mix_less_the_voice(self):
        try:
            import numpy as np
            import scipy  # noqa: F401
        except ImportError:
            self.skipTest("numpy and scipy are needed for the kit's mix")
        kit = Path(razgon_bridge.__file__).resolve().parents[1] / "razgon-plugin" / "razgon-2d-studio-plugin" / "skills" / "make-2d-video" / "kit"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "audio").symlink_to(kit / "audio")
            (root / "tools").symlink_to(kit / "tools")
            razgon = root / "projects" / "t"
            for folder in ("input", "story", "build"):
                (razgon / folder).mkdir(parents=True)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=200:duration=12:sample_rate=48000", "-af", "volume=0.3",
                            "-ac", "2", str(razgon / "input" / "voice.wav")], check=True)
            shots = [{"id": "e01", "start": 0.0, "end": 6.0, "amb": {"name": "wind", "gain": -22}, "sfx": [{"at": 1.0, "name": "swish"}]},
                     {"id": "e02", "start": 6.0, "end": 12.0, "amb": {"name": "city", "gain": -24}}]
            (razgon / "story" / "shots.json").write_text(json.dumps({"duration": 12.0, "shots": shots,
                "music": [{"start": 0, "end": 12, "mood": "calm", "intensity": 0.4}], "sfx": [{"t": 9.5, "name": "ding", "gain": -10}]}))
            (razgon / "config.json").write_text(json.dumps({"voiceover": "input/voice.wav", "music": {"gainDb": -13}, "sfx": {"gainDb": -6}}))
            parts = razgon_bridge.render_bed(razgon)
            lean = np.frombuffer(parts.read_bytes()[44:], np.int16).copy()
            import mix as MIX
            whole = razgon_bridge._bed_from_whole_mix(razgon, MIX)
            old = np.frombuffer(whole.read_bytes()[44:], np.int16)
        self.assertEqual(len(lean), len(old))
        self.assertLessEqual(int(np.abs(lean.astype(np.int32) - old).max()), 1)   # float rounding of the voice taken out
        self.assertGreater(int(np.abs(old).max()), 100)                              # there is sound in it

if __name__ == "__main__":
    unittest.main()


class EpisodeFolderTest(unittest.TestCase):
    """Two Cyrillic episodes with one number got one Razgon folder (6 November 2026): the slug keeps the words now,
    a linked episode keeps its folder, and another project's folder is refused."""

    class FakeStudio:
        def __init__(self, link=None):
            self.link = link or {}

        def call(self, method, path, body=None):
            return self.link

    def test_cyrillic_names_keep_their_words(self):
        self.assertEqual(razgon_bridge.slugify("25 Сухость глаз"), "25-sukhost-glaz")
        self.assertNotEqual(razgon_bridge.slugify("25 Сухость глаз"), razgon_bridge.slugify("25 Головокружение при вставании"))
        self.assertEqual(razgon_bridge.slugify("08 Internet Gone"), "08-internet-gone")

    def test_new_linked_and_foreign_folders(self):
        import tempfile
        root = Path(tempfile.mkdtemp())
        project = {"id": "a" * 24, "episode_path": "/x/Алексей Горбунов/25 Сухость глаз"}
        target = razgon_bridge.episode_target(self.FakeStudio(), project, root, None)
        self.assertEqual(target.name, "aleksey-gorbunov-25-sukhost-glaz")
        linked = root / "projects" / "25"
        linked.mkdir(parents=True)
        self.assertEqual(razgon_bridge.episode_target(self.FakeStudio({"project": str(linked)}), project, root, None), linked)
        (linked / "story").mkdir()
        (linked / "story" / "studio_frames.json").write_text('{"project_id": "' + "b" * 24 + '"}', encoding="utf-8")
        with self.assertRaises(razgon_bridge.BridgeError):
            razgon_bridge.episode_target(self.FakeStudio(), project, root, "25")
