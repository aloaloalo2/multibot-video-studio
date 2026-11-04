import sys,tempfile,unittest,subprocess,json,shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import eleven_voices,store

class ElevenVoiceReuseTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        p=patch.object(store,'DATA_ROOT',Path(self.temp.name));p.start();self.addCleanup(p.stop)

    def test_same_audio_reuses_clone_across_file_copies_and_repeated_calls(self):
        create=Mock(return_value='first')
        self.assertEqual(eleven_voices.resolve('key','channel','pl',b'same recording',None,create),'first')
        self.assertEqual(eleven_voices.resolve('key','channel','pl',b'same recording',None,create),'first')
        create.assert_called_once_with(1)

    def test_account_channel_language_and_changed_audio_are_isolated(self):
        create=Mock(side_effect=['one','two','three','four','five'])
        for args,want in [(('key','c','pl',b'a'),'one'),(('other-key','c','pl',b'a'),'two'),
                          (('key','other-channel','pl',b'a'),'three'),(('key','c','uk',b'a'),'four'),
                          (('key','c','pl',b'b'),'five')]:
            self.assertEqual(eleven_voices.resolve(*args,None,create),want)
        self.assertEqual(create.call_args.args,(2,))

    def test_existing_clone_is_registered_without_uploading(self):
        create=Mock(side_effect=AssertionError('do not upload'))
        self.assertEqual(eleven_voices.resolve('key','c','es',b'a','existing-id',create),'existing-id')
        self.assertEqual(eleven_voices.resolve('key','c','es',b'a',None,create),'existing-id')
        create.assert_not_called()

    def test_verified_full_recording_alias_reuses_legacy_clone_in_other_projects(self):
        create=Mock(side_effect=AssertionError('do not upload'))
        eleven_voices.resolve('key','c','uk',b'old reference','existing-id',create)
        # A separately verified full upload can be linked to its former shortened
        # reference. Future projects need neither that old file nor another upload.
        eleven_voices.resolve('key','c','uk',b'full reference','existing-id',create)
        self.assertEqual(eleven_voices.resolve('key','c','uk',b'full reference',None,create),'existing-id')
        create.assert_not_called()

    def test_parallel_projects_create_only_one_clone_for_the_same_reference(self):
        create=Mock(return_value='shared')
        with ThreadPoolExecutor(max_workers=4) as pool:
            result=list(pool.map(lambda _:eleven_voices.resolve('key','c','pl',b'a',None,create),range(8)))
        self.assertEqual(result,['shared']*8)
        create.assert_called_once()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'needs ffmpeg')
class ElevenUploadTest(unittest.TestCase):
    def test_instant_clone_uses_one_compact_sample_and_preserves_a_long_source(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'full.mp3'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=1201',
                            '-ar','44100','-ac','1','-b:a','192k',str(source)],check=True)
            before=source.read_bytes()
            self.assertGreater(len(before),eleven_voices.UPLOAD_BYTES*eleven_voices.UPLOAD_FILES)
            parts=eleven_voices.clone_files(source,folder/'upload')
            self.assertEqual(len(parts),1)
            self.assertLess(parts[0].stat().st_size,eleven_voices.UPLOAD_BYTES)
            self.assertAlmostEqual(store.media_duration(parts[0]),70,delta=.15)
            self.assertEqual(source.read_bytes(),before)
            subprocess.run(['ffmpeg','-v','error','-i',str(parts[0]),'-f','null','-'],check=True,capture_output=True)

    def test_video_input_is_encoded_as_mp3_and_quiet_intro_is_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'reference.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=100',
                            '-af','adelay=30000','-c:a','aac',str(source)],check=True)
            before=source.read_bytes()
            parts=eleven_voices.clone_files(source,folder/'upload')
            self.assertEqual(len(parts),1)
            self.assertEqual(parts[0].suffix,'.mp3')
            self.assertLess(parts[0].stat().st_size,eleven_voices.UPLOAD_BYTES)
            self.assertGreaterEqual(json.loads((folder/'upload'/'preparation.json').read_text())['start'],30)
            self.assertEqual(source.read_bytes(),before)

    def test_long_mp3_is_sent_whole_without_reencoding_or_oversize_files(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'full.mp3'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=121',
                            '-ar','44100','-ac','1','-b:a','160k',str(source)],check=True)
            before=source.read_bytes()
            parts=eleven_voices.upload_files(source,folder/'upload')
            self.assertGreater(len(parts),1)
            self.assertTrue(all(0<p.stat().st_size<=900_000 for p in parts))
            def packets(path):
                raw=subprocess.check_output(['ffprobe','-v','error','-select_streams','a:0','-show_packets',
                    '-show_entries','packet=data_hash','-show_data_hash','sha256','-of','json',str(path)])
                return [p['data_hash'] for p in json.loads(raw)['packets']]
            self.assertEqual([packet for part in parts for packet in packets(part)],packets(source))
            self.assertEqual(source.read_bytes(),before)
            for part in parts:
                subprocess.run(['ffmpeg','-v','error','-i',str(part),'-f','null','-'],check=True,capture_output=True)

    def test_small_prepared_mp3_keeps_its_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'voice.mp3'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=6',str(source)],check=True)
            self.assertEqual(eleven_voices.upload_files(source,folder/'unused'),[source])
            self.assertFalse((folder/'unused').exists())

    def test_too_many_samples_stop_locally_before_splitting_and_keep_the_full_source(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'full.mp3'
            source.write_bytes(b'preserved full audio' * 2000)
            before=source.read_bytes()
            with patch.object(store,'media_duration',return_value=1605), \
                 patch.object(eleven_voices.subprocess,'run') as split:
                with self.assertRaisesRegex(RuntimeError,'до 25 аудіофрагментів'):
                    eleven_voices.upload_files(source,folder/'upload',max_bytes=1000)
            split.assert_not_called()
            self.assertEqual(source.read_bytes(),before)
            self.assertFalse((folder/'upload').exists())

    def test_near_count_limit_keeps_full_recording_in_at_most_25_files(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'full.mp3'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=60',
                            '-ar','44100','-ac','1','-b:a','160k',str(source)],check=True)
            before=source.read_bytes()
            parts=eleven_voices.upload_files(source,folder/'upload',max_bytes=50_000)
            self.assertEqual(len(parts),25)
            self.assertTrue(all(0<p.stat().st_size<=50_000 for p in parts))
            self.assertAlmostEqual(sum(store.media_duration(p) for p in parts),store.media_duration(source),delta=1.5)
            self.assertEqual(source.read_bytes(),before)
