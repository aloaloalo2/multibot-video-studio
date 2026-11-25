import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import montage_ops  # noqa: E402
import motion_code  # noqa: E402
import store  # noqa: E402
import timeline_manifest  # noqa: E402
import unittest  # noqa: E402
import test_agent_tools  # noqa: E402

CODE = """
function draw(ctx, t, info) {
  const a = info.ease.out(info.span(t, 0, 1));
  ctx.strokeStyle = '#2ee6c8'; ctx.lineWidth = 8;
  ctx.beginPath(); ctx.moveTo(info.w * .2, info.h * .8); ctx.lineTo(info.w * (.2 + .5 * a), info.h * .8); ctx.stroke();
  ctx.fillStyle = '#ffd166'; ctx.font = '700 80px Manrope'; ctx.fillText(info.words.length + ' слів', info.w * .2, info.h * .3);
  if (info.images.dot) ctx.drawImage(info.images.dot, info.w * .7, info.h * .2, 120, 120);
}
"""


class MotionCodeTest(unittest.TestCase):
    """Motion design written as code (motion_code.py): the op lays it in the frame, the export draws it as a video with
    alpha from the same runtime as the preview. The studio server and the photo montage come from the agent tools test."""
    setUpClass = classmethod(test_agent_tools.AgentToolsTest.setUpClass.__func__)
    tearDownClass = classmethod(test_agent_tools.AgentToolsTest.tearDownClass.__func__)
    project = test_agent_tools.AgentToolsTest.project

    def test_motion_code_goes_over_the_frame_and_renders_with_alpha(self):
        project = self.project(frames=2)
        episode = Path(project["episode_path"])
        from PIL import Image
        Image.new("RGBA", (64, 64), (255, 80, 80, 255)).save(episode / "dot.png")
        words = [{"text": "раз", "start": 4.2, "end": 4.5}, {"text": "два", "start": 5.0, "end": 5.3}, {"text": "поза", "start": 9.0, "end": 9.3}]
        with patch.object(montage_ops.Context, "words", return_value=words), patch.object(motion_code, "STUDIO_URL", self.base_url):
            report = montage_ops.run(project["id"], [{"op": "motion_code", "frame": 2, "code": CODE, "start": .5, "duration": 2,
                                                      "title": "лінія", "assets": {"dot": str(episode / "dot.png")}}])
            self.assertIn("моушн-код «лінія»", " ".join(report["report"]))
            current = store.load_project(project["id"])
            clip = next(c for t in current["tracks"] for c in t["clips"] if c.get("content_type") == "code")
            self.assertEqual((clip["start"], clip["duration"], clip["title"]), (4.5, 2.0, "K002 моушн лінія"))
            self.assertEqual([w["text"] for w in clip["code_words"]], ["два"])          # only the words of its own time
            self.assertEqual(set(clip["code_assets"]), {"dot"})
            group = next(g for g in current["scene_groups"] if g.get("title") == "Кадр 2")
            self.assertIn(clip["id"], group["clip_ids"])                                    # it lies in the frame's group
            manifest = timeline_manifest.build(current, visual_only=True)
            rendered = next(c for layer in manifest["timeline_layers"] for c in layer["clips"] if c["id"] == clip["id"])
            self.assertEqual((rendered["type"], rendered["content_type"]), ("video", None))
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=pix_fmt,nb_frames", "-of", "json", rendered["source"]],
                                   capture_output=True, text=True).stdout
            stream = json.loads(probe)["streams"][0]
            self.assertTrue(stream["pix_fmt"].startswith("yuva"))                          # transparent where nothing is drawn
            self.assertEqual(int(stream["nb_frames"]), 2 * int(current.get("fps") or 25))
            again = timeline_manifest.build(store.load_project(project["id"]), visual_only=True)   # the same code: the same file
            self.assertEqual(rendered["source"], next(c["source"] for layer in again["timeline_layers"] for c in layer["clips"] if c["id"] == clip["id"]))
            check = motion_code.stills(current, clip, [.2, 1.0], store.cache_dir(current) / "motion-code" / "check-test")
            self.assertTrue(check["ok"], check)
            broken = motion_code.stills(current, {**clip, "code": "function draw(ctx, t) { nothing.here(); }"}, [.2],
                                        store.cache_dir(current) / "motion-code" / "check-broken")
            self.assertFalse(broken["ok"])
            self.assertIn("nothing", broken["error"])

    def test_code_is_refused_without_a_draw_function_or_outside_the_frame(self):
        project = self.project(frames=1)
        with self.assertRaises(store.StudioError):
            montage_ops.run(project["id"], [{"op": "motion_code", "frame": 1, "code": "console.log(1)"}])
        with patch.object(montage_ops.Context, "words", return_value=[]), self.assertRaises(montage_ops.OpError):
            montage_ops.run(project["id"], [{"op": "motion_code", "frame": 1, "code": CODE, "start": 3, "duration": 2}])


if __name__ == "__main__":
    unittest.main()
