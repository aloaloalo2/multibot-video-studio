import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import heygen_frames
import store


class HeyGenFramesTest(unittest.TestCase):
    def test_missing_avatar_stops_before_sending_audio(self):
        with patch.object(heygen_frames.host_from_voice, 'voice_video', return_value=None), \
             patch.object(heygen_frames, 'configured_look', return_value=None):
            with self.assertRaisesRegex(store.StudioError, 'аватар'):
                heygen_frames.validate({'channel_id': 'c'}, {'timing': {'audio': {'asset_id': 'a'}}})

    def test_generation_is_reused_and_only_host_frames_are_sent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'voice.wav'
            audio.write_bytes(b'voice')
            project = {'id': 'p', 'channel_id': 'c', 'fps': 25, 'production_request': {'id': 'r'}, 'assets': []}
            plan = {'timing': {'audio': {'asset_id': 'a', 'sha256': 'hash'}}, 'frames': [
                {'number': 1, 'format': 'host', 'start': 1, 'end': 3},
                {'number': 2, 'format': 'text', 'start': 3, 'end': 5}]}
            request = {'id': 'r', 'frames': 2}
            def cut(command, **kwargs):
                Path(command[-1]).write_bytes(b'audio segment')
                return type('Result', (), {'returncode': 0})()
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, size=-1):
                    if hasattr(self, 'sent'): return b''
                    self.sent = True
                    return b'video'
            with patch.object(store, 'load_project', return_value=project), patch.object(store, 'load_project_plan', return_value=plan), \
                 patch.object(store, 'project_dir', return_value=root), patch.object(store, 'made_frames', return_value=[]), \
                 patch.object(store, 'resolve_asset', side_effect=lambda p, aid: {'path': str(audio)} if aid == 'a' else {'id': aid}), \
                 patch.object(store, 'audio_fingerprint', return_value='hash'), patch.object(store, 'media_duration', return_value=2), \
                 patch.object(store, 'import_asset_file', return_value={'id': 'video'}), patch.object(heygen_frames, 'configured_look', return_value='look'), \
                 patch.object(heygen_frames, '_cancelled', return_value=False), patch.object(heygen_frames.host_from_voice, 'voice_video', return_value=None), \
                 patch.object(heygen_frames.heygen_avatars, 'supports_avatar_iii', return_value=True), \
                 patch.object(heygen_frames, '_upload', return_value='audio-id') as upload, patch.object(heygen_frames.subprocess, 'run', side_effect=cut), \
                 patch.object(heygen_frames.heygen_voice, '_call', side_effect=[{'data': {'video_id': 'v'}}, {'data': {'status': 'completed', 'video_url': 'https://example.com/video'}}]) as api, \
                 patch.object(heygen_frames.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response()), \
                 patch.object(heygen_frames.montage_ops, 'run') as montage:
                heygen_frames.make('p', request)
                heygen_frames.make('p', request)
            self.assertEqual(upload.call_count, 1)
            self.assertEqual(api.call_count, 2)
            self.assertEqual(api.call_args_list[0].args[1]['avatar_id'], 'look')
            self.assertEqual(api.call_args_list[0].args[1]['engine'], {'type': 'avatar_iii'})
            self.assertEqual(montage.call_count, 2)
            self.assertEqual(montage.call_args.args[1][0]['frame'], 1)

    def test_unknown_submission_is_not_sent_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'voice.wav'
            audio.write_bytes(b'voice')
            project = {'id': 'p', 'channel_id': 'c', 'fps': 25, 'production_request': {'id': 'r'}}
            plan = {'timing': {'audio': {'asset_id': 'a'}}, 'frames': [{'number': 1, 'format': 'host', 'start': 0, 'end': 2}]}
            def cut(command, **kwargs):
                Path(command[-1]).write_bytes(b'audio')
                return type('Result', (), {'returncode': 0})()
            with patch.object(store, 'load_project', return_value=project), patch.object(store, 'load_project_plan', return_value=plan), \
                 patch.object(store, 'project_dir', return_value=root), patch.object(store, 'made_frames', return_value=[]), \
                 patch.object(store, 'resolve_asset', return_value={'path': str(audio)}), patch.object(store, 'audio_fingerprint', return_value='hash'), \
                 patch.object(heygen_frames, 'configured_look', return_value='look'), patch.object(heygen_frames, '_cancelled', return_value=False), \
                 patch.object(heygen_frames.host_from_voice, 'voice_video', return_value=None), patch.object(heygen_frames, '_upload', return_value='a'), \
                 patch.object(heygen_frames.heygen_avatars, 'supports_avatar_iii', return_value=True), \
                 patch.object(heygen_frames.subprocess, 'run', side_effect=cut), \
                 patch.object(heygen_frames.heygen_voice, '_call', side_effect=heygen_frames.heygen_voice.Lost('timeout')) as api:
                for _ in range(2):
                    with self.assertRaises(store.StudioError):
                        heygen_frames.make('p', {'id': 'r', 'frames': 1})
            self.assertEqual(api.call_count, 1)


if __name__ == '__main__':
    unittest.main()
