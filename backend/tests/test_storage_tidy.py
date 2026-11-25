import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
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


if __name__ == "__main__":
    unittest.main()
