"""The agent's tools: montage operations, the project summary, the studio status, export stills and fast answers."""
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import app  # noqa: E402
import agent_view  # noqa: E402
import montage_ops  # noqa: E402
import store  # noqa: E402
import word_timing  # noqa: E402

PHOTO_KEYS = [{"time": 0, "x": .585, "y": .5, "scale": 1.18}, {"time": 3.999, "x": .415, "y": .5, "scale": 1.30}]


class AgentToolsTest(unittest.TestCase):
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
        cls.channel = store.YOUTUBE_ROOT / "Agent Channel"
        cls.channel.mkdir(parents=True)
        (cls.channel / "video-plan.json").write_text(json.dumps({"weights": {"stock_photo": 100}}))
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

    def request(self, path, method="GET", body=None):
        payload = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base_url + path, data=payload, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read()
                kind = response.headers.get("Content-Type", "")
                return response.status, json.loads(data) if kind.startswith("application/json") else data.decode() if kind.startswith("text/") else data
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def project(self, frames=4, portrait_at=None):
        """A montage of `frames` photo frames of 4 s («Кадр 1» …), the photos panning and zooming, and a channel plate."""
        cid = store.channel_id(self.channel)
        AgentToolsTest.count = getattr(AgentToolsTest, "count", 0) + 1
        project = store.create_project(cid, f"Agent tools {AgentToolsTest.count}")
        episode = Path(project["episode_path"])
        episode.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1600, 900), (40, 90, 120)).save(episode / "wide.png")
        Image.new("RGB", (900, 1600), (120, 60, 40)).save(episode / "tall.png")
        Image.new("RGB", (1600, 900), (20, 160, 60)).save(episode / "other.png")
        wide = store.import_asset_file(project, episode / "wide.png")
        tall = store.import_asset_file(store.load_project(project["id"]), episode / "tall.png")
        actions = []
        for n in range(1, frames + 1):
            portrait = n == portrait_at
            keys = [{"time": 0, "scale": 1.0}, {"time": 3.999, "scale": 1.1}] if portrait else PHOTO_KEYS
            actions.append({"type": "add_clip", "payload": {"layer_id": "layer-1", "title": f"K{n:03d} фото", "kind": "image", "asset_id": (tall if portrait else wide)["id"],
                                                            "start": 4 * (n - 1), "duration": 4, "x": .5, "y": .5, "width": 1 if portrait else 1.0,
                                                            "height": 1, "keyframes": keys}})
        actions.append({"type": "add_clip", "payload": {"layer_id": "layer-1", "title": "Плашка", "kind": "animation", "content_type": "shape", "color": "#0d3b8a",
                                                        "start": 0, "duration": 4 * frames, "x": .1, "y": .1, "width": .2, "height": .08}})
        store.apply_action(project["id"], "batch", {"actions": actions})
        current = store.load_project(project["id"])
        ids = {c["title"]: c["id"] for t in current["tracks"] for c in t["clips"]}
        groups = [{"type": "group_clips", "payload": {"title": f"Кадр {n}", "clip_ids": [ids[f"K{n:03d} фото"]]}} for n in range(1, frames + 1)]
        groups.append({"type": "group_clips", "payload": {"title": "Плашка каналу", "role": "overlay", "clip_ids": [ids["Плашка"]]}})
        store.apply_action(project["id"], "batch", {"actions": groups})
        return store.load_project(project["id"])

    def clips(self, pid):
        return {c["title"]: c for t in store.load_project(pid)["tracks"] for c in t["clips"]}

    def test_an_accent_stays_on_the_same_point_of_the_moving_photo(self):
        project = self.project()
        status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"expected_revision": project["revision"], "ops": [
            {"op": "accent", "frame": 2, "kind": "circle", "at": [900, 500], "radii": [100, 60], "appear": 1.0},
            {"op": "accent", "frame": 2, "kind": "arrow", "from": [1300, 200], "to": [1000, 420], "appear": 1.2}]})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["applied"], 3)   # two clips and the plate back on top
        current = store.load_project(project["id"])
        clips = {c["title"]: c for t in current["tracks"] for c in t["clips"]}
        photo = montage_ops.Picture(current, clips["K002 фото"])
        for title in ("K002 акцент 0 коло", "K002 акцент 1 стрілка"):
            ring = clips[title]
            self.assertEqual(ring["easing"], clips["K002 фото"]["easing"])
            anchor = None
            for moment in (0, .7, 2, 3.3, 3.99):
                x, y = (montage_ops.keyframe_value(ring, prop, moment) for prop in ("x", "y"))
                spot = photo.to_photo(x * 1920, y * 1080, moment)
                anchor = anchor or spot
                self.assertAlmostEqual(spot[0], anchor[0], places=3, msg=f"{title} at {moment}")
                self.assertAlmostEqual(spot[1], anchor[1], places=3, msg=f"{title} at {moment}")
                self.assertAlmostEqual(montage_ops.keyframe_value(ring, "scale", moment), photo.state(moment)[2] / photo.state(2)[2], places=3)
            self.assertAlmostEqual(montage_ops.keyframe_value(ring, "opacity", .5), 0)
            self.assertAlmostEqual(montage_ops.keyframe_value(ring, "opacity", 2), 1)
        circle = clips["K002 акцент 0 коло"]
        mid = [montage_ops.keyframe_value(circle, prop, 2) for prop in ("x", "y")]
        self.assertAlmostEqual(mid[0] * 1920, 900, delta=.6)   # at the middle moment it is where it was asked
        self.assertAlmostEqual(mid[1] * 1080, 500, delta=.6)
        self.assertTrue(Path(store.resolve_asset(current, circle["asset_id"])["path"]).is_file())
        last = [c["title"] for c in current["tracks"][-1]["clips"]]
        self.assertEqual(last, ["Плашка"])   # the channel plate stays the top of the picture
        self.assertIn("кадр 2: circle", result["report"])

    def test_a_label_over_the_photo_rides_with_it_and_beside_a_vertical_one_stands_still(self):
        project = self.project(frames=2, portrait_at=2)
        status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"ops": [
            {"op": "accent", "frame": 1, "kind": "text", "text": "Сначала тарелка салата", "at": [1100, 300], "appear": .5, "style": "card"},
            {"op": "accent", "frame": 2, "kind": "text", "text": "банку с водой", "at": [1650, 640], "appear": .5, "style": "yellow"},
            {"op": "accent", "frame": 2, "kind": "circle", "at": [960, 500], "radii": [80, 80], "appear": .5}]})
        self.assertEqual(status, 200, result)
        clips = self.clips(project["id"])
        label, card = clips["K001 акцент 0 текст"], clips["K001 акцент 0 картка"]
        self.assertEqual(label["text"], "Сначала тарелка салата")
        self.assertEqual([round(w["start"], 2) for w in label["text_words"]], [.5, .62, .74])
        self.assertEqual(len({p["x"] for p in label["keyframes"] if "x" in p}), 2)   # pinned: it moves
        self.assertEqual(card["mask"], "rounded")
        self.assertAlmostEqual(montage_ops.keyframe_value(card, "opacity", 2), .9)
        side = clips["K002 акцент 0 текст"]
        self.assertFalse(any("x" in p for p in side.get("keyframes", [])))           # in the black field: it stands
        self.assertTrue(any("x" in p for p in clips["K002 акцент 1 коло"]["keyframes"]))   # on the vertical photo: it moves

    def test_dry_run_and_revision_guard_change_nothing(self):
        project = self.project(frames=2)
        status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"dry_run": True, "ops": [
            {"op": "accent", "frame": 1, "kind": "card", "at": [400, 300], "size": [300, 90], "appear": 1}]})
        self.assertEqual((status, result["applied"]), (200, 0))
        self.assertEqual([a["type"] for a in result["actions"]], ["add_clip", "reorder_stack"])
        self.assertEqual(store.load_project(project["id"])["revision"], project["revision"])
        status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"expected_revision": project["revision"] - 1, "ops": [
            {"op": "accent", "frame": 1, "kind": "card", "at": [400, 300]}]})
        self.assertEqual(status, 409)
        status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"ops": [{"op": "accent", "frame": 9, "kind": "card", "at": [1, 1]}]})
        self.assertEqual(status, 404)
        status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"ops": [{"op": "erase_everything"}]})
        self.assertEqual(status, 400)

    def test_clear_accents_and_replace_keep_the_montage(self):
        project = self.project(frames=2)
        self.request(f"/api/projects/{project['id']}/ops", "POST", {"ops": [{"op": "accent", "frame": 1, "kind": "card", "at": [400, 300], "appear": 1}]})
        status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"ops": [{"op": "clear_accents", "frame": 1},
                                                                                                {"op": "replace", "frame": 2, "path": str(Path(project["episode_path"]) / "other.png")}]})
        self.assertEqual(status, 200, result)
        clips = self.clips(project["id"])
        self.assertFalse([t for t in clips if "акцент" in t])
        photo = clips["K002 фото"]
        self.assertTrue(store.resolve_asset(store.load_project(project["id"]), photo["asset_id"])["path"].endswith("other.png"))
        self.assertEqual(photo["keyframes"], PHOTO_KEYS)

    def test_place_puts_plan_frames_in_their_groups_and_counts_them_made(self):
        project = self.project(frames=1)
        episode = Path(project["episode_path"])
        plan = {"frames": [{"number": n, "format": "text" if n == 3 else "stock_photo", "start": 4.0 * (n - 1), "end": 4.0 * n,
                            "sentences": [f"Речення {n}."]} for n in range(1, 4)],
                "timing": {"status": "audio_synced"}, "script_sha256": "x"}
        with patch.object(store, "load_project_plan", return_value=plan):
            status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"ops": [
                {"op": "place", "frame": 2, "path": str(episode / "other.png")}, {"op": "place", "frame": 3, "text": True}]})
            self.assertEqual(status, 200, result)
            current = store.load_project(project["id"])
            clips = self.clips(project["id"])
            groups = {g["title"]: g for g in current["scene_groups"]}
            self.assertIn(clips["K002 кадр"]["id"], groups["Кадр 2"]["clip_ids"])
            self.assertIn(clips["K003 кадр"]["id"], groups["Кадр 3"]["clip_ids"])
            self.assertEqual((clips["K002 кадр"]["start"], clips["K002 кадр"]["duration"]), (4.0, 4.0))
            self.assertEqual([k["scale"] for k in clips["K002 кадр"]["keyframes"]], [1.0, 1.08])
            self.assertEqual(clips["K003 кадр"]["text_role"], "full_frame")
            # a frame already on the timeline is changed with replace, not placed twice
            status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"ops": [{"op": "place", "frame": 1, "path": str(episode / "other.png")}]})
            self.assertEqual(status, 400, result)
            self.assertEqual(store.made_frames(current, plan), [1, 2, 3])
            # the plate is not a frame of the film
            self.assertNotIn("Плашка", [c["title"] for c in store.film_clips(current)])

    def test_a_photo_channel_asks_for_frames_and_the_list_shows_their_progress(self):
        project = self.project(frames=1)
        plan = {"frames": [{"number": n, "format": "stock_photo", "start": 4.0 * (n - 1), "end": 4.0 * n, "sentences": [f"Речення {n}."]} for n in range(1, 4)],
                "timing": {"status": "audio_synced"}, "script_sha256": "x"}
        with patch.object(store, "load_project_plan", return_value=plan):
            with self.assertRaises(store.StudioError) as made:
                store.request_production(project["id"], 1)   # frame 1 is already on the timeline
            self.assertEqual(made.exception.status, 409)
            store.request_production(project["id"], 3)
            with self.assertRaises(store.StudioError):
                store.request_production(project["id"], 3)   # one request at a time
            listed = next(p for p in store.list_projects() if p["id"] == project["id"])
            self.assertEqual(listed["production_request"], {"status": "requested", "frames": 3, "limit": False, "made": 1})
            stale = {**plan, "director_stale": True}
        with patch.object(store, "load_project_plan", return_value=stale):
            other = self.project(frames=1)
            with self.assertRaises(store.StudioError):
                store.request_production(other["id"], 3)

    def test_transitions_follow_the_channel_rules(self):
        project = self.project(frames=12)
        current = store.load_project(project["id"])
        # frame 7 becomes a full-frame text frame: it must start with a cut
        text = {"type": "add_clip", "payload": {"layer_id": "layer-1", "title": "K007 текст", "kind": "text", "text": "Главное", "start": 24, "duration": 4,
                                                "text_role": "full_frame", "source_text": "Главное", "group_id": next(g["id"] for g in current["scene_groups"] if g["title"] == "Кадр 7")}}
        store.apply_action(project["id"], "batch", {"actions": [text]})
        status, result = self.request(f"/api/projects/{project['id']}/ops", "POST", {"ops": [{"op": "transitions", "share": .7, "seed": 5}]})
        self.assertEqual(status, 200, result)
        current = store.load_project(project["id"])
        groups = {g["id"]: g["title"] for g in current["scene_groups"]}
        joins = {groups[j["from_ref"][6:]]: j for j in current["join_transitions"]}
        self.assertEqual(len(joins), round(.7 * 11))
        self.assertNotIn("Кадр 6", joins)
        order = [joins.get(f"Кадр {n}") for n in range(1, 12)]
        self.assertFalse([a for a, b in zip(order, order[1:]) if a and b and a["type"] == b["type"] and a["type"] != "crossfade"])
        self.assertIn("стиків 11: план 8", result["report"][0])
        status, again = self.request(f"/api/projects/{project['id']}/ops", "POST", {"ops": [{"op": "transitions", "share": .7, "seed": 5}]})
        self.assertEqual(again["applied"], 0)   # the seams are already as the rule wants

    def test_summary_names_each_frame_and_its_problems(self):
        project = self.project(frames=3)
        clips = self.clips(project["id"])
        # frame 3 starts 0.5 s late (a gap) and its photo is a full-frame landscape shown smaller than the frame
        store.apply_action(project["id"], "batch", {"actions": [
            {"type": "move_clip", "payload": {"clip_id": clips["K003 фото"]["id"], "start": 8.5}},
            {"type": "update_clip", "payload": {"clip_id": clips["K002 фото"]["id"], "patch": {"keyframes": [{"time": 0, "x": .6, "scale": 1}, {"time": 3.9, "x": .4, "scale": 1}]}}}]})
        status, text = self.request(f"/api/projects/{project['id']}/summary?format=text")
        self.assertEqual(status, 200)
        self.assertIn("кадрів 3", text)
        self.assertIn("порожньо 0.50с до наступного", text)
        self.assertIn("відкритий край", text)
        status, data = self.request(f"/api/projects/{project['id']}/summary?frames=2-3&issues=1")
        self.assertEqual([row["n"] for row in data["frames"]], [2])
        self.assertEqual(data["fps"], 30)

    def test_status_and_exports_answer_in_one_request(self):
        project = self.project(frames=1)
        status, data = self.request("/api/studio/status")
        self.assertEqual((status, data["busy"]), (200, []))
        with patch.object(app, "project_jobs", return_value={"режисура": "running"}):
            status, data = self.request("/api/studio/status")
        self.assertTrue(any(line.startswith("режисура:") for line in data["busy"]))
        app.JOBS_ROOT.mkdir(parents=True, exist_ok=True)
        store.atomic_json(app.JOBS_ROOT / "aaaaaaaaaaaaaaaaaaaaaaaa.json", {"id": "aaaaaaaaaaaaaaaaaaaaaaaa", "project_id": project["id"], "status": "complete",
                                                                             "progress": 100, "output_path": "/x/Video.mp4", "error": None})
        status, data = self.request(f"/api/projects/{project['id']}/exports")
        self.assertEqual((status, data["active"], data["jobs"][0]["output_path"]), (200, None, "/x/Video.mp4"))

    def test_project_answers_reuse_readiness_until_something_it_reads_changes(self):
        project = self.project(frames=1)
        calls = []
        real = store.plan_readiness
        with patch.object(store, "plan_readiness", side_effect=lambda *a, **k: calls.append(1) or real(*a, **k)):
            for _ in range(3):
                self.request(f"/api/projects/{project['id']}")
            self.assertEqual(len(calls), 1)
            store.apply_action(project["id"], "rename_project", {"name": "Renamed"})
            self.request(f"/api/projects/{project['id']}")
            self.assertEqual(len(calls), 2)

    def test_index_stamps_scripts_with_their_content(self):
        status, page = self.request("/")
        self.assertEqual(status, 200)
        version = lambda html, name: html.split(f'/{name}?v=', 1)[1].split('"', 1)[0]
        stamp = version(page, "universal.js")
        self.assertRegex(stamp, r"^[0-9a-f]{12}$")
        self.assertEqual(stamp, app.hashlib.sha256((app.FRONTEND_ROOT / "universal.js").read_bytes()).hexdigest()[:12])
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "a.js").write_text("one")
            with patch.object(app, "FRONTEND_ROOT", Path(folder)):
                first = app.versioned_index(b'<script src="/a.js?v=manual"></script>').decode()
                (Path(folder) / "a.js").write_text("two!")
                second = app.versioned_index(b'<script src="/a.js?v=manual"></script>').decode()
        self.assertNotEqual(first, second)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_still_is_drawn_by_the_export_renderer(self):
        project = self.project(frames=2)
        status, result = self.request(f"/api/projects/{project['id']}/still", "POST", {"time": 5.0})
        self.assertEqual(status, 200, result)
        with Image.open(result["output"]) as image:
            self.assertEqual(image.size, (1920, 1080))
            self.assertGreater(image.getpixel((960, 540))[2], 90)   # the blue-grey photo of frame 2
        status, again = self.request(f"/api/projects/{project['id']}/still", "POST", {"time": 5.0})
        self.assertTrue(again["cached"])
        status, data = self.request(result["urls"][0])
        self.assertEqual(status, 200)


@unittest.skipUnless(shutil.which("node"), "node required")
class VoicePlayerTest(unittest.TestCase):
    def test_the_plan_player_finds_the_voice_by_its_bytes_when_the_plan_names_another_id(self):
        sys.path.insert(0, str(BACKEND.parent / "engine" / "tests"))
        import preview_js
        plan = {"timing": {"audio": {"asset_id": "fromapath0000000000a", "sha256": "abc"}}}
        cases = [
            (plan, {"assets": [{"id": "fromapath0000000000a"}], "audio_gain": {"other": .8}}),   # the plan's file is in the project
            (plan, {"assets": [{"id": "voice00000000000000b"}], "audio_gain": {"voice00000000000000b": .84}}),   # GORBUNOV-23
            (plan, {"assets": [], "audio_gain": {}}),                                              # nothing better known
            ({"timing": {}}, {"assets": [], "audio_gain": {"x": 1}}),                             # no voice yet
        ]
        found = preview_js.run(["voiceAssetId"], f"console.log(JSON.stringify({json.dumps(cases)}.map(([p,q])=>voiceAssetId(p,q))))")
        self.assertEqual(found, ["fromapath0000000000a", "voice00000000000000b", "fromapath0000000000a", None])


class WordTimingTest(unittest.TestCase):
    def test_digit_words_take_the_time_of_their_spoken_words(self):
        words = [{"text": t, "start": i * .5, "sentence": 1} for i, t in enumerate("питались полтора года по трём разным схемам".split())]
        self.assertEqual([(w["text"], w["start"]) for w in word_timing.digit_words([1], words, "ru")],
                         [("питались", 0), ("1,5", .5), ("года", 1), ("по", 1.5), ("3", 2), ("разным", 2.5), ("схемам", 3)])
        frame = {"number": 4, "sentences": ["Питались 1,5 года по 3 разным схемам."], "sentence_timings": [{"number": 1}]}
        tokens = word_timing.frame_tokens(frame, words)
        self.assertEqual(word_timing.find_phrase(tokens, "1,5 года"), [("1,5", .5), ("года", 1)])
        self.assertEqual(word_timing.word_time(tokens, "схем"), 3)
        with self.assertRaises(ValueError):
            word_timing.find_phrase(tokens, "два года")


if __name__ == "__main__":
    unittest.main()
