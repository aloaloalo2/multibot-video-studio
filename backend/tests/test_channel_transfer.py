import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import channel_transfer as transfer
import store
import author_rules
import channel_voice_lab
import director


class ChannelTransferTests(unittest.TestCase):
    def test_competitors_are_portable_with_saved_names_and_avatars(self):
        source=store.create_channel('Competitor source')
        target=store.create_channel('Competitor target')
        record={'competitors':[{'id':'UC'+'a'*22,'name':'Saved name','url':'https://www.youtube.com/channel/UC'+'a'*22,'icon_url':'data:image/png;base64,YQ=='}]}
        source_path=store.DATA_ROOT/'channels'/source['id']/'competitors.json'
        store.atomic_json(source_path,record)
        raw=transfer.export_bundle(source['id'])
        transfer.import_bundle(target['id'],raw,lambda cid:None)
        self.assertEqual(store.read_json(store.DATA_ROOT/'channels'/target['id']/'competitors.json'),record)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.youtube = self.root / 'channels'
        self.data = self.root / 'data'
        self.youtube.mkdir()
        self.patches = [patch.object(store, 'YOUTUBE_ROOT', self.youtube), patch.object(store, 'DATA_ROOT', self.data),
                        patch.object(store, 'DISABLED_PATH', self.data / 'disabled.json'),
                        patch.object(store, 'GLOBAL_SETTINGS_PATH', self.data / 'settings.json'),
                        patch.object(author_rules, 'writing_rules', return_value='Writing wishes'),
                        patch.object(author_rules, 'claude_memory', return_value='Montage wishes')]
        for p in self.patches: p.start()
        self.source = self.youtube / 'Source'; self.target = self.youtube / 'Target'
        for folder in (self.source, self.target):
            folder.mkdir()
            store.atomic_json(folder / store.PLAN_CONFIG, {'weights': {'animation': 100}, 'thumbnail_wishes': folder.name, 'script_wishes': 'Script wishes for '+folder.name, 'auto_narration':folder==self.source, 'auto_montage':folder==self.source})
        self.cid, self.tid = map(store.channel_id, (self.source, self.target))
        (self.youtube / 'AGENTS.md').write_text('Shared montage wishes')
        (self.source / 'AGENTS.md').write_text('Source channel rules')
        self.cr = self.data / 'channels' / self.cid
        self.cr.mkdir(parents=True)
        for name in ('icon.png', 'logo.png', 'thumbnail-hero.png'): (self.cr / name).write_bytes(name.encode())
        voice = self.cr / 'voice-lab'; voice.mkdir()
        store.atomic_json(voice / 'settings.json', channel_voice_lab.validated({'provider': 'heygen', 'heygen_voice_id': 'exact-remote-id', 'reverb':{'enabled':True,'preset':'office','amount':25}, 'room_noise':{'enabled':True,'preset':'city','amount':35}}))
        (voice / 'reference.mp3').write_bytes(b'same audio')
        store.atomic_json(voice / 'reference.json', {'filename': 'sample.mp3'})
        (voice / 'samples').mkdir(); (voice / 'samples/paid.mp3').write_bytes(b'paid sample excluded')
        store.atomic_json(self.cr / 'episode-ideas.json', {'not': 'settings'})
        (self.source / 'Episode').mkdir(); (self.source / 'Episode/secret.txt').write_text('episode excluded')
        store.atomic_json(self.data / 'agent-channel-memory' / (self.cid + '.json'), {'text': 'Director wishes'})
        (self.source / 'Еталон стилю').mkdir()
        (self.source / 'Еталон стилю/Еталон прев\'ю.png').write_bytes(b'style picture')
        self.stamp = (voice / 'reference.mp3').stat().st_mtime_ns

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def test_roundtrip_settings_rules_voice_identity_and_exclusions(self):
        bundle = transfer.export_bundle(self.cid,include_voice_files=True)
        manifest, files = transfer.read_bundle(bundle)
        self.assertFalse(any('Episode' in n or 'samples' in n or 'episode-ideas' in n for n in files))
        (self.target / 'Episode').mkdir(); keep = self.target / 'Episode/video.mp4'; keep.write_bytes(b'preserve')
        target_root = self.data / 'channels' / self.tid
        store.atomic_json(target_root / 'episode-ideas.json', {'keep': True})
        result = transfer.import_bundle(self.tid, bundle, lambda cid: None)
        self.assertEqual(store.read_channel_settings(self.target), store.read_channel_settings(self.source))
        self.assertEqual(keep.read_bytes(), b'preserve')
        self.assertFalse((self.target / store.PLAN_CONFIG).exists())
        self.assertFalse((self.target / 'AGENTS.md').exists())
        self.assertEqual(store.read_json(target_root / 'episode-ideas.json'), {'keep': True})
        self.assertEqual(store.read_channel_settings(self.target)['script_wishes'], 'Script wishes for Source')
        self.assertIs(store.read_channel_settings(self.target)['auto_narration'],True)
        self.assertIs(store.read_channel_settings(self.target)['auto_montage'],True)
        settings = store.read_json(target_root / 'voice-lab/settings.json')
        self.assertEqual(settings, store.read_json(self.cr / 'voice-lab/settings.json'))
        self.assertEqual(settings['heygen_voice_id'], 'exact-remote-id')
        self.assertEqual((target_root / 'voice-lab/reference.mp3').stat().st_mtime_ns, self.stamp)
        self.assertEqual(store.read_json(target_root / 'voice-lab/reference.json')['clone_owner'], self.cid)
        self.assertEqual(store.channel_rules_source(self.target).read_text(), 'Source channel rules')
        self.assertEqual((self.target / 'Еталон стилю/Еталон прев\'ю.png').read_bytes(), b'style picture')
        self.assertEqual(author_rules.for_channel(self.target, self.youtube)['author_writing_rules'], 'Writing wishes')
        self.assertIn('portable-rules.json', director.channel_memory({'channel_id': self.tid}))
        backups = transfer.list_backups(self.tid)
        self.assertEqual(len(backups), 1)
        self.assertGreater(backups[0]['bytes'], 0)
        restored = transfer.restore_backup(self.tid, result['backup_id'], lambda cid: None)
        self.assertEqual(store.read_channel_settings(self.target)['thumbnail_wishes'], 'Target')
        self.assertEqual(store.read_channel_settings(self.target)['script_wishes'], 'Script wishes for Target')
        self.assertIs(store.read_channel_settings(self.target)['auto_narration'],False)
        self.assertIs(store.read_channel_settings(self.target)['auto_montage'],False)
        self.assertFalse((target_root / 'voice-lab').exists())
        self.assertEqual(keep.read_bytes(), b'preserve')
        transfer.delete_backup(self.tid, result['backup_id'])
        self.assertEqual(len(transfer.list_backups(self.tid)), 1)

    def repack(self, bundle, transform):
        with zipfile.ZipFile(io.BytesIO(bundle)) as z: files = {n: z.read(n) for n in z.namelist()}
        transform(files)
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            for n, raw in files.items(): z.writestr(n, raw)
        return out.getvalue()

    def test_portable_export_has_ids_and_no_voice_audio(self):
        raw=transfer.export_bundle(self.cid)
        manifest,files=transfer.read_bundle(raw)
        self.assertEqual(manifest['version'],2)
        self.assertFalse(any(name.endswith(('.mp3','.wav','.flac')) for name in files))
        transfer.import_bundle(self.tid,raw,lambda cid:None)
        profile=channel_voice_lab.snapshot(self.tid)
        self.assertEqual(profile['settings']['heygen_voice_id'],'exact-remote-id')
        self.assertIsNone(profile['reference'])
        self.assertIsNotNone(channel_voice_lab.effective_reference(self.tid,profile['settings']))

    def test_fish_and_eleven_manual_ids_survive_without_recordings(self):
        s=channel_voice_lab.validated({'provider':'fishaudio','fish_voice_id':'fish-existing','eleven_voice_id':'eleven-existing'})
        store.atomic_json(self.cr/'voice-lab/settings.json',s)
        raw=transfer.export_bundle(self.cid)
        transfer.import_bundle(self.tid,raw,lambda cid:None)
        profile=channel_voice_lab.snapshot(self.tid)
        self.assertEqual(profile['settings']['fish_voice_id'],'fish-existing')
        self.assertEqual(profile['settings']['eleven_voice_id'],'eleven-existing')
        self.assertFalse((transfer._channel_root(self.tid)/'voice-lab/reference.mp3').exists())

    def test_export_requires_an_id_for_a_configured_recording(self):
        store.atomic_json(self.cr/'voice-lab/settings.json',channel_voice_lab.validated({'provider':'fishaudio'}))
        with self.assertRaises(store.StudioError):transfer.export_bundle(self.cid)
        self.assertIsInstance(transfer.export_bundle(self.cid,include_voice_files=True),bytes)

    def test_translation_export_preserves_ids_without_audio_or_transcripts(self):
        version='e'*32;base=self.data/'language-defaults'/self.cid;voice=base/version/'en';voice.mkdir(parents=True)
        audio=voice/'own-voice.mp3';audio.write_bytes(b'private recording');(voice/'own-voice.txt').write_text('private transcript')
        store.atomic_json(voice/'own-voice.json',{'fish_model':'fish-existing','fish_stamp':audio.stat().st_mtime_ns})
        payload={'settings':{'provider':'fishaudio'},'languages':['en'],'voices':{'en':{'clone':'eleven-existing','sha256':'hash','text':'private transcript'}}}
        store.atomic_json(base/'current.json',{'version':version,'payload':payload})
        raw=transfer.export_bundle(self.cid);_,files=transfer.read_bundle(raw)
        self.assertFalse(any('own-voice' in name for name in files))
        self.assertNotIn(b'private transcript',files['languages/current.json'])
        transfer.import_bundle(self.tid,raw,lambda cid:None)
        import language_defaults
        self.assertEqual(language_defaults.remote_ids(self.tid,'en'),{'fishaudio':'fish-existing','elevenlabs':'eleven-existing'})

    def test_global_blacklist_cannot_break_channel_export_or_replace_receiver_settings(self):
        store.update_global_settings({'word_blacklist':['старе слово']})
        raw=transfer.export_bundle(self.cid)
        _,files=transfer.read_bundle(raw)
        self.assertNotIn('studio_word_blacklist',json.loads(files['channel/portable-rules.json'])['author'])
        store.update_global_settings({'word_blacklist':['слово отримувача']})
        transfer.import_bundle(self.tid,raw,lambda cid:None)
        self.assertEqual(store.global_settings()['word_blacklist'],['слово отримувача'])
        self.assertEqual(author_rules.for_channel(self.target,self.youtube)['studio_word_blacklist'],['слово отримувача'])

    def test_rejects_traversal_unknown_members_corruption_and_symlinks(self):
        raw = transfer.export_bundle(self.cid)
        for name in ('../outside', '/tmp/outside', 'channel/../../outside', 'voice/job.json', 'keys.json', 'channel\\icon.png'):
            bad = self.repack(raw, lambda f: f.update({name: b'bad'}))
            with self.subTest(name=name), self.assertRaises(store.StudioError): transfer.read_bundle(bad)
        with self.assertRaises(store.StudioError): transfer.read_bundle(self.repack(raw, lambda f: f.update({'settings.json': b'{}'})))
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            info = zipfile.ZipInfo('channel/icon.png'); info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, 'elsewhere')
        with self.assertRaises(store.StudioError): transfer.read_bundle(out.getvalue())
        outside = self.root / 'outside'; outside.write_text('untouched')
        target_root = self.data / 'channels' / self.tid; target_root.mkdir()
        (target_root / 'icon.png').symlink_to(outside)
        with self.assertRaises(store.StudioError): transfer.import_bundle(self.tid, raw, lambda cid: None)
        self.assertEqual(outside.read_text(), 'untouched')

    def test_busy_import_and_failed_commit_leave_original_settings(self):
        raw = transfer.export_bundle(self.cid)
        def busy(cid): raise store.StudioError('Busy', 409)
        with self.assertRaises(store.StudioError): transfer.import_bundle(self.tid, raw, busy)
        before = store.channel_settings_source(self.target).read_bytes()
        replace = os.replace
        def fail_once(source, target):
            if str(source).endswith('/settings.json') and 'staged-' in str(source):
                raise OSError('simulated full disk')
            return replace(source, target)
        with patch.object(transfer.os, 'replace', side_effect=fail_once), self.assertRaises(OSError):
            transfer.import_bundle(self.tid, raw, lambda cid: None)
        self.assertEqual(store.channel_settings_source(self.target).read_bytes(), before)
        self.assertFalse((self.data / 'channels' / self.tid / 'logo.png').exists())
        self.assertEqual(len(transfer.list_backups(self.tid)), 1)

    def test_eleven_clones_and_translation_mtimes_survive(self):
        account = 'a' * 64; digest = hashlib.sha256(b'same audio').hexdigest()
        key = f'{account}:{self.cid}:en:{digest}'
        entry = {'account': account, 'channel_id': self.cid, 'language': 'en', 'audio_sha256': digest, 'voice_id': 'existing-cloud-voice'}
        store.atomic_json(self.data / 'voice-clones/elevenlabs.json', {'voices': {key: entry}})
        version = 'b' * 32; base = self.data / 'language-defaults' / self.cid
        store.atomic_json(base / 'current.json', {'version': version, 'channel_id': self.cid, 'payload': {'voices': {'en': {'clone': 'voice-id'}}}})
        voice = base / version / 'en'; voice.mkdir(parents=True)
        (voice / 'own-voice.mp3').write_bytes(b'language ref'); (voice / 'own-voice.txt').write_text('text')
        stamp = (voice / 'own-voice.mp3').stat().st_mtime_ns
        store.atomic_json(voice / 'own-voice.json', {'fish_model': 'same-fish-model', 'fish_stamp': stamp})
        raw = transfer.export_bundle(self.cid,include_voice_files=True)
        (self.data / 'voice-clones/elevenlabs.json').unlink()
        transfer.import_bundle(self.tid, raw, lambda cid: None)
        self.assertEqual(store.read_json(self.data / 'voice-clones/elevenlabs.json')['voices'][key], entry)
        copied = self.data / 'language-defaults' / self.tid / version / 'en'
        self.assertEqual((copied / 'own-voice.mp3').stat().st_mtime_ns, stamp)
        self.assertEqual(store.read_json(copied / 'own-voice.json')['fish_stamp'], stamp)
        self.assertEqual(store.read_json(copied.parent.parent / 'current.json')['channel_id'], self.tid)

if __name__ == '__main__': unittest.main()
