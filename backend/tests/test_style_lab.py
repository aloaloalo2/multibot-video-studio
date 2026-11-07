import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import channel_branding  # noqa: E402
import store  # noqa: E402
import style_lab  # noqa: E402

STYLES_JS = """export const STYLES = {
  dusk: {
    name: 'Cinematic Dusk', desc: 'Warm.',
    ink: '#000',
  },
  neon: {
    name: 'Neon Noir', desc: 'Deep blacks.',
    ink: '#000',
  },
};
"""


def film(base: Path, slug="film") -> Path:
    project = base / "razgon" / "projects" / slug
    for name in ("story", "timeline", "scenes", "input", "assets"):
        (project / name).mkdir(parents=True)
    (project / "story" / "shots.json").write_text(json.dumps({"duration": 100, "shots": [
        {"start": 0, "end": 20, "set": "lab", "scene": "a blueprint diagram of the heart"},
        {"start": 20, "end": 40, "set": "home", "scene": "close on YOU yawning in bed"},
        {"start": 40, "end": 60, "set": "home", "scene": "YOU walks to the kitchen"},
        {"start": 60, "end": 100, "set": "street", "scene": "YOU crosses the street at dusk"}]}))
    (project / "config.json").write_text(json.dumps({"style": "neon", "overlay": "input/plashka.png", "fps": 25}))
    (project / "assets" / "index.json").write_text('["rocket"]')
    return project


class StyleLabTest(unittest.TestCase):
    def test_settings_validation_and_text_style(self):
        style_lab.validate({"style": "neon", "assets": False, "title_font": "Nunito", "accent": "#ff4fa3"})
        for bad in ({"style": "Neon Noir!"}, {"assets": "yes"}, {"title_font": "Comic Sans"}, {"accent": "pink"}):
            with self.assertRaises(style_lab.StyleLabError):
                style_lab.validate(bad)
        with self.assertRaises(channel_branding.BrandingError):
            channel_branding.validate({"animation": {"accent": "pink"}})
        self.assertEqual(style_lab.razgon_text({"title_font": "Nunito", "accent": "#112233"}), {"fonts": {"title": "Nunito", "ui": "Nunito", "serif": "Nunito"}, "ui": {"accent": "#112233"}})
        self.assertEqual(style_lab.razgon_text(None), {})

    def test_presets_times_and_lab_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "razgon" / "engine").mkdir(parents=True)
            (base / "razgon" / "engine" / "styles.js").write_text(STYLES_JS)
            (base / "razgon" / "render.mjs").write_text("")
            project = film(base)
            self.assertEqual([s["id"] for s in style_lab.presets(base / "razgon")], ["dusk", "neon"])
            # The close-up first, then one shot per other set; the third moment falls back to the nearest shot not yet
            # used, never the diagram.
            self.assertEqual(style_lab.sample_times(project), [29.0, 78.0, 49.0])
            channel = base / "channel"; (channel / "01 Episode").mkdir(parents=True)
            (channel / "01 Episode" / "razgon.json").write_text(json.dumps({"razgon_root": str(base / "razgon"), "project": str(project)}))
            self.assertEqual(style_lab.films(channel), [(base / "razgon", project)])
            with patch.object(store, "DATA_ROOT", base / "data"):
                plain = style_lab.lab("c" * 16, base / "razgon", project, False, {"fonts": {"title": "Nunito"}})
                self.assertEqual(json.loads((plain / "assets" / "index.json").read_text()), [])
                config = json.loads((plain / "config.json").read_text())
                self.assertIsNone(config["overlay"])
                self.assertEqual(config["fonts"], {"title": "Nunito"})
                self.assertEqual((plain / "scenes").resolve(), (project / "scenes").resolve())
                full = style_lab.lab("c" * 16, base / "razgon", project, True, {})
                self.assertEqual((full / "assets").resolve(), (project / "assets").resolve())
            # The film itself is untouched.
            self.assertEqual(json.loads((project / "config.json").read_text())["overlay"], "input/plashka.png")

    def test_regular_card_assets_toggle_changes_the_rendered_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);scene=film(base,"style-card-info");(scene/"scenes/shots").mkdir()
            root=base/"razgon";(root/"library/props").mkdir(parents=True)
            for name in ("carrots","brain","eye_model"):(root/"library/props"/f"{name}.png").write_bytes(b"fixture")
            seen=[]
            def render(root,folder,ids,times):
                seen.append(json.loads((folder/"assets/index.json").read_text()))
                self.assertEqual(json.loads((folder/"config.json").read_text())["bars"], "none")
                self.assertTrue(all(shot["bars"] == "none" for shot in json.loads((folder/"story/shots.json").read_text())["shots"]))
                self.assertFalse((folder/"story").is_symlink())
                self.assertIn("picture(g, 'brain'",(folder/"scenes/shots/01_info.js").read_text())
                out=folder/"build/styles";out.mkdir();(out/"neon_2.0s_2.00.jpeg").write_bytes(b"rendered")
                return out
            with patch.object(store,"DATA_ROOT",base/"data"),patch.object(style_lab,"card_scene",return_value=(scene,2.0)),patch.object(style_lab,"render_stills",side_effect=render):
                plain=style_lab.card_set(root,["neon"],1,"Nunito",False,kind="regular")
                props=style_lab.card_set(root,["neon"],1,"Nunito",True,kind="regular")
                self.assertNotEqual(plain,props)
            self.assertEqual(seen,[[],["carrots","brain","eye_model"]])

    def test_preview_file_rejects_paths_outside_the_cache(self):
        for key, name in (("../" * 3, "dusk-0.jpg"), ("a" * 20, "../../logo.png")):
            with self.assertRaises(style_lab.StyleLabError):
                style_lab.preview_file("c" * 16, key, name)


if __name__ == "__main__":
    unittest.main()
