import json
import io
import os
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
import eleven_api  # noqa: E402
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
        catalogue = patch.object(eleven_api, "catalog", return_value={"models": eleven_api.FALLBACK, "verified": False})
        catalogue.start()
        self.addCleanup(catalogue.stop)
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
                     patch.object(store, "DATA_ROOT", self.studio / "data"),
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

    def wait(self, slot=None):
        for _ in range(200):
            if slot and languages.job_key(self.pid, *slot.split("|")) not in languages.ACTIVE:
                return languages.load_state(self.pid)["jobs"][slot]
            if not slot and not languages.ACTIVE:
                return languages.load_state(self.pid)["job"]
            time.sleep(0.05)
        self.fail("the job did not finish")

    def test_direct_montage_language_source_uses_transcript_without_a_frame_plan(self):
        document = {"script": "First sentence. Second sentence.", "timing": {
            "status": "audio_synced", "audio": {"asset_id": "a" * 20, "duration": 6},
            "sentences": [{"start": 0, "end": 1, "text": "First sentence."},
                          {"start": 4, "end": 6, "text": "Second sentence."}]}}
        translated = ["Primera frase.", "Segunda frase."]
        with patch.object(store, "project_plan_mode", return_value="direct"), \
             patch.object(store, "load_project_source", return_value=document), \
             patch.object(store, "load_project_plan", side_effect=AssertionError("No frame plan required")), \
             patch.object(languages, "progress"), \
             patch.object(languages, "translate_lines", return_value=(translated, .01)) as initial, \
             patch.object(languages, "before_translate", return_value=(translated, 0)), \
             patch.object(languages, "save_translation") as publish, \
             patch.object(languages, "speak", side_effect=AssertionError("No paid speech")):
            source = languages.source(self.project)
            self.assertEqual(source["script"], document["script"])
            self.assertEqual(source["voice"], self.voice)
            languages._translate(self.pid, "es", {"translation_model": languages.DEFAULT_TRANSLATION_MODEL})
        self.assertEqual([x["source"] for x in initial.call_args.args[1]],
                         ["First sentence.", "Second sentence."])
        self.assertEqual(publish.call_args.args[4], "\n".join(translated))

    def test_thumbnail_gallery_only_lists_existing_translated_images_without_voicing(self):
        languages.update(self.pid,lambda d:d.update(languages={"uk":{},"es":{},"invalid":{}},original_language="en"))
        work=languages.work_dir(self.pid,"uk");work.mkdir(parents=True);(work/"thumbnail.png").write_bytes(b"png")
        with patch.object(languages,"voice_for",side_effect=AssertionError("gallery must not prepare voices")):
            result=languages.thumbnail_gallery(self.pid)
        self.assertEqual(result["original_language"],"en")
        self.assertEqual([x["code"] for x in result["translated_thumbnails"]],["uk"])

    def test_external_state_reader_preserves_work_owned_by_the_running_server(self):
        job={'status':'running','kind':'thumbnail','code':'pl','owner_pid':os.getpid()+1000}
        store.atomic_json(languages.state_path(self.pid),{'jobs':{'pl|thumbnail':job}})
        with patch.object(languages.os,'kill'):
            self.assertEqual(languages.load_state(self.pid)['jobs']['pl|thumbnail']['status'],'running')
            languages.update(self.pid,lambda d:d.update(other_setting=True))
        self.assertEqual(store.read_json(languages.state_path(self.pid))['jobs']['pl|thumbnail']['status'],'running')

    def test_completed_thumbnail_surviving_restart_can_be_recovered_without_generation(self):
        from PIL import Image
        import os
        work=languages.work_dir(self.pid,'pl');work.mkdir(parents=True)
        Image.new('RGB',(64,36),'red').save(work/'thumbnail.png')
        Image.new('RGB',(64,36),'blue').save(work/'thumbnail-new.png')
        (work/'thumbnail-prompt.txt').write_text('Add Poland flag')
        started=(work/'thumbnail-new.png').stat().st_mtime-1
        languages.save_state(self.pid,{'languages':{'pl':{}},'jobs':{'pl|thumbnail':{'kind':'thumbnail','code':'pl','status':'failed','started_at':started,'add_flag':True}}})
        with patch.object(languages,'overview',return_value={}),patch.object(languages.subprocess,'Popen',side_effect=AssertionError('no generation')):
            languages.recover_thumbnail(self.pid,'pl')
        job=languages.load_state(self.pid)['jobs']['pl|thumbnail']
        self.assertEqual((job['status'],job['version'],job['recovered']),('done',2,True))
        self.assertEqual(languages.file_path(self.pid,'pl','thumbnail').name,'v2.png')
        self.assertEqual([x['number'] for x in languages.thumbnail_gallery(self.pid)['translated_thumbnails']],[2,1])

    def test_chunks_cut_at_paragraphs_and_sentences_and_keep_every_word(self):
        text = "Один. Два три.\n\n" + " ".join(f"Речення номер {n}." for n in range(60))
        pieces = languages.chunks(text, 200)
        self.assertTrue(all(len(piece) <= 200 for piece in pieces))
        self.assertEqual(" ".join(" ".join(pieces).split()), " ".join(text.split()))
        self.assertEqual(languages.chunks("Коротко.", 200), ["Коротко."])

    def test_price_counts_characters_or_bytes(self):
        with patch.object(eleven_api, "model", return_value={"credits_per_char": .2}):
            self.assertEqual(languages.price("elevenlabs", "a" * 10000, "eleven_v4_turbo"), 2600)
            self.assertEqual(languages.price("elevenlabs", "я я", "eleven_v4_turbo"), .78)
        with patch.object(eleven_api, "model", return_value={}):
            self.assertIsNone(languages.price("elevenlabs", "a" * 10000, "unknown"))
        # Fish Audio bills UTF-8 bytes: Cyrillic is two a letter
        self.assertEqual(languages.price("fishaudio", "я" * 100000, "s2.1-pro"), 3.0)
        self.assertEqual(languages.price("fishaudio", "a" * 100000, "s2.1-pro"), 1.5)
        self.assertEqual(languages.price("fishaudio", "a" * 100000), 0)          # S2.1 Pro Free by default
        with patch.object(languages.time, "time", return_value=1794502800 - 60):
            self.assertEqual(languages.price("fishaudio", "я" * 100000, "drama-3"), 2.0)     # the launch price, $10/M bytes
        with patch.object(languages.time, "time", return_value=1794502800 + 60):
            self.assertEqual(languages.price("fishaudio", "я" * 100000, "drama-3"), 10.0)    # $50/M bytes after 12 November
        self.assertNotIn("s1", languages.FISH_ENGINES)

    def test_saved_translation_gets_number_comparison_without_rewriting_or_spending(self):
        source='In 2017 he gained 25 pounds.'
        translated='En dos mil diecisiete ganó veinticinco libras.'
        languages.update(self.pid,lambda d:d.update(languages={'es':{}},original_language='en'))
        work=languages.work_dir(self.pid,'es');work.mkdir(parents=True,exist_ok=True)
        text_path=work/'text.txt';text_path.write_text(translated,encoding='utf-8')
        before=text_path.read_bytes()
        with patch.object(store,'load_project_plan',return_value={'script':source}), \
             patch.object(languages,'ask',side_effect=AssertionError('No paid translation')), \
             patch.object(languages,'speak',side_effect=AssertionError('No paid speech')):
            item=languages.overview(self.pid)['items'][0]
        self.assertEqual(text_path.read_bytes(),before)
        self.assertEqual(item['text'],translated)
        self.assertEqual(item['chars'],sum(c.isalpha() for c in translated))
        self.assertEqual(item['display_chars'],sum(c.isalpha() for c in translated))
        compared=item['translation_length']['number_comparison']
        self.assertTrue(compared['available'])
        self.assertEqual(compared['source_chars'],sum(c.isalpha() for c in source))
        self.assertEqual(compared['translated_chars'],sum(c.isalpha() for c in 'En 2017 ganó 25 libras'))
        self.assertTrue(compared['punctuation_excluded'])
        self.assertEqual(item['prices']['fishaudio'],languages.price('fishaudio',translated,languages.fish_engine(self.pid)))

    def test_translate_sample_and_whole_voice_fitted_to_the_video(self):
        answers = iter(["First sentence. Next sentence! Third part here.", '{"ok":true,"ids":[0]}', "What If Test"])
        with patch.object(languages, "ask", side_effect=lambda messages, max_tokens=12000: (next(answers), 0.01)), \
             patch.object(languages.translation_budget, "number_refinement_plan", return_value={"available":False,"ids":[]}):
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
        self.assertFalse((self.episode / "Мови" / "English" / "Озвучка English.mp3").exists())
        self.assertTrue(languages.file_path(self.pid, "en", "voice").is_file())
        self.assertTrue((languages.work_dir(self.pid, "en") / "parts").is_dir())
        made = languages.voice_key(self.pid, "elevenlabs", "en")
        self.assertTrue(made.startswith("elevenlabs-eleven_v4-episode"))
        self.assertTrue(languages.file_path(self.pid, "en", "sample-" + made).is_file())
        self.assertEqual(languages.overview(self.pid)["items"][0]["files"]["samples"], [made])
        # Fish's engine keeps a sample of its own: switching engines never plays another one's
        languages.set_provider(self.pid, "fishaudio", "s2.1-pro")
        fish = languages.overview(self.pid)["items"][0]["voice_key"]
        self.assertTrue(fish.startswith("fishaudio-s2.1-pro-lively-episode"))
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
        languages.ACTIVE.add(languages.job_key(self.pid, "en", "voice"))
        with self.assertRaises(store.StudioError):
            languages.start(self.pid, "translate", "en")
        self.assertTrue(languages.busy(self.pid))
        self.assertFalse(languages.busy(self.pid, "en", "thumbnail"))
        self.assertFalse(languages.busy(self.pid, "de"))
        self.assertEqual(languages.active_projects(), {self.pid})
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
        report = languages.load_state(self.pid)["languages"]["es"]["translation_length"]
        self.assertEqual(report["translated_chars"], 4)
        self.assertTrue(report["advisory_only"])
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

    def test_cancel_drains_parallel_responses_into_the_resumable_draft(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        started,release=threading.Event(),threading.Event()
        lock=threading.Lock();count=0
        class Draft:
            data={}
            cost=0
            def save(self,**values):self.data.update(values)
            def charge(self,value):self.cost+=value
        draft=Draft();job={'key':self.pid+'|es|voice'}
        lines=[{'start':i*2,'end':i*2+1.5,'source':f'Line {i}.'} for i in range(60)]
        def part(code,items,before):
            nonlocal count
            with lock:
                count+=1
                if count==2:started.set()
            release.wait(5)
            return ['Texto traducido.']*len(items),.01
        with patch.object(languages,'translate_part',side_effect=part),patch.object(languages,'progress'):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future=executor.submit(languages.translate_lines,'es',lines,120,self.pid,job,draft)
                try:
                    self.assertTrue(started.wait(5))
                    languages.CANCEL.add(job['key']);release.set()
                    with self.assertRaises(languages.Stop):future.result(timeout=5)
                finally:
                    release.set();languages.CANCEL.discard(job['key'])
        self.assertEqual(sum(map(len,draft.data['initial_parts'].values())),60)
        self.assertAlmostEqual(draft.cost,.02)

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
        self.assertEqual(data["filename"], self.voice.name)
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
        languages.set_provider(self.pid, "fishaudio", "s2.1-pro")
        self.assertEqual(languages.voice_id(self.pid, "fishaudio", "uk")["engine"], "s2.1-pro")
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
        self.assertEqual(languages.voice_for(self.pid, "de")["from"], "original")
        self.assertIsNone(languages.voice_for(self.pid, "de", original=False))
        languages.remove_channel_voice("c" * 16, "de")
        self.assertEqual(languages.voice_for(self.pid, "de")["from"], "original")
        self.assertIsNone(languages.voice_for(self.pid, "de", original=False))
        with patch("speech.transcribe", side_effect=RuntimeError("no model")), self.assertRaises(store.StudioError):
            languages.save_channel_voice("c" * 16, "de", io.BytesIO(recording), len(recording), "")   # no words, no passage

    def test_a_loud_stereo_video_as_the_example_is_not_clipped(self):
        # user, 2 November 2026: «закинув мп4 ролика як приклад… озвучує голос аж перегруз»
        import io
        loud = Path(self.tmp.name) / "loud.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "aevalsrc=0.97*sin(2*PI*220*t)|0.97*sin(2*PI*220*t):s=48000:d=8", "-c:a", "aac", str(loud)], check=True)
        languages.add(self.pid, "en")
        data = loud.read_bytes()
        with patch("speech.transcribe", side_effect=RuntimeError("no model")):
            languages.save_own_voice(self.pid, "en", io.BytesIO(data), len(data), "A passage read aloud.")
        out = subprocess.run(["ffmpeg", "-i", str(languages.work_dir(self.pid, "en") / "own-voice.mp3"), "-af",
                              "astats=measure_overall=Peak_level:measure_perchannel=0", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        peak = float(out.split("Peak level dB:")[-1].split()[0])
        self.assertLess(peak, -1.0)

    def test_uploaded_voice_keeps_its_full_duration_and_the_content_after_45_seconds(self):
        import numpy as np
        source = self.studio / "long-example.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=45",
                        "-f", "lavfi", "-i", "sine=frequency=1000:duration=20", "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1",
                        str(source)], check=True)
        raw = source.read_bytes()
        work = self.studio / "full-example"
        with patch.object(languages, "heard", return_value="Це повний запис до самого кінця") as heard:
            languages.store_example(work, "own-voice", "uk", io.BytesIO(raw), len(raw), "")
        voice = languages.read_example(work, "own-voice", "episode")
        self.assertAlmostEqual(voice["duration"], 65, delta=0.15)
        self.assertAlmostEqual(heard.call_args.args[1], 65, delta=0.15)
        tail = subprocess.run(["ffmpeg", "-v", "error", "-ss", "60", "-i", str(voice["path"]), "-t", "2",
                               "-ar", "8000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
        samples = np.frombuffer(tail, dtype=np.float32)
        self.assertGreater(len(samples), 8000)
        peak = np.argmax(np.abs(np.fft.rfft(samples))) * 8000 / len(samples)
        self.assertAlmostEqual(peak, 1000, delta=3)

    def test_truncated_legacy_normalized_copy_is_restored_from_the_preserved_full_source(self):
        work = languages.work_dir(self.pid, "en")
        work.mkdir(parents=True)
        raw = tone(work / "own-voice.mp3", 65)
        copy = work / "own-voice-normalized.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(raw), "-t", "45", str(copy)], check=True)
        (work / "own-voice.txt").write_text("All words including the end.")
        store.atomic_json(work / "own-voice.json", {"heard": True, "example_level_version": 1,
                          "example_source_stamp": languages.example_source_stamp(raw), "example_normalized_copy": True,
                          "fish_model": "short-clone", "fish_stamp": copy.stat().st_mtime_ns})
        with patch.object(languages, "run", wraps=languages.run) as convert:
            first = languages.read_example(work, "own-voice", "episode")
            second = languages.read_example(work, "own-voice", "episode")
        self.assertAlmostEqual(first["duration"], 65, delta=0.15)
        self.assertIsNone(first["fish_model"])
        self.assertEqual(first["stamp"], second["stamp"])
        self.assertEqual(convert.call_count, 1)

    def test_full_v1_reference_keeps_its_saved_clone_without_reencoding(self):
        work = languages.work_dir(self.pid, "en")
        work.mkdir(parents=True)
        raw = tone(work / "own-voice.mp3", 8)
        (work / "own-voice.txt").write_text("All the words.")
        store.atomic_json(work / "own-voice.json", {"heard": True, "example_level_version": 1,
                          "example_source_stamp": languages.example_source_stamp(raw), "example_normalized_copy": False,
                          "fish_model": "keep-clone", "fish_stamp": raw.stat().st_mtime_ns})
        with patch.object(languages, "run") as convert:
            voice = languages.read_example(work, "own-voice", "episode")
        self.assertEqual(voice["fish_model"], "keep-clone")
        convert.assert_not_called()

    def test_legacy_clone_example_is_leveled_once_and_old_model_is_invalidated(self):
        work = languages.work_dir(self.pid, "en")
        work.mkdir(parents=True)
        raw = work / "own-voice.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "aevalsrc=0.97*sin(2*PI*220*t)|0.97*sin(2*PI*220*t):s=48000:d=8", str(raw)], check=True)
        original = raw.read_bytes()
        (work / "own-voice.txt").write_text("An example of the speaker.")
        store.atomic_json(work / "own-voice.json", {"heard": True, "fish_model": "old-loud-model", "fish_stamp": int(raw.stat().st_mtime)})
        with patch.object(languages, "run", wraps=languages.run) as convert:
            first = languages.own_voice(self.pid, "en")
            second = languages.own_voice(self.pid, "en")
            self.assertEqual(convert.call_count, 1)
        self.assertEqual(raw.read_bytes(), original)
        self.assertNotEqual(first["path"], raw)
        self.assertEqual(first["stamp"], second["stamp"])
        self.assertIsNone(first["fish_model"])
        self.assertTrue(first["heard"])
        from audio_level import measure
        with patch("audio_level.CACHE", work / "levels.json"):
            level = measure(first["path"])
        self.assertIsNotNone(level)
        self.assertLessEqual(level["peak"], -1.5)
        self.assertAlmostEqual(level["lufs"], -18, delta=1)
        languages.drop_example(work, "own-voice")
        self.assertFalse(first["path"].exists())

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
            data = languages.save_own_voice(self.pid, "en", io.BytesIO(recording), len(recording), item["passage"], "C:\\Samples\\Мій голос.wav")
        own = data["items"][0]["own_voice"]
        self.assertEqual(own["filename"], "Мій голос.wav")
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
            self.assertEqual(languages.voice_id(self.pid, "elevenlabs", "en")["id"], "mine-en")
            self.assertEqual(languages.voice_id(self.pid, "elevenlabs", "en")["id"], "mine-en")     # kept for the same example
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
        # the thumbnail is translated while the text of the same language is at work (user, 2 November 2026)
        languages.ACTIVE.add(languages.job_key(self.pid, "de", "voice"))
        with patch.object(thumbnail_gen, "CODEX", self.voice), patch.object(languages.subprocess, "Popen", Codex):
            languages.start(self.pid, "thumbnail", "de", wishes="напис жовтий")
            self.assertEqual(self.wait("de|thumbnail")["status"], "done")
        self.assertIn(languages.job_key(self.pid, "de", "voice"), languages.ACTIVE)
        languages.ACTIVE.clear()
        self.assertIn("into German", prompts[0])
        self.assertIn("напис жовтий", prompts[0])
        self.assertTrue(languages.file_path(self.pid, "de", "thumbnail").is_file())
        self.assertTrue((self.episode / "Мови" / "Deutsch" / "Прев'ю Deutsch.png").is_file())
        with patch.object(thumbnail_gen,"CODEX",self.voice),patch.object(languages.subprocess,"Popen",Codex):
            languages.start(self.pid,'thumbnail','pl',wishes='невеликий прапор на кепці',add_flag=True)
            self.assertEqual(self.wait('pl|thumbnail')['status'],'done')
        self.assertIn('translate every word written on it into Polish',prompts[-1])
        self.assertIn('national flag of Poland (PL)',prompts[-1])
        self.assertIn('clothing patch',prompts[-1])
        self.assertIn('small round flag badge',prompts[-1])
        self.assertNotIn('If there is no text on the picture, return it unchanged',prompts[-1])
        self.assertEqual(languages.load_state(self.pid)['languages']['pl']['thumbnail_settings_used']['country'],'PL')
        self.assertEqual(languages.thumbnail_options(self.pid),{'add_flag':True})
        self.assertEqual((languages.work_dir(self.pid,'pl')/'thumbnail-prompt.txt').read_text(),prompts[-1])

    def test_thumbnail_flag_choice_is_channel_scoped_and_shared_languages_never_inherit_a_flag(self):
        self.assertEqual(languages.thumbnail_options(self.pid),{'add_flag':False})
        languages.save_thumbnail_options(self.pid,True)
        with patch.object(languages,'cover',return_value=self.voice),patch.object(languages.threading,'Thread'):
            try:
                polish=languages.start(self.pid,'thumbnail','pl')
                ukrainian=languages.start(self.pid,'thumbnail','uk')
                spanish=languages.start(self.pid,'thumbnail','es')
                english=languages.start(self.pid,'thumbnail','en')
                self.assertTrue(polish['add_flag'])
                self.assertTrue(ukrainian['add_flag'])
                self.assertFalse(spanish['add_flag'])
                self.assertFalse(english['add_flag'])
                self.assertTrue(languages.thumbnail_options(self.pid)['add_flag'])
                with self.assertRaisesRegex(store.StudioError,'однозначного прапора'):
                    languages.start(self.pid,'thumbnail','de',add_flag=True)
            finally:languages.ACTIVE.clear()
        with patch.object(store,'load_project',return_value={**self.project,'id':'other'}):
            self.assertTrue(languages.thumbnail_options('other')['add_flag'])
        with patch.object(store,'load_project',return_value={**self.project,'id':'other','channel_id':'d'*16}):
            self.assertFalse(languages.thumbnail_options('other')['add_flag'])
        languages.save_thumbnail_options(self.pid,False)
        self.assertFalse(languages.thumbnail_options(self.pid)['add_flag'])
        with self.assertRaises(store.StudioError):languages.save_thumbnail_options(self.pid,'false')

    def test_thumbnail_flag_availability_is_returned_to_the_ui(self):
        languages.update(self.pid,lambda d:d.update(languages={'pl':{},'uk':{},'es':{},'en':{}}))
        languages.save_thumbnail_options(self.pid,True)
        data=languages.overview(self.pid)
        countries={x['code']:x['flag_country'] for x in data['items']}
        self.assertEqual(countries['pl']['code'],'PL')
        self.assertEqual(countries['uk']['code'],'UA')
        self.assertIsNone(countries['es'])
        self.assertIsNone(countries['en'])
        self.assertTrue(data['thumbnail_options']['add_flag'])

    def test_eleven_clone_has_channel_language_labels_and_survives_a_file_timestamp_change(self):
        self.example('es')
        with patch.object(languages,'request',return_value=b'{"voice_id":"existing-spanish"}') as send:
            first=languages.voice_id(self.pid,'elevenlabs','es')
            example=languages.own_voice(self.pid,'es')
            example['path'].touch()
            again=languages.voice_id(self.pid,'elevenlabs','es')
        self.assertEqual(first['id'],again['id'])
        self.assertEqual(send.call_count,1)
        fields=send.call_args.args[1].decode('utf-8',errors='replace')
        self.assertIn('What If · Іспанська',fields)
        self.assertIn('{"language": "es"}',fields)
        self.assertNotIn('VideoKey · 05 Test',fields)

    def test_reuploading_the_same_recording_in_another_project_reuses_its_clone(self):
        raw=self.voice.read_bytes()
        work=languages.work_dir(self.pid,'uk')
        with patch.object(languages,'heard',return_value='Той самий приклад голосу для різних випусків'), \
             patch.object(languages,'request',return_value=b'{"voice_id":"shared-uk"}') as upload:
            languages.store_example(work,'own-voice','uk',io.BytesIO(raw),len(raw),'','first.wav')
            first=languages.voice_id(self.pid,'elevenlabs','uk')
            original_bytes=languages.own_voice(self.pid,'uk')['path'].read_bytes()
            second={**self.project,'id':'e'*24,'name':'Another episode'}
            with patch.object(store,'load_project',return_value=second), \
                 patch.object(store,'project_dir',return_value=self.studio/'another-project'):
                languages.store_example(languages.work_dir(second['id'],'uk'),'own-voice','uk',
                                        io.BytesIO(raw),len(raw),'','renamed.wav')
                self.assertEqual(languages.own_voice(second['id'],'uk')['path'].read_bytes(),original_bytes)
                with patch.object(languages.eleven_voices,'clone_files',side_effect=AssertionError('must reuse before preparing')):
                    self.assertEqual(languages.voice_id(second['id'],'elevenlabs','uk')['id'],first['id'])
            upload.assert_called_once()

    def test_failed_reference_preparation_never_sends_a_clone_request(self):
        self.example('uk')
        with patch.object(languages.eleven_voices,'clone_files',side_effect=RuntimeError('Не вдалося підготувати приклад')), \
             patch.object(languages,'request') as upload:
            with self.assertRaisesRegex(RuntimeError,'Не вдалося підготувати'):
                languages.voice_id(self.pid,'elevenlabs','uk')
            upload.assert_not_called()
        self.assertTrue(languages.own_voice(self.pid,'uk')['path'].is_file())

    def test_lines_are_translated_and_voiced_in_time_with_the_original(self):
        plan = {"script": "One. Two. Three. Four.", "timing": {"audio": {"asset_id": "a" * 20}, "sentences": [
            {"text": "One.", "start": 0.2, "end": 1.0}, {"text": "Two.", "start": 1.1, "end": 1.8},     # run on: one line
            {"text": "Three.", "start": 3.0, "end": 3.8}, {"text": "Four.", "start": 4.5, "end": 5.4}]}}
        self.assertEqual([(line["start"], line["source"]) for line in languages.segments_of(plan)],
                         [(0.2, "One. Two."), (3.0, "Three."), (4.5, "Four.")])
        asked = []
        def ask(messages, max_tokens=12000):
            if 'Independently compare EVERY translation' in messages[0]['content']:
                return '{"ok":true,"ids":[0,1,2]}', 0.0
            if not messages[1]["content"].startswith("["):
                return "Що якби", 0.0                            # the title
            asked.append(json.loads(messages[1]["content"]))
            if len(asked) == 1:
                return '["Раз. Два."]', 0.0                     # a wrong count is asked again
            return '["Раз. Два.", "Три.", "Чотири."]', 0.0
        with patch.object(languages.store, "load_project_plan", return_value=plan), patch.object(languages, "ask", side_effect=ask), \
             patch.object(languages.translation_budget, "number_refinement_plan", return_value={"available":False,"ids":[]}):
            languages.add(self.pid, "uk")
            languages.start(self.pid, "translate", "uk")
            job = self.wait()
        self.assertEqual(job["status"], "done", job.get("error"))
        self.assertEqual(asked[0][1]["seconds"], 1.1)          # 0.8 s said, room for up to 1.4 times that before the next
        self.assertNotIn("max_chars", asked[0][0])  # timing is context; character count never limits natural translation
        item = languages.overview(self.pid)["items"][0]
        self.assertEqual((item["text"].strip(), item["lines"]), ("Раз. Два.\nТри.\nЧотири.", 3))
        with self.assertRaises(store.StudioError):
            languages.save_text(self.pid, "uk", "Раз. Два. Три.\nЧотири.")          # two lines for three places
        # Even an overlong phrase gets one paid take. Local fitting stays bounded and reports the issue.
        lengths, calls = iter([1.5, 3.0, 0.5]), []
        def speak(provider, voice, text, target, before="", after="", speed=1.0):
            calls.append((text, speed))
            tone(target.with_suffix(".wav"), next(lengths))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(target.with_suffix(".wav")), str(target)], check=True)
        self.example("uk")
        languages.update(self.pid, lambda data: data.update(eleven_engine="eleven_flash_v2_5"))  # historical model with service-side speed
        with patch.object(eleven_api, "model", return_value={"name": "Legacy", "languages": [],"credits_per_char":.2}), \
                patch.object(languages, "speak", side_effect=speak), patch.object(languages, "shorten", return_value="Три!") as shorter, \
                patch.object(languages, "request", return_value=json.dumps({"voice_id": "v1"}).encode()):
            languages.start(self.pid, "voice", "uk", "elevenlabs")
            job = self.wait()
        self.assertEqual(job["status"], "done", job.get("error"))
        shorter.assert_not_called()
        self.assertEqual(calls, [("Раз. Два.", 1.0), ("Три.", 1.0), ("Чотири.", 1.0)])
        voice = languages.load_state(self.pid)["languages"]["uk"]["voice"]
        self.assertTrue(voice["synced"])
        self.assertEqual((voice["shortened"], voice["quicker"], voice["fastest"]), (0, 1.0, 1.15))
        self.assertGreater(voice["latest"],0)
        self.assertGreater(len(voice["timing_issues"]),0)
        self.assertFalse(voice["paid_timing_retries"])
        self.assertEqual(languages.line_texts(self.pid, "uk"), ["Раз. Два.", "Три.", "Чотири."])
        requests=store.read_json(languages.work_dir(self.pid,"uk")/"parts/requests.json",[])
        self.assertEqual(len(requests),3)
        self.assertTrue(all(item["status"]=="complete" and item["selected"] for item in requests))
        self.assertEqual([x["text"] for x in requests],["Раз. Два.", "Три.", "Чотири."])
        self.assertEqual(job["takes"],3)
        self.assertEqual(job["cost"],4.0)
        self.assertTrue(job["cost_estimated"])
        self.assertTrue(languages.overview(self.pid)["items"][0]["voice_current"])
        self.assertTrue(voice['review'])
        for a,b in zip(voice['review'],voice['review'][1:]):self.assertLessEqual(a['start'],b['start'])
        with patch.object(languages,'speak',side_effect=AssertionError('refit must use saved audio')), \
                patch.object(languages,'request',side_effect=AssertionError('no network during refit')), \
                patch.object(languages,'ask',side_effect=AssertionError('no translation during refit')):
            languages.start(self.pid,'refit','uk')
            repaired=self.wait()
        self.assertEqual(repaired['status'],'done',repaired.get('error'))
        self.assertEqual((repaired['cost'],repaired['takes']),(0,0))
        work=languages.work_dir(self.pid,'uk')
        self.assertTrue(list((work/'recovery').rglob('voice.mp3')))

    def test_fish_engines_keep_sampling_separate_and_drama_starts_at_api_defaults(self):
        languages.update(self.pid, lambda data: data.update(fish_engine="s2.1-pro-free", fish_style="lively"))
        self.assertEqual(languages.fish_style(self.pid), "lively")
        languages.set_provider(self.pid, "fishaudio", engine="drama-3")
        self.assertEqual(languages.fish_style(self.pid), "normal")
        sent = []
        with patch.object(languages, "key", return_value="k"), patch.object(languages, "request", side_effect=lambda url, body, headers, what: sent.append((body, headers)) or b"x" * 2000):
            languages.speak("fishaudio", {"model_id": "saved-voice", "engine": languages.fish_engine(self.pid),
                                        "style": languages.fish_style(self.pid)}, "Привіт.", self.studio / "test.mp3")
        body, headers = sent[0]
        self.assertEqual(headers["model"], "drama-3")
        for name in ("temperature", "top_p"):
            self.assertIn(languages.msgpack(name) + languages.msgpack(0.7), body)
        self.assertIn(languages.msgpack("reference_id") + languages.msgpack("saved-voice"), body)
        with patch.object(languages, "key", return_value="k"), patch.object(languages, "request", side_effect=lambda url, body, headers, what: sent.append((body, headers)) or b"x" * 2000):
            languages.speak("fishaudio", {"model_id": "saved-voice", "engine": "drama-3"}, "Привіт.", self.studio / "test.mp3")
        for name in ("temperature", "top_p"):
            self.assertIn(languages.msgpack(name) + languages.msgpack(0.7), sent[-1][0])
        languages.set_provider(self.pid, "fishaudio", style="exact")
        languages.set_provider(self.pid, "fishaudio", engine="s2.1-pro-free")
        self.assertEqual(languages.fish_style(self.pid), "lively")
        languages.set_provider(self.pid, "fishaudio", engine="drama-3")
        self.assertEqual(languages.fish_style(self.pid), "exact")

    def test_legacy_drama_sampling_survives_migration_and_a_new_drama_uses_normal(self):
        languages.update(self.pid, lambda data: data.update(fish_engine="drama-3"))
        self.assertEqual(languages.fish_style(self.pid), "normal")
        languages.update(self.pid, lambda data: data.update(fish_style="exact"))
        self.assertEqual(languages.fish_style(self.pid), "exact")
        languages.set_provider(self.pid, "fishaudio", engine="s2.1-pro-free")
        self.assertEqual(languages.fish_style(self.pid), "lively")
        languages.set_provider(self.pid, "fishaudio", engine="drama-3")
        self.assertEqual(languages.fish_style(self.pid), "exact")

    def test_eleven_model_selection_has_its_own_cache_and_keeps_fish_settings(self):
        languages.add(self.pid, "ru")
        languages.set_provider(self.pid, "fishaudio", "drama-3", "normal")
        before = languages.voice_key(self.pid, "fishaudio", "ru")
        data = languages.set_provider(self.pid, "elevenlabs", "eleven_v4")
        self.assertEqual(data["provider"], "elevenlabs")
        first = languages.voice_key(self.pid, "elevenlabs", "ru")
        languages.set_provider(self.pid, "elevenlabs", "eleven_v4_turbo")
        self.assertNotEqual(languages.voice_key(self.pid, "elevenlabs", "ru"), first)
        self.assertEqual(languages.voice_key(self.pid, "fishaudio", "ru"), before)
        self.assertEqual(languages.fish_style(self.pid), "normal")
        self.assertEqual(languages.fish_engine(self.pid), "drama-3")
        with self.assertRaises(store.StudioError):
            languages.set_provider(self.pid, "elevenlabs", "not-a-model")
        with self.assertRaises(store.StudioError):
            languages.file_path(self.pid, "ru", "sample-../../secret")

    def test_unsupported_eleven_language_is_refused_before_cloning_or_spending(self):
        with patch.object(eleven_api, "model", return_value={"name": "English only", "languages": ["en"]}), \
                patch.object(languages, "request") as request:
            with self.assertRaisesRegex(store.StudioError, "не підтримує"):
                languages.start(self.pid, "sample", "uk", "elevenlabs")
            request.assert_not_called()

    def test_sample_estimates_match_the_selected_sentence_count_and_model(self):
        languages.add(self.pid, "ru")
        text = " ".join(f"Это предложение номер {n}." for n in range(1, 22))
        work = languages.work_dir(self.pid, "ru")
        work.mkdir(parents=True, exist_ok=True)
        (work / "text.txt").write_text(text)
        with patch.object(eleven_api, "model", return_value={"credits_per_char": 0.5}):
            item = next(x for x in languages.overview(self.pid)["items"] if x["code"] == "ru")
        for count in (3, 5, 10, 20):
            self.assertEqual(item["sample_prices"]["elevenlabs"][str(count)], round(len(languages.sample_text(text, count)) * .5, 2))
        self.assertLess(item["sample_prices"]["elevenlabs"]["3"], item["sample_prices"]["elevenlabs"]["20"])

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
        languages.set_provider(self.pid, "fishaudio", "s2.1-pro")
        self.assertFalse(current())                                   # another engine
        languages.set_provider(self.pid, "fishaudio", "s2.1-pro-free")
        self.assertTrue(current())
        languages.save_text(self.pid, "de", "Ganz anders.")
        self.assertFalse(current())                                   # other words

    def test_the_sample_takes_as_many_sentences_as_chosen(self):
        text = "Один. Два! Три?\nЧотири. П'ять. Шість."
        self.assertEqual(languages.sample_text(text, 3), "Один. Два! Три?")
        self.assertEqual(languages.sample_text(text, 5), "Один. Два! Три? Чотири. П'ять.")
        self.assertEqual(languages.sample_text(text, 20), "Один. Два! Три? Чотири. П'ять. Шість.")

    def test_sample_takes_are_reused_by_full_narration_and_the_estimate(self):
        code='en';self.example(code)
        work=languages.work_dir(self.pid,code)
        lines=['The first sentence is here.','This is the second sentence.','We now hear the third sentence.','Here is the final sentence.']
        (work/'text.txt').write_text('\n'.join(lines))
        segments=[{'source':line,'start':n*1.5,'end':n*1.5+1} for n,line in enumerate(lines)]
        spoken=[]
        def speak(provider,voice,text,target,*args,**kwargs):
            spoken.append(text);tone(target,.5)
        with patch.object(languages,'synced_segments',return_value=segments),patch.object(languages,'progress'), \
             patch.object(languages,'speak',side_effect=speak),patch.object(languages,'voice_id',return_value={'id':'existing'}) as clone, \
             patch.object(eleven_api,'model',return_value={'credits_per_char':.5}):
            sample_job={'sentences':3};languages.sample(self.pid,code,'elevenlabs',sample_job)
            self.assertEqual(spoken,lines[:3]);self.assertEqual(sample_job['takes'],3)
            estimate=languages.voice_estimate(self.pid,code,'elevenlabs','\n'.join(lines))
            self.assertEqual((estimate['reused'],estimate['generate']),(3,1))
            self.assertEqual(languages.sample_prices(self.pid,code,'elevenlabs','\n'.join(lines))['3'],0)
            clone.reset_mock();spoken.clear()
            repeated={'sentences':3};languages.sample(self.pid,code,'elevenlabs',repeated)
            self.assertEqual((repeated['takes'],repeated['reused'],repeated['cost']),(0,3,0))
            clone.assert_not_called();self.assertEqual(spoken,[])
            job={};languages.whole_synced(self.pid,code,'elevenlabs',job,segments)
            self.assertEqual(spoken,[lines[3]])
            self.assertEqual((job['takes'],job['reused']),(1,3))
            self.assertTrue((work/'voice.mp3').is_file())

    def test_interrupted_sample_preserves_completed_paid_phrases(self):
        code='en';self.example(code);work=languages.work_dir(self.pid,code)
        lines=['Here is the first sentence.','This is the second sentence.','Here is the final sentence.']
        (work/'text.txt').write_text('\n'.join(lines))
        def speak(provider,voice,text,target,*args):
            if text==lines[1]:raise RuntimeError('connection lost')
            tone(target,.5)
        with patch.object(languages,'synced_segments',return_value=[{}]*3),patch.object(languages,'progress'), \
             patch.object(languages,'voice_id',return_value={'id':'existing'}),patch.object(languages,'speak',side_effect=speak):
            with self.assertRaisesRegex(RuntimeError,'connection lost'):
                languages.sample(self.pid,code,'elevenlabs',{'sentences':3})
            estimate=languages.voice_estimate(self.pid,code,'elevenlabs','\n'.join(lines))
            self.assertEqual((estimate['reused'],estimate['generate']),(1,2))

    def test_shorter_sample_reuses_whole_cached_phrase_without_paid_speech(self):
        code='en';self.example(code);work=languages.work_dir(self.pid,code)
        lines=['This is the first sentence. Here is the second sentence. We hear the third sentence.',
               'This is the fourth sentence. Here is the fifth sentence. This last sentence finishes the phrase.']
        text='\n'.join(lines);(work/'text.txt').write_text(text)
        identity,_=languages.voice_cache_context(self.pid,code,'elevenlabs')
        for n,line in enumerate(lines):
            languages.voice_cache.remember(work,identity,line,tone(work/f'paid-{n}.mp3',1))
        with patch.object(languages,'synced_segments',return_value=[{}]*2),patch.object(languages,'progress'), \
             patch.object(languages,'speak',side_effect=AssertionError('Must not buy an already cached phrase')), \
             patch.object(languages,'voice_id',side_effect=AssertionError('No clone needed')), \
             patch.object(eleven_api,'model',return_value={'credits_per_char':.5}):
            options=languages.sample_options(self.pid,code,'elevenlabs',text)
            self.assertEqual([option['price'] for option in options.values()],[0,0,0,0])
            self.assertEqual(options['5']['sentences'],6)
            job={'sentences':5};languages.sample(self.pid,code,'elevenlabs',job)
        self.assertEqual((job['takes'],job['reused'],job['cost']),(0,2,0))
        sample_key=languages.voice_key(self.pid,'elevenlabs',code)
        self.assertTrue((work/f'sample-{sample_key}.mp3').is_file())
        meta=languages.load_state(self.pid)['languages'][code]['samples'][sample_key]
        self.assertEqual((meta['requested_sentences'],meta['sentences']),(5,6))
        self.assertGreater(meta['duration'],1.9)
        request=next((work/'sample-parts').glob('*/request.json'))
        self.assertEqual(store.read_json(request,{})['texts'],lines)

    def test_sample_keeps_exact_cached_prefix_and_never_buys_extra_sentences(self):
        code='en';self.example(code);work=languages.work_dir(self.pid,code)
        lines=['First sentence. Second sentence. Third sentence.',
               'Fourth sentence. Fifth sentence. Sixth sentence.']
        text='\n'.join(lines);(work/'text.txt').write_text(text)
        prefix='Fourth sentence. Fifth sentence.'
        with patch.object(languages,'synced_segments',return_value=[{}]*2):
            # No cached full unit: request only the selected words.
            self.assertEqual(languages.sample_pieces(self.pid,code,text,5,{}),[lines[0],prefix])
            # A cached exact prefix wins even when a longer take is also available.
            self.assertEqual(languages.sample_pieces(self.pid,code,text,5,{prefix:Path('short'),lines[1]:Path('long')}),[lines[0],prefix])

    def test_a_paid_fish_engine_without_credit_says_what_to_do(self):
        import io, urllib.error
        body = b'{"message": "Insufficient API credit for this model. For text-to-speech you can generate for free right now with the model s2.1-pro-free"}'
        refusal = urllib.error.HTTPError("https://api.fish.audio/v1/tts", 402, "Payment Required", {}, io.BytesIO(body))
        with patch("urllib.request.urlopen", side_effect=refusal), self.assertRaises(RuntimeError) as caught:
            languages.request("https://api.fish.audio/v1/tts", b"", {}, "Fish Audio")
        self.assertIn("S2.1 Pro Free", str(caught.exception))
        self.assertIn("баланс API", str(caught.exception))

    def test_lines_lost_by_the_translator_are_asked_again_and_then_alone(self):
        # user, 2 November 2026: «Перекладач двічі повернув не ту кількість фраз»
        self.assertEqual(languages.line_answers('{"1": "Раз", "3": "Три"}', [1, 2, 3]), {1: "Раз", 3: "Три"})
        self.assertEqual(languages.line_answers('[{"id": 2, "text": "Два"}]', [1, 2]), {2: "Два"})
        self.assertEqual(languages.line_answers('["Раз", "Два"]', [1, 2]), {1: "Раз", 2: "Два"})
        self.assertEqual(languages.line_answers('["Раз. Два"]', [1, 2]), {})
        lines = [{"start": i * 2.0, "end": i * 2.0 + 1.5, "source": f"Line {i}."} for i in range(4)]
        asked = []
        def ask(messages, max_tokens=12000):
            asked.append(messages[1]["content"])
            if len(asked) == 1:
                return '{"1": "Один.", "2": "Два і три.", "4": "Чотири."}', 0.0      # line 3 merged into line 2
            if len(asked) == 2:
                return '{}', 0.0                                                 # still missing
            return "Три.", 0.0                                                   # alone
        job = {"key": "x"}
        with patch.object(languages, "ask", side_effect=ask), patch.object(languages, "progress"):
            texts, _ = languages.translate_lines("uk", lines, 8.0, self.pid, job)
        self.assertEqual(texts, ["Один.", "Два і три.", "Три.", "Чотири."])
        self.assertEqual([item["id"] for item in json.loads(asked[1])], [3])
        self.assertEqual(asked[2], "Line 2.")

    def test_minimax_returns_empty_reply_for_smaller_batches_without_escalating_tokens(self):
        sent = []
        replies = iter([
            {"choices": [{"message": {"content": ""}, "finish_reason": "length"}], "usage": {"cost": .001}},
            {"choices": [{"message": {"content": "Привіт"}, "finish_reason": "stop"}], "usage": {"cost": .002}}])
        def request(url, body, headers, what):
            sent.append(json.loads(body))
            return json.dumps(next(replies)).encode()
        with patch.object(languages, "request", side_effect=request):
            text, cost = languages.ask([{"role": "user", "content": "Hi"}], 600)
        self.assertEqual((text, round(cost,4)), ("", .001))
        self.assertTrue(all(call['model']==languages.DEFAULT_TRANSLATION_MODEL for call in sent))
        self.assertTrue(all(call['reasoning']=={'effort':'low'} for call in sent))
        self.assertEqual([call['max_tokens'] for call in sent], [4096])

    def test_cancel_request_survives_worker_updates_until_a_new_run(self):
        job={'slot':'es|voice','key':self.pid+'|es|voice','code':'es','kind':'translate',
             'started_at':100,'status':'running','stage':'Перекладаємо'}
        languages.put_job(self.pid,dict(job))
        languages.CANCEL.add(job['key'])
        try:
            languages.put_job(self.pid,dict(job,progress=50))
            saved=languages.load_state(self.pid)['jobs'][job['slot']]
            self.assertTrue(saved['cancel_requested'])
            self.assertIn('Скасовуємо',saved['stage'])
        finally:
            languages.CANCEL.discard(job['key'])
        languages.put_job(self.pid,dict(job,status='cancelled'))
        self.assertTrue(languages.load_state(self.pid)['jobs'][job['slot']]['cancel_requested'])
        languages.put_job(self.pid,dict(job,started_at=101))
        self.assertFalse(languages.load_state(self.pid)['jobs'][job['slot']].get('cancel_requested'))

    def test_parts_of_a_long_text_are_translated_side_by_side_in_order(self):
        names = [chr(0x430 + i % 32) * (1 + i // 32) for i in range(70)]       # no digits: no speech fix asked
        lines = [{"start": i * 2.0, "end": i * 2.0 + 1.5, "source": f"Line {name}."} for i, name in enumerate(names)]
        def ask(messages, max_tokens=12000):
            items = json.loads(messages[1]["content"])
            time.sleep(0.05)
            return json.dumps({str(item["id"]): item["text"].replace("Line", "Рядок") for item in items}), 0.01
        with patch.object(languages, "ask", side_effect=ask), patch.object(languages, "progress"):
            texts, cost = languages.translate_lines("uk", lines, 140.0, self.pid, {"key": "x"})
        self.assertEqual(texts, [f"Рядок {name}." for name in names])
        self.assertAlmostEqual(cost, 0.03)

    def test_the_translation_is_written_to_be_heard(self):
        # user, 2 November 2026: «1999-го — такі речення погані… краще слова тисяча дев'ятсот…»
        self.assertIn("1999 року", languages.translator("uk"))
        self.assertIn("in words", languages.translator("uk"))
        asked = []
        def ask(messages, max_tokens=12000):
            asked.append(json.loads(messages[1]["content"]))
            return json.dumps(["У тисяча дев'ятсот дев'яносто дев'ятому році все змінилось."]), 0.01
        with patch.object(languages, "ask", side_effect=ask):
            texts, cost = languages.speakable("uk", ["Все гаразд.", "У 1999-го все змінилось.", "Так."])
        self.assertEqual(asked, [["У 1999-го все змінилось."]])       # only the line with digits goes back
        self.assertEqual(texts[1], "У тисяча дев'ятсот дев'яносто дев'ятому році все змінилось.")
        self.assertEqual((texts[0], texts[2], cost), ("Все гаразд.", "Так.", 0.01))
        with patch.object(languages, "ask", side_effect=AssertionError):
            self.assertEqual(languages.speakable("uk", ["Без цифр."]), (["Без цифр."], 0.0))
        with patch.object(languages, "ask", return_value=("не масив", 0.01)):
            self.assertEqual(languages.speakable("uk", ["20% людей"])[0], ["20% людей"])

    def test_a_job_left_running_by_a_restart_reads_failed(self):
        languages.update(self.pid, lambda data: data.__setitem__("job", {"status": "running"}))
        self.assertEqual(languages.load_state(self.pid)["job"]["status"], "failed")

    def test_wrong_language_never_reaches_clone_or_paid_speech(self):
        work=languages.work_dir(self.pid,'es');work.mkdir(parents=True)
        bad='Во время грозы мы ищем укрытие внутри закрытого здания, чтобы защититься от удара молнии.'
        (work/'text.txt').write_text(bad)
        with patch.object(languages,'voice_for',return_value={'path':self.voice}), patch.object(languages,'voice_id') as clone, patch.object(languages,'speak') as speech:
            for kind in ['sample','voice']:
                with self.assertRaisesRegex(store.StudioError,'іншу мову'):
                    languages.start(self.pid,kind,'es','elevenlabs')
            with self.assertRaises(store.StudioError):
                languages.sample(self.pid,'es','elevenlabs',{})
            with self.assertRaises(store.StudioError):
                languages.whole_synced(self.pid,'es','elevenlabs',{},[{'start':0,'end':3}])
            clone.assert_not_called();speech.assert_not_called()
        self.assertEqual((work/'text.txt').read_text(),bad)

    def test_correcting_text_does_not_hide_wrong_language_in_paid_takes(self):
        work=languages.work_dir(self.pid,'es');work.mkdir(parents=True)
        (work/'text.txt').write_text('Durante la tormenta buscamos refugio dentro de un edificio cerrado para protegernos de los rayos.')
        store.atomic_json(work/'parts/manifest.json',[{'text':'Во время грозы мы ищем укрытие внутри закрытого здания, чтобы защититься от удара молнии.','start':12,'end':17}])
        self.assertEqual(languages.translation_check(self.pid,'es')['state'],'ok')
        self.assertEqual(languages.voice_language_check(self.pid,'es')['state'],'blocked')
        self.assertFalse(languages.voice_current(self.pid,'es',{}))
        with self.assertRaisesRegex(store.StudioError,'іншу мову'):
            languages.language_mix.snapshot(self.project,'es')

    def test_foreign_model_batch_is_retried_before_it_can_be_saved(self):
        correct='Durante la tormenta buscamos refugio dentro de un edificio cerrado para protegernos de los rayos.'
        wrong='Во время грозы мы ищем укрытие внутри закрытого здания, чтобы защититься от удара молнии.'
        answers=[(json.dumps({'1':wrong}),.01),(json.dumps({'1':correct}),.01)]
        with patch.object(languages,'ask',side_effect=answers) as ask:
            result,cost=languages.translate_part('es',[{'text':'During the storm.','seconds':8,'max_chars':150}],'')
        self.assertEqual(result,[correct]);self.assertEqual(ask.call_count,2)
        with patch.object(languages,'ask',return_value=(json.dumps({'1':wrong}),.01)):
            with self.assertRaises(store.StudioError):
                languages.translate_part('es',[{'text':'During the storm.','seconds':8,'max_chars':150}],'')

    def test_number_cleanup_cannot_switch_to_russian(self):
        with patch.object(languages,'ask',return_value=(json.dumps(['Это произошло в две тысячи десятом году, когда учёные начали исследование.']),.01)):
            with self.assertRaises(store.StudioError):
                languages.speakable('es',['Esto ocurrió en 2010.'])
        for code in ['es','pl','de','fr']:
            self.assertNotRegex(languages.translator(code),r'[а-яА-ЯёЁ]')
            self.assertIn('ISO '+code,languages.translator(code))

    def test_parallel_language_batches_retain_their_own_target_and_order(self):
        from concurrent.futures import ThreadPoolExecutor
        phrases={'es':'Durante la tormenta buscamos refugio dentro de un edificio cerrado para protegernos de los rayos.',
                 'pl':'Podczas burzy szukamy schronienia wewnątrz zamkniętego budynku, aby ochronić się przed uderzeniem pioruna.'}
        def ask(messages,max_tokens=12000):
            code='es' if 'ISO es' in messages[0]['content'] else 'pl'
            items=json.loads(messages[1]['content'])
            time.sleep(.02 if code=='es' else .005)
            return json.dumps({str(item['id']):phrases[code] for item in items}),.01
        lines=[{'start':i*9,'end':i*9+8,'source':'Find shelter from the storm.'} for i in range(65)]
        with patch.object(languages,'ask',side_effect=ask),patch.object(languages,'progress'),ThreadPoolExecutor(max_workers=2) as pool:
            futures={code:pool.submit(languages.translate_lines,code,lines,585,self.pid,{'key':code}) for code in phrases}
            for code,future in futures.items():self.assertEqual(future.result()[0],[phrases[code]]*65)

    def test_trace_keeps_the_exact_model_output_and_target_without_keys(self):
        raw={'id':'generation-test','model':'returned-model','choices':[{'message':{'content':'Texto en español.'},'finish_reason':'stop'}],'usage':{'cost':.01}}
        with languages.translation_trace(self.pid,'es',{'key':'run'},30),patch.object(languages,'request',return_value=json.dumps(raw).encode()):
            languages.ask([{'role':'user','content':'Translate.'}])
        paths=list((languages.work_dir(self.pid,'es')/'translation-attempts').rglob('*.json'))
        self.assertEqual(len(paths),1)
        entry=json.loads(paths[0].read_text());self.assertEqual((entry['target'],entry['offset'],entry['request_id']),('es',30,'generation-test'))
        self.assertEqual(entry['choices'],raw['choices']);self.assertNotIn('Authorization',paths[0].read_text())


    def test_changed_phrase_reuses_paid_neighbours_and_returning_to_old_words_costs_nothing(self):
        work=languages.work_dir(self.pid,'uk');work.mkdir(parents=True)
        texts=['Перша фраза.','Друга фраза.','Третя фраза.']
        (work/'text.txt').write_text('\n'.join(texts)+'\n')
        segments=[{'start':n*2,'end':n*2+1.5,'source':t} for n,t in enumerate(texts)]
        store.atomic_json(languages.segments_path(self.pid,'uk'),segments)
        languages.update(self.pid,lambda d:d.update(provider='elevenlabs',languages={'uk':{}},eleven_engine='eleven_v4_turbo'))
        self.example('uk')
        sample=tone(work/'test.mp3',.6)
        calls=[]
        def speak(provider,voice,text,target,*args,**kwargs):
            calls.append(text);shutil.copy2(sample,target)
        with patch.object(languages,'speak',side_effect=speak),patch.object(languages,'voice_id',return_value={'id':'known'}) as clone,patch.object(languages,'announce_model'),patch.object(languages,'progress'):
            languages.whole_synced(self.pid,'uk','elevenlabs',{},segments)
            self.assertEqual(calls,texts)
            original=[(work/'parts'/f'{n:05d}.mp3').read_bytes() for n in range(3)]
            languages.save_text(self.pid,'uk','\n'.join([texts[0],'Змінена друга фраза.',texts[2]]))
            item=languages.overview(self.pid)['items'][0]
            self.assertFalse(item['voice_current']);self.assertFalse(item['voice_matches_text'])
            estimate=item['voice_estimates']['elevenlabs']
            self.assertEqual((estimate['generate'],estimate['reused']),(1,2))
            self.assertEqual(estimate['base'],languages.price('elevenlabs','Змінена друга фраза.','eleven_v4_turbo'))
            calls.clear();job={}
            languages.whole_synced(self.pid,'uk','elevenlabs',job,segments)
            self.assertEqual(calls,['Змінена друга фраза.'])
            self.assertEqual((job['takes'],job['reused']),(1,2))
            for n in (0,2):self.assertEqual((work/'parts'/f'{n:05d}.mp3').read_bytes(),original[n])
            self.assertTrue(list((work/'voice-history').rglob('voice.mp3')))
            languages.save_text(self.pid,'uk','\n'.join(texts))
            calls.clear();clone.reset_mock();job={'cache_only':True}
            languages.whole_synced(self.pid,'uk','elevenlabs',job,segments)
            self.assertEqual(calls,[]);clone.assert_not_called()
            self.assertEqual((job['cost'],job['takes'],job['reused']),(0,0,3))
            self.assertTrue(languages.overview(self.pid)['items'][0]['voice_current'])
            languages.set_provider(self.pid,'elevenlabs','eleven_v4')
            self.assertEqual(languages.voice_estimate(self.pid,'uk','elevenlabs','\n'.join(texts))['generate'],3)

    def test_cache_only_rebuild_refuses_missing_take_before_archiving_or_payment(self):
        work=languages.work_dir(self.pid,'uk');work.mkdir(parents=True)
        (work/'text.txt').write_text('Це перше речення.\nЦе друге речення.\n')
        (work/'voice.mp3').write_bytes(b'previous accepted voice')
        parts=work/'parts';parts.mkdir();(parts/'keep.txt').write_text('previous takes')
        segments=[{'start':n*3,'end':n*3+2,'source':'Original.'} for n in range(2)]
        self.example('uk')
        with patch.object(languages,'speak',side_effect=AssertionError('No paid synthesis')), \
             patch.object(languages,'voice_id',side_effect=AssertionError('No paid cloning')), \
             patch.object(languages,'archive_voice_parts') as archive:
            with self.assertRaisesRegex(store.StudioError,'бракує готових записів'):
                languages.whole_synced(self.pid,'uk','elevenlabs',{'cache_only':True},segments)
        archive.assert_not_called()
        self.assertEqual((work/'voice.mp3').read_bytes(),b'previous accepted voice')
        self.assertEqual((parts/'keep.txt').read_text(),'previous takes')

    def test_cache_only_requires_boolean_and_timed_voice_job(self):
        for kind,value in [('voice','true'),('sample',True),('translate',True)]:
            with self.subTest(kind=kind,value=value),self.assertRaises(store.StudioError):
                languages.start(self.pid,kind,'uk','elevenlabs',cache_only=value)
        with patch.object(languages,'read_text',return_value='Це український текст.'), \
             patch.object(languages,'synced_segments',return_value=[]), \
             patch.object(languages,'voice_id',side_effect=AssertionError('No cloning')):
            with self.assertRaisesRegex(store.StudioError,'збережених таймінгів'):
                languages.whole(self.pid,'uk','elevenlabs',{'cache_only':True})

    def test_cached_local_drift_finishes_missing_take_once_and_reports_review(self):
        work=languages.work_dir(self.pid,'uk');work.mkdir(parents=True)
        texts=[f'Це збережена фраза номер {n} для перевірки.' for n in range(6)]
        (work/'text.txt').write_text('\n'.join(texts))
        (work/'voice.mp3').write_bytes(b'previous accepted voice')
        self.example('uk')
        audio=tone(work/'cached.mp3',3.8)
        segments=[{'start':i*1.5,'end':i*1.5+1.5,'source':text} for i,text in enumerate(texts)]
        segments[-1].update(start=40,end=45)
        calls=[]
        def synth(provider,voice,text,target,*args,**kwargs):
            calls.append(text)
            shutil.copy2(audio,target)
        job={}
        with patch.object(languages,'source',return_value={'duration':50}), \
             patch.object(languages.voice_cache,'candidates',return_value={text:audio for text in texts[:5]}), \
             patch.object(languages,'progress'),patch.object(languages,'voice_id',return_value='saved-voice') as clone, \
             patch.object(languages,'speak',side_effect=synth):
            languages.whole_synced(self.pid,'uk','elevenlabs',job,segments)
        clone.assert_called_once()
        self.assertEqual(calls,[texts[-1]])
        self.assertEqual(job['reused'],5)
        self.assertTrue(job['timing_review'])
        self.assertAlmostEqual(store.media_duration(work/'voice.mp3'),50,delta=.05)
        manifest=json.loads((work/'parts/manifest.json').read_text())
        self.assertEqual([part['text'] for part in manifest],texts)
        self.assertTrue(all(languages.dubbing_fit.MIN_SPEED<=part['speed']<=languages.dubbing_fit.MAX_SPEED for part in manifest))
        self.assertTrue(all(a['end']<=b['start'] for a,b in zip(manifest,manifest[1:])))
        self.assertFalse(json.loads((work/'alignment-preflight.json').read_text())['within_limit'])

    def test_overlong_cached_narration_is_complete_playable_and_marked_for_review(self):
        work=languages.work_dir(self.pid,'uk');work.mkdir(parents=True)
        texts=['Це перша збережена фраза.','Це друга збережена фраза.']
        (work/'text.txt').write_text('\n'.join(texts))
        self.example('uk');audio=tone(work/'cached.mp3',3)
        segments=[{'start':n,'end':n+1,'source':text} for n,text in enumerate(texts)]
        job={'cache_only':True}
        with patch.object(languages,'source',return_value={'duration':2}), \
             patch.object(languages.voice_cache,'candidates',return_value={text:audio for text in texts}), \
             patch.object(languages,'progress'),patch.object(languages,'voice_id') as clone, \
             patch.object(languages,'speak') as synth:
            languages.whole_synced(self.pid,'uk','elevenlabs',job,segments)
        clone.assert_not_called();synth.assert_not_called()
        manifest=json.loads((work/'parts/manifest.json').read_text())
        self.assertEqual([part['text'] for part in manifest],texts)
        self.assertTrue(job['timing_review'])
        self.assertGreater(job['overrun_seconds'],3)
        self.assertTrue(all(languages.dubbing_fit.MIN_SPEED<=part['speed']<=languages.dubbing_fit.MAX_SPEED for part in manifest))
        self.assertAlmostEqual(store.media_duration(work/'voice.mp3'),manifest[-1]['end'],delta=.06)
        self.assertGreater(manifest[-1]['end'],5)

    def test_interrupted_run_reuses_successful_take_without_repeating_payment(self):
        work=languages.work_dir(self.pid,'uk');work.mkdir(parents=True)
        texts=['Перша фраза.','Друга фраза.']
        (work/'text.txt').write_text('\n'.join(texts)+'\n')
        segments=[{'start':n*3,'end':n*3+2,'source':t} for n,t in enumerate(texts)]
        store.atomic_json(languages.segments_path(self.pid,'uk'),segments)
        languages.update(self.pid,lambda d:d.update(provider='elevenlabs',languages={'uk':{}}))
        self.example('uk');sample=tone(work/'test.mp3',.5);calls=[]
        def speak(provider,voice,text,target,*args,**kwargs):
            calls.append(text)
            if len(calls)==2:raise languages.Stop()
            shutil.copy2(sample,target)
        with patch.object(languages,'speak',side_effect=speak),patch.object(languages,'voice_id',return_value={'id':'known'}),patch.object(languages,'announce_model'),patch.object(languages,'progress'):
            with self.assertRaises(languages.Stop):languages.whole_synced(self.pid,'uk','elevenlabs',{},segments)
            ledger=store.read_json(work/'parts/requests.json')
            self.assertEqual([r['status'] for r in ledger],['complete','uncertain'])
            self.assertEqual(languages.voice_estimate(self.pid,'uk','elevenlabs','\n'.join(texts))['reused'],1)
            languages.whole_synced(self.pid,'uk','elevenlabs',{},segments)
            self.assertEqual(calls,[texts[0],texts[1],texts[1]])
            self.assertTrue(list((work/'voice-history').rglob('requests.json')))

    def test_cache_context_isolated_by_language_voice_model_and_sampling(self):
        self.example('uk');self.example('pl')
        identities=[languages.voice_cache_context(self.pid,code,provider)[0] for code,provider in [('uk','elevenlabs'),('pl','elevenlabs'),('uk','fishaudio')]]
        self.assertEqual(len({languages.voice_cache.digest(i) for i in identities}),3)
        old=identities[2]
        languages.set_provider(self.pid,'fishaudio',style='exact')
        self.assertNotEqual(languages.voice_cache_context(self.pid,'uk','fishaudio')[0],old)
        old=languages.voice_cache_context(self.pid,'uk','elevenlabs')[0]
        path=languages.voice_for(self.pid,'uk')['path']
        # Copying the same audio to a new timestamp does not invalidate the paid takes.
        os.utime(path,None)
        with patch.object(languages,'prepared_example',return_value=(path,{})):
            self.assertEqual(languages.voice_cache_context(self.pid,'uk','elevenlabs')[0],old)

    def test_normal_narration_preserves_saved_words_and_never_calls_text_model(self):
        code='en';work=languages.work_dir(self.pid,code);work.mkdir(parents=True)
        ordinals=['first','second','third','fourth','fifth','sixth','seventh','eighth']
        texts=[f'The {word} report explains how the changing weather affects people in the local park.' for word in ordinals]
        saved='\n'.join(texts)+'\n';(work/'text.txt').write_text(saved)
        total=46.;segments=[{'start':i*total/8,'end':(i+1)*total/8-.3,'source':text} for i,text in enumerate(texts)]
        store.atomic_json(languages.segments_path(self.pid,code),segments)
        languages.update(self.pid,lambda d:d.update(provider='elevenlabs',languages={code:{}},eleven_engine='eleven_v4_turbo'))
        self.example(code,'This is the voice used to tell the whole story.')
        audio=tone(work/'fixture.mp3',6);spoken=[]
        def speak(provider,voice,text,target,*args,**kwargs):
            spoken.append(text);shutil.copy2(audio,target)
        with patch.object(languages,'source',return_value={'duration':total}),patch.object(languages,'speak',side_effect=speak), \
                patch.object(languages,'voice_id',return_value={'id':'existing'}),patch.object(languages,'announce_model'), \
                patch.object(languages,'progress'),patch.object(languages,'prepare_unvoiced') as prepare, \
                patch.object(languages,'ask',side_effect=AssertionError('No text model during narration')), \
                patch.object(languages,'copy_out'):
            languages.whole_synced(self.pid,code,'elevenlabs',{'preserve_text':False},segments)
            prepare.assert_not_called()
        self.assertEqual(spoken,texts)
        self.assertEqual((work/'text.txt').read_text(),saved)
        self.assertFalse((work/'text-pacing.tmp').exists())
        self.assertFalse(list((work/'parts').glob('adaptation-*.json')))
        self.assertEqual(len(store.read_json(work/'parts/requests.json')),8)
        manifest=store.read_json(work/'parts/manifest.json')
        self.assertTrue(all(languages.dubbing_fit.MIN_SPEED<=x['speed']<=languages.dubbing_fit.MAX_SPEED for x in manifest))
        self.assertLessEqual(manifest[-1]['end'],total)
        self.assertTrue(languages.voice_matches_text(self.pid,code,languages.load_state(self.pid)['languages'][code]['voice']))

    def test_pacing_requires_meaning_check_before_any_new_speech(self):
        texts=['The weather affects everyone who visits the park during the course of the afternoon.']
        compact='The weather affects everyone visiting the park in the afternoon.'
        segments=[{'source':texts[0]}]
        for verdict in ({'ok':False},{'ok':True,'ids':[]},{'ok':True,'ids':[0]}):
            with patch.object(languages,'ask',side_effect=[(json.dumps({'0':compact}),.001),(json.dumps(verdict),.001)]), \
                    patch.object(languages,'speak') as speak:
                if verdict=={'ok':True,'ids':[0]}:
                    self.assertEqual(languages.prepare_unvoiced(self.pid,'en',texts,segments,{0:70},{}),{0:compact})
                else:
                    with self.assertRaisesRegex(RuntimeError,'перевірку змісту'):
                        languages.prepare_unvoiced(self.pid,'en',texts,segments,{0:70},{})
                speak.assert_not_called()

    def test_reviewed_repair_keeps_text_without_buying_cached_takes_again(self):
        code='en';work=languages.work_dir(self.pid,code);work.mkdir(parents=True)
        texts=[f'The report number {word} explains the weather in the park.' for word in
               ['one','two','three','four','five','six','seven','eight']]
        (work/'text.txt').write_text('\n'.join(texts)+'\n')
        total=46.;segments=[{'start':i*total/8,'end':(i+1)*total/8-.3,'source':text} for i,text in enumerate(texts)]
        store.atomic_json(languages.segments_path(self.pid,code),segments)
        languages.update(self.pid,lambda d:d.update(provider='elevenlabs',languages={code:{}},eleven_engine='eleven_v4_turbo'))
        self.example(code,'This is the voice used to tell the whole story.')
        audio=tone(work/'fixture.mp3',6)
        def speak(provider,voice,text,target,*args,**kwargs):shutil.copy2(audio,target)
        with patch.object(languages,'source',return_value={'duration':total,'script':'\n'.join(texts)}), \
                patch.object(languages,'speak',side_effect=speak) as speech, \
                patch.object(languages,'voice_id',return_value={'id':'existing'}),patch.object(languages,'announce_model'), \
                patch.object(languages,'progress'),patch.object(languages,'prepare_unvoiced') as prepare, \
                patch.object(languages,'copy_out'):
            languages.whole_synced(self.pid,code,'elevenlabs',{'preserve_text':True},segments)
            self.assertEqual(speech.call_count,8)
            self.assertEqual(languages.line_texts(self.pid,code),texts)
            languages.whole_synced(self.pid,code,'elevenlabs',{'preserve_text':True},segments)
            self.assertEqual(speech.call_count,8)
            prepare.assert_not_called()
        manifest=store.read_json(work/'parts/manifest.json')
        self.assertTrue(all(languages.dubbing_fit.MIN_SPEED<=x['speed']<=languages.dubbing_fit.MAX_SPEED and x['reused'] for x in manifest))
        self.assertLessEqual(manifest[-1]['end'],total)


if __name__ == "__main__":
    unittest.main()
