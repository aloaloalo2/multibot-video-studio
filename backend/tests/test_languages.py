import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import credentials  # noqa: E402
import languages  # noqa: E402
import store  # noqa: E402


def tone(path: Path, seconds: float) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}",
                    "-ar", "44100", str(path)], check=True)
    return path


class Vault:
    def __init__(self, keys):
        self.keys = keys

    def read(self, service):
        if service not in self.keys:
            raise RuntimeError("no key")
        return self.keys[service]

    def configured(self, service):
        return service in self.keys


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg")
class LanguagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.episode = base / "What If" / "05 Test"
        self.episode.mkdir(parents=True)
        self.studio = base / "studio"
        self.studio.mkdir()
        self.voice = tone(base / "voice.wav", 6)
        self.channel = base / "What If"
        self.project = {"id": "f" * 24, "name": "05 Test", "episode_path": str(self.episode), "channel_id": "c" * 16,
                        "assets": [{"id": "a" * 20, "path": str(self.voice), "kind": "audio"}]}
        plan = {"script": "Перше речення. Друге речення!\n\nТретій абзац тут.", "timing": {"audio": {"asset_id": "a" * 20}}}
        keys = {credentials.service_name(name): "k" for name in ("openrouter", "elevenlabs")}
        for item in (patch.object(store, "load_project", return_value=self.project),
                     patch.object(store, "load_project_plan", return_value=plan),
                     patch.object(store, "project_dir", return_value=self.studio),
                     patch.object(store, "resolve_asset", return_value=self.project["assets"][0]),
                     patch.object(store, "get_channel_folder", return_value=self.channel),
                     patch.object(credentials, "vault", return_value=Vault(keys))):
            item.start()
            self.addCleanup(item.stop)
        languages.ACTIVE.clear()
        self.pid = self.project["id"]

    def example(self, code, words="Це приклад голосу цією мовою для озвучки"):
        """An example of the voice in the language, dropped into the episode."""
        work = languages.work_dir(self.pid, code)
        work.mkdir(parents=True, exist_ok=True)
        tone(work / "own-voice.wav", 6)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(work / "own-voice.wav"), str(work / "own-voice.mp3")], check=True)
        (work / "own-voice.wav").unlink()
        (work / "own-voice.txt").write_text(words, encoding="utf-8")

    def wait(self):
        for _ in range(200):
            if not languages.ACTIVE:
                return languages.load_state(self.pid)["job"]
            time.sleep(0.05)
        self.fail("the job did not finish")

    def test_chunks_cut_at_paragraphs_and_sentences_and_keep_every_word(self):
        text = "Один. Два три.\n\n" + " ".join(f"Речення номер {n}." for n in range(60))
        pieces = languages.chunks(text, 200)
        self.assertTrue(all(len(piece) <= 200 for piece in pieces))
        self.assertEqual(" ".join(" ".join(pieces).split()), " ".join(text.split()))
        self.assertEqual(languages.chunks("Коротко.", 200), ["Коротко."])

    def test_price_counts_characters_or_bytes(self):
        self.assertEqual(languages.price("elevenlabs", "a" * 10000), 1.0)
        # Fish Audio bills UTF-8 bytes: Cyrillic is two a letter
        self.assertEqual(languages.price("fishaudio", "я" * 100000, "s1"), 3.0)
        self.assertEqual(languages.price("fishaudio", "a" * 100000, "s2.1-pro"), 1.5)
        self.assertEqual(languages.price("fishaudio", "a" * 100000), 0)          # S2.1 Pro Free by default
        self.assertIsNone(languages.price("fishaudio", "a" * 100000, "drama-3"))  # no price named by Fish

    def test_translate_sample_and_whole_voice_fitted_to_the_video(self):
        answers = iter(["First sentence. Second sentence!\n\nThird paragraph here.", "What If Test"])
        with patch.object(languages, "ask", side_effect=lambda messages, max_tokens=12000: (next(answers), 0.01)):
            languages.add(self.pid, "en")
            languages.start(self.pid, "translate", "en")
            job = self.wait()
        self.assertEqual(job["status"], "done", job)
        data = languages.overview(self.pid)
        item = data["items"][0]
        self.assertEqual((item["code"], item["title"]), ("en", "What If Test"))
        self.assertIn("First sentence.", item["text"])
        self.assertTrue((self.episode / "Мови" / "English" / "Текст English.txt").is_file())
        self.assertTrue((self.episode / "Мови" / "English" / "Заголовок English.txt").is_file())

        clones, spoken = [], []
        def request(url, data, headers, what):
            clones.append(url)
            return json.dumps({"voice_id": "v1"}).encode()
        def speak(provider, voice, text, target, before="", after=""):
            spoken.append(text)
            tone(target.with_suffix(".wav"), 4)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(target.with_suffix(".wav")), str(target)], check=True)
        self.example("en")
        with patch.object(languages, "request", side_effect=request), patch.object(languages, "speak", side_effect=speak):
            languages.start(self.pid, "sample", "en", "elevenlabs")
            self.assertEqual(self.wait()["status"], "done")
            with patch.object(languages, "VOICE_CHUNK", 25):
                languages.start(self.pid, "voice", "en", "elevenlabs")
                job = self.wait()
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(len(clones), 1)                      # the voice is cloned once and kept
        self.assertGreater(len(spoken), 2)
        voice = languages.load_state(self.pid)["languages"]["en"]["voice"]
        # 3+ parts of 4 s against a 6 s video: sped up by at most FIT_MAX, the rest stays longer
        self.assertEqual(voice["speed"], languages.FIT_MAX)
        self.assertGreater(voice["longer"], 0)
        self.assertTrue((self.episode / "Мови" / "English" / "Озвучка English.mp3").is_file())
        made = languages.voice_key(self.pid, "elevenlabs", "en")
        self.assertTrue(made.startswith("elevenlabs-episode"))
        self.assertTrue(languages.file_path(self.pid, "en", "sample-" + made).is_file())
        self.assertEqual(languages.overview(self.pid)["items"][0]["files"]["samples"], [made])
        # Fish's engine keeps a sample of its own: switching engines never plays another one's
        languages.set_provider(self.pid, "fishaudio", "s1")
        fish = languages.overview(self.pid)["items"][0]["voice_key"]
        self.assertTrue(fish.startswith("fishaudio-s1-lively-episode"))
        with self.assertRaises(store.StudioError):
            languages.file_path(self.pid, "en", "sample-" + fish)

    def test_a_short_voice_is_padded_to_the_video(self):
        work = languages.work_dir(self.pid, "de")
        work.mkdir(parents=True)
        (work / "text.txt").write_text("Kurz.", encoding="utf-8")
        self.example("de")
        def speak(provider, voice, text, target, before="", after=""):
            tone(target.with_suffix(".wav"), 2)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(target.with_suffix(".wav")), str(target)], check=True)
        with patch.object(languages, "speak", side_effect=speak), \
                patch.object(languages, "request", return_value=json.dumps({"voice_id": "v1"}).encode()):
            languages.start(self.pid, "voice", "de", "elevenlabs")
            self.assertEqual(self.wait()["status"], "done")
        voice = languages.load_state(self.pid)["languages"]["de"]["voice"]
        self.assertNotIn("speed", voice)
        self.assertAlmostEqual(voice["duration"], 6, delta=0.15)

    def test_start_refuses_without_key_text_or_a_second_job(self):
        with self.assertRaises(store.StudioError):
            languages.start(self.pid, "sample", "en", "fishaudio")          # no Fish key
        with self.assertRaises(store.StudioError):
            languages.start(self.pid, "voice", "en", "elevenlabs")         # nothing translated yet
        with self.assertRaises(store.StudioError):
            languages.start(self.pid, "translate", "xx")
        languages.ACTIVE.add(self.pid)
        with self.assertRaises(store.StudioError):
            languages.start(self.pid, "translate", "en")
        languages.ACTIVE.clear()

    def test_saved_text_drops_the_old_sample_and_remove_keeps_the_episode_copies(self):
        languages.add(self.pid, "es")
        work = languages.work_dir(self.pid, "es")
        work.mkdir(parents=True, exist_ok=True)
        (work / "sample.mp3").write_bytes(b"x")
        (work / "sample-fishaudio-s1.mp3").write_bytes(b"x")
        languages.save_text(self.pid, "es", "Hola.", "Título")
        self.assertFalse((work / "sample.mp3").exists())
        self.assertFalse((work / "sample-fishaudio-s1.mp3").exists())
        self.assertEqual(languages.overview(self.pid)["items"][0]["title"], "Título")
        languages.remove(self.pid, "es")
        self.assertFalse(work.exists())
        self.assertTrue((self.episode / "Мови" / "Español" / "Текст Español.txt").is_file())
        self.assertEqual(languages.overview(self.pid)["items"], [])

    def test_cancel_stops_a_translation_at_the_next_part_and_saves_nothing(self):
        import threading
        asked, release = threading.Event(), threading.Event()
        def ask(messages, max_tokens=12000):
            asked.set()
            release.wait(5)
            return "Translated text long enough to pass.", 0.0
        with patch.object(languages, "ask", side_effect=ask):
            languages.start(self.pid, "translate", "en")
            self.assertTrue(asked.wait(5))
            languages.cancel(self.pid)
            release.set()
            job = self.wait()
        self.assertEqual(job["status"], "cancelled")
        self.assertFalse((languages.work_dir(self.pid, "en") / "text.txt").exists())
        self.assertFalse(languages.CANCEL)

    def test_the_voice_is_found_when_the_plan_names_it_by_another_id(self):
        """Timings attached by a path name the voice by an id the project never had: the clip that starts the film is it."""
        other = tone(Path(self.tmp.name) / "music.wav", 2)
        project = {**self.project, "assets": [{"id": "b" * 20, "path": str(self.voice)}, {"id": "c" * 20, "path": str(other)}],
                   "tracks": [{"clips": [{"kind": "audio", "asset_id": "c" * 20, "start": 0, "duration": 2, "title": "Музика"},
                                         {"kind": "audio", "asset_id": "b" * 20, "start": 0, "duration": 6, "title": "voice"}]}]}
        def resolve(project, aid):
            found = next((asset for asset in project["assets"] if asset["id"] == aid), None)
            if not found:
                raise store.StudioError("Матеріал не знайдено", 404)
            return found
        with patch.object(store, "resolve_asset", side_effect=resolve), patch("audio_level.voice_gains", return_value={}):
            self.assertEqual(languages.voice_file(project, {"asset_id": "z" * 20}), self.voice)
            self.assertIsNone(languages.voice_file({**project, "tracks": []}, {"asset_id": "z" * 20}))

    def test_the_original_card_plays_the_episodes_voice(self):
        self.assertEqual(languages.original_file(self.pid), self.voice)
        data = languages.overview(self.pid)["source"]
        self.assertTrue(data["voice"])
        self.assertAlmostEqual(data["duration"], 6, delta=0.1)

    def test_the_originals_language_is_found_once(self):
        # the setUp script is Ukrainian; a recognition's language wins and is kept after
        self.assertEqual(languages.overview(self.pid)["source"]["language"], "uk")
        self.assertEqual(languages.load_state(self.pid)["original_language"], "uk")
        self.assertEqual(languages.guess_language("Привет, это тест"), "ru")
        self.assertEqual(languages.guess_language("Hello there"), "en")
        languages.update(self.pid, lambda data: data.pop("original_language"))
        (self.studio / "analysis" / "j1").mkdir(parents=True)
        store.atomic_json(self.studio / "analysis-state.json", {"job_id": "j1"})
        store.atomic_json(self.studio / "analysis" / "j1" / "result.json", {"engine": {"language": "de"}})
        self.assertEqual(languages.original_language(self.pid, self.project, "Перше речення."), "de")

    def test_fish_clones_inline_from_the_example_else_from_the_original(self):
        sent = []
        def request(url, data, headers, what):
            sent.append((url, data, headers))
            return b"\xff" * 2000
        with patch.object(languages, "key", return_value="k"):
            # no example yet: the start of the original voice, with the words said in it
            first = languages.voice_id(self.pid, "fishaudio", "uk")
            self.assertEqual(first["text"], "Перше речення. Друге речення! Третій абзац тут.")
            self.assertEqual(languages.voice_for(self.pid, "uk")["from"], "original")
            self.example("uk")
            with patch.object(languages, "request", side_effect=request):
                voice = languages.voice_id(self.pid, "fishaudio", "uk")
                languages.speak("fishaudio", voice, "Привіт.", self.studio / "out.mp3")
        self.assertEqual(voice["text"], "Це приклад голосу цією мовою для озвучки")
        self.assertTrue(sent[0][0].endswith("/model"))          # a saved model was tried first; refused here, inline stands
        url, body, headers = sent[-1]
        self.assertTrue(url.endswith("/v1/tts"))
        self.assertEqual((headers["Content-Type"], headers["model"]), ("application/msgpack", "s2.1-pro-free"))
        self.assertIn(voice["audio"][:200], body)
        self.assertIn(languages.msgpack("temperature") + languages.msgpack(0.9), body)     # «Живіше» by default
        self.assertNotIn("clones", languages.load_state(self.pid))
        languages.set_provider(self.pid, "fishaudio", style="exact")
        self.assertEqual(languages.voice_id(self.pid, "fishaudio", "uk")["style"], "exact")
        self.assertIn("-exact-", languages.voice_key(self.pid, "fishaudio", "uk"))
        with self.assertRaises(store.StudioError):
            languages.set_provider(self.pid, "fishaudio", style="nope")
        languages.set_provider(self.pid, "fishaudio", "s1")
        self.assertEqual(languages.voice_id(self.pid, "fishaudio", "uk")["engine"], "s1")
        with self.assertRaises(store.StudioError):
            languages.set_provider(self.pid, "fishaudio", "nope")

    def test_the_channels_example_serves_every_episode_and_an_episodes_own_wins(self):
        import io
        recording = tone(Path(self.tmp.name) / "native.wav", 9).read_bytes()
        words = [{"text": word} for word in "Hallo das ist ein Beispiel auf Deutsch".split()]
        with patch("speech.transcribe", return_value=(words, {})):
            data = languages.save_channel_voice("c" * 16, "de", io.BytesIO(recording), len(recording), "")
        self.assertEqual([item["code"] for item in data["voices"]], ["de"])
        self.assertTrue((self.channel / languages.CHANNEL_VOICES / "Deutsch.mp3").is_file())
        languages.add(self.pid, "de")
        item = languages.overview(self.pid)["items"][0]
        self.assertIsNotNone(item["channel_voice"])
        self.assertIsNone(item["own_voice"])
        self.assertEqual(languages.voice_for(self.pid, "de")["from"], "channel")
        self.assertEqual(languages.voice_id(self.pid, "fishaudio", "de")["text"], "Hallo das ist ein Beispiel auf Deutsch")
        self.example("de", "Eigene Worte dieser Folge hier")
        self.assertEqual(languages.voice_for(self.pid, "de")["from"], "episode")
        self.assertEqual(languages.voice_id(self.pid, "fishaudio", "de")["text"], "Eigene Worte dieser Folge hier")
        languages.remove_own_voice(self.pid, "de")
        self.assertEqual(languages.voice_for(self.pid, "de")["from"], "channel")
        languages.remove_channel_voice("c" * 16, "de")
        self.assertEqual(languages.voice_for(self.pid, "de")["from"], "original")
        self.assertIsNone(languages.voice_for(self.pid, "de", original=False))
        with patch("speech.transcribe", side_effect=RuntimeError("no model")), self.assertRaises(store.StudioError):
            languages.save_channel_voice("c" * 16, "de", io.BytesIO(recording), len(recording), "")   # no words, no passage

    def test_the_authors_recording_in_the_language_is_the_clones_reference(self):
        import io
        languages.add(self.pid, "en")
        languages.save_text(self.pid, "en", "First sentence here. Second one. " * 20, "T")
        item = languages.overview(self.pid)["items"][0]
        self.assertTrue(item["passage"].startswith("First sentence here."))
        self.assertLessEqual(len(item["passage"]), languages.PASSAGE_CHARS + 40)
        recording = tone(Path(self.tmp.name) / "me.wav", 8).read_bytes()
        work = languages.work_dir(self.pid, "en")
        (work / "sample-fishaudio-s2.1-pro-free.mp3").write_bytes(b"x")
        with patch("speech.transcribe", side_effect=RuntimeError("no model")):
            data = languages.save_own_voice(self.pid, "en", io.BytesIO(recording), len(recording), item["passage"])
        own = data["items"][0]["own_voice"]
        self.assertFalse(own["heard"])                   # no recognition: the passage stands, and the page says so
        self.assertAlmostEqual(own["duration"], 8, delta=0.2)
        self.assertFalse((work / "sample-fishaudio-s2.1-pro-free.mp3").exists())       # the old voice's sample goes
        fish = languages.voice_id(self.pid, "fishaudio", "en")
        self.assertEqual(fish["text"], item["passage"])
        self.assertEqual(fish["audio"], (work / "own-voice.mp3").read_bytes())
        self.assertEqual(languages.voice_for(self.pid, "de")["from"], "original")   # another language has no example of its own
        added = []
        def request(url, body, headers, what):
            added.append(url)
            return json.dumps({"voice_id": "mine-en"}).encode()
        with patch.object(languages, "request", side_effect=request):
            self.assertEqual(languages.voice_id(self.pid, "elevenlabs", "en"), "mine-en")
            self.assertEqual(languages.voice_id(self.pid, "elevenlabs", "en"), "mine-en")     # kept for the same example
        self.assertEqual(len(added), 1)
        with self.assertRaises(store.StudioError):
            languages.save_own_voice(self.pid, "en", io.BytesIO(b"x" * 10), 10, item["passage"])     # not audio
        short = tone(Path(self.tmp.name) / "short.wav", 2).read_bytes()
        with self.assertRaises(store.StudioError):
            languages.save_own_voice(self.pid, "en", io.BytesIO(short), len(short), item["passage"])
        languages.remove_own_voice(self.pid, "en")
        self.assertIsNone(languages.overview(self.pid)["items"][0]["own_voice"])

    def test_free_speech_in_the_language_is_recognised_for_the_reference(self):
        import io
        languages.add(self.pid, "uk")
        recording = tone(Path(self.tmp.name) / "me.wav", 8).read_bytes()
        words = [{"text": word} for word in "Привіт це я говорю українською мовою".split()]
        with patch("speech.transcribe", return_value=(words, {})) as recognise:
            languages.save_own_voice(self.pid, "uk", io.BytesIO(recording), len(recording), "уривок, який не читали")
        self.assertEqual(recognise.call_args.kwargs["language"], "uk")
        self.assertEqual(languages.own_voice(self.pid, "uk")["text"], "Привіт це я говорю українською мовою")
        self.assertTrue(languages.own_voice(self.pid, "uk")["heard"])
    def test_the_thumbnail_is_translated_with_the_authors_wishes(self):
        from PIL import Image
        import thumbnail_gen
        cover = self.studio / "preview" / "Превью.png"
        cover.parent.mkdir()
        Image.new("RGB", (64, 36)).save(cover)
        prompts = []
        class Codex:
            def __init__(self, command, cwd, **kwargs):
                self.cwd, self.returncode, self.pid = Path(cwd), 0, 0
            def communicate(self, prompt, timeout=None):
                prompts.append(prompt)
                Image.new("RGB", (64, 36), "red").save(self.cwd / "thumbnail-new.png")
                return "", ""
            def poll(self):
                return 0
        languages.add(self.pid, "de")
        with patch.object(thumbnail_gen, "CODEX", self.voice), patch.object(languages.subprocess, "Popen", Codex):
            languages.start(self.pid, "thumbnail", "de", wishes="напис жовтий")
            self.assertEqual(self.wait()["status"], "done")
        self.assertIn("into German", prompts[0])
        self.assertIn("напис жовтий", prompts[0])
        self.assertTrue(languages.file_path(self.pid, "de", "thumbnail").is_file())
        self.assertTrue((self.episode / "Мови" / "Deutsch" / "Прев'ю Deutsch.png").is_file())

    def test_lines_are_translated_and_voiced_in_time_with_the_original(self):
        plan = {"script": "x", "timing": {"audio": {"asset_id": "a" * 20}, "sentences": [
            {"text": "One.", "start": 0.2, "end": 1.0}, {"text": "Two.", "start": 1.1, "end": 1.8},     # run on: one line
            {"text": "Three.", "start": 3.0, "end": 3.8}, {"text": "Four.", "start": 4.5, "end": 5.4}]}}
        self.assertEqual([(line["start"], line["source"]) for line in languages.segments_of(plan)],
                         [(0.2, "One. Two."), (3.0, "Three."), (4.5, "Four.")])
        asked = []
        def ask(messages, max_tokens=12000):
            if not messages[1]["content"].startswith("["):
                return "Що якби", 0.0                            # the title
            asked.append(json.loads(messages[1]["content"]))
            if len(asked) == 1:
                return '["Раз. Два."]', 0.0                     # a wrong count is asked again
            return '["Раз. Два.", "Три.", "Чотири."]', 0.0
        with patch.object(languages.store, "load_project_plan", return_value=plan), patch.object(languages, "ask", side_effect=ask):
            languages.add(self.pid, "uk")
            languages.start(self.pid, "translate", "uk")
            job = self.wait()
        self.assertEqual(job["status"], "done", job.get("error"))
        self.assertEqual(asked[0][1]["seconds"], 1.1)          # 0.8 s said, room for up to 1.4 times that before the next
        self.assertEqual(asked[0][0]["max_chars"], int(asked[0][0]["seconds"] * 15))
        item = languages.overview(self.pid)["items"][0]
        self.assertEqual((item["text"].strip(), item["lines"]), ("Раз. Два.\nТри.\nЧотири.", 3))
        with self.assertRaises(store.StudioError):
            languages.save_text(self.pid, "uk", "Раз. Два. Три.\nЧотири.")          # two lines for three places
        # the second line is far too long for its place: sped up at most 1.25 times, and the third starts late
        lengths = iter([1.5, 3.0, 0.5])
        def speak(provider, voice, text, target, before="", after=""):
            tone(target.with_suffix(".wav"), next(lengths))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(target.with_suffix(".wav")), str(target)], check=True)
        self.example("uk")
        with patch.object(languages, "speak", side_effect=speak), \
                patch.object(languages, "request", return_value=json.dumps({"voice_id": "v1"}).encode()):
            languages.start(self.pid, "voice", "uk", "elevenlabs")
            job = self.wait()
        self.assertEqual(job["status"], "done", job.get("error"))
        voice = languages.load_state(self.pid)["languages"]["uk"]["voice"]
        self.assertTrue(voice["synced"])
        self.assertEqual(voice["fastest"], 1.25)
        self.assertAlmostEqual(voice["latest"], 0.95, delta=0.1)       # 3.0 + 3.0/1.25 = 5.4 against 4.5
        self.assertAlmostEqual(voice["duration"], 6, delta=0.15)       # the video's length: silence after the last line

    def test_a_saved_fish_model_is_made_once_per_example_and_used_by_id(self):
        self.example("ru")
        sent = []
        def request(url, data, headers, what):
            sent.append((url, data))
            return json.dumps({"_id": "model-1"}).encode() if url.endswith("/model") else b"\xff" * 2000
        with patch.object(languages, "key", return_value="k"), patch.object(languages, "request", side_effect=request):
            before = languages.voice_key(self.pid, "fishaudio", "ru")
            voice = languages.voice_id(self.pid, "fishaudio", "ru")
            languages.speak("fishaudio", voice, "Привет.", self.studio / "out.mp3")
            again = languages.voice_id(self.pid, "fishaudio", "ru")
        self.assertEqual((voice["model_id"], again["model_id"]), ("model-1", "model-1"))
        self.assertEqual(sum(url.endswith("/model") for url, _ in sent), 1)                 # made once, kept
        tts = [data for url, data in sent if url.endswith("/v1/tts")][0]
        self.assertIn(languages.msgpack("reference_id") + languages.msgpack("model-1"), tts)
        self.assertNotIn(languages.msgpack("references"), tts)
        self.assertNotEqual(languages.voice_key(self.pid, "fishaudio", "ru"), before)      # the model's samples are its own
        # a refusal is remembered for a while: no new attempt on every request
        self.example("de")
        refused = []
        def refuse(url, data, headers, what):
            refused.append(url)
            raise RuntimeError("Fish Audio (модель голосу): помилка 403")
        with patch.object(languages, "key", return_value="k"), patch.object(languages, "request", side_effect=refuse):
            self.assertIsNone(languages.voice_id(self.pid, "fishaudio", "de")["model_id"])
            self.assertIsNone(languages.voice_id(self.pid, "fishaudio", "de")["model_id"])
        self.assertEqual(len(refused), 1)

    def test_a_voicing_leaves_the_card_once_anything_that_made_it_changes(self):
        work = languages.work_dir(self.pid, "de")
        work.mkdir(parents=True)
        (work / "text.txt").write_text("Kurz.", encoding="utf-8")
        self.example("de")
        def speak(provider, voice, text, target, before="", after=""):
            tone(target.with_suffix(".wav"), 2)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(target.with_suffix(".wav")), str(target)], check=True)
        languages.add(self.pid, "de")
        with patch.object(languages, "speak", side_effect=speak), patch.object(languages, "key", return_value="k"), \
                patch.object(languages, "request", side_effect=RuntimeError("no model")):
            languages.start(self.pid, "voice", "de", "fishaudio")
            self.assertEqual(self.wait()["status"], "done")
        current = lambda: languages.overview(self.pid)["items"][0]["voice_current"]
        voice = languages.load_state(self.pid)["languages"]["de"]["voice"]
        self.assertEqual(voice["made_by"], "Fish Audio · S2.1 Pro Free · Живіше")
        self.assertTrue(current())
        languages.set_provider(self.pid, "fishaudio", "s1")
        self.assertFalse(current())                                   # another engine
        languages.set_provider(self.pid, "fishaudio", "s2.1-pro-free")
        self.assertTrue(current())
        languages.save_text(self.pid, "de", "Ganz anders.")
        self.assertFalse(current())                                   # other words

    def test_a_paid_fish_engine_without_credit_says_what_to_do(self):
        import io, urllib.error
        body = b'{"message": "Insufficient API credit for this model. For text-to-speech you can generate for free right now with the model s2.1-pro-free"}'
        refusal = urllib.error.HTTPError("https://api.fish.audio/v1/tts", 402, "Payment Required", {}, io.BytesIO(body))
        with patch("urllib.request.urlopen", side_effect=refusal), self.assertRaises(RuntimeError) as caught:
            languages.request("https://api.fish.audio/v1/tts", b"", {}, "Fish Audio")
        self.assertIn("S2.1 Pro Free", str(caught.exception))
        self.assertIn("баланс API", str(caught.exception))

    def test_a_job_left_running_by_a_restart_reads_failed(self):
        languages.update(self.pid, lambda data: data.__setitem__("job", {"status": "running"}))
        self.assertEqual(languages.load_state(self.pid)["job"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
