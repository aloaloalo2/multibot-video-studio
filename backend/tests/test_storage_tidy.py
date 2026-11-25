import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import storage_tidy  # noqa: E402

OLD = time.time() - 30 * 86400


def write(path: Path, size: int = 100, old: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if old:
        os.utime(path, (OLD, OLD))
    return path


def age(root: Path) -> None:
    for item in [root, *root.rglob("*")]:
        os.utime(item, (OLD, OLD))


class TidyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.project = self.data / "projects" / ("a" * 24)
        (self.project / "project.json").parent.mkdir(parents=True)
        self.voice = write(self.data / "voice.mp3", 50)
        (self.project / "project.json").write_text(json.dumps({"assets": [{"path": str(self.voice)}]}))
        self.work = self.project / "languages" / "uk"
        write(self.work / "voice.mp3", 1000)
        write(self.work / "parts" / "00000.mp3", 300)            # paid take
        write(self.work / "parts" / "00000-line.wav", 700)
        write(self.work / "parts" / "00001-gap.wav", 50)
        write(self.work / "parts" / "manifest.json", 10)
        for stamp in ("100", "200"):
            history = self.work / "voice-history" / stamp
            write(history / "voice.mp3", 900)
            write(history / "parts" / "00000.mp3", 300)           # paid take, reused by voice_cache
            write(history / "parts" / "00000-line.wav", 600)
            write(history / "parts" / "requests.json", 10)
            write(self.work / "mix-history" / stamp / "Озвучка.mp3", 800)
            write(self.work / "recovery" / stamp / "voice.mp3", 400)
        age(self.work)

    def run_tidy(self, **kwargs):
        return storage_tidy.tidy(self.data, **kwargs)

    def test_clears_dead_weight_and_keeps_paid_takes_and_the_newest_versions(self):
        result = self.run_tidy()
        self.assertFalse(list(self.work.rglob("*.wav")))
        self.assertTrue((self.work / "voice.mp3").is_file())
        self.assertTrue((self.work / "parts" / "00000.mp3").is_file())
        self.assertTrue((self.work / "parts" / "manifest.json").is_file())
        for stamp in ("100", "200"):
            self.assertTrue((self.work / "voice-history" / stamp / "parts" / "00000.mp3").is_file())
            self.assertTrue((self.work / "voice-history" / stamp / "parts" / "requests.json").is_file())
        self.assertFalse((self.work / "voice-history" / "100" / "voice.mp3").exists())
        self.assertTrue((self.work / "voice-history" / "200" / "voice.mp3").is_file())
        self.assertEqual([p.name for p in (self.work / "mix-history").iterdir()], ["200"])
        self.assertEqual([p.name for p in (self.work / "recovery").iterdir()], ["200"])
        self.assertEqual(result["freed"], 700 + 50 + 600 * 2 + 900 + 800 + 400)

    def test_dry_run_counts_the_same_and_changes_nothing(self):
        before = sorted(str(p) for p in self.data.rglob("*"))
        dry = self.run_tidy(apply=False)
        self.assertEqual(sorted(str(p) for p in self.data.rglob("*")), before)
        self.assertEqual(dry["freed"], self.run_tidy()["freed"])

    def test_a_busy_project_is_left_alone(self):
        self.assertEqual(self.run_tidy(skip={self.project.name})["freed"], 0)
        self.assertTrue((self.work / "parts" / "00000-line.wav").is_file())

    def test_a_voicing_in_progress_keeps_its_wavs(self):
        write(self.work / "parts" / "00002-line.wav", 10, old=False)
        os.utime(self.work / "parts", None)
        self.run_tidy()
        self.assertTrue((self.work / "parts" / "00000-line.wav").is_file())

    def test_an_unvoiced_language_keeps_its_wavs(self):
        (self.work / "voice.mp3").unlink()
        self.run_tidy()
        self.assertTrue((self.work / "parts" / "00000-line.wav").is_file())

    def test_long_logs_keep_their_tail(self):
        log = self.project / "production-x.log"
        log.write_bytes(b"line\n" * (storage_tidy.LOG_LIMIT // 5 + 1000) + b"LAST\n")
        os.utime(log, (OLD, OLD))
        self.run_tidy()
        self.assertLessEqual(log.stat().st_size, storage_tidy.LOG_KEEP + 200)
        self.assertTrue(log.read_bytes().endswith(b"LAST\n"))

    def test_leveled_copies_go_only_when_unused_and_old(self):
        stat = self.voice.stat()
        key = hashlib.sha1(f"{self.voice.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()).hexdigest()[:20]
        used = write(self.data / "leveled" / f"{key}.flac", 10)
        unused = write(self.data / "leveled" / ("0" * 20 + ".flac"), 10)
        fresh = write(self.data / "leveled" / ("1" * 20 + ".flac"), 10, old=False)
        self.run_tidy()
        self.assertTrue(used.is_file())
        self.assertFalse(unused.exists())
        self.assertTrue(fresh.is_file())

    def test_a_copy_of_a_voice_whose_file_time_changed_stays(self):
        # a copy whose voice only got another file time (a clone, a restored date) is still that voice's: 37 copies went
        # once for a rounded time and the playing voice vanished (user, 25 November 2026: «звука нема»)
        import json as json_module
        copy = write(self.data / "leveled" / ("2" * 20 + ".flac"), 10)
        copy.with_suffix(".json").write_text(json_module.dumps({"source": str(self.voice.resolve()), "size": self.voice.stat().st_size}))
        self.run_tidy()
        self.assertTrue(copy.is_file())

    def test_an_unreadable_project_keeps_every_leveled_copy(self):
        broken = self.data / "projects" / ("b" * 24)
        broken.mkdir()
        (broken / "project.json").write_text("{")
        unused = write(self.data / "leveled" / ("0" * 20 + ".flac"), 10)
        self.run_tidy()
        self.assertTrue(unused.is_file())


class CacheRulesTest(unittest.TestCase):
    """The rules of 25 November 2026: copies of sounds the studio already holds, idle caches, CapCut, old versions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.project = self.data / "projects" / ("c" * 24)
        self.media_voice = write(self.project / "media" / "Озвучка.flac", 500)
        self.ending_voice = write(self.project / "narration-ending" / "x-v1" / "Озвучка.flac", 500)
        self.episode_voice = write(self.data / "YOUTUBE" / "Канал" / "Випуск" / "voice.wav", 500)
        self.other = write(self.project / "languages" / "uk" / "voice.mp3", 500)
        self.cached = write(self.project / "held-tails" / "tail.mov", 500)
        assets = [{"id": "m" * 20, "path": str(self.media_voice)}, {"id": "n" * 20, "path": str(self.ending_voice)},
                  {"id": "e" * 20, "path": str(self.episode_voice)}, {"id": "o" * 20, "path": str(self.other)},
                  {"id": "h" * 20, "path": str(self.cached)}, {"id": "g" * 20, "path": str(self.project / "media" / "gone.wav")}]
        (self.project / "project.json").write_text(json.dumps({"assets": assets, "tracks": []}))
        self.kept = {asset["id"]: write(self.project / "kept" / f"{asset['id']}.m4a", 40) for asset in assets}

    def run_tidy(self, **kwargs):
        return storage_tidy.tidy(self.data, **kwargs)

    def test_a_kept_copy_goes_only_when_its_original_lies_in_the_projects_own_media(self):
        self.run_tidy()
        self.assertFalse(self.kept["m" * 20].exists())
        self.assertFalse(self.kept["n" * 20].exists())
        # the copy is all that plays once the episode folder is deleted: it stays
        self.assertTrue(self.kept["e" * 20].is_file())
        # a voicing or a cache may go some day: their copies stay too
        self.assertTrue(self.kept["o" * 20].is_file())
        self.assertTrue(self.kept["h" * 20].is_file())
        # an original that is gone already: its copy is what plays now
        self.assertTrue(self.kept["g" * 20].is_file())

    def test_a_kept_copy_of_an_empty_original_stays(self):
        self.media_voice.write_bytes(b"")
        self.run_tidy()
        self.assertTrue(self.kept["m" * 20].is_file())

    def test_a_half_made_kept_copy_goes_after_the_quiet_hour(self):
        old = write(self.project / "kept" / ("z" * 20 + ".tmp.m4a"), 10)
        fresh = write(self.project / "kept" / ("y" * 20 + ".tmp.m4a"), 10, old=False)
        self.run_tidy()
        self.assertFalse(old.exists())
        self.assertTrue(fresh.is_file())

    def test_keep_makes_no_copy_of_a_sound_in_the_studios_own_media(self):
        import keep
        import store
        from unittest import mock
        self.assertTrue(storage_tidy.lasting(self.media_voice, self.project))
        self.assertFalse(storage_tidy.lasting(self.episode_voice, self.project))
        self.assertFalse(storage_tidy.lasting(self.other, self.project))
        project = {"assets": [{"id": "m" * 20, "path": str(self.media_voice)}],
                   "tracks": [{"clips": [{"kind": "audio", "asset_id": "m" * 20}]}]}
        self.kept["m" * 20].unlink()
        with mock.patch.object(store, "PROJECTS_ROOT", self.data / "projects"), \
                mock.patch.object(store, "load_project", return_value=project), \
                mock.patch.object(store, "load_project_narration", return_value={}), \
                mock.patch.object(keep.subprocess, "run") as ffmpeg:
            self.assertEqual(keep.keep_project("c" * 24), 0)
        ffmpeg.assert_not_called()

    def test_an_idle_cache_goes_whole_and_a_cache_in_use_stays(self):
        idle = write(self.project / "render-cache" / "chunk" / "a" / "file.mp4", 300)
        age(self.project / "render-cache")
        busy = write(self.project / "stills" / "old.png", 300)
        write(self.project / "stills" / "new.png", 10, old=False)
        result = self.run_tidy()
        self.assertFalse(idle.exists())
        self.assertFalse((self.project / "render-cache").exists())
        self.assertTrue(busy.is_file())
        self.assertGreaterEqual(result["by_kind"]["кеш випуску, не потрібний тиждень"], 300)

    def test_held_tails_and_motion_code_keep_their_own_prune(self):
        age(self.project / "held-tails")
        self.run_tidy()
        self.assertTrue(self.cached.is_file())

    def test_old_seam_previews_of_a_project_go(self):
        old = write(self.project / "capcut" / "razgon-old.mp4", 100)
        fresh = write(self.project / "capcut" / "razgon-new.mp4", 100, old=False)
        self.run_tidy()
        self.assertFalse(old.exists())
        self.assertTrue(fresh.is_file())

    def test_the_shared_capcut_cache_keeps_under_its_limit_newest_first(self):
        cache = self.data / "capcut-cache"
        files = []
        for number in range(4):
            path = write(cache / f"{number}.mov", 100, old=False)
            moment = time.time() - 7200 - number * 60          # 0 is the newest; all are past the quiet hour
            os.utime(path, (moment, moment))
            files.append(path)
        fresh = write(cache / "running.raw", 1000, old=False)  # written now: an export may be reading it
        with unittest.mock.patch.object(storage_tidy, "CAPCUT_LIMIT", 250):
            self.run_tidy()
        self.assertTrue(fresh.is_file())
        self.assertEqual([path.exists() for path in files], [False, False, False, False])
        with unittest.mock.patch.object(storage_tidy, "CAPCUT_LIMIT", 10_000):
            kept = write(cache / "x.mov", 100, old=False)
            self.run_tidy()
        self.assertTrue(kept.is_file())

    def test_the_limit_keeps_the_most_recently_used(self):
        cache = self.data / "capcut-cache"
        paths = []
        for number in range(3):
            path = write(cache / f"{number}.mov", 100, old=False)
            moment = time.time() - 7200 - number * 60
            os.utime(path, (moment, moment))
            paths.append(path)
        with unittest.mock.patch.object(storage_tidy, "CAPCUT_LIMIT", 250):
            self.run_tidy()
        self.assertEqual([path.exists() for path in paths], [True, True, False])

    def test_only_superseded_cache_versions_go(self):
        old = write(self.data / "cache" / "sound-previews-v1" / "a.wav", 100)
        recent_old = write(self.data / "cache" / "sfx-library-v1" / "a.wav", 100, old=False)
        newest = write(self.data / "cache" / "sound-previews-v5" / "a.wav", 100)
        single = write(self.data / "cache" / "music-style-previews-v2" / "a.wav", 100)
        write(self.data / "cache" / "sfx-library-v3" / "a.wav", 100)
        self.run_tidy()
        self.assertFalse(old.exists())
        self.assertTrue(recent_old.is_file())       # written within the hour: an older studio may still use it
        self.assertTrue(newest.is_file())
        self.assertTrue(single.is_file())

    def test_dry_run_changes_nothing_and_counts_the_same(self):
        write(self.project / "stills" / "old.png", 300)
        write(self.data / "cache" / "a-v1" / "x", 50)
        write(self.data / "cache" / "a-v2" / "x", 50)
        before = sorted(str(p) for p in self.data.rglob("*"))
        dry = self.run_tidy(apply=False)
        self.assertEqual(sorted(str(p) for p in self.data.rglob("*")), before)
        self.assertEqual(dry["freed"], self.run_tidy()["freed"])


if __name__ == "__main__":
    unittest.main()
