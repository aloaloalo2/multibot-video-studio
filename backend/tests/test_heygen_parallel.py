import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import heygen_frames
import heygen_voice as hg
import project_narration as narration


class WorkersTest(unittest.TestCase):
    """Paid HeyGen models voice several phrases at once; Turbo Free and Starfish keep one (25 November 2026)."""

    def test_only_paid_models_take_several_phrases_at_once(self):
        self.assertEqual(hg.workers('heygen-voice-1-turbo-free'), hg.SLOTS)
        self.assertEqual(hg.workers(None), hg.SLOTS)
        self.assertEqual(hg.workers('starfish'), hg.SLOTS)
        self.assertEqual(hg.workers('heygen-voice-1-turbo'), hg.PAID_SLOTS)
        self.assertEqual(hg.workers('heygen-voice-1'), hg.PAID_SLOTS)

    def test_voice_all_runs_paid_heygen_phrases_side_by_side_and_keeps_order(self):
        together = threading.Barrier(2, timeout=5)
        def phrase(project, settings, ref, entry, secret, voice):
            together.wait()   # two phrases are at HeyGen at the same time
            return entry['key']
        entries = [{'key': str(i), 'text': str(i), 'cached': False} for i in range(4)]
        heard = []
        with tempfile.TemporaryDirectory() as folder, patch.object(narration, 'phrase_audio', side_effect=phrase):
            takes = narration.voice_all({}, {'provider': 'heygen', 'heygen_model': 'heygen-voice-1-turbo'}, {}, entries,
                                        None, None, Path(folder), lambda: None, heard.append)
        self.assertEqual(takes, ['0', '1', '2', '3'])
        self.assertEqual(len(heard), 4)

    def test_turbo_free_phrases_go_one_by_one(self):
        running = [0]; peak = [0]; lock = threading.Lock()
        def phrase(project, settings, ref, entry, secret, voice):
            with lock:
                running[0] += 1; peak[0] = max(peak[0], running[0])
            with lock:
                running[0] -= 1
            return entry['key']
        entries = [{'key': str(i), 'text': str(i), 'cached': False} for i in range(5)]
        with tempfile.TemporaryDirectory() as folder, patch.object(narration, 'phrase_audio', side_effect=phrase):
            narration.voice_all({}, {'provider': 'heygen', 'heygen_model': 'heygen-voice-1-turbo-free'}, {}, entries,
                                None, None, Path(folder), lambda: None, lambda entry: None)
        self.assertEqual(peak[0], 1)


class ReadyVoiceTest(unittest.TestCase):
    def setUp(self):
        hg.READY.clear()

    def tearDown(self):
        hg.READY.clear()

    def test_phrases_side_by_side_ask_about_their_voice_once(self):
        calls = []
        def call(path, body=None, **_):
            calls.append(path)
            return {'data': {'status': 'ACTIVE', 'mode': 'instant'}}
        with patch.object(hg, 'call', side_effect=call):
            workers = [threading.Thread(target=hg.ready_voice, args=('/v3/models/audio/voices/v',)) for _ in range(4)]
            for worker in workers: worker.start()
            for worker in workers: worker.join(5)
        self.assertEqual(calls, ['/v3/models/audio/voices/v'])


class FrameDownloadTest(unittest.TestCase):
    """A paid host video cut short by the connection is not kept: the next round downloads it again."""

    class Response(io.BytesIO):
        def __init__(self, body, length):
            super().__init__(body); self.headers = {'Content-Length': str(length)}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def test_a_short_download_raises_lost_and_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'frame.mp4'; receipt = Path(folder) / 'frame.json'
            job = {'record': {'video_id': 'abc123'}, 'receipt': receipt, 'output': output, 'frame': {'number': 3}}
            with patch.object(heygen_frames.heygen_voice, '_call', return_value={'data': {'status': 'completed', 'video_url': 'https://x/v.mp4'}}), \
                 patch.object(heygen_frames.urllib.request, 'urlopen', return_value=self.Response(b'half', 100)), \
                 patch.object(heygen_frames.store, 'media_duration', return_value=5):
                with self.assertRaises(hg.Lost):
                    heygen_frames._ready(job)
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix('.part').exists())
            self.assertFalse(receipt.exists())


if __name__ == '__main__':
    unittest.main()
