"""The export draws what the preview shows: the preview's own JavaScript against the engine on the same clips.

Pure math is compared directly (keyframes, word entrances, contained pictures, transition covers, the motion that
carries an outgoing clip through its transition); what only a render can show (a vertical video in its box, a moving
label's entrance, slide and zoom transitions) is rendered with generated media and measured against the preview's
numbers.
"""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "backend"))
sys.path.insert(0, str(HERE))
import render  # noqa: E402
import transition_graphics  # noqa: E402
import joins  # noqa: E402
import preview_js  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
ENGINE = HERE.parent / "render.py"

KEYFRAME_CLIPS = [
    {"x": .3, "keyframes": [{"time": 1, "x": .8}]},                                            # first keyframe after 0
    {"scale": 1, "keyframes": [{"time": 0, "scale": 1.2}, {"time": 2, "scale": 1.0}]},        # a keyframe at 0 wins
    {"x": .5, "easing": "ease_in_out", "keyframes": [{"time": 0, "x": .2}, {"time": 1, "x": .9}, {"time": 2.5, "x": .4}]},
    {"opacity": 1, "keyframes": [{"time": .5, "opacity": 0}, {"time": 1, "opacity": 1}]},
    {"y": .4, "keyframes": [{"time": 0, "y": .7}]},                                            # a single keyframe holds
    {"scale": 1.1, "easing": "ease_out", "keyframes": [{"time": .4, "scale": 1.3, "x": .6}, {"time": 2, "scale": 1.0}]},
]
LOCALS = [0, .2, .4, .5, .75, .99, 1, 1.5, 2, 2.9]


@unittest.skipUnless(preview_js.NODE, "node required")
class PreviewMathParity(unittest.TestCase):
    def test_keyframe_values_match_the_preview(self):
        clips = []
        for index, extra in enumerate(KEYFRAME_CLIPS):
            clips.append({"id": f"c{index}", "type": "animation", "content_type": "shape", "color": "#ffffff", "start": 0, "duration": 3,
                          "width": .2, "height": .2, **extra})
        project = {"width": 320, "height": 180, "fps": 30, "timeline_layers": [{"id": "l", "clips": clips}]}
        visual, _, _ = render.timeline_plan(project, Path("unused.json"), 320, 180, 30)
        bases = {"x": .5, "y": .5, "scale": 1, "opacity": 1}
        script = f"const clips={json.dumps(clips)},locals={json.dumps(LOCALS)};" + \
            "console.log(JSON.stringify(clips.map(c=>['x','y','scale','opacity'].map(k=>locals.map(t=>keyframeValue(c,k,Number(c[k]??(k==='x'||k==='y'?.5:1)),t))))))"
        preview = preview_js.run(["easedProgress", "keyframePoints", "keyframeValue"], script)
        for clip, record, values in zip(clips, visual, preview):
            for key, row in zip(("x", "y", "scale", "opacity"), values):
                base = float(clip.get(key, bases[key]))
                for local, expected in zip(LOCALS, row):
                    exported = render.scalar_value(record["keyframes"], key, base, local, record["easing"])
                    self.assertAlmostEqual(exported, expected, places=6, msg=f"{clip['id']} {key} at {local}")

    def test_word_entrances_match_the_preview(self):
        types = ["fade", "up", "down", "left", "right", "pop", "grow", "shrink", "blur", "blur_up", "letters_up", "letters_blur"]
        raws = [0, .1, .3, .45, .66, .7, .9, 1]
        script = f"const types={json.dumps(types)},raws={json.dumps(raws)};" + r"""
const state={project:{width:1920}};
const element=()=>{const children={'.word-sharp':{style:{}},'.word-blur':{style:{}}};return {style:{},querySelector:s=>children[s]};};
console.log(JSON.stringify(types.map(type=>raws.map(raw=>{
  const node=element(),effect={type,duration:.2,distance:30};applyWordEntrance(node,1,{word_entrance:effect},1+raw*.2,1920);
  const m=node.style.transform.match(/translate\(([-\d.e]+)px, *([-\d.e]+)px\) scale\(([-\d.e]+)\)/);
  const sharp=node.querySelector('.word-sharp').style.opacity,blur=node.querySelector('.word-blur').style.opacity;
  return [Number(m[1]),Number(m[2]),Number(m[3]),Number(node.style.opacity)*(sharp===undefined?1:Number(sharp)),blur===undefined?0:Number(blur)];
}))))"""
        preview = preview_js.run(["easedProgress", "applyWordEntrance"], script)
        for type_, rows in zip(types, preview):
            for raw, expected in zip(raws, rows):
                exported = render.entrance_state({"type": type_, "duration": .2, "distance": 30}, raw)
                for name, a, b in zip(("dx", "dy", "scale", "opacity", "blur"), exported, expected):
                    self.assertAlmostEqual(a, b, places=6, msg=f"{type_} {name} at {raw}")

    def test_a_picture_takes_the_same_share_of_its_box(self):
        cases = [(90, 160, 1920, 1080), (1600, 900, 1920, 1080), (4000, 1000, 800, 800), (300, 300, 400, 200)]
        preview = preview_js.run(["containedBox"], f"console.log(JSON.stringify({json.dumps(cases)}.map(c=>containedBox(...c))))")
        with tempfile.TemporaryDirectory() as folder:
            for (w, h, bw, bh), share in zip(cases, preview):
                path = Path(folder) / f"{w}x{h}.png"
                Image.new("RGB", (w, h)).save(path)
                cw, ch = render.contained(str(path), bw, bh)
                self.assertAlmostEqual(cw / bw, share["width"], delta=1.5 / bw)
                self.assertAlmostEqual(ch / bh, share["height"], delta=1.5 / bh)

    def test_transition_covers_have_the_same_shapes(self):
        styles = [style for style, config in transition_graphics.PRESETS.items() if config.get("kind") != "cinematic"]
        moments = [.05, .2, .42, .5, .6, .8, .95]
        script = f"const graphicTransitionPresets={json.dumps(transition_graphics.PRESETS)};" + \
            f"console.log(JSON.stringify({json.dumps(styles)}.map(s=>{json.dumps(moments)}.map(p=>graphicShapes(s,p,960,540)))))"
        preview = preview_js.run(["easedProgress", "graphicShapes"], script)
        rounded = lambda value: json.loads(json.dumps(value), parse_float=lambda f: round(float(f), 3))
        for style, frames in zip(styles, preview):
            for p, shapes in zip(moments, frames):
                self.assertEqual(rounded(transition_graphics.shapes(style, p, 960, 540)), rounded(shapes), f"{style} at {p}")

    def test_an_outgoing_clip_moves_through_its_transition_as_in_the_preview(self):
        cases = [
            [{"time": 0, "scale": 1.0, "x": .4}, {"time": 3, "scale": 1.3, "x": .6}],     # still moving at its end
            [{"time": 0, "scale": 1.0}, {"time": 1, "scale": 1.2}],                       # stopped a while ago
            [{"time": 0, "scale": 1.2}],                                                  # a single keyframe
            [{"time": 1, "scale": 1.2}, {"time": 2.999, "scale": 1.3}],                  # first keyframe later than 0
        ]
        moments = [3.05, 3.2, 3.35]
        for points in cases:
            clip = {"id": "a", "kind": "image", "start": 0, "duration": 3, "x": .5, "y": .5, "scale": 1, "opacity": 1, "keyframes": points}
            project = {"fps": 30, "tracks": [{"id": "t", "clips": [clip, {"id": "b", "kind": "image", "start": 3, "duration": 2}]}],
                       "scene_groups": [{"id": "a", "clip_ids": ["a"]}, {"id": "b", "clip_ids": ["b"]}]}
            joins.set_transition(project, {"from_ref": "group:a", "to_ref": "group:b", "type": "crossfade", "duration": .35})
            layers = [{"id": "t", "z": 0, "clips": [{**c, "type": c["kind"]} for c in project["tracks"][0]["clips"]]}]
            joins.transport(project, layers)
            exported = layers[0]["clips"][0]["keyframes"]
            script = f"const clip={json.dumps(clip)},moments={json.dumps(moments)},graphicTransitionPresets={{}};" + \
                "const transitionInfo=()=>({outgoing:{seam:3,duration:.35,type:'none'}});" + \
                "console.log(JSON.stringify(moments.map(t=>transitionValues(clip,t,{x:keyframeValue(clip,'x',.5,t),y:.5,scale:keyframeValue(clip,'scale',1,t),opacity:1}))))"
            preview = preview_js.run(["easedProgress", "keyframePoints", "keyframeValue", "visualFrameTime", "joinFrames", "transitionValues"],
                                     "const state={project:{fps:30}};" + script)
            for moment, values in zip(moments, preview):
                for key in ("x", "scale"):
                    keys = [dict(p) for p in exported]
                    for prop, base in (("x", .5), ("scale", 1.0)):
                        times = [float(p["time"]) for p in keys if prop in p]
                        if times and min(times) > 1e-9:
                            keys.append({"time": 0, prop: base})
                    self.assertAlmostEqual(render.scalar_value(keys, key, .5 if key == "x" else 1.0, moment, "linear"), values[key], places=5,
                                           msg=f"{points} {key} at {moment}")


@unittest.skipUnless(preview_js.NODE and FFMPEG, "node and ffmpeg required")
class RenderedParity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mbvs-parity-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def render(self, manifest):
        path = self.root / "project.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        output = self.root / f"out-{len(list(self.root.glob('out-*')))}.mp4"
        result = subprocess.run([sys.executable, str(ENGINE), "--project", str(path), "--output", str(output)], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])
        return output

    def frame(self, output, second):
        data = subprocess.check_output([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{second:.4f}", "-i", str(output), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"])
        return Image.open(io.BytesIO(data)).convert("RGB")

    def preview_values(self, clip, moments, join, fps=20):
        script = f"const clip={json.dumps(clip)},moments={json.dumps(moments)},graphicTransitionPresets={{}},state={{project:{{fps:{fps}}}}};" + \
            f"const transitionInfo=()=>({json.dumps(join)});" + \
            "console.log(JSON.stringify(moments.map(t=>transitionValues(clip,t-clip.start,{x:clip.x,y:clip.y,scale:1,opacity:1}))))"
        return preview_js.run(["easedProgress", "keyframePoints", "keyframeValue", "visualFrameTime", "joinFrames", "transitionValues"], script)

    def test_a_transition_of_a_fractional_length_runs_on_whole_frames_in_both(self):
        # 0.35 s at 25 fps: the export draws 9 frames (0.36 s); the preview used to finish 0.01 s sooner and stood
        # up to 35 px apart from the film halfway through a slide (GORBUNOV-23, frames 82-83)
        join = {"type": "slide_left", "duration": .35, "seam": 1.0}
        blue = {"id": "blue", "type": "animation", "content_type": "shape", "color": "#0000ff", "start": 1, "duration": 1, "x": .5, "y": .5,
                "width": .5, "height": .5, "join_in": join}
        output = self.render({"width": 320, "height": 180, "fps": 25, "background": "#000000", "timeline_layers": [{"id": "b", "clips": [blue]}]})
        for moment in (1.16, 1.2, 1.24, 1.28):
            values = self.preview_values(blue, [moment], {"incoming": join}, fps=25)[0]
            image = self.frame(output, moment)
            blues = [x for x in range(320) if image.getpixel((x, 90))[2] > 150]
            self.assertAlmostEqual(min(blues), values["x"] * 320 - 80, delta=2.5, msg=moment)

    def test_vertical_video_sits_in_the_middle_of_its_box(self):
        source = self.root / "tall.mp4"
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0xe03c3c:s=90x160:r=15:d=1.2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], check=True)
        output = self.render({"width": 320, "height": 180, "fps": 15, "background": "#000000", "timeline_layers": [{"id": "v", "clips": [
            {"id": "tall", "type": "video", "source": str(source), "start": 0, "duration": 1, "x": .5, "y": .5, "width": 1, "height": 1}]}]})
        image = self.frame(output, .5)
        red = [x for x in range(320) if image.getpixel((x, 90))[0] > 150]
        self.assertAlmostEqual((min(red) + max(red)) / 2, 160, delta=3)       # centred, as object-fit: contain
        self.assertAlmostEqual(max(red) - min(red) + 1, 101, delta=4)         # 180 * 90/160, not stretched

    def test_slide_left_puts_both_frames_where_the_preview_does(self):
        join = {"type": "slide_left", "duration": .5, "seam": 1}
        red = {"id": "red", "type": "animation", "content_type": "shape", "color": "#ff0000", "start": 0, "duration": 1.5, "x": .5, "y": .5,
               "width": .5, "height": .5, "join_out": join}
        blue = {"id": "blue", "type": "animation", "content_type": "shape", "color": "#0000ff", "start": 1, "duration": 1, "x": .5, "y": .5,
                "width": .5, "height": .5, "join_in": join}
        output = self.render({"width": 320, "height": 180, "fps": 20, "background": "#000000",
                              "timeline_layers": [{"id": "a", "clips": [red]}, {"id": "b", "clips": [blue]}]})
        moment = 1.25   # halfway: the outgoing frame's right half and the incoming frame's left half are both on screen
        image = self.frame(output, moment)
        out = self.preview_values({**red, "duration": 1}, [moment], {"outgoing": join})[0]
        into = self.preview_values(blue, [moment], {"incoming": join})[0]
        reds = [x for x in range(320) if image.getpixel((x, 90))[0] > 150 and image.getpixel((x, 90))[2] < 100]
        blues = [x for x in range(320) if image.getpixel((x, 90))[2] > 150 and image.getpixel((x, 90))[0] < 100]
        self.assertAlmostEqual(max(reds) + 1, out["x"] * 320 + 80, delta=3)
        self.assertAlmostEqual(min(blues), into["x"] * 320 - 80, delta=3)

    def test_zoom_in_scales_and_fades_the_incoming_frame_as_the_preview(self):
        join = {"type": "zoom_in", "duration": .5, "seam": 0}
        blue = {"id": "blue", "type": "animation", "content_type": "shape", "color": "#0000ff", "start": 0, "duration": 1.5, "x": .3, "y": .5,
                "width": .5, "height": .5, "join_in": join}
        output = self.render({"width": 320, "height": 180, "fps": 20, "background": "#000000", "timeline_layers": [{"id": "b", "clips": [blue]}]})
        moment = .25
        values = self.preview_values(blue, [moment], {"incoming": join})[0]
        image = self.frame(output, moment)
        lit = [x for x in range(320) if image.getpixel((x, 90))[2] > 40]
        self.assertAlmostEqual((min(lit) + max(lit) + 1) / 2, values["x"] * 320, delta=3)
        self.assertAlmostEqual(max(lit) - min(lit) + 1, 160 * values["scale"], delta=4)
        self.assertAlmostEqual(image.getpixel((round(values["x"] * 320), 90))[2] / 255, values["opacity"], delta=.08)

    def test_a_label_on_a_moving_photo_enters_like_the_preview(self):
        # the word rises 40 px into place while the label pans; the old export only faded it in where it stood
        effect = {"type": "up", "duration": .4, "distance": 40}
        label = {"id": "label", "type": "text", "text": "НН", "start": 0, "duration": 2, "x": .3, "y": .5, "width": .4, "height": .4,
                 "font_size": 40, "color": "#ffffff", "keyframes": [{"time": 0, "x": .3}, {"time": 2, "x": .7}], "word_entrance": effect,
                 "text_words": [{"text": "НН", "start": .5, "x": .5, "y": .5, "width": .5, "height": .5}]}
        output = self.render({"width": 320, "height": 180, "fps": 20, "background": "#000000", "timeline_layers": [{"id": "t", "clips": [label]}]})
        def bright(second):
            image = self.frame(output, second)
            points = [(x, y) for x in range(320) for y in range(180) if max(image.getpixel((x, y))) > 60]
            return sum(y for _, y in points) / len(points), max(max(image.getpixel(p)) for p in points), sum(x for x, _ in points) / len(points)
        resting_y, full, _ = bright(1.5)
        entering_y, peak, entering_x = bright(.6)
        _, dy, _, opacity, _ = render.entrance_state(effect, .25)
        self.assertAlmostEqual(entering_y - resting_y, dy, delta=3)
        self.assertAlmostEqual(peak / full, opacity, delta=.12)
        self.assertAlmostEqual(entering_x, (.3 + .4 * .6 / 2) * 320, delta=4)


if __name__ == "__main__":
    unittest.main()
