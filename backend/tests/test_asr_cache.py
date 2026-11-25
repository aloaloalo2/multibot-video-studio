"""Whisper's words of one audio file are kept and reused: the same voice is never recognised twice."""
import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analysis_jobs
import speech
import store

WORDS = [{"text": "Hello", "start": 0.0, "end": 0.4, "probability": 0.9}]
ENGINE = {"engine": "mlx-whisper", "model": speech.MODEL_NAME, "local": True}


class AsrCacheTest(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack(); self.addCleanup(stack.close)
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        stack.enter_context(patch.object(store, "PROJECTS_ROOT", root / "projects"))
        (root / "projects" / "p1").mkdir(parents=True)
        stack.enter_context(patch.object(store, "project_dir", lambda pid: root / "projects" / pid))

    def test_words_of_the_same_audio_come_back_unchanged_and_copied(self):
        analysis_jobs.keep_words("p1", "job1", "sha-a", WORDS, ENGINE)
        words, engine = analysis_jobs.cached_words("p1", "sha-a")
        self.assertEqual(words, WORDS)
        self.assertEqual(engine["cached_from"], "job1")
        words[0]["text"] = "changed"
        self.assertEqual(analysis_jobs.cached_words("p1", "sha-a")[0], WORDS)

    def test_other_audio_or_model_is_recognised_again(self):
        analysis_jobs.keep_words("p1", "job1", "sha-a", WORDS, ENGINE)
        self.assertIsNone(analysis_jobs.cached_words("p1", "sha-b"))
        with patch.object(speech, "MODEL_NAME", "large-v3-turbo"):
            self.assertIsNone(analysis_jobs.cached_words("p1", "sha-a"))

    def test_a_missing_or_broken_cache_is_no_cache(self):
        self.assertIsNone(analysis_jobs.cached_words("p1", "sha-a"))
        folder = store.project_dir("p1") / "analysis"
        folder.mkdir()
        (folder / analysis_jobs.ASR_CACHE).write_text('{"sha-a": "../../etc"}')
        self.assertIsNone(analysis_jobs.cached_words("p1", "sha-a"))


class VoiceTest(unittest.TestCase):
    def test_a_piece_is_a_slice_of_the_decoded_samples(self):
        import numpy as np
        voice = speech.Voice("x.wav", np.arange(48000, dtype=np.float32))
        piece = voice.piece(1.0, 1.5)
        self.assertEqual((len(piece.samples), float(piece.samples[0])), (8000, 16000.0))
        self.assertIsNone(voice.piece(5, 6))


if __name__ == "__main__":
    unittest.main()
