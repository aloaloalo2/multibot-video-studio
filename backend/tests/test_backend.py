import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import app  # noqa: E402
import store  # noqa: E402
import credentials  # noqa: E402
import speech  # noqa: E402


class BackendTest(unittest.TestCase):
    def test_library_thumbnail_is_small_and_preserves_original(self):
        from PIL import Image
        import hashlib,io
        p=store.create_project(store.channel_id(self.channel),'Thumbnail check');source=self.channel/'thumb-source.png';Image.new('RGBA',(1600,1000),(210,150,100,160)).save(source);original=hashlib.sha256(source.read_bytes()).hexdigest()
        asset=store.import_asset_file(p,source)
        status,data=self.request('/api/projects/'+p['id']+'/assets/'+asset['id']+'/thumbnail')
        self.assertEqual(status,200);self.assertLess(len(data),source.stat().st_size)
        with Image.open(io.BytesIO(data)) as im:self.assertLessEqual(im.width,256);self.assertLessEqual(im.height,160)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),original)
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.originals = (store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT, store.DISABLED_PATH, store.GLOBAL_SETTINGS_PATH, app.JOBS_ROOT)
        store.YOUTUBE_ROOT = base / "YOUTUBE"
        store.DATA_ROOT = base / "data"
        store.PROJECTS_ROOT = store.DATA_ROOT / "projects"
        store.DISABLED_PATH = store.DATA_ROOT / "disabled_channels.json"
        store.GLOBAL_SETTINGS_PATH = store.DATA_ROOT / "settings.json"
        app.JOBS_ROOT = store.DATA_ROOT / "jobs"
        cls.channel = store.YOUTUBE_ROOT / "Test Channel"
        cls.channel.mkdir(parents=True)
        (cls.channel / "video-plan.json").write_text(json.dumps({"short_sentence_words": 5, "opening_clip_count": 6, "opening_seconds": 90, "opening_clip_types": ["stock_video"] * 6, "weights": {"stock_video": 10, "stock_photo": 70, "animation": 20}}))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        store.YOUTUBE_ROOT, store.DATA_ROOT, store.PROJECTS_ROOT, store.DISABLED_PATH, store.GLOBAL_SETTINGS_PATH, app.JOBS_ROOT = cls.originals
        cls.tmp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        payload = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base_url + path, data=payload, method=method, headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                data = response.read()
                return response.status, json.loads(data) if response.headers.get("Content-Type", "").startswith("application/json") else data
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_atomic_batch_is_one_undo_and_invalid_batch_preserves_project(self):
        project = store.create_project(store.channel_id(self.channel), "Batch montage")
        pid = project["id"]
        path = "/api/projects/" + pid + "/actions"
        edits = [{"type":"add_clip", "payload":{"layer_id":"layer-1", "kind":"text", "text":"First", "start":0, "duration":1}},
                 {"type":"add_clip", "payload":{"layer_id":"layer-1", "kind":"text", "text":"Second", "start":1, "duration":1}}]
        code, result = self.request(path, "POST", {"type":"batch", "payload":{"actions":edits}, "expected_revision":0})
        self.assertEqual(code, 200)
        self.assertEqual(result["project"]["revision"], 1)
        self.assertEqual(sum(len(t["clips"]) for t in result["project"]["tracks"]), 2)
        before = store.project_path(pid).read_bytes()
        code, _ = self.request(path, "POST", {"type":"batch", "payload":{"actions":[edits[0],{"type":"unknown"}]}, "expected_revision":1})
        self.assertEqual(code, 400)
        self.assertEqual(store.project_path(pid).read_bytes(), before)
        code, result = self.request(path, "POST", {"type":"undo", "expected_revision":1})
        self.assertEqual(code, 200)
        self.assertFalse(any(t["clips"] for t in result["project"]["tracks"]))
        code, _ = self.request(path, "POST", {"type":"batch", "payload":{"actions":edits}, "expected_revision":1})
        self.assertEqual(code, 409)

    def test_background_speech_analysis_applies_only_complete_matches(self):
        cid = store.channel_id(self.channel)
        project = store.create_project(cid, "Speech analysis")
        pid = project["id"]
        script = "First complete sentence. Second complete sentence."
        store.generate_project_plan(cid, project["name"], project["episode_path"], project_id=pid, script=script)
        source = Path(project["episode_path"]) / "narration.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b"\0\0" * 16000)
        original = source.read_bytes()
        asset = store.asset_record(source, pid)
        words = [{"text": text, "start": index * .2, "end": index * .2 + .15, "probability": .99} for index, text in enumerate(speech.tokens(script))]
        with patch.object(speech, "transcribe", return_value=(words, {"engine": "test", "model": "fixture", "local": True})):
            code, result = self.request("/api/projects/" + pid + "/plan/analyze", "POST", {"asset_id": asset["id"]})
            self.assertEqual(code, 202)
            for _ in range(100):
                code, analysis = self.request("/api/projects/" + pid + "/analysis")
                if analysis["job"]["status"] in {"complete", "failed"}: break
                time.sleep(.02)
        self.assertEqual(analysis["job"]["status"], "complete", analysis["job"].get("error"))
        self.assertTrue(analysis["report"]["applied"])
        self.assertEqual(analysis["report"]["word_match_percent"], 100)
        self.assertTrue(store.plan_readiness(store.load_project(pid))["plan_ready"])
        self.assertFalse(store.plan_readiness(store.load_project(pid))["export_ready"])
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(any(track["clips"] for track in store.load_project(pid)["tracks"]))
        before = store.load_project_plan(pid)
        with patch.object(speech, "transcribe", return_value=(words[:-1], {"engine": "test", "model": "fixture", "local": True})):
            self.request("/api/projects/" + pid + "/plan/analyze", "POST", {"asset_id": asset["id"]})
            for _ in range(100):
                _, analysis = self.request("/api/projects/" + pid + "/analysis")
                if analysis["job"]["status"] in {"complete", "failed"}: break
                time.sleep(.02)
        self.assertEqual(analysis["report"]["status"], "needs_review")
        self.assertFalse(analysis["report"]["applied"])
        self.assertEqual(store.load_project_plan(pid), before)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is needed for video audio extraction")
    def test_video_analysis_reuses_extracted_audio_without_duplicate_assets(self):
        cid = store.channel_id(self.channel)
        project = store.create_project(cid, "Video speech analysis")
        pid = project["id"]
        script = "First complete sentence. Second complete sentence."
        store.generate_project_plan(cid, project["name"], project["episode_path"], project_id=pid, script=script)
        source = Path(self.tmp.name) / "video-voice.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b"\0\0" * 16000)
        video = Path(self.tmp.name) / "voice-video.mp4"
        subprocess.run([shutil.which("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(source), "-f", "lavfi", "-i", "color=c=black:s=64x64:r=8", "-c:v", "libx264", "-c:a", "aac", "-shortest", "-y", str(video)], check=True, capture_output=True)
        asset = store.import_asset_file(store.load_project(pid), video)
        words = [{"text": text, "start": index * .2, "end": index * .2 + .15, "probability": .99} for index, text in enumerate(speech.tokens(script))]
        results = []
        with patch.object(speech, "transcribe", return_value=(words, {"engine": "test", "model": "fixture", "local": True})):
            for _ in range(2):
                code, result = self.request("/api/projects/" + pid + "/plan/analyze", "POST", {"asset_id": asset["id"]})
                self.assertEqual(code, 202)
                for _ in range(200):
                    _, analysis = self.request("/api/projects/" + pid + "/analysis")
                    if analysis["job"]["status"] in {"complete", "failed"}: break
                    time.sleep(.02)
                self.assertEqual(analysis["job"]["status"], "complete", analysis["job"].get("error"))
                self.assertTrue(analysis["report"]["applied"])
                results.append(analysis["report"]["audio"]["asset_id"])
        self.assertEqual(results[0], results[1])
        self.assertEqual(sum(asset["kind"] == "audio" for asset in store.discover_assets(store.load_project(pid))), 1)

    def test_draft_export_is_blocked_and_timing_file_unlocks_only_montage(self):
        cid = store.channel_id(self.channel)
        project = store.create_project(cid, "Timing file workflow")
        pid = project["id"]
        script = "First complete sentence about a simple subject. Second complete sentence about another simple subject."
        endpoint = "/api/projects/" + pid + "/plan/generate"
        status, result = self.request(endpoint, "POST", {"script": script, "duration": 2})
        self.assertEqual(status, 200)
        self.assertFalse(result["project"]["production"]["plan_ready"])
        status, _ = self.request("/api/projects/" + pid + "/export", "POST", {"confirm_export": True})
        self.assertEqual(status, 409)
        phrases = [{"text": text, "start": start, "end": end} for text, start, end in zip(store.planner.split_sentences(script), [.1, 1.1], [.8, 1.8])]
        timings = {"duration": 2, "sentences": phrases}
        status, result = self.request(endpoint, "POST", {"script": script, "timings": timings})
        self.assertEqual(status, 200)
        self.assertTrue(result["project"]["production"]["plan_ready"])
        self.assertFalse(result["project"]["production"]["export_ready"])
        self.assertEqual(result["plan"]["frames"][0]["end"], 1.1)
        self.assertFalse(any(track["clips"] for track in result["project"]["tracks"]))
        with self.assertRaises(store.StudioError):
            app.start_export(store.load_project(pid), True)
        status, _ = self.request(endpoint, "POST", {"script": script, "timings": {"duration": 2, "sentences": phrases[:1]}})
        self.assertEqual(status, 400)
        self.assertEqual(store.load_project_plan(pid)["timing"]["status"], "audio_synced")
        source = Path(project["episode_path"]) / "voice.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b"\0\0" * 16000)
        asset = store.asset_record(source, pid)
        project = store.apply_action(pid, "add_clip", {"layer_id": project["tracks"][0]["id"], "kind": "audio", "asset_id": asset["id"], "start": 0, "duration": 2})
        self.assertTrue(store.plan_readiness(project)["export_ready"])
        clip = project["tracks"][0]["clips"][0]
        project = store.apply_action(pid, "set_clip_volume", {"clip_id": clip["id"], "volume": 0})
        self.assertFalse(store.plan_readiness(project)["export_ready"])
        # Replacing the script resets the workflow to draft without touching montage.
        status, result = self.request(endpoint, "POST", {"script": "A changed complete sentence about a simple subject."})
        self.assertEqual(status, 200)
        self.assertFalse(result["project"]["production"]["plan_ready"])
        self.assertEqual(len(result["project"]["tracks"][0]["clips"]), 1)
        script_file = Path(project["episode_path"]) / "script.txt"
        script_file.write_text(script)
        timing_file = Path(project["episode_path"]) / "phrases.json"
        timing_file.write_text(json.dumps(timings))
        tool = BACKEND.parents[1] / "tools" / "video_plan.py"
        run = subprocess.run([sys.executable, str(tool), "--channel", str(self.channel), "--script", str(script_file), "--timings", str(timing_file), "--studio-url", self.base_url], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["timing_basis"], "audio_alignment")
        self.assertTrue(store.plan_readiness(store.load_project(pid))["plan_ready"])

    def test_project_proportions_are_isolated_and_can_return_to_channel_defaults(self):
        cid = store.channel_id(self.channel)
        original = (self.channel / "video-plan.json").read_bytes()
        project = store.create_project(cid, "Project proportions")
        endpoint = "/api/projects/" + project["id"] + "/plan/generate"
        script = "First complete sentence about a simple subject."
        status, result = self.request(endpoint, "POST", {"script": script, "weights": {"text": 100}})
        self.assertEqual(status, 200)
        self.assertEqual(result["plan"]["settings_scope"], "project")
        self.assertIn(result["plan"]["frames"][0]["format"], {"stock_video", "generated_video"})
        self.assertTrue(all(frame["format"] == "text" for frame in result["plan"]["frames"][1:]))
        self.assertEqual((self.channel / "video-plan.json").read_bytes(), original)
        self.assertTrue(store.plan_settings_match(project["id"], result["plan"]))
        status, result = self.request(endpoint, "POST", {"script": script})
        self.assertEqual(result["project"]["plan_weights"], {"text": 100})
        status, result = self.request(endpoint, "POST", {"script": script, "use_channel_weights": True})
        self.assertEqual(status, 200)
        self.assertNotIn("plan_weights", result["project"])
        self.assertEqual(result["plan"]["settings_snapshot"]["weights"], store.read_json(self.channel / "video-plan.json")["weights"])
        self.assertTrue(store.plan_settings_match(project["id"], result["plan"]))

    def test_health_channels_project_actions_and_undo(self):
        status, health = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["service"], "multibot-video-studio")
        status, channels = self.request("/api/channels")
        self.assertEqual(status, 200)
        channel_id = store.channel_id(self.channel)
        self.assertIn(channel_id, {item["id"] for item in channels["channels"]})
        status, result = self.request("/api/projects", "POST", {"channel_id": channel_id, "name": "Episode 1"})
        self.assertEqual(status, 201)
        project = result["project"]
        self.assertEqual(project["revision"], 0)
        self.assertFalse(project["can_undo"])
        self.assertFalse(project["can_redo"])
        self.assertEqual(project["schema_version"], 2)
        self.assertEqual(len(project["tracks"]), 1)
        self.assertEqual(project["tracks"][0]["type"], "universal")
        self.assertFalse(project["tracks"][0]["clips"])
        project_id = project["id"]
        status, refusal = self.request("/api/projects/%s/export" % project_id, "POST", {"confirm_export": False})
        self.assertEqual(status, 400)
        self.assertIn("експорт", refusal["error"])
        plan_dir = self.channel / "Episode 1"
        plan_dir.mkdir()
        plan_path = plan_dir / "План видео.json"
        plan_path.write_text(json.dumps({"frames": [
            {"number": 1, "start": 0, "end": 8, "sentences": ["First."], "format": "generated_video"},
            {"number": 2, "start": 8, "end": 14, "sentences": ["Second."], "format": "stock_photo"},
        ]}))
        status, result = self.request("/api/projects/import", "POST", {"channel_id": channel_id, "plan_path": str(plan_path)})
        self.assertEqual(status, 201)
        imported = result["project"]
        self.assertFalse(any(track["clips"] for track in imported["tracks"]))
        self.assertFalse(imported["production"]["plan_ready"])
        # Independent editing fixture; importing a draft must not create clips.
        imported["tracks"] = [{"id": "edit-" + str(i), "name": "Шар " + str(i + 1), "type": "universal", "z_index": i, "clips": [{"id": "text-" + str(i), "kind": "text", "text": text, "title": text, "start": start, "duration": duration, "trim_start": 0, "volume": 1}]} for i, (text, start, duration) in enumerate([("First.", 0, 8), ("Second.", 8, 6)])]
        imported["revision"] = 0
        store.save_project(imported)
        self.assertEqual(len(imported["tracks"]), 2)
        self.assertTrue(all(layer["type"] == "universal" and len(layer["clips"]) == 1 for layer in imported["tracks"]))
        sid = imported["tracks"][0]["clips"][0]["id"]
        pid = imported["id"]
        status, result = self.request("/api/projects/%s/actions" % pid, "POST", {"type": "split_clip", "payload": {"clip_id": sid, "at": 4}, "expected_revision": 0})
        self.assertEqual(status, 200)
        self.assertEqual(len(result["project"]["tracks"]), 3)
        self.assertAlmostEqual(result["project"]["duration"], 14)
        self.assertEqual(result["project"]["revision"], 1)
        self.assertTrue(result["project"]["can_undo"])
        self.assertFalse(result["project"]["can_redo"])
        status, conflict = self.request("/api/projects/%s/actions" % pid, "POST", {"type": "undo", "payload": {}, "expected_revision": 0})
        self.assertEqual(status, 409)
        status, result = self.request("/api/projects/%s/actions" % pid, "POST", {"type": "undo", "payload": {}, "expected_revision": 1})
        self.assertEqual(status, 200)
        self.assertEqual(len(result["project"]["tracks"]), 2)
        self.assertEqual(result["project"]["revision"], 2)
        self.assertFalse(result["project"]["can_undo"])
        self.assertTrue(result["project"]["can_redo"])
        status, result = self.request("/api/projects/import/data", "POST", {"channel_id": channel_id, "name": "Browser Plan", "plan": {"frames": [{"start": 0, "end": 2, "sentences": ["Browser import."], "format": "text"}]}})
        self.assertEqual(status, 201)
        self.assertFalse(any(track["clips"] for track in result["project"]["tracks"]))
        self.assertTrue(Path(result["project"]["plan_source"]).is_file())

    def test_studio_generates_with_latest_saved_settings_and_preserves_montage(self):
        cid = store.channel_id(self.channel)
        original = store.read_json(self.channel / "video-plan.json")
        self.addCleanup(lambda: store.atomic_json(self.channel / "video-plan.json", original))
        episode = self.channel / "Studio generated"
        episode.mkdir(exist_ok=True)
        script = episode / "script.txt"
        script.write_text("First complete longer sentence about cinnamon. Second complete longer sentence about dinner.")
        settings = {"weights": {"text": 100}, "first_clip_seconds": 0, "max_sentences_per_scene": 3}
        status, _ = self.request("/api/channels/" + cid, "PATCH", {"settings": settings})
        self.assertEqual(status, 200)
        payload = {"channel_id": cid, "name": episode.name, "episode_path": str(episode), "script_path": str(script)}
        status, result = self.request("/api/projects/generate-plan", "POST", payload)
        self.assertEqual(status, 200)
        pid = result["project"]["id"]
        self.assertTrue(result["settings_match"])
        self.assertEqual(result["plan"]["generator"], "multibot-video-studio")
        self.assertIn(result["plan"]["frames"][0]["format"], {"stock_video", "generated_video"})
        self.assertTrue(all(frame["format"] == "text" for frame in result["plan"]["frames"][1:]))
        self.assertEqual(result["plan"]["settings_snapshot"]["weights"], {"text": 100})
        self.assertEqual(store.read_json(Path(result["plan"]["report"]["json"])), store.load_project_plan(pid))
        montage = store.load_project(pid)["tracks"]
        self.request("/api/channels/" + cid, "PATCH", {"settings": {"weights": {"animation": 100}}})
        status, stale = self.request("/api/projects/" + pid + "/plan")
        self.assertFalse(stale["settings_match"])
        status, updated = self.request("/api/projects/" + pid + "/plan/generate", "POST", {"script": script.read_text()})
        self.assertEqual(status, 200)
        self.assertEqual(updated["project"]["id"], pid)
        self.assertIn(updated["plan"]["frames"][0]["format"], {"stock_video", "generated_video"})
        self.assertTrue(all(frame["format"] == "animation" for frame in updated["plan"]["frames"][1:]))
        self.assertEqual(store.load_project(pid)["tracks"], montage)
        self.assertTrue(list((store.project_dir(pid) / "plan-history").glob("*.json")))
        status, _ = self.request("/api/projects/generate-plan", "POST", {**payload, "settings": {"weights": {"text": 100}}})
        self.assertEqual(status, 400)
        status, _ = self.request("/api/projects/generate-plan", "POST", {**payload, "script_path": str(self.channel / "outside.txt")})
        self.assertEqual(status, 400)
        tool = BACKEND.parents[1] / "tools" / "video_plan.py"
        run = subprocess.run([sys.executable, str(tool), "--channel", str(self.channel), "--script", str(script), "--studio-url", self.base_url], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["project_id"], pid)
        self.assertEqual(store.load_project_plan(pid)["settings_snapshot"]["weights"], {"animation": 100})

    def test_attaching_timings_writes_digit_script_and_keeps_spoken_original(self):
        cid = store.channel_id(self.channel)
        episode = self.channel / "Post Whisper numbers"
        episode.mkdir(exist_ok=True)
        script = "Насыпьте восемь граммов. Затем двадцать один грамм."
        source_path = episode / "Сценарий.txt"
        source_path.write_text(script, encoding="utf-8")
        payload = {"channel_id": cid, "name": episode.name, "episode_path": str(episode), "script_path": str(source_path),
                   "timings": {"duration": 3, "sentences": [{"text":"Насыпьте 8 граммов.","start":0,"end":1}, {"text":"Затем 21 грамм.","start":1.3,"end":2.8}]}}
        status, result = self.request("/api/projects/generate-plan", "POST", payload)
        self.assertEqual(status, 200)
        plan = result["plan"]
        self.assertEqual(plan["number_format"], "digits_after_whisper")
        self.assertEqual(source_path.read_text(), "Насыпьте 8 граммов. Затем 21 грамм.")
        self.assertEqual(Path(plan["spoken_script_file"]).read_text(), script)
        self.assertEqual(plan["timing"]["sentences"][1]["start"], 1.3)
        status, again = self.request("/api/projects/generate-plan", "POST", payload)
        self.assertEqual(status, 200)
        self.assertEqual(again["project"]["id"], result["project"]["id"])
        self.assertEqual(again["plan"]["spoken_script"], script)
        store.planner.validate_synced_plan(again["plan"], 3)

    def test_settings_media_range_and_source_safety(self):
        cid = store.channel_id(self.channel)
        status, result = self.request("/api/channels/%s" % cid, "PATCH", {"settings": {"weights": {"stock_video": 20, "stock_photo": 60, "animation": 20}}})
        self.assertEqual(status, 200)
        self.assertEqual(sum(result["channel"]["settings"]["weights"].values()), 100)
        status, result = self.request("/api/channels/%s" % cid, "PATCH", {"settings": {"opening_clip_count": 4}})
        self.assertEqual(status, 200)
        self.assertEqual(len(result["channel"]["settings"]["opening_clip_types"]), 4)
        status, bad = self.request("/api/channels/%s" % cid, "PATCH", {"settings": {"weights": {"stock_photo": 20}}})
        self.assertEqual(status, 400)
        self.assertEqual(sum(store.read_json(self.channel / "video-plan.json")["weights"].values()), 100)
        project = store.create_project(cid, "Media Test")
        episode = Path(project["episode_path"])
        episode.mkdir()
        media = episode / "test.jpg"
        media.write_bytes(b"0123456789")
        status, result = self.request("/api/projects/%s/assets" % project["id"])
        self.assertEqual(status, 200)
        aid = result["assets"][0]["id"]
        status, data = self.request("/api/projects/%s/assets/%s/file" % (project["id"], aid), headers={"Range": "bytes=2-5"})
        self.assertEqual(status, 206)
        self.assertEqual(data, b"2345")
        uploaded = urllib.request.Request(self.base_url + "/api/projects/%s/assets/upload" % project["id"], data=b"fake-image", method="POST", headers={"Content-Type": "application/octet-stream", "X-File-Name": "browser%20frame.png"})
        with urllib.request.urlopen(uploaded, timeout=5) as response:
            upload_result = json.load(response)
            self.assertEqual(response.status, 201)
        self.assertEqual(upload_result["asset"]["name"], "browser frame.png")
        self.assertEqual(Path(upload_result["asset"]["path"]).read_bytes(), b"fake-image")
        self.assertFalse(store.under(Path(self.tmp.name) / "outside.jpg", episode))

    def test_create_channel_from_studio(self):
        status, result = self.request("/api/channels/create", "POST", {"name": "New Studio Channel"})
        self.assertEqual(status, 201)
        channel = result["channel"]
        self.assertEqual(channel["name"], "New Studio Channel")
        self.assertEqual(sum(channel["settings"]["weights"].values()), 100)
        self.assertTrue((store.YOUTUBE_ROOT / "New Studio Channel" / "video-plan.json").is_file())
        status, channels = self.request("/api/channels")
        self.assertEqual(status, 200)
        self.assertIn(channel["id"], {item["id"] for item in channels["channels"]})

    def test_channel_motion_is_used_by_new_animation(self):
        cid = store.channel_id(self.channel)
        endpoint = "/api/channels/" + cid
        self.addCleanup(lambda: store.update_channel_settings(cid, {"motion_easing": "ease_in_out"}))
        status, _ = self.request(endpoint, "PATCH", {"settings": {"motion_easing": "ease_out"}})
        self.assertEqual(status, 200)
        status, _ = self.request(endpoint, "PATCH", {"settings": {"motion_easing": "unknown"}})
        self.assertEqual(status, 400)
        project = store.create_project(cid, "Motion defaults")
        project = store.apply_action(project["id"], "add_clip", {"layer_id": project["tracks"][0]["id"], "kind": "animation", "duration": 1, "keyframes": [{"time": 0, "x": .2}, {"time": 1, "x": .8}]})
        self.assertEqual(project["tracks"][0]["clips"][0]["easing"], "ease_out")
        manifest = app.normalize_for_engine(project)
        self.assertEqual(manifest["timeline_layers"][0]["clips"][0]["easing"], "ease_out")

    def test_service_keys_are_write_only_and_not_saved_in_project_data(self):
        class TestVault:
            def __init__(self):
                self.entries = {}
            def configured(self, service):
                return service in self.entries
            def save(self, service, secret):
                self.entries[service] = secret
        fake = TestVault()
        example = "example-test-value-for-vault"
        with patch.object(credentials, "_keychain", fake):
            status, result = self.request("/api/service-keys")
            self.assertEqual(status, 200)
            self.assertEqual({item["id"] for item in result["providers"]}, {"pixabay", "pexels", "unsplash"})
            status, result = self.request("/api/service-keys", "POST", {"provider_id": "pixabay", "key": example})
            self.assertEqual(status, 200)
            self.assertEqual(fake.entries["pixabay-youtube-api"], example)
            self.assertNotIn(example, json.dumps(result))
            status, result = self.request("/api/service-keys", "POST", {"provider_id": "custom", "name": "Test stock service", "key": example})
            self.assertEqual(status, 200)
            self.assertTrue(result["provider"]["configured"])
            metadata = credentials.metadata_path().read_text()
            self.assertIn("Test stock service", metadata)
            self.assertNotIn(example, metadata)
            status, result = self.request("/api/service-keys")
            self.assertEqual(status, 200)
            self.assertNotIn(example, json.dumps(result))
            self.assertTrue(next(item for item in result["providers"] if item["id"] == "pixabay")["configured"])
            status, _ = self.request("/api/service-keys", "POST", {"provider_id": "pexels", "key": "invalid\nvalue"})
            self.assertEqual(status, 400)
            self.assertNotIn("multibot-video-studio-pexels", fake.entries)

    def test_project_rename_delete_and_restore_preserve_materials(self):
        cid = store.channel_id(self.channel)
        project = store.create_project(cid, "Project management")
        endpoint = "/api/projects/" + project["id"]
        episode = Path(project["episode_path"])
        episode.mkdir()
        source = episode / "original.png"
        source.write_bytes(b"original-media")
        asset = store.import_asset_file(project, source)
        revision = store.load_project(project["id"])["revision"]
        status, _ = self.request(endpoint, "PATCH", {"name": " ", "expected_revision": revision})
        self.assertEqual(status, 400)
        self.assertEqual(store.load_project(project["id"])["name"], "Project management")
        status, result = self.request(endpoint, "PATCH", {"name": "Нова назва", "expected_revision": revision})
        self.assertEqual(status, 200)
        self.assertEqual(result["project"]["name"], "Нова назва")
        self.assertEqual(result["project"]["episode_path"], str(episode))
        status, _ = self.request(endpoint, "PATCH", {"name": "Stale rename", "expected_revision": revision})
        self.assertEqual(status, 409)
        status, _ = self.request(endpoint, "DELETE")
        self.assertEqual(status, 200)
        status, _ = self.request(endpoint)
        self.assertEqual(status, 404)
        status, listed = self.request("/api/projects?channel=" + cid)
        self.assertEqual(status, 200)
        self.assertNotIn(project["id"], {item["id"] for item in listed["projects"]})
        self.assertEqual(source.read_bytes(), b"original-media")
        self.assertEqual(Path(asset["path"]).read_bytes(), b"original-media")
        status, restored = self.request(endpoint + "/restore", "POST", {})
        self.assertEqual(status, 200)
        self.assertEqual(restored["project"]["name"], "Нова назва")
        status, listed = self.request("/api/projects?channel=" + cid)
        self.assertIn(project["id"], {item["id"] for item in listed["projects"]})
        status, _ = self.request(endpoint)
        self.assertEqual(status, 200)

    def test_attached_plan_routes_updates_and_preserves_montage(self):
        cid = store.channel_id(self.channel)
        episode = self.channel / "Attached plan"
        episode.mkdir()
        plan = {"report": {"timing": "Попередній таймінг"}, "frames": [{"number": 1, "start": 0, "end": 8, "format": "stock_video", "sentences": ["Перший кадр."]}]}
        payload = {"channel_id": cid, "name": "Attached plan", "episode_path": str(episode), "plan": plan}
        status, created = self.request("/api/projects/from-plan", "POST", payload)
        self.assertEqual(status, 200)
        project = created["project"]
        self.assertEqual(len(project["tracks"]), 1)
        self.assertFalse(project["tracks"][0]["clips"])
        endpoint = "/api/projects/" + project["id"]
        status, result = self.request(endpoint + "/plan")
        self.assertEqual(status, 200)
        self.assertEqual(result["plan"], plan)
        for path in ("/channels/" + cid, "/channels/" + cid + "/projects/" + project["id"], created["plan_url"]):
            status, html = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn(b'id="project-plan"', html)
        store.apply_action(project["id"], "add_clip", {"layer_id": project["tracks"][0]["id"], "kind": "text", "text": "Збережений монтаж", "duration": 2})
        plan["frames"][0]["sentences"] = ["Оновлена репліка."]
        status, updated = self.request("/api/projects/from-plan", "POST", payload)
        self.assertEqual(status, 200)
        self.assertEqual(updated["project"]["id"], project["id"])
        self.assertEqual(updated["project"]["tracks"][0]["clips"][0]["text"], "Збережений монтаж")
        status, result = self.request(endpoint + "/plan")
        self.assertEqual(result["plan"]["frames"][0]["sentences"], ["Оновлена репліка."])
        status, result = self.request(endpoint + "/plan", "POST", {"plan": {"frames": []}})
        self.assertEqual(status, 400)
        store.apply_action(project["id"], "undo", {})
        self.assertEqual(store.load_project_plan(project["id"])["frames"][0]["sentences"], ["Оновлена репліка."])

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is needed for mixed media fixtures")
    def test_each_media_item_uses_a_universal_layer(self):
        from PIL import Image
        cid = store.channel_id(self.channel)
        project = store.create_project(cid, "Mixed universal layer")
        layer_id = project["tracks"][0]["id"]
        episode = Path(project["episode_path"])
        episode.mkdir()
        Image.new("RGB", (160, 90), "#116a8c").save(episode / "image.png")
        subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=8", "-t", "1", str(episode / "video.mp4")], check=True, capture_output=True)
        subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1", str(episode / "audio.wav")], check=True, capture_output=True)
        for kind, filename in (("image", "image.png"), ("video", "video.mp4"), ("audio", "audio.wav")):
            asset = store.import_asset_file(store.load_project(project["id"]), episode / filename)
            store.apply_action(project["id"], "add_clip", {"layer_id": layer_id, "kind": kind, "asset_id": asset["id"], "duration": 1})
        store.apply_action(project["id"], "add_clip", {"layer_id": layer_id, "kind": "text", "text": "Текст на тому ж шарі", "duration": 1})
        store.apply_action(project["id"], "add_clip", {"layer_id": layer_id, "kind": "animation", "content_type": "shape", "duration": 1})
        status, result = self.request("/api/projects/" + project["id"])
        self.assertEqual(status, 200)
        saved = result["project"]
        self.assertEqual(len(saved["tracks"]), 5)
        self.assertTrue(all(layer["type"] == "universal" and len(layer["clips"]) == 1 for layer in saved["tracks"]))
        self.assertEqual({clip["kind"] for layer in saved["tracks"] for clip in layer["clips"]}, {"image", "video", "audio", "text", "animation"})
        manifest = app.normalize_for_engine(saved)
        self.assertEqual(len(manifest["timeline_layers"]), 5)
        self.assertTrue(all(len(layer["clips"]) == 1 for layer in manifest["timeline_layers"]))

    def test_empty_project_can_build_visual_and_audio_timeline(self):
        cid = store.channel_id(self.channel)
        project = store.create_project(cid, "Timeline Test")
        pid = project["id"]
        endpoint = "/api/projects/%s/actions" % pid
        first_layer = project["tracks"][0]["id"]
        status, result = self.request(endpoint, "POST", {"type": "add_clip", "payload": {"layer_id": first_layer, "kind": "animation", "content_type": "shape", "duration": 3, "title": "Початок", "preset": "slide_in", "preset_duration": .5, "keyframes": [{"time": 0, "x": 0, "y": .5, "scale": .5, "opacity": .1}, {"time": 1, "x": .5, "y": .5, "scale": 1, "opacity": 1}]}, "expected_revision": 0})
        self.assertEqual(status, 200)
        first = result["project"]["tracks"][0]["clips"][0]
        self.assertEqual(first["kind"], "animation")
        self.assertEqual(first["preset"], "slide_in")
        self.assertEqual(first["keyframes"][0]["scale"], .5)
        self.assertAlmostEqual(result["project"]["duration"], 3)
        status, result = self.request(endpoint, "POST", {"type": "add_layer", "payload": {"name": "Текст та звук"}, "expected_revision": 1})
        self.assertEqual(status, 200)
        second_layer = result["project"]["tracks"][1]["id"]
        status, result = self.request(endpoint, "POST", {"type": "update_layer", "payload": {"layer_id": second_layer, "name": "Тези та звук"}, "expected_revision": 2})
        self.assertEqual(status, 200)
        self.assertEqual(result["project"]["tracks"][1]["name"], "Тези та звук")
        status, result = self.request(endpoint, "POST", {"type": "add_clip", "payload": {"layer_id": second_layer, "kind": "text", "start": 3, "duration": 2, "title": "Теза", "text": "Важлива теза"}, "expected_revision": 3})
        self.assertEqual(status, 200)
        self.assertAlmostEqual(result["project"]["duration"], 5)
        source = Path(self.tmp.name) / "voice.wav"
        source.write_bytes(b"RIFF0000WAVE")
        status, result = self.request("/api/projects/%s/assets/pick" % pid, "POST", {"path": str(source)})
        self.assertEqual(status, 201)
        aid = result["asset"]["id"]
        status, result = self.request(endpoint, "POST", {"type": "add_clip", "payload": {"layer_id": second_layer, "kind": "audio", "asset_id": aid, "start": 0, "duration": 5, "volume": 0.8}, "expected_revision": 5})
        self.assertEqual(status, 200)
        clip = result["project"]["tracks"][2]["clips"][0]
        self.assertEqual(clip["asset_id"], aid)
        manifest = app.normalize_for_engine(result["project"])
        self.assertEqual(manifest["timeline_layers"][0]["clips"][0]["preset"], "slide_in")
        self.assertEqual(manifest["timeline_layers"][0]["clips"][0]["keyframes"][0]["opacity"], .1)
        self.assertEqual(manifest["timeline_layers"][1]["clips"][0]["text"], "Важлива теза")
        self.assertEqual(manifest["timeline_layers"][2]["clips"][0]["duration"], 5)
        status, result = self.request(endpoint, "POST", {"type": "delete_clip", "payload": {"clip_id": clip["id"]}, "expected_revision": 6})
        self.assertEqual(status, 200)
        self.assertEqual(len(result["project"]["tracks"][1]["clips"]), 1)

    def test_legacy_manifest_migrates_on_read_without_overwriting_source(self):
        cid = store.channel_id(self.channel)
        project = store.create_project(cid, "Legacy Test")
        old = dict(project)
        old.pop("schema_version")
        old["scenes"] = [{"id": "old-scene", "type": "text", "start": 0, "duration": 3, "title": "Стара теза", "text": "Стара теза", "transition": {"type": "cut", "duration": 0}}]
        old["tracks"] = [{"id": "voice", "name": "Озвучка", "type": "voice", "clips": [{"id": "old-audio", "start": 0, "duration": 3, "volume": .5, "asset_id": "missing"}]}]
        store.atomic_json(store.project_path(project["id"]), old)
        upgraded = store.load_project(project["id"])
        self.assertEqual(upgraded["schema_version"], 2)
        self.assertEqual([clip["kind"] for layer in upgraded["tracks"] for clip in layer["clips"]], ["text", "audio"])
        self.assertNotIn("schema_version", store.read_json(store.project_path(project["id"])))
        updated = store.apply_action(project["id"], "move_clip", {"clip_id": "old-scene", "start": 1})
        self.assertEqual(updated["schema_version"], 2)
        self.assertEqual(updated["tracks"][0]["clips"][0]["start"], 1)
        stored = store.read_json(store.project_path(project["id"]))
        self.assertEqual(stored["legacy_backup"]["scenes"][0]["id"], "old-scene")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is needed for export integration")
    def test_export_renders_managed_project_into_temp_episode(self):
        status, result = self.request("/api/settings", "PATCH", {"settings": {"default_width": 320, "default_height": 180, "default_fps": 8, "export_subfolder": "Ready"}})
        self.assertEqual(status, 200)
        self.assertEqual(result["settings"]["export_subfolder"], "Ready")
        self.addCleanup(lambda: store.update_global_settings(store.GLOBAL_DEFAULTS))
        cid = store.channel_id(self.channel)
        project = store.create_project(cid, "Render Test")
        self.assertEqual((project["width"], project["height"], project["fps"]), (320, 180, 8))
        from PIL import Image
        image_path = Path(self.tmp.name) / "frame.png"
        Image.new("RGB", (320, 180), "#146a7a").save(image_path)
        asset = store.import_asset_file(project, image_path)
        layer_id = project["tracks"][0]["id"]
        project = store.apply_action(project["id"], "add_clip", {"layer_id": layer_id, "kind": "image", "asset_id": asset["id"], "start": 0, "duration": 1.2})
        first_id = project["tracks"][0]["clips"][0]["id"]
        project = store.apply_action(project["id"], "add_clip", {"layer_id": layer_id, "kind": "text", "start": 1.0, "duration": 1.2, "title": "Перевірка", "text": "Перевірка"})
        project = store.apply_action(project["id"], "set_transition", {"clip_id": first_id, "type": "crossfade", "duration": .2})
        audio_path = Path(self.tmp.name) / "tone.wav"
        subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2.2", "-y", str(audio_path)], check=True, capture_output=True)
        audio = store.import_asset_file(project, audio_path)
        self.assertGreater(audio["duration"], 1.9)
        project = store.apply_action(project["id"], "add_clip", {"layer_id": layer_id, "kind": "audio", "asset_id": audio["id"], "start": 0, "duration": audio["duration"], "volume": .2})
        result = store.generate_project_plan(cid, project["name"], project["episode_path"], project_id=project["id"], script="First synthetic sentence. Second synthetic sentence.", narration={"asset_id": audio["id"], "sentences": [{"text": "First synthetic sentence.", "start": .1, "end": .8}, {"text": "Second synthetic sentence.", "start": 1.1, "end": 2.0}]})
        project = result["project"]
        job = app.start_export(project, True)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            job = app.load_job(job["id"])
            if job["status"] in {"complete", "failed"}:
                break
            time.sleep(.1)
        self.assertEqual(job["status"], "complete", job.get("error"))
        output = Path(job["output_path"])
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 1024)
        self.assertEqual(output.parent.resolve(), (self.channel / "Render Test" / "Ready").resolve())


if __name__ == "__main__":
    unittest.main()
