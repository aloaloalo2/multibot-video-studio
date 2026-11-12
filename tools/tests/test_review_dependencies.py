import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

KIT = Path(__file__).resolve().parents[2] / "razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit"
sys.path.insert(0, str(KIT / "tools"))
import frame_review as review
import review_dependencies as deps
from review_dependencies import fingerprints


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proj = self.root / "projects/test"
        for folder in ("scenes", "story", "input", "assets"):
            (self.proj / folder).mkdir(parents=True)
        (self.root / "engine").mkdir()
        (self.root / "engine/core.js").write_text("export const x = 1;")
        (self.proj / "config.json").write_text('{"fps":25}')
        (self.proj / "story/shots.json").write_text(json.dumps({"shots": [
            {"id": f"s{n}", "start": (n - 1) * 10, "end": n * 10} for n in range(1, 6)]}))
        for n in range(1, 6):
            (self.proj / f"scenes/s{n}.js").write_text(f"take('s{n}', {{}});")

    def hashes(self):
        return fingerprints(self.proj, self.root, review.frames_of(self.proj))

    def test_scene_change_invalidates_only_own_and_adjacent_frames(self):
        before = self.hashes()
        (self.proj / "scenes/s3.js").write_text("take('s3', {fixed:true});")
        after = self.hashes()
        self.assertEqual([n for n in before if before[n] != after[n]], [2, 3, 4])

    def test_shared_helpers_and_engine_invalidate_all(self):
        for path in (self.proj / "scenes/helper.js", self.root / "engine/core.js"):
            before = self.hashes(); path.write_text("changed"); after = self.hashes()
            self.assertTrue(all(before[n] != after[n] for n in before))

    def test_unused_asset_and_generation_files_do_not_invalidate_ready_frames(self):
        before=self.hashes()
        (self.proj/'assets/unused.png').write_bytes(b'unused image')
        (self.proj/'assets/index.json').write_text('["unused"]')
        (self.proj/'assets/src').mkdir()
        (self.proj/'assets/src/prompt.txt').write_text('New generation instructions')
        self.assertEqual(before,self.hashes())

    def test_only_consumers_and_adjacent_cuts_depend_on_a_referenced_asset(self):
        (self.proj/'assets/tree.png').write_bytes(b'old tree')
        (self.proj/'scenes/s3.js').write_text("take('s3', {draw(g){pic(g,'tree',0,0,100)}});")
        before=self.hashes()
        (self.proj/'assets/tree.png').write_bytes(b'changed tree')
        after=self.hashes()
        self.assertEqual([n for n in before if before[n]!=after[n]],[2,3,4])

    def test_asset_registry_membership_and_missing_media_are_real_dependencies(self):
        (self.proj/'assets/index.json').write_text('[]')
        (self.proj/'scenes/s3.js').write_text("take('s3', {draw(g){pic(g,'tree',0,0,100)}});")
        before=self.hashes()
        (self.proj/'assets/tree.png').write_bytes(b'newly available tree')
        after=self.hashes()
        self.assertEqual([n for n in before if before[n]!=after[n]],[2,3,4])
        (self.proj/'assets/index.json').write_text('["tree"]')
        listed=self.hashes()
        self.assertEqual([n for n in after if after[n]!=listed[n]],[2,3,4])

    def test_array_take_registration_is_local_instead_of_a_global_helper(self):
        (self.proj/'scenes/joined.js').write_text("take(['s1','s2'], {draw(){}});")
        before=self.hashes()
        (self.proj/'scenes/joined.js').write_text("take(['s1','s2'], {draw(){const corrected=true;}});")
        after=self.hashes()
        self.assertEqual([n for n in before if before[n]!=after[n]],[1,2,3])

    def test_unused_pure_helper_does_not_invalidate_other_parts(self):
        before=self.hashes()
        helper=self.proj/'scenes/next-part.js'
        helper.write_text('export function nextScene(g) { pic(g, "future_prop"); }')
        (self.proj/'assets/future_prop.png').write_bytes(b'new future prop')
        self.assertEqual(before,self.hashes())
        (self.proj/'scenes/s5.js').write_text("import {nextScene} from './next-part.js'; take('s5', {draw:nextScene});")
        after=self.hashes()
        self.assertEqual([n for n in before if before[n]!=after[n]],[4,5])

    def test_imported_global_side_effects_still_invalidate_the_whole_film(self):
        before=self.hashes()
        (self.proj/'scenes/global.js').write_text('E.settings.palette = "changed";')
        self.assertTrue(all(before[n]!=self.hashes()[n] for n in before))

    def test_dynamic_prop_selection_and_missing_parser_keep_conservative_checks(self):
        (self.proj/'scenes/helper.js').write_text('export function draw(g) { pic(g, chooseAsset()); } E.draw = draw;')
        before=self.hashes()
        (self.proj/'assets/a.png').write_bytes(b'new potentially selected prop')
        after=self.hashes()
        self.assertTrue(all(before[n]!=after[n] for n in before))
        (self.proj/'scenes/helper.js').unlink()
        with patch.object(deps,'run_parser',side_effect=OSError('Parser unavailable')):
            before=self.hashes()
            (self.proj/'assets/a.png').write_bytes(b'changed potential prop')
            self.assertTrue(all(before[n]!=self.hashes()[n] for n in before))

    def test_aliases_wrappers_and_iteration_preserve_actual_asset_dependencies(self):
        source="""import {pic as image} from './helper.js';
          function grounded(g,name) { image(g,name); }
          take('s3', {draw(g) { for (const [name,x] of [['tree',Math.random()]]) grounded(g,name); }});
        """
        (self.proj/'scenes/s3.js').write_text(source)
        (self.proj/'assets/tree.png').write_bytes(b'tree')
        before=self.hashes()
        (self.proj/'assets/unused.png').write_bytes(b'unused')
        self.assertEqual(before,self.hashes())
        (self.proj/'assets/tree.png').write_bytes(b'changed tree')
        self.assertEqual([n for n,v in before.items() if v!=self.hashes()[n]],[2,3,4])

    def test_dynamic_template_covers_new_matching_assets_without_global_invalidation(self):
        (self.proj/'scenes/s3.js').write_text("take('s3', {draw(g){pic?.(g,`tree_${E.kind}`)}});")
        before=self.hashes()
        (self.proj/'assets/tree_new.png').write_bytes(b'new possible tree')
        self.assertEqual([n for n,v in before.items() if v!=self.hashes()[n]],[2,3,4])

    def test_imported_shot_module_is_also_a_dependency(self):
        (self.proj / "scenes/s1.js").write_text("import './s5.js'; take('s1', {});")
        before = self.hashes()
        (self.proj / "scenes/s5.js").write_text("take('s5', {fixed:true});")
        self.assertNotEqual(before[1], self.hashes()[1])

    def test_unknown_image_sources_and_registry_readers_remain_conservative(self):
        for source in (
            "const cache = new Map([['x', E.image]]); take('s3',{draw(g){g.drawImage(cache.get('x'),0,0)}});",
            "let cache = new Map(); cache = E.images; take('s3',{draw(g){g.drawImage(cache.get('x'),0,0)}});",
            "const {fetch: readAssets} = window; readAssets('/project/assets/index.json'); take('s3',{});",
            "function load(mode,url){return fetch(url)}; load('json','/project/assets/index.json'); take('s3',{});",
            "function draw(g){pic(g,E.prop)}; take('s3',{draw});",
        ):
            with self.subTest(source=source):
                (self.proj/'scenes/s3.js').write_text(source)
                (self.proj/'assets/a.png').write_bytes(b'before')
                before=self.hashes()
                (self.proj/'assets/a.png').write_bytes(b'after')
                self.assertEqual([n for n,v in before.items() if v!=self.hashes()[n]],[2,3,4])

    def test_closed_procedural_canvas_cache_keeps_unused_assets_out(self):
        (self.proj/'scenes/s3.js').write_text("""const cache=new Map();
          function make(){if(cache.has('map'))return cache.get('map');
            const c=document.createElement('canvas');cache.set('map',c);return c;}
          take('s3',{draw(g){g.drawImage(make(),0,0)}});""")
        before=self.hashes()
        (self.proj/'assets/unused.png').write_bytes(b'not used by procedural canvas')
        self.assertEqual(before,self.hashes())

    def test_malformed_parser_output_falls_back_to_all_media(self):
        answer=SimpleNamespace(returncode=0,stdout=json.dumps({str(p):{} for p in (self.proj/'scenes').glob('*.js')}))
        with patch.object(deps,'run_parser',return_value=answer):
            before=self.hashes()
            (self.proj/'assets/unknown.png').write_bytes(b'possibly used')
            self.assertTrue(all(before[n]!=self.hashes()[n] for n in before))

    def test_colour_changes_do_not_reuse_an_old_visual_verdict(self):
        first=self.root/'first.png';second=self.root/'second.png'
        Image.new('RGB',(64,36),(255,0,0)).save(first)
        Image.new('RGB',(64,36),(0,130,0)).save(second)
        self.assertFalse(review.same_picture(review.thumb(first),review.thumb(second)))

    def render(self, args, **kwargs):
        self.calls += 1
        out = Path(args[args.index("--dir") + 1]); out.mkdir(exist_ok=True)
        for value in args[args.index("--stills") + 1].split(","):
            Image.new("RGB", (64, 36), (20, 40, 60)).save(out / f"{value}s_{float(value):.2f}.png")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def test_unchanged_sheets_use_no_renderer_and_scoped_review_keeps_status_honest(self):
        self.calls = 0
        args = SimpleNamespace(frames="", scale=.34, all=False)
        with patch.object(review.subprocess, "run", side_effect=self.render), contextlib.redirect_stdout(io.StringIO()):
            review.sheets(self.proj, self.root, args)
            review.mark(self.proj, SimpleNamespace(frames="1-5", verdict="ok", note=""))
            self.assertEqual(review.status(self.proj), 0)
            review.sheets(self.proj, self.root, args)
            self.assertEqual(self.calls, 1)
            (self.proj / "scenes/s3.js").write_text("take('s3', {fixed:true});")
            review.sheets(self.proj, self.root, SimpleNamespace(frames="3", scale=.34, all=False))
            self.assertEqual(review.status(self.proj), 1)  # adjacent frames still need review
            review.sheets(self.proj, self.root, args)
            self.assertEqual(review.status(self.proj), 0)  # identical pixels retain the visual verdict

    def test_scoped_status_rejects_missing_stills_and_unknown_ids(self):
        self.calls=0
        with patch.object(review.subprocess,'run',side_effect=self.render), contextlib.redirect_stdout(io.StringIO()):
            review.sheets(self.proj,self.root,SimpleNamespace(frames='1',scale=.34,all=False))
            review.mark(self.proj,SimpleNamespace(frames='1',verdict='ok',note=''))
            self.assertEqual(review.status(self.proj,'1'),0)
            self.assertEqual(review.status(self.proj,'1,999'),1)
            self.assertEqual(review.status(self.proj,'0'),1)
            self.assertEqual(review.status(self.proj),1)
            next((self.proj/'build/review/frames').glob('*.png')).unlink()
            self.assertEqual(review.status(self.proj,'1'),1)

    def test_deleted_still_forces_render(self):
        self.calls = 0
        args = SimpleNamespace(frames="1", scale=.34, all=False)
        with patch.object(review.subprocess, "run", side_effect=self.render), contextlib.redirect_stdout(io.StringIO()):
            review.sheets(self.proj, self.root, args)
            next((self.proj / "build/review/frames").glob("*.png")).unlink()
            review.sheets(self.proj, self.root, args)
            self.assertEqual(self.calls, 2)

    def test_cached_unreviewed_batch_has_its_own_sheet_without_rerendering(self):
        self.calls=0
        with patch.object(review.subprocess,'run',side_effect=self.render), contextlib.redirect_stdout(io.StringIO()):
            review.sheets(self.proj,self.root,SimpleNamespace(frames='1',scale=.3,all=False))
            first=self.proj/'build/review/review_frames_001.png'
            original=first.read_bytes()
            review.sheets(self.proj,self.root,SimpleNamespace(frames='2',scale=.3,all=False))
            self.assertEqual(first.read_bytes(),original)
            review.sheets(self.proj,self.root,SimpleNamespace(frames='1',scale=.3,all=False))
            self.assertEqual(self.calls,2)
            self.assertTrue((self.proj/'build/review/review_frames_002.png').is_file())

    def test_stale_verdict_cannot_be_marked_without_fresh_stills(self):
        self.calls=0
        with patch.object(review.subprocess,'run',side_effect=self.render), contextlib.redirect_stdout(io.StringIO()):
            review.sheets(self.proj,self.root,SimpleNamespace(frames='1-5',scale=.3,all=False))
            review.mark(self.proj,SimpleNamespace(frames='1-5',verdict='ok',note=''))
            (self.proj/'scenes/s3.js').write_text("take('s3',{changed:true})")
            with self.assertRaisesRegex(SystemExit,'changed'):
                review.mark(self.proj,SimpleNamespace(frames='3',verdict='ok',note=''))
            self.assertNotEqual(review.status(self.proj,'3'),0)


if __name__ == "__main__":
    unittest.main()
