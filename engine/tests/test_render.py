"""End-to-end render checks with generated media only."""

import json
import io
from array import array
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ENGINE = Path(__file__).resolve().parents[1] / "render.py"
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg and FFprobe required")
class RenderIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mbvs-engine-test-")
        self.root = Path(self.temp.name)
        Image.new("RGB", (320, 180), (49, 93, 117)).save(self.root / "still.png")
        Image.new("RGBA", (60, 45), (245, 175, 63, 210)).save(self.root / "badge.png")
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x805747:s=320x180:r=15:d=1.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.root / "clip.mp4")], check=True)
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4", "-c:a", "pcm_s16le", str(self.root / "voice.wav")], check=True)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, manifest, output_name="result.mp4", extra=None):
        manifest_path = self.root / "project.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        output = self.root / output_name
        command = [sys.executable, str(ENGINE), "--project", str(manifest_path), "--output", str(output)]
        if extra:
            command += extra
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        return result, output

    def test_renders_mixed_scenes_layers_audio_and_crossfade(self):
        project = {
            "width": 320, "height": 180, "fps": 15,
            "scenes": [
                {"id": "s1", "type": "video", "source": "clip.mp4", "duration": 1.2,
                 "layers": [{"type": "text", "text": "Початок", "x": 10, "y": 15, "font_size": 25, "start": 0.2, "duration": 0.6}],
                 "transition_out": {"type": "crossfade", "duration": 0.25}},
                {"id": "s2", "type": "image", "source": "still.png", "duration": 1.1,
                 "layers": [{"type": "image", "source": "badge.png", "width": 60, "height": 45, "x": 20, "y": 80,
                             "keyframes": [{"time": 0, "x": 20}, {"time": 1, "x": 160}]}],
                 "transition_out": {"type": "cut"}},
                {"id": "s3", "type": "text", "text": "Готово", "duration": 0.8},
            ],
            "tracks": [{"kind": "voice", "source": "voice.wav", "volume": 0.8, "start": 0, "trim_start": 0.2, "duration": 2.6}],
        }
        result, output = self.invoke(project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(output.is_file())
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        self.assertEqual(events[-1]["stage"], "complete")
        self.assertEqual(sum(event["stage"] == "scene_done" for event in events), 3)
        info = json.loads(subprocess.check_output([FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(output)]))
        kinds = {stream["codec_type"] for stream in info["streams"]}
        self.assertEqual(kinds, {"video", "audio"})
        self.assertAlmostEqual(float(info["format"]["duration"]), 2.85, delta=0.25)
        self.assertFalse(list(self.root.glob(".*.render-*.mp4")))

    def test_bad_media_fails_without_output(self):
        project = {"width": 320, "height": 180, "fps": 15,
                   "scenes": [{"type": "video", "source": "missing.mp4", "duration": 1}]}
        result, output = self.invoke(project)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        self.assertIn('"stage": "error"', result.stdout)

    def test_legacy_swipe_transition_exports(self):
        project = {"width": 320, "height": 180, "fps": 15,
                   "scenes": [{"type": "color", "color": "#aa3322", "duration": .8,
                               "transition_out": {"type": "swipe", "duration": .2}},
                              {"type": "color", "color": "#2244aa", "duration": .8}]}
        result, output = self.invoke(project, "swipe.mp4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(output.is_file())

    def test_timed_text_appears_only_inside_layer_interval_and_silent_audio_exists(self):
        project = {"width": 320, "height": 180, "fps": 15,
                   "scenes": [{"type": "color", "color": "#101114", "duration": 1.5,
                               "layers": [{"type": "text", "text": "ВАЖЛИВО", "x": 0.5, "y": 0.5,
                                           "width": 0.8, "height": 0.3, "font_size": 34,
                                           "start": 0.5, "duration": 0.5}]}]}
        result, output = self.invoke(project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        def bright_count(second):
            image_bytes = subprocess.check_output([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(second),
                                                   "-i", str(output), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"])
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            return sum(1 for r, g, b in image.getdata() if min(r, g, b) > 150)

        self.assertLess(bright_count(0.2), 5)
        self.assertGreater(bright_count(0.7), 50)
        self.assertLess(bright_count(1.2), 5)
        info = json.loads(subprocess.check_output([FFPROBE, "-v", "error", "-show_streams", "-of", "json", str(output)]))
        self.assertIn("audio", {stream["codec_type"] for stream in info["streams"]})

    def test_universal_layers_with_animation_overlap_sound_and_swipe(self):
        project = {
            "width": 320, "height": 180, "fps": 15,
            "timeline_layers": [
                {"id": "background", "z": 0, "clips": [
                    {"id": "still", "type": "image", "source": "still.png", "start": 0, "duration": 1.4,
                     "transition": {"type": "swipe", "duration": 0.2}},
                    {"id": "video", "type": "video", "source": "clip.mp4", "start": 1.2, "duration": 1.0,
                     "volume": 0}]},
                {"id": "top", "z": 1, "clips": [
                    {"id": "title", "type": "text", "text": "РУХ", "start": 0.2, "duration": 1.0,
                     "x": 0.5, "y": 0.5, "width": 0.6, "height": 0.3,
                     "keyframes": [{"time": 0, "scale": 0.8, "opacity": 0, "x": 0.3},
                                   {"time": 0.6, "scale": 1.2, "opacity": 1, "x": 0.5}]},
                    {"id": "shape", "type": "animation", "color": "#ffcc44", "start": 1.3, "duration": 0.7, "units": "px",
                     "x": 20, "y": 20, "width": 60, "height": 40,
                     "keyframes": [{"time": 0, "x": 20, "opacity": 0.2, "scale": 0.8},
                                   {"time": 0.7, "x": 120, "opacity": 1, "scale": 1.2}]}]},
                {"id": "sound", "z": 2, "clips": [
                    {"id": "voice", "type": "audio", "source": "voice.wav", "start": 0.1,
                     "duration": 1.8, "trim_start": 0.2, "volume": 0.6}]},
            ]
        }
        result, output = self.invoke(project, "universal.mp4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(output.is_file())
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        self.assertEqual(events[-1]["stage"], "complete")
        self.assertEqual(events[-1]["scenes"], 6)
        info = json.loads(subprocess.check_output([FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(output)]))
        self.assertAlmostEqual(float(info["format"]["duration"]), 2.2, delta=0.2)
        self.assertEqual({stream["codec_type"] for stream in info["streams"]}, {"video", "audio"})
        def count_pixels(second, predicate):
            image_bytes = subprocess.check_output([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(second),
                                                   "-i", str(output), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"])
            return sum(1 for color in Image.open(io.BytesIO(image_bytes)).convert("RGB").getdata() if predicate(*color))
        self.assertGreater(count_pixels(.9, lambda r, g, b: min(r, g, b) > 180),
                           count_pixels(.3, lambda r, g, b: min(r, g, b) > 180) + 20)
        self.assertGreater(count_pixels(1.9, lambda r, g, b: r > 180 and g > 145 and b < 120),
                           count_pixels(1.35, lambda r, g, b: r > 180 and g > 145 and b < 120) + 50)
        self.assertFalse(list(self.root.glob(".*.render-*.mp4")))

    def test_universal_video_audio_volume_and_silent_default(self):
        sounding = self.root / "sounding.mp4"
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=0x805747:s=320x180:r=15:d=1", "-f", "lavfi", "-i",
                        "sine=frequency=440:sample_rate=48000:duration=1", "-c:v", "libx264", "-pix_fmt",
                        "yuv420p", "-c:a", "aac", "-shortest", str(sounding)], check=True)
        source_before = sounding.read_bytes()

        def level(path):
            raw = subprocess.check_output([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(path),
                                           "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"])
            samples = array("h")
            samples.frombytes(raw)
            return max(abs(sample) for sample in samples)

        for volume, filename in [(None, "muted.mp4"), (.8, "audible.mp4")]:
            clip = {"id": "video", "type": "video", "source": "sounding.mp4", "start": 0, "duration": .8}
            if volume is not None:
                clip["volume"] = volume
            project = {"width": 320, "height": 180, "fps": 15,
                       "timeline_layers": [{"id": "all", "z": 0, "clips": [clip]}]}
            result, output = self.invoke(project, filename)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            frame_bytes = subprocess.check_output([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", "0.4",
                                                   "-i", str(output), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"])
            center = Image.open(io.BytesIO(frame_bytes)).convert("RGB").getpixel((160, 90))
            self.assertGreater(center[0], 70)
            if volume is None:
                self.assertLess(level(output), 4)
            else:
                self.assertGreater(level(output), 100)
        self.assertEqual(sounding.read_bytes(), source_before)

    def test_cancel_keeps_episode_output_absent(self):
        manifest = {"width": 320, "height": 180, "fps": 15,
                    "timeline_layers": [{"id": "visual", "z": 0, "clips": [
                        {"id": "long", "type": "image", "source": "still.png", "start": 0, "duration": 60}]}]}
        project_file = self.root / "cancel.json"
        project_file.write_text(json.dumps(manifest), encoding="utf-8")
        output = self.root / "cancelled.mp4"
        process = subprocess.Popen([sys.executable, str(ENGINE), "--project", str(project_file), "--output", str(output)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        observed = []
        try:
            for line in process.stdout:
                observed.append(line)
                # the first sign of work on either route: the CPU route's scene_start, the Apple GPU route's gpu_start
                if '"stage": "scene_start"' in line or '"stage": "gpu_start"' in line:
                    process.terminate()
                    break
            remaining, errors = process.communicate(timeout=15)
            observed.append(remaining)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        self.assertNotEqual(process.returncode, 0, "".join(observed))
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".*.render-*.mp4")))

    def test_four_motion_curves_have_expected_rendered_positions(self):
        modes = [("linear", .25), ("ease_in", .25**3), ("ease_out", 1-.75**3), ("ease_in_out", .25**2*(3-2*.25))]
        project = {"width": 320, "height": 180, "fps": 20, "timeline_layers": [
            {"id": mode, "clips": [{"id": mode, "type": "animation", "content_type": "shape", "color": "#ffffff", "start": index, "duration": 1, "width": .1, "height": .1, "x": .2, "y": .5, "easing": mode, "keyframes": [{"time": 0, "x": .2}, {"time": 1, "x": .8}]}]}
            for index, (mode, _) in enumerate(modes)
        ]}
        result, output = self.invoke(project, "motion-curves.mp4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for index, (mode, progress) in enumerate(modes):
            data = subprocess.check_output([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(index+.25), "-i", str(output), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"])
            image = Image.open(io.BytesIO(data)).convert("RGB")
            bright = [x for x in range(320) if min(image.getpixel((x, 90))) > 200]
            self.assertTrue(bright, mode)
            center = (min(bright)+max(bright))/2
            self.assertAlmostEqual(center, (.2+.6*progress)*320, delta=4, msg=mode)

    def frame(self, output, second):
        data = subprocess.check_output([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(second), "-i", str(output), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"])
        return Image.open(io.BytesIO(data)).convert("RGB")

    def test_vertical_image_sits_in_the_middle_of_its_box(self):
        # a 3:4 photo in a full 16:9 box keeps its shape between two black side fields, as the preview shows it
        Image.new("RGB", (90, 120), (230, 60, 60)).save(self.root / "tall.png")
        project = {"width": 320, "height": 180, "fps": 15, "background": "#000000", "timeline_layers": [{"id": "photo", "clips": [
            {"id": "tall", "type": "image", "source": "tall.png", "start": 0, "duration": 1, "x": .5, "y": .5, "width": 1, "height": 1}]}]}
        result, output = self.invoke(project, "tall.mp4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        image = self.frame(output, .5)
        red = [x for x in range(320) if image.getpixel((x, 90))[0] > 150]
        self.assertAlmostEqual((min(red) + max(red)) / 2, 160, delta=3)
        self.assertAlmostEqual(max(red) - min(red) + 1, 135, delta=4)   # 180 * 3/4, not stretched

    def test_words_of_a_moving_text_move_with_it(self):
        # a label pinned to a panning photo: its card and its timed words carry the same keyframes and stay together
        motion = [{"time": 0, "x": .3, "y": .5, "scale": 1}, {"time": 1.5, "x": .7, "y": .5, "scale": 1}]
        project = {"width": 320, "height": 180, "fps": 20, "background": "#000000", "timeline_layers": [
            {"id": "card", "clips": [{"id": "card", "type": "animation", "content_type": "shape", "color": "#2040c0", "start": 0, "duration": 1.5,
                                      "x": .3, "y": .5, "width": .3, "height": .2, "easing": "ease_in_out", "keyframes": motion}]},
            {"id": "label", "clips": [{"id": "label", "type": "text", "text": "НН", "start": 0, "duration": 1.5, "x": .3, "y": .5, "width": .3, "height": .2,
                                       "font_size": 30, "color": "#ffffff", "easing": "ease_in_out", "keyframes": motion,
                                       "text_words": [{"text": "НН", "start": 0, "x": .5, "y": .5, "width": .5, "height": .6}]}]}]}
        result, output = self.invoke(project, "moving-text.mp4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for second in (.1, .75, 1.4):
            image = self.frame(output, second)
            card = [x for x in range(320) if image.getpixel((x, 75))[2] > 150 and image.getpixel((x, 75))[0] < 90]
            white = [x for x in range(320) for y in range(70, 110) if min(image.getpixel((x, y))) > 200]
            self.assertTrue(card and white, second)
            self.assertAlmostEqual((min(white) + max(white)) / 2, (min(card) + max(card)) / 2, delta=6, msg=second)

    def test_transition_connects_separate_item_layers(self):
        project = {"width": 320, "height": 180, "fps": 20, "layer_mode": "item", "timeline_layers": [
            {"id": "first", "clips": [{"id": "red", "type": "animation", "content_type": "shape", "color": "#ff0000", "start": 0, "duration": 1, "width": 1, "height": 1, "transition": {"type": "crossfade", "duration": .4}}]},
            {"id": "second", "clips": [{"id": "blue", "type": "animation", "content_type": "shape", "color": "#0000ff", "start": 1, "duration": 1, "width": 1, "height": 1}]}
        ]}
        result, output = self.invoke(project, "item-transition.mp4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        def pixel_at(time):
            data = subprocess.check_output([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(time), "-i", str(output), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"])
            return Image.open(io.BytesIO(data)).convert("RGB").getpixel((160,90))
        self.assertGreater(pixel_at(.4)[0], 220)
        self.assertLess(pixel_at(.8)[0], 180)
        self.assertLess(pixel_at(1.2)[2], 180)
        self.assertGreater(pixel_at(1.6)[2], 220)


if __name__ == "__main__":
    unittest.main()
