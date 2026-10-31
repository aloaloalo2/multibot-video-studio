import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.tests import test_backend as support

app, store = support.app, support.store
import razgon_export  # noqa: E402

RAZGON = razgon_export.BRIDGE.parents[1] / "What If" / "razgon-2d-studio"
FPS = 25
# Stands in for Razgon's renderer: every rendered frame clip is plain red, and each render logs its start and end time.
# A file "fail" in the project makes the render of the frame starting at 1.4 s fail.
FAKE_RENDER = """import fs from 'node:fs'; import path from 'node:path'; import { spawnSync } from 'node:child_process';
const a = process.argv.slice(2), arg = (k) => a[a.indexOf('--' + k) + 1], t0 = Date.now();
const cfg = JSON.parse(fs.readFileSync(path.join(arg('project'), 'config.json'), 'utf8'));
const n = Math.round(+arg('to') * cfg.fps) - Math.round(+arg('from') * cfg.fps);
if (+arg('from') === 1.4 && fs.existsSync(path.join(arg('project'), 'fail'))) process.exit(1);
spawnSync('sleep', ['0.4']);
const status = spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', `color=c=red:s=320x180:r=${cfg.fps}`, '-frames:v', String(n),
  '-c:v', 'libx264', '-pix_fmt', 'yuv420p', arg('out')]).status;
fs.appendFileSync(path.join(arg('project'), 'renders.log'), `${arg('from')} ${t0} ${Date.now()}\\n`);
process.exit(status);
"""


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def pixel(path, seconds, x, y):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    offset = (y * 320 + x) * 3
    return tuple(raw[offset:offset + 3])


def loudness(path):
    log = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(log.rsplit("I:", 1)[1].split("LUFS")[0])


def frame_count(path):
    return int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets",
                               "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip())


def audio_hash(path):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-c", "copy", "-f", "streamhash", "-"],
                          capture_output=True, text=True, check=True).stdout


def ssim(a, b):
    log = subprocess.run(["ffmpeg", "-nostats", "-i", str(a), "-i", str(b), "-lavfi", "ssim", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(log.rsplit("All:", 1)[1].split()[0])


@unittest.skipUnless(shutil.which("node") and shutil.which("ffmpeg") and (RAZGON / "audio" / "mix.py").is_file(), "Razgon 2D Studio, node and ffmpeg required")
class RazgonExportTest(unittest.TestCase):
    setUpClass = classmethod(support.BackendTest.setUpClass.__func__)
    tearDownClass = classmethod(support.BackendTest.tearDownClass.__func__)

    def episode(self, name):
        """A three-frame Razgon episode: frames 1 and 3 are still code blocks, frame 2 is a rendered blue clip on the timeline."""
        base = Path(self.tmp.name) / ("razgon-" + name)
        root, film = base / "studio", base / "studio" / "projects" / "demo"
        for folder in (film / "story", film / "input", film / "build", root / "tools"):
            folder.mkdir(parents=True, exist_ok=True)
        (root / "audio").symlink_to(RAZGON / "audio")   # Razgon's own mixer, with music and SFX switched off below
        (root / "render.mjs").write_text(FAKE_RENDER)
        (root / "tools" / "live.mjs").write_text("")
        ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:duration=2:sample_rate=48000", "-af", "volume=-24dB", "-ac", "2", film / "input" / "voiceover.wav")
        ffmpeg("-f", "lavfi", "-i", "color=c=black@0:s=320x180,format=rgba,drawbox=x=280:y=0:w=40:h=24:color=white@1:t=fill:replace=1", "-frames:v", "1", film / "input" / "plashka.png")
        (film / "config.json").write_text(json.dumps({"title": "Demo", "fps": FPS, "aspect": "16:9", "resolution": "180p", "duration": 2.0, "loudness": -14,
                                                      "voiceover": "input/voiceover.wav", "overlay": "input/plashka.png",
                                                      "music": {"enabled": False}, "sfx": {"enabled": False}}))
        (film / "story" / "shots.json").write_text(json.dumps({"duration": 2.0, "shots": [{"id": "s1", "start": 0, "end": 2.0}]}))

        project = store.create_project(store.channel_id(self.channel), "Razgon " + name)
        episode = Path(project["episode_path"]); episode.mkdir(parents=True, exist_ok=True)
        (episode / "razgon.json").write_text(json.dumps({"razgon_root": str(root), "project": str(film)}))
        voice, plate = episode / "voice.wav", episode / "plashka.png"
        shutil.copy2(film / "input" / "voiceover.wav", voice); shutil.copy2(film / "input" / "plashka.png", plate)
        blue = episode / "frame_002.mp4"
        ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=320x180:r=%d" % FPS, "-frames:v", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p", blue)
        assets = {key: store.asset_record(path, project["id"], "episode") for key, path in {"voice": voice, "blue": blue, "plate": plate}.items()}
        (film / "story" / "studio_frames.json").write_text(json.dumps({
            "project_id": project["id"], "script_sha256": "script", "audio_sha256": "audio", "voice_asset_id": assets["voice"]["id"],
            "duration": 2.0, "fps": FPS, "frames": [{"number": 1, "start": 0, "end": .4}, {"number": 2, "start": .4, "end": 1.4}, {"number": 3, "start": 1.4, "end": 2.0}]}))
        clip = lambda **fields: {"start": 0, "duration": 2.0, "trim_start": 0, "volume": 1, "transition": {"type": "cut", "duration": 0}, "x": .5, "y": .5,
                                 "width": 1, "height": 1, "scale": 1, "opacity": 1, "keyframes": [], **fields}
        project = store.load_project(project["id"])
        project.update(fps=FPS, width=320, height=180, duration=2.0, assets=list(assets.values()))
        project["tracks"] = [{"id": "layer-1", "name": "Шар 1", "type": "universal", "clips": [clip(id="voice", kind="audio", asset_id=assets["voice"]["id"], title="Озвучка")]},
                             {"id": "layer-2", "name": "f1", "type": "universal", "clips": [clip(id="f1", kind="animation", content_type="shape", duration=.4, opacity=0, title="Razgon · кадр 001")]},
                             {"id": "layer-3", "name": "f2", "type": "universal", "clips": [clip(id="f2", kind="video", asset_id=assets["blue"]["id"], start=.4, duration=1.0, volume=0, title="Razgon · кадр 002")]},
                             {"id": "layer-5", "name": "f3", "type": "universal", "clips": [clip(id="f3", kind="animation", content_type="shape", start=1.4, duration=.6, opacity=0, title="Razgon · кадр 003")]},
                             {"id": "layer-4", "name": "Плашка каналу", "type": "universal", "clips": [clip(id="plate", kind="image", asset_id=assets["plate"]["id"], title="Плашка каналу")]}]
        store.save_project(project)
        plan = {"script_sha256": "script", "timing": {"status": "audio_synced", "audio": {"sha256": "audio", "asset_id": assets["voice"]["id"]}}}
        return store.load_project(project["id"]), root, film, plan

    def export(self, project, plan, status="complete", engine=False):
        ready = {"stage": "audio_synced", "plan_ready": True, "export_ready": True, "reason": ""}
        # the fake render.mjs takes no memory: the RAM of the machine running the tests must not decide how many frames
        # render side by side (razgon_bridge.RAM_LIMIT)
        normalize = app.normalize_for_engine if engine else lambda project: (_ for _ in ()).throw(AssertionError("a Razgon film does not go through the Studio engine"))
        with patch.dict(os.environ, {"RAZGON_RAM_LIMIT": "100"}), \
             patch.object(store, "plan_readiness", return_value=ready), patch.object(store, "load_project_plan", return_value=plan), \
             patch.object(app, "normalize_for_engine", side_effect=normalize):
            job = app.start_export(store.load_project(project["id"]), True)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline and job["status"] not in {"complete", "failed", "cancelled"}:
                time.sleep(.1)
                job = app.load_job(job["id"])
        self.assertEqual(job["status"], status, job)
        return job

    def renders(self, film):
        return sorted(line.split() for line in (film / "renders.log").read_text().splitlines())

    def test_export_renders_code_blocks_and_matches_bridge_final(self):
        project, root, film, plan = self.episode("film")
        job = self.export(project, plan)
        out = Path(job["output_path"])
        self.assertEqual((job["razgon_completed"], job["razgon_total"], job["progress"]), (3, 3, 100))   # the whole film
        renders = self.renders(film)
        self.assertEqual([item[0] for item in renders], ["0.0", "1.4"])   # only the code blocks were drawn,
        self.assertLess(max(int(item[1]) for item in renders), min(int(item[2]) for item in renders))   # side by side
        self.assertEqual(frame_count(out), 2 * FPS)
        red, blue, red_end = pixel(out, .2, 160, 90), pixel(out, .9, 160, 90), pixel(out, 1.7, 160, 90)
        self.assertTrue(red[0] > 200 > max(red[1:]) and red_end[0] > 200 > max(red_end[1:]) and blue[2] > 200 > max(blue[:2]), (red, blue, red_end))
        self.assertGreater(min(pixel(out, .2, 300, 10) + pixel(out, .9, 300, 10)), 230)   # the channel plate stays on top
        self.assertAlmostEqual(loudness(out), -14, delta=1)

        # a second export draws nothing: the clip in build/studio was rendered from the same scenes for the same times
        again = self.export(project, plan)
        self.assertEqual(self.renders(film), renders)
        self.assertEqual((again["razgon_completed"], again["razgon_total"]), (3, 3))   # all done from the start

        # the agent's route gives the same film: final glues build/studio, where push leaves the timeline's clips. The sound is
        # identical; the picture matches frame for frame (Apple's hardware encoder does not repeat its bits run to run)
        shutil.copy2(Path(project["episode_path"]) / "frame_002.mp4", film / "build" / "studio" / "frame_002.mp4")
        final = Path(self.tmp.name) / "final.mp4"
        subprocess.run([sys.executable, str(razgon_export.BRIDGE), "final", "--razgon", str(film), "--out", str(final)], check=True, capture_output=True)
        self.assertEqual((frame_count(final), audio_hash(final)), (frame_count(out), audio_hash(out)))
        self.assertGreater(ssim(final, out), .99)

    def test_timeline_that_is_not_the_film(self):
        project, root, film, plan = self.episode("edited")
        project["tracks"][0]["clips"].append({"id": "own", "kind": "text", "text": "Hi", "start": 0, "duration": 1, "title": "Мій текст"})
        with patch.object(store, "load_project_plan", return_value=plan):
            # frames 1 and 3 are still code and the timeline is more than the film: the bridge renders only those two, then
            # the Studio engine exports the timeline (a mixed episode, test_mixed_episode_export)
            self.assertEqual(razgon_export.export_job(project), {"mixed": True, "razgon": str(film), "blocks": {"f1": 1, "f3": 3}})
            with patch.object(store, "load_project_plan", return_value={**plan, "script_sha256": "changed"}):
                with self.assertRaises(store.StudioError) as caught:   # the Razgon project no longer matches the plan
                    razgon_export.export_job(project)
            self.assertEqual(caught.exception.status, 409)
            rendered = json.loads(json.dumps(project))
            for layer in (1, 3):
                rendered["tracks"][layer]["clips"][0].update(kind="video", asset_id=project["tracks"][2]["clips"][0]["asset_id"], content_type=None, opacity=1)
            self.assertIsNone(razgon_export.export_job(rendered))   # every frame rendered: the Studio engine exports it as before
            project["tracks"][0]["clips"].pop()   # without its own text the timeline is the film again
            spec = razgon_export.export_job(project)
        self.assertEqual((spec["render"], spec["clips"]["1"], spec["clips"]["3"], Path(spec["overlay"]).name), (2, None, None, "plashka.png"))
        self.assertTrue(spec["clips"]["2"].endswith("frame_002.mp4"))
        self.assertIsNone(razgon_export.export_job(store.create_project(store.channel_id(self.channel), "Not Razgon")))

    def test_mixed_episode_export(self):
        """Photos, stock and text around some Razgon frames (Alexey Gorbunov, 31 October 2026): «Експорт MP4» renders only
        the code blocks, then the Studio engine exports the whole timeline with its own clips and a transition."""
        project, root, film, plan = self.episode("mixed")
        project["tracks"].insert(4, {"id": "layer-6", "name": "own", "type": "universal", "clips": [
            {"id": "own", "kind": "animation", "content_type": "shape", "color": "#00ff00", "start": 0, "duration": .2, "trim_start": 0, "volume": 1,
             "transition": {"type": "cut", "duration": 0}, "x": .1, "y": .9, "width": .1, "height": .1, "scale": 1, "opacity": 1, "keyframes": [], "title": "Мій знак"}]})
        # a transition out of a code block fades over the block's held tail
        project["scene_groups"] = [{"id": "g1", "title": "Кадр 1", "clip_ids": ["f1"], "role": "scene"}, {"id": "g2", "title": "Кадр 2", "clip_ids": ["f2"], "role": "scene"}]
        project["join_transitions"] = [{"id": "j", "from_ref": "group:g1", "to_ref": "group:g2", "type": "crossfade", "duration": .2, "seam": .4}]
        store.save_project(project)
        job = self.export(store.load_project(project["id"]), plan, engine=True)
        self.assertEqual([item[0] for item in self.renders(film)], ["0.0", "1.4"])   # only the code blocks were drawn
        self.assertEqual((job["razgon_completed"], job["razgon_total"]), (2, 2))
        self.assertTrue((film / "build" / "studio" / "frame_001_tail.mp4").is_file())   # the held tail for the transition out of it
        out = Path(job["output_path"])
        red, blue, red_end = pixel(out, .3, 160, 90), pixel(out, .9, 160, 90), pixel(out, 1.8, 160, 90)
        self.assertTrue(red[0] > 200 > max(red[1:]) and red_end[0] > 200 > max(red_end[1:]) and blue[2] > 200 > max(blue[:2]), (red, blue, red_end))
        fading = pixel(out, .46, 160, 90)
        self.assertTrue(fading[0] > 20 and fading[2] > 20, fading)   # red fading into blue: the tail fills the transition
        mark = pixel(out, .1, 32, 162)
        self.assertTrue(mark[1] > 200 > max(mark[0], mark[2]), mark)   # the author's own clip is in the film

    def test_failed_frame_is_named_in_the_job(self):
        project, root, film, plan = self.episode("failing")
        (film / "fail").write_text("")
        job = self.export(project, plan, status="failed")
        self.assertEqual(job["error"], "Кадр 3: render.mjs завершився з кодом 1")
        self.assertIsNone(job["output_path"])
