import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402
import thumbnail_gen  # noqa: E402


class ThumbnailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.episode = base / "What If" / "05 Test"
        self.episode.mkdir(parents=True)
        (base / "What If" / "Еталон стилю").mkdir()
        Image.new("RGB", (32, 18)).save(base / "What If" / "Еталон стилю" / "Референс кадру 1.png")
        (base / "What If" / "Еталон стилю" / "Еталон промпт прев'ю.txt").write_text('YouTube thumbnail for "DAY 365".', encoding="utf-8")
        self.project = {"id": "f" * 24, "name": "05 Test", "episode_path": str(self.episode)}
        self.studio = base / "studio"                     # the studio's own project folder
        self.studio.mkdir()
        for item in (patch.object(store, "load_project", return_value=self.project),
                     patch.object(store, "load_project_plan", return_value={"spoken_script": "Your eyes dry out."}),
                     patch.object(thumbnail_gen, "job_path", return_value=base / "job.json"),
                     patch.object(store, "project_dir", return_value=self.studio),
                     patch.object(thumbnail_gen.director, "executable", return_value=Path("claude"))):
            item.start()
            self.addCleanup(item.stop)
        thumbnail_gen.ACTIVE.clear()

    def test_defaults_take_the_first_ab_title_and_the_spoken_script(self):
        self.assertEqual(thumbnail_gen.defaults(self.project["id"])["title"], "05 Test")
        (self.episode / "Метаданные.txt").write_text("ТАЙТЛИ (3 варіанти)\n\nWhat If You Never Blinked?\nЩо, якщо...\n", encoding="utf-8")
        data = thumbnail_gen.defaults(self.project["id"])
        self.assertEqual((data["title"], data["script"], data["preview"]), ("What If You Never Blinked?", "Your eyes dry out.", False))

    def test_claude_gets_the_title_wishes_script_and_the_channels_approved_prompts(self):
        refs = thumbnail_gen.references(self.episode)
        text = thumbnail_gen.brief("What If?", "The script.", "big word DRY", self.episode, refs)
        for part in ('"What If?"', "big word DRY", "The script.", "правий верхній кут порожній", 'thumbnail for "DAY 365"', "Референс кадру 1.png", "тільки самим промптом"):
            self.assertIn(part, text)
        self.assertNotIn("Побажання автора", thumbnail_gen.brief("T", "S", "  ", self.episode, refs))
        drawing = thumbnail_gen.drawing("A neon close-up.", "Превью v2.png")
        self.assertTrue(drawing.startswith("A neon close-up."))
        self.assertIn('"Превью v2.png"', drawing)

    def test_trending_codex_gets_english_rules_and_original_language_content(self):
        text = thumbnail_gen.trending("Що буде завтра?", "Українська озвучка.", "Більше емоції", "Превью v2.png")
        for part in ("40-70%", "Signal colours", "Peak action", "Concrete stakes", "Atmospheric integration",
                     "Title and image synergy", "same language", "Що буде завтра?", "Українська озвучка.",
                     "Більше емоції", '"Превью v2.png"', "Choose one clear"):
            self.assertIn(part, text)

    def test_trending_goes_directly_to_codex_and_is_saved_as_a_new_version(self):
        with self.tools(), patch.object(thumbnail_gen, "write_prompt") as claude, \
             patch.object(thumbnail_gen, "write_prompt_deepseek") as deepseek:
            thumbnail_gen.run(self.project["id"], "Що буде завтра?", "Текст ролика.", "Велике обличчя", writer="trending")
        claude.assert_not_called(); deepseek.assert_not_called()
        self.assertEqual(len(self.calls), 1)
        command, sent = self.calls[0]
        self.assertIn("exec", command)
        self.assertIn("40-70%", sent["input"])
        self.assertIn("Що буде завтра?", sent["input"])
        self.assertEqual(thumbnail_gen.state(self.project["id"])["prompt_cost_usd"], 0)
        self.assertEqual(thumbnail_gen.versions(self.project["id"])[0]["writer"], "trending")

    def test_trending_start_skips_prompt_stage_and_disallows_edit_base(self):
        self.made_frames(2)
        with patch.object(thumbnail_gen, "CODEX", Path(sys.executable)), patch.object(thumbnail_gen.threading, "Thread") as thread:
            job = thumbnail_gen.start(self.project["id"], "T", "S", writer="trending")
        self.assertEqual((job["writer"], job["stage"]), ("trending", "drawing"))
        self.assertEqual(thread.call_args.kwargs["args"][4], "trending")
        with self.assertRaisesRegex(store.StudioError, "без бази"):
            thumbnail_gen.start(self.project["id"], "T", "S", writer="trending", base="Превью v1.png")

    def test_host_reference_and_opt_out_reach_each_thumbnail_writer_and_codex(self):
        import channel_hero
        hero=Path(self.tmp.name)/'host.png';Image.new('RGB',(16,16),'green').save(hero)
        for writer in ('claude','deepseek','trending'):
            for enabled in (True,False):
                for image in (self.studio/'preview').glob('*.png'):
                    image.unlink()
                with self.subTest(writer=writer,enabled=enabled), self.tools(), \
                     patch.object(thumbnail_gen.director,'channel_settings',return_value={'thumbnail_wishes':'CHANNEL THUMBNAIL STYLE'}), \
                     patch.object(channel_hero,'prepare',return_value=(hero if enabled else None,'\nHOST INCLUDED\n' if enabled else '\nHOST EXCLUDED\n')) as prepared, \
                     patch.object(thumbnail_gen,'write_prompt',return_value=('A carefully designed thumbnail. '*10,{})) as claude, \
                     patch.object(thumbnail_gen,'write_prompt_deepseek',return_value=('A carefully designed thumbnail. '*10,{})) as deepseek:
                    thumbnail_gen.run(self.project['id'],'T','S','',writer=writer,use_hero=enabled)
                    self.assertEqual(thumbnail_gen.state(self.project['id'])['status'],'done')
                    self.assertEqual(prepared.call_args.args[-1],enabled)
                    command,sent=self.calls[-1]
                    self.assertEqual(str(hero) in command,enabled)
                    self.assertIn('HOST INCLUDED' if enabled else 'HOST EXCLUDED',sent['input'])
                    self.assertIn('CHANNEL THUMBNAIL STYLE',sent['input'])
                    prompt_writer=claude if writer=='claude' else deepseek if writer=='deepseek' else None
                    if prompt_writer:
                        self.assertIn('HOST INCLUDED' if enabled else 'HOST EXCLUDED',prompt_writer.call_args.args[0])
                        self.assertIn('CHANNEL THUMBNAIL STYLE',prompt_writer.call_args.args[0])
                    else:
                        self.assertIn('CHANNEL THUMBNAIL STYLE',sent['input'])

    def test_deepseek_receives_labeled_host_image_before_scene_references(self):
        import io
        import credentials
        hero=Path(self.tmp.name)/'Головний герой.png'
        Image.new('RGB',(16,16),'green').save(hero)
        refs=[hero]
        for number in range(5):
            ref=Path(self.tmp.name)/f'scene-{number}.png'
            Image.new('RGB',(16,9),'blue').save(ref);refs.append(ref)
        response={'choices':[{'message':{'content':'A deliberate thumbnail composition. '*12}}],'usage':{'cost':0}}
        with patch.object(credentials,'vault') as vault, patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as opened:
            vault.return_value.read.return_value='test-only'
            thumbnail_gen.write_prompt_deepseek('MAIN CHARACTER REFERENCE: Головний герой.png',self.episode,refs)
        payload=json.loads(opened.call_args.args[0].data)
        content=payload['messages'][0]['content']
        self.assertIn('Головний герой.png',content[1]['text'])
        self.assertIn('Main character identity',content[1]['text'])
        self.assertEqual(content[2]['type'],'image_url')
        self.assertIn('scene-0.png',content[3]['text'])
        self.assertEqual(sum(item['type']=='image_url' for item in content),4)
        opened.assert_called_once()

    def test_edit_uses_only_selected_image_and_preserves_old_versions(self):
        work=thumbnail_gen.keep_dir(self.project['id']);work.mkdir()
        selected=work/'Превью v1.png';Image.new('RGB',(16,9),'red').save(selected)
        Image.new('RGB',(16,9),'green').save(work/'Превью v2.png')
        original=selected.read_bytes();calls=[]
        def draw(command,**kwargs):
            calls.append((command,kwargs['input']))
            Image.new('RGB',(16,9),'blue').save(work/'Превью v3.png')
            return subprocess.CompletedProcess(command,0,'','')
        with patch.object(subprocess,'run',side_effect=draw),patch.object(thumbnail_gen,'write_prompt') as writer, \
             patch.object(thumbnail_gen.director,'channel_settings',return_value={'thumbnail_wishes':'DO NOT ADD THIS TO EDITS'}):
            thumbnail_gen.run(self.project['id'],'T','S','Make the phone larger',base=selected.name)
        writer.assert_not_called()
        self.assertEqual(len(calls),1)
        command,prompt=calls[0]
        self.assertEqual(command.count('-i'),1)
        self.assertEqual(command[command.index('-i')+1],str(selected))
        self.assertIn('Make the phone larger',prompt)
        self.assertNotIn('DO NOT ADD THIS',prompt)
        self.assertEqual(selected.read_bytes(),original)
        self.assertEqual([item['number'] for item in thumbnail_gen.versions(self.project['id'])],[3,2,1])
        self.assertEqual(thumbnail_gen.state(self.project['id'])['status'],'done')

    def test_edit_current_cover_is_archived_without_requiring_video_frames(self):
        Image.new('RGB',(16,9),'red').save(self.episode/'Превью.png')
        with patch.object(thumbnail_gen,'CODEX',Path(sys.executable)),patch.object(thumbnail_gen.threading,'Thread') as thread:
            job=thumbnail_gen.start(self.project['id'],'T','S','Bigger title',base='current')
        self.assertEqual(job['base'],'Превью до v1.png')
        self.assertTrue(thumbnail_gen.version_file(self.project['id'],job['base']).is_file())
        self.assertEqual(thread.call_args.kwargs['args'][5],job['base'])
        thumbnail_gen.ACTIVE.clear()
        for base in ('../Превью.png',123,''):
            with self.subTest(base=base),self.assertRaises(store.StudioError):
                thumbnail_gen.start(self.project['id'],'T','S','Change',base=base)

    def tools(self, picture=True, answer=None):
        """Claude Code answers with a prompt, Codex saves the picture; each call is recorded."""
        self.calls = []
        def run(command, **kwargs):
            self.calls.append((command, kwargs))
            if command[0] == "claude":
                reply = answer or {"result": "A neon close-up of the frozen hero. " * 8, "total_cost_usd": 0.2}
                return subprocess.CompletedProcess(command, 0, json.dumps(reply), "")
            self.assertIn("-i", command)                      # the channel's style frame is attached
            if picture:
                Image.new("RGB", (16, 9), (0, 0, 255)).save(Path(kwargs["cwd"]) / "Превью v1.png")
            return subprocess.CompletedProcess(command, 0 if picture else 1, "ok", "" if picture else "quota")
        return patch.object(subprocess, "run", side_effect=run)

    def test_clone_uses_reference_before_frames_and_conditional_host_without_extra_prompt_author(self):
        Image.new('RGB', (32, 18)).save(self.studio / 'idea-reference.jpg')
        store.atomic_json(self.studio / 'idea-reference.json', {'title': 'Source'})
        work = thumbnail_gen.keep_dir(self.project['id']);work.mkdir()
        hero = work / 'Головний герой.png';Image.new('RGB', (16, 16)).save(hero)
        with self.tools(), patch.object(thumbnail_gen.channel_hero, 'prepare', return_value=(hero, 'Include this recognizable person prominently')), \
             patch.object(thumbnail_gen, 'frame_stills') as frames, patch.object(thumbnail_gen, 'write_prompt') as writer:
            thumbnail_gen.run(self.project['id'], 'Our title', 'Our script', '', writer='trending')
        self.assertEqual(thumbnail_gen.state(self.project['id'])['status'], 'done')
        self.assertEqual(len(self.calls), 1);frames.assert_not_called();writer.assert_not_called()
        command, sent = self.calls[0]
        self.assertIn(str(work / 'idea-reference.jpg'), command)
        self.assertIn(str(hero), command)
        self.assertIn('neutral story subject', sent['input'])
        self.assertIn('ear-and-nose coordination exercise', sent['input'])
        self.assertIn('Replace this demonstrator with our attached channel hero', sent['input'])
        self.assertIn('people-free', sent['input'])
        self.assertNotIn('Include this recognizable person prominently', sent['input'])
        thumbnail_gen.ACTIVE.clear()
        with patch.object(thumbnail_gen, 'CODEX', Path(sys.executable)), patch.object(thumbnail_gen.threading, 'Thread'):
            self.assertEqual(thumbnail_gen.start(self.project['id'], 'Our title', 'Our script')['status'], 'running')

    def test_a_run_keeps_the_old_thumbnail_and_puts_the_new_one_in_place(self):
        Image.new("RGB", (16, 9), (255, 0, 0)).save(self.episode / "Превью.png")
        thumbnail_gen.ACTIVE.add(self.project["id"])
        with self.tools():
            thumbnail_gen.run(self.project["id"], "T", "S", "")
        (claude, _), (codex, sent) = self.calls
        self.assertIn("--allowedTools", claude)
        self.assertIn(str(self.studio / "preview"), claude)                             # Claude may read the stills there
        self.assertTrue(sent["input"].startswith("A neon close-up of the frozen hero."))   # Codex draws Claude's prompt
        self.assertEqual(thumbnail_gen.state(self.project["id"])["status"], "done")
        kept = self.studio / "preview"                                                  # the studio's own copy
        self.assertEqual(Image.open(kept / "Превью.png").getpixel((0, 0)), (0, 0, 255))
        self.assertEqual(Image.open(kept / "Превью до v1.png").getpixel((0, 0)), (255, 0, 0))
        self.assertTrue((kept / "Лог генерації v1.txt").is_file())
        # the episode folder gets its copy and the prompt, as the channel rules ask
        self.assertEqual(Image.open(self.episode / "Превью.png").getpixel((0, 0)), (0, 0, 255))
        self.assertTrue((self.episode / "Превью" / "Промпт прев'ю v1.txt").read_text(encoding="utf-8").startswith("A neon close-up"))

    def test_the_thumbnail_outlives_the_episode_folder(self):
        Image.new("RGB", (16, 9), (0, 200, 0)).save(self.episode / "Превью.jpg")
        kept = thumbnail_gen.preview(self.project)                                     # copied in on first sight
        self.assertEqual(kept, self.studio / "preview" / "Превью.png")
        shutil.rmtree(self.episode)
        self.assertEqual(thumbnail_gen.preview(self.project), kept)
        self.assertEqual(Image.open(kept).getpixel((0, 0))[1], 200)
        self.assertEqual(thumbnail_gen.defaults(self.project["id"])["title"], "05 Test")
        self.made_frames(2)
        thumbnail_gen.ACTIVE.clear()
        with self.tools():
            thumbnail_gen.run(self.project["id"], "T", "S", "")                           # a new one is made without it
        self.assertEqual(thumbnail_gen.state(self.project["id"])["status"], "done")
        self.assertFalse(self.episode.exists())

    def test_a_run_without_a_picture_fails_and_changes_nothing(self):
        thumbnail_gen.ACTIVE.add(self.project["id"])
        with self.tools(picture=False):
            thumbnail_gen.run(self.project["id"], "T", "S", "")
        result = thumbnail_gen.state(self.project["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("quota", result["error"])
        self.assertFalse((self.episode / "Превью.png").exists())
        self.assertFalse((self.studio / "preview" / "Превью.png").exists())

    def test_the_claude_limit_stops_the_run_before_codex(self):
        thumbnail_gen.ACTIVE.add(self.project["id"])
        limit = {"is_error": True, "api_error": "usage_limit_reached", "result": "You've hit your session limit · resets 3pm"}
        with self.tools(answer=limit):
            thumbnail_gen.run(self.project["id"], "T", "S", "")
        self.assertEqual(len(self.calls), 1)
        self.assertIn("оновиться о 15:00", thumbnail_gen.state(self.project["id"])["error"])

    def made_frames(self, count):
        media = Path(self.tmp.name) / "media"
        media.mkdir(exist_ok=True)
        self.project["assets"], clips = [], []
        for number in range(1, count + 1):
            Image.new("RGB", (16, 9), (number * 20, 0, 0)).save(media / f"frame_{number:03d}.png")
            self.project["assets"].append({"id": f"a{number}", "path": str(media / f"frame_{number:03d}.png")})
            clips.append({"kind": "image", "asset_id": f"a{number}", "start": number * 10, "duration": 10, "title": f"Razgon · кадр {number:03d}"})
        clips.append({"kind": "image", "asset_id": "logo", "start": 0, "duration": 99, "title": "Логотип каналу"})
        self.project["tracks"] = [{"clips": clips}]

    def test_the_video_s_own_frames_are_the_style_reference(self):
        self.made_frames(5)
        work = Path(self.tmp.name) / "work"
        work.mkdir()
        stills = thumbnail_gen.frame_stills(self.project, work)
        self.assertEqual([path.name for path in stills], ["Кадр ролику 1.png", "Кадр ролику 2.png", "Кадр ролику 3.png"])
        self.assertEqual([Image.open(path).getpixel((0, 0))[0] for path in stills], [20, 60, 100])   # first, middle, last

    def test_start_needs_a_title_and_two_made_frames(self):
        with self.assertRaises(store.StudioError):
            thumbnail_gen.start(self.project["id"], " ", "S")
        self.made_frames(1)
        with self.assertRaises(store.StudioError) as caught:
            thumbnail_gen.start(self.project["id"], "T", "S")
        self.assertEqual(caught.exception.status, 409)
        self.made_frames(2)

    def test_a_razgon_episode_takes_its_style_from_frames_drawn_as_code(self):
        razgon = Path(self.tmp.name) / "razgon" / "projects" / "05-test"
        (self.episode / "razgon.json").write_text(json.dumps({"razgon_root": str(razgon.parents[1]), "project": str(razgon)}), encoding="utf-8")
        (razgon / "story").mkdir(parents=True)
        (razgon / "story" / "studio_frames.json").write_text(json.dumps({"frames": [
            {"number": n, "start": (n - 1) * 10.0, "end": n * 10.0} for n in (1, 2, 3, 4)]}), encoding="utf-8")
        work = Path(self.tmp.name) / "work"
        work.mkdir()

        def render(command, **kwargs):
            out = Path(command[command.index("--dir") + 1])
            out.mkdir(parents=True, exist_ok=True)
            for t in command[command.index("--stills") + 1].split(","):
                Image.new("RGB", (16, 9), (int(float(t)), 0, 0)).save(out / f"{t}s_{t}.png")
            Image.new("RGB", (16, 9)).save(out / "sheet_01.png")
            return subprocess.CompletedProcess(command, 0)

        with patch.object(thumbnail_gen.frame_progress, "razgon_project", return_value=razgon), \
                patch.object(thumbnail_gen.frame_progress, "drawn", return_value=[1, 2, 3, 4]), \
                patch.object(thumbnail_gen.subprocess, "run", side_effect=render) as run:
            self.assertEqual(store.picture_count(self.project), 4)                     # code frames count as made
            stills = thumbnail_gen.code_stills(self.project, work)
        self.assertIn("--stills", run.call_args.args[0])
        self.assertEqual([Image.open(path).getpixel((0, 0))[0] for path in stills], [5, 25, 35])   # first, middle, last


if __name__ == "__main__":
    unittest.main()
