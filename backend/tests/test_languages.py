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
        self.project = {"id": "f" * 24, "name": "05 Test", "episode_path": str(self.episode),
                        "assets": [{"id": "a" * 20, "path": str(self.voice), "kind": "audio"}]}
        plan = {"script": "Перше речення. Друге речення!\n\nТретій абзац тут.", "timing": {"audio": {"asset_id": "a" * 20}}}
        keys = {credentials.service_name(name): "k" for name in ("openrouter", "elevenlabs")}
        for item in (patch.object(store, "load_project", return_value=self.project),
                     patch.object(store, "load_project_plan", return_value=plan),
                     patch.object(store, "project_dir", return_value=self.studio),
                     patch.object(store, "resolve_asset", return_value=self.project["assets"][0]),
                     patch.object(credentials, "vault", return_value=Vault(keys))):
            item.start()
            self.addCleanup(item.stop)
        languages.ACTIVE.clear()
        self.pid = self.project["id"]

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
        self.assertEqual(languages.price("fishaudio", "я" * 100000), 3.0)
        self.assertEqual(languages.price("fishaudio", "a" * 100000), 1.5)

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
        self.assertTrue(languages.file_path(self.pid, "en", "sample").is_file())

    def test_a_short_voice_is_padded_to_the_video(self):
        work = languages.work_dir(self.pid, "de")
        work.mkdir(parents=True)
        (work / "text.txt").write_text("Kurz.", encoding="utf-8")
        languages.update(self.pid, lambda data: data.setdefault("clones", {}).__setitem__("elevenlabs", "v1"))
        def speak(provider, voice, text, target, before="", after=""):
            tone(target.with_suffix(".wav"), 2)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(target.with_suffix(".wav")), str(target)], check=True)
        with patch.object(languages, "speak", side_effect=speak):
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
        languages.save_text(self.pid, "es", "Hola.", "Título")
        self.assertFalse((work / "sample.mp3").exists())
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

    def test_a_job_left_running_by_a_restart_reads_failed(self):
        languages.update(self.pid, lambda data: data.__setitem__("job", {"status": "running"}))
        self.assertEqual(languages.load_state(self.pid)["job"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
