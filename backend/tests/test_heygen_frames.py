import contextlib
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
                 patch.object(heygen_frames.heygen_avatars, 'engines', return_value=['avatar_iii']), \
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
                 patch.object(heygen_frames.heygen_avatars, 'engines', return_value=['avatar_iii']), \
                 patch.object(heygen_frames.subprocess, 'run', side_effect=cut), \
                 patch.object(heygen_frames.heygen_voice, '_call', side_effect=heygen_frames.heygen_voice.Lost('timeout')) as api:
                for _ in range(2):
                    with self.assertRaises(store.StudioError):
                        heygen_frames.make('p', {'id': 'r', 'frames': 1})
            self.assertEqual(api.call_count, 1)


    def test_all_host_frames_are_sent_before_waiting_and_placed_as_they_come(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'voice.wav'
            audio.write_bytes(b'voice')
            project = {'id': 'p', 'channel_id': 'c', 'fps': 25, 'production_request': {'id': 'r'}, 'assets': []}
            plan = {'timing': {'audio': {'asset_id': 'a'}}, 'frames': [
                {'number': 1, 'format': 'host', 'start': 0, 'end': 2},
                {'number': 2, 'format': 'razgon_2d', 'start': 2, 'end': 4},
                {'number': 3, 'format': 'host', 'start': 4, 'end': 6},
                {'number': 4, 'format': 'host', 'start': 6, 'end': 8}]}
            def cut(command, **kwargs):
                Path(command[-1]).write_bytes(b'audio')
                return type('Result', (), {'returncode': 0})()
            events = []
            polls = {'v1': iter(['processing', 'completed']), 'v3': iter(['completed']), 'v4': iter(['failed'])}
            def call(path, body=None, **kwargs):
                if path == '/v3/videos':
                    video = 'v' + str(len([e for e in events if e[0] == 'submit']) + {0: 1, 1: 2, 2: 2}[len([e for e in events if e[0] == 'submit'])])
                    events.append(('submit', video))
                    return {'data': {'video_id': video}}
                video = path.rsplit('/', 1)[1]
                status = next(polls[video])
                events.append(('poll', video, status))
                return {'data': {'status': status, 'video_url': 'https://example.com/' + video}}
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, size=-1):
                    if hasattr(self, 'sent'): return b''
                    self.sent = True
                    return b'video'
            def place(pid, ops):
                events.append(('place', ops[0]['frame']))
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(store, 'load_project', return_value=project))
                stack.enter_context(patch.object(store, 'load_project_plan', return_value=plan))
                stack.enter_context(patch.object(store, 'project_dir', return_value=root))
                stack.enter_context(patch.object(store, 'made_frames', return_value=[]))
                stack.enter_context(patch.object(store, 'resolve_asset', side_effect=lambda p, aid: {'path': str(audio)} if aid == 'a' else {'id': aid}))
                stack.enter_context(patch.object(store, 'audio_fingerprint', return_value='hash'))
                stack.enter_context(patch.object(store, 'media_duration', return_value=2))
                stack.enter_context(patch.object(store, 'import_asset_file', return_value={'id': 'video'}))
                stack.enter_context(patch.object(heygen_frames, 'configured_look', return_value='look'))
                stack.enter_context(patch.object(heygen_frames, '_cancelled', return_value=False))
                stack.enter_context(patch.object(heygen_frames.host_from_voice, 'voice_video', return_value=None))
                stack.enter_context(patch.object(heygen_frames.heygen_avatars, 'engines', return_value=['avatar_iii']))
                stack.enter_context(patch.object(heygen_frames, '_upload', return_value='audio-id'))
                stack.enter_context(patch.object(heygen_frames.subprocess, 'run', side_effect=cut))
                stack.enter_context(patch.object(heygen_frames.heygen_voice, '_call', side_effect=call))
                stack.enter_context(patch.object(heygen_frames.time, 'sleep'))
                stack.enter_context(patch.object(heygen_frames, 'SUBMIT_GAP', 0))
                stack.enter_context(patch.object(heygen_frames, 'ONE_VIDEO', False))
                stack.enter_context(patch.object(heygen_frames.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response()))
                stack.enter_context(patch.object(heygen_frames.montage_ops, 'run', side_effect=place))
                with self.assertRaisesRegex(store.StudioError, 'кадру 4'):
                    heygen_frames.make('p', {'id': 'r', 'frames': 4})
                self.assertEqual(heygen_frames.pending('p', {'frames': 4}), [1, 3, 4])   # made_frames is mocked empty
            self.assertEqual([e[0] for e in events[:3]], ['submit'] * 3)   # every host video is at HeyGen before the first wait
            self.assertEqual([e for e in events if e[0] == 'place'], [('place', 3), ('place', 1)])   # the ready one goes first
            self.assertNotIn(('place', 2), events)


    def test_the_voice_is_found_by_its_hash_when_the_plan_has_no_asset_id(self):
        project = {'assets': [{'id': 'music', 'kind': 'audio'}, {'id': 'voice', 'kind': 'audio', 'narration_ending': {'sha256': 'h'}}]}
        plan = {'timing': {'audio': {'duration': 9, 'sha256': 'h'}}}
        with patch.object(store, 'resolve_asset', side_effect=lambda p, aid: {'id': aid, 'path': aid + '.flac'}):
            self.assertEqual(heygen_frames.audio_asset(project, plan)['id'], 'voice')
            self.assertIsNone(heygen_frames.audio_asset(project, {'timing': {'audio': {'duration': 9}}}))


    def test_all_host_frames_go_to_heygen_as_one_video_and_are_cut_back(self):
        import wave
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'voice.wav'
            audio.write_bytes(b'voice')
            project = {'id': 'p', 'channel_id': 'c', 'fps': 25, 'production_request': {'id': 'r'}, 'assets': []}
            plan = {'timing': {'audio': {'asset_id': 'a'}}, 'frames': [
                {'number': 1, 'format': 'host', 'start': 0, 'end': 2},
                {'number': 2, 'format': 'razgon_2d', 'start': 2, 'end': 4},
                {'number': 3, 'format': 'host', 'start': 4, 'end': 5},
                {'number': 4, 'format': 'host', 'start': 6, 'end': 9}]}
            cuts = []
            def run(command, **kwargs):
                target = Path(command[-1])
                if '-c:v' in command:   # a frame cut from the long video
                    cuts.append((float(command[command.index('-ss') + 1]), float(command[command.index('-t') + 1])))
                    target.write_bytes(b'frame video')
                else:                   # a piece of the voice, as many samples as its seconds
                    seconds = float(command[command.index('-t') + 1])
                    with wave.open(str(target), 'wb') as out:
                        out.setnchannels(1); out.setsampwidth(2); out.setframerate(48000)
                        out.writeframes(b'\1\0' * int(round(seconds * 48000)))
                return type('Result', (), {'returncode': 0})()
            calls = []
            def call(path, body=None, **kwargs):
                calls.append(path)
                if path == '/v3/videos':
                    return {'data': {'video_id': 'long'}}
                return {'data': {'status': 'completed', 'video_url': 'https://example.com/long'}}
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, size=-1):
                    if hasattr(self, 'sent'): return b''
                    self.sent = True
                    return b'video'
            placed = []
            with contextlib.ExitStack() as stack:
                for target, name, value in [
                        (store, 'load_project', project), (store, 'load_project_plan', plan), (store, 'project_dir', root),
                        (store, 'made_frames', []), (store, 'audio_fingerprint', 'hash'), (store, 'media_duration', 2),
                        (store, 'import_asset_file', {'id': 'video'}), (heygen_frames, 'configured_look', 'look'),
                        (heygen_frames, '_cancelled', False), (heygen_frames, '_upload', 'audio-id')]:
                    stack.enter_context(patch.object(target, name, return_value=value))
                stack.enter_context(patch.object(store, 'resolve_asset', side_effect=lambda p, aid: {'path': str(audio)} if aid == 'a' else {'id': aid}))
                stack.enter_context(patch.object(heygen_frames.host_from_voice, 'voice_video', return_value=None))
                stack.enter_context(patch.object(heygen_frames.heygen_avatars, 'engines', return_value=['avatar_iii']))
                stack.enter_context(patch.object(heygen_frames.subprocess, 'run', side_effect=run))
                stack.enter_context(patch.object(heygen_frames.heygen_voice, '_call', side_effect=call))
                stack.enter_context(patch.object(heygen_frames.time, 'sleep'))
                stack.enter_context(patch.object(heygen_frames.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response()))
                stack.enter_context(patch.object(heygen_frames.montage_ops, 'run', side_effect=lambda pid, ops: placed.append(ops[0]['frame'])))
                heygen_frames.make('p', {'id': 'r', 'frames': 4})
                heygen_frames.make('p', {'id': 'r', 'frames': 4})   # again: the frames are cut already, nothing is bought
            self.assertEqual(calls.count('/v3/videos'), 1)                 # one paid video for three host frames
            self.assertEqual(placed, [1, 3, 4, 1, 3, 4])
            # each frame is cut where its voice sits in the joined track: pieces of 2 s, 1 s and 3 s with 0.4 s between,
            # each with the silent 0.4 s after it as its tail, for a transition on the living host instead of a held picture
            # and the 0.4 s before it as its head (the first frame has none)
            self.assertEqual([(round(a, 3), round(b, 3)) for a, b in cuts], [(0.0, 2.4), (2.0, 1.8), (3.4, 3.8)])
            with wave.open(str(next(root.glob('heygen-frames/one-*.wav'))), 'rb') as joined:
                self.assertAlmostEqual(joined.getnframes() / 48000, 7.2, places=3)   # the last piece has its pause too


    def test_the_first_host_frame_goes_to_avatar_iv_and_the_rest_as_one_avatar_iii_video(self):
        import wave
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'voice.wav'
            audio.write_bytes(b'voice')
            project = {'id': 'p', 'channel_id': 'c', 'fps': 25, 'production_request': {'id': 'r'}, 'assets': []}
            plan = {'timing': {'audio': {'asset_id': 'a'}}, 'frames': [
                {'number': 1, 'format': 'host', 'start': 0, 'end': 2},
                {'number': 2, 'format': 'razgon_2d', 'start': 2, 'end': 4},
                {'number': 3, 'format': 'host', 'start': 4, 'end': 5},
                {'number': 4, 'format': 'host', 'start': 6, 'end': 9}]}
            cuts = []
            def run(command, **kwargs):
                target = Path(command[-1])
                if '-c:v' in command:   # a frame cut from the long video
                    cuts.append((float(command[command.index('-ss') + 1]), float(command[command.index('-t') + 1])))
                    target.write_bytes(b'frame video')
                else:                   # a piece of the voice, as many samples as its seconds
                    seconds = float(command[command.index('-t') + 1])
                    with wave.open(str(target), 'wb') as out:
                        out.setnchannels(1); out.setsampwidth(2); out.setframerate(48000)
                        out.writeframes(b'\1\0' * int(round(seconds * 48000)))
                return type('Result', (), {'returncode': 0})()
            calls, bodies = [], []
            def call(path, body=None, **kwargs):
                calls.append(path)
                if path == '/v3/videos':
                    bodies.append(body)
                    return {'data': {'video_id': 'first' if body['engine']['type'] == 'avatar_iv' else 'long'}}
                return {'data': {'status': 'completed', 'video_url': 'https://example.com/long'}}
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, size=-1):
                    if hasattr(self, 'sent'): return b''
                    self.sent = True
                    return b'video'
            placed = []
            with contextlib.ExitStack() as stack:
                for target, name, value in [
                        (store, 'load_project', project), (store, 'load_project_plan', plan), (store, 'project_dir', root),
                        (store, 'made_frames', []), (store, 'audio_fingerprint', 'hash'), (store, 'media_duration', 2),
                        (store, 'import_asset_file', {'id': 'video'}), (heygen_frames, 'configured_look', 'look'),
                        (heygen_frames, '_cancelled', False), (heygen_frames, '_upload', 'audio-id')]:
                    stack.enter_context(patch.object(target, name, return_value=value))
                stack.enter_context(patch.object(store, 'resolve_asset', side_effect=lambda p, aid: {'path': str(audio)} if aid == 'a' else {'id': aid}))
                stack.enter_context(patch.object(heygen_frames.host_from_voice, 'voice_video', return_value=None))
                stack.enter_context(patch.object(heygen_frames.heygen_avatars, 'engines', return_value=['avatar_iii', 'avatar_iv']))
                stack.enter_context(patch.object(heygen_frames.subprocess, 'run', side_effect=run))
                stack.enter_context(patch.object(heygen_frames.heygen_voice, '_call', side_effect=call))
                stack.enter_context(patch.object(heygen_frames.time, 'sleep'))
                stack.enter_context(patch.object(heygen_frames.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response()))
                stack.enter_context(patch.object(heygen_frames.montage_ops, 'run', side_effect=lambda pid, ops: placed.append(ops[0]['frame'])))
                stack.enter_context(patch.object(heygen_frames, 'first_frame_settings', return_value={'enabled': True, 'expressiveness': 'high', 'motion_prompt': 'Nods'}))
                heygen_frames.make('p', {'id': 'r', 'frames': 4})
                heygen_frames.make('p', {'id': 'r', 'frames': 4})   # again: nothing is bought twice
            self.assertEqual(calls.count('/v3/videos'), 2)
            first, rest = bodies
            self.assertEqual((first['engine'], first['motion_prompt'], first['expressiveness']), ({'type': 'avatar_iv'}, 'Nods', 'high'))
            self.assertEqual(rest['engine'], {'type': 'avatar_iii'})
            self.assertNotIn('motion_prompt', rest)
            self.assertEqual(sorted(placed), [1, 1, 3, 3, 4, 4])
            # frames 3 and 4 are cut from the one Avatar III video: pieces of 1 s and 3 s with 0.4 s between, each with
            # that pause as its tail
            self.assertEqual([(round(a, 3), round(b, 3)) for a, b in cuts], [(0.0, 1.4), (1.0, 3.8)])

    def test_host_frames_zoom_in_and_out_in_turn_by_their_length(self):
        # the first host frame zooms in; the order of the rest is the film's own (test_host_zoom_order_is_the_films_own)
        plan = {'frames': [{'number': 1, 'format': 'razgon_2d', 'start': 0, 'end': 4},
                           {'number': 2, 'format': 'host', 'start': 4, 'end': 5},
                           {'number': 3, 'format': 'razgon_2d', 'start': 5, 'end': 9},
                           {'number': 4, 'format': 'host', 'start': 9, 'end': 14},
                           {'number': 5, 'format': 'host', 'start': 14, 'end': 30}]}
        frames = {f['number']: f for f in plan['frames']}
        self.assertEqual(heygen_frames.host_zoom(plan, frames[2]), ('zoom_in', 2.0))     # one second: at least 2%
        self.assertEqual(heygen_frames.host_zoom(plan, frames[4])[1], 7.5)    # five seconds: 1.5 points less
        self.assertEqual(heygen_frames.host_zoom(plan, frames[5])[1], 15.0)   # long: 15% stays

    def test_host_zoom_order_is_the_films_own(self):
        import host_from_voice
        orders = {seed: host_from_voice.host_directions(seed, 12) for seed in ('a' * 24, 'b' * 24, 'c' * 24, 'd' * 24)}
        for moves in orders.values():
            self.assertEqual(moves[0], 'zoom_in')                                   # the film opens coming in
            self.assertFalse(any(moves[i] == moves[i + 1] == moves[i + 2] for i in range(10)))
        self.assertGreater(len({tuple(m) for m in orders.values()}), 1)             # films differ
        self.assertEqual(host_from_voice.host_directions('a' * 24, 12), orders['a' * 24])   # one film stays the same
        bases = host_from_voice.host_bases('a' * 24, 20)
        self.assertTrue(all(0 <= b <= 6 for b in bases))
        self.assertTrue(all(abs(x - y) >= 1.5 for x, y in zip(bases, bases[1:])))   # neighbours start differently
        self.assertGreater(len(set(bases)), 3)


if __name__ == '__main__':
    unittest.main()
