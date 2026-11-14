import array
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[2]/'engine')]
import narration_revision as revision
import narration_sequence
import project_narration as narration
import store


class RevisionTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.pid='a'*24
        self.oldtext='First sentence has one word. Second sentence stays unchanged. Third sentence also stays.'
        self.newtext=self.oldtext.replace('one word','a word')
        self.settings=revision.lab.validated({'provider':'heygen','heygen_voice_id':'original-voice'})
        self.ref=revision.lab.effective_reference('c'*16,self.settings)
        self.source=self.root/'original.wav'
        self.write_wave(self.source,[300]*8000+[600]*8000+[900]*8000)
        self.asset={'id':'old-audio','path':str(self.source),'duration':3,'kind':'audio'}
        self.project={'id':self.pid,'channel_id':'c'*16,'revision':7,'assets':[self.asset],
                      'voice_script':{'text':self.oldtext},'tracks':[{'clips':[{'id':'voice','kind':'audio','asset_id':self.asset['id'],'duration':3}]}]}
        self.job={'status':'done','script':self.oldtext,'asset_id':self.asset['id'],'render_settings':self.settings}
        self.rows=[{'text':part,'key':revision.lab.fingerprint({**self.settings,'text':part},self.ref)} for part in narration.phrases(self.oldtext)]
        self.proof={'version':2,'source':'generated_takes','sentence_timings':[{'start':i,'end':i+1} for i in range(3)]}
        for stub in [patch.object(store,'project_dir',return_value=self.root),patch.object(store,'load_project',side_effect=lambda pid:copy.deepcopy(self.project)),
                     patch.object(narration,'ACTIVE',set()),patch.object(revision.lab,'NARRATIONS',{}),patch.object(narration,'HEYGEN_QUEUE',[])]:
            stub.start();self.addCleanup(stub.stop)
        import shutil
        shutil.copy2(self.source,narration.root(self.pid)/'speed-original.mp3')
        store.atomic_json(narration.root(self.pid)/'speed-original.json',{'speed':self.settings['speed']})
        store.atomic_json(narration.root(self.pid)/'job.json',self.job)
        store.atomic_json(narration.root(self.pid)/'phrases.json',self.rows)

    @staticmethod
    def write_wave(path,samples):
        with wave.open(str(path),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(array.array('h',samples).tobytes())

    def prepare(self,text=None):
        with patch.object(narration_sequence,'verify',return_value=self.proof):
            return revision.prepare(self.pid,text or self.newtext,revision.digest(self.oldtext))

    def test_one_edit_uses_recorded_voice_and_exact_existing_slot(self):
        with patch.object(revision.lab,'snapshot',side_effect=AssertionError('Must not read current channel voice')):
            ctx=self.prepare()
        self.assertEqual(ctx['changed'],[0])
        self.assertEqual(ctx['settings']['heygen_voice_id'],'original-voice')
        self.assertEqual(ctx['timings'][0],{'start':0,'end':1})

    def test_sentence_count_and_concurrent_source_changes_fail_before_synthesis(self):
        with self.assertRaises(store.StudioError):self.prepare(self.newtext+' Added fourth sentence.')
        with self.assertRaises(store.StudioError):revision.prepare(self.pid,self.newtext,'stale-hash')
        self.assertEqual(store.read_json(narration.root(self.pid)/'job.json')['asset_id'],'old-audio')

    def test_splicing_keeps_every_unchanged_sample_and_total_duration(self):
        replacement=self.root/'replacement.wav';target=self.root/'patched.wav'
        self.write_wave(replacement,[-400]*8000)
        revision.splice(self.source,target,[(1,2,replacement)])
        with wave.open(str(self.source),'rb') as a,wave.open(str(target),'rb') as b:
            before=a.readframes(a.getnframes());after=b.readframes(b.getnframes())
        self.assertEqual(before[:16000],after[:16000]);self.assertEqual(before[32000:],after[32000:])
        self.assertEqual(after[16000:32000],array.array('h',[-400]*8000).tobytes())
        self.assertEqual(len(before),len(after))

    def test_provider_failure_never_replaces_script_audio_or_plan(self):
        ctx=self.prepare();job={'id':'revision-test','status':'running','total':1}
        narration.ACTIVE.add(self.pid)
        with patch.object(revision.languages,'run',side_effect=lambda command,*_:revision.write_wave(Path(command[-1]),[0]*24000)), \
             patch.object(narration,'wait_heygen'),patch.object(narration,'phrase_audio',side_effect=RuntimeError('Provider unavailable')), \
             patch.object(store,'save_project') as save:
            revision.run(self.pid,ctx,job)
        save.assert_not_called()
        self.assertEqual(job['status'],'failed');self.assertNotIn(self.pid,narration.ACTIVE)
        self.assertEqual(store.read_json(narration.root(self.pid)/'job.json')['script'],self.oldtext)

    def test_success_synthesizes_only_changed_sentence_and_preserves_other_pcm(self):
        ctx=self.prepare();job={'id':'successful-edit','status':'running','total':1}
        replacement=self.root/'take.wav';self.write_wave(replacement,[-400]*8000)
        def imported(project,path,kind):
            asset={'id':'updated-audio','path':str(path),'duration':store.media_duration(path),'kind':'audio'}
            self.project['assets'].append(asset)
            return asset
        with patch.object(narration,'wait_heygen'),patch.object(narration,'phrase_audio',return_value=replacement) as paid, \
             patch.object(store,'import_asset_file',side_effect=imported), \
             patch.object(store,'save_project',side_effect=lambda value:self.project.update(copy.deepcopy(value))), \
             patch.object(store,'load_project_plan',return_value={'script':self.oldtext,'frames':[],'timing':{}}):
            revision.run(self.pid,ctx,job)
        self.assertEqual(job['status'],'done',job.get('error'))
        paid.assert_called_once()
        self.assertEqual(paid.call_args.args[3]['text'],narration.phrases(self.newtext)[0])
        self.assertEqual(self.project['tracks'][0]['clips'][0]['asset_id'],'updated-audio')
        self.assertEqual(self.project['voice_script']['text'],self.newtext)
        updated=Path(self.project['assets'][-1]['path']);decoded=self.root/'decoded.wav'
        revision.languages.run(['ffmpeg','-v','error','-y','-i',str(updated),'-c:a','pcm_s16le',str(decoded)],'test decode')
        with wave.open(str(self.source),'rb') as a,wave.open(str(decoded),'rb') as b:
            before=a.readframes(a.getnframes());after=b.readframes(b.getnframes())
        self.assertEqual(before[16000:],after[16000:])
        self.assertNotEqual(before[:16000],after[:16000])
        self.assertEqual(len(before),len(after))
        self.assertIsNotNone(narration_sequence.verify(self.project,self.project['assets'][-1],self.newtext))

    def test_duplicate_click_does_not_start_another_worker(self):
        body={'client_id':'request-123','text':self.newtext,'expected_sha256':revision.digest(self.oldtext)}
        with patch.object(narration_sequence,'verify',return_value=self.proof),patch.object(revision.threading,'Thread') as thread:
            revision.start(self.pid,body);revision.start(self.pid,body)
        self.assertEqual(thread.call_count,1)
        narration.ACTIVE.discard(self.pid);narration.release_heygen(self.pid)

    def test_plan_text_updates_preserve_frame_ids_and_all_timings(self):
        ctx=self.prepare()
        plan={'script':self.oldtext,'timing':{'sentences':[{'text':self.rows[0]['text'],'start':0,'end':1}]},
              'frames':[{'number':4,'start':0,'end':1,'sentences':[self.rows[0]['text']],'sentence_timings':[{'text':self.rows[0]['text'],'start':0,'end':1}]}]}
        result=revision.patched_plan(plan,ctx,self.asset)
        self.assertEqual(result['frames'][0]['sentences'],[narration.phrases(self.newtext)[0]])
        self.assertEqual(result['frames'][0]['number'],4);self.assertEqual(result['frames'][0]['end'],1)
        self.assertEqual(plan['script'],self.oldtext)

    def test_razgon_voice_sync_keeps_scenes_frames_and_config_unchanged(self):
        root=self.root/'animation';(root/'story').mkdir(parents=True);(root/'input').mkdir()
        config={'voiceover':'input/voiceover.flac','style':'neon'}
        link={'project_id':self.pid,'script_sha256':'old','audio_sha256':'old-audio','frames':[{'number':1,'start':0,'end':3}]}
        store.atomic_json(root/'config.json',config);store.atomic_json(root/'story/studio_frames.json',link)
        store.atomic_json(self.root/'razgon-link.json',{'project':str(root)})
        revision.sync_razgon_voice(self.project,{'script_sha256':'new'},self.asset)
        updated=store.read_json(root/'story/studio_frames.json')
        self.assertEqual(updated['frames'],link['frames'])
        self.assertEqual(updated['script_sha256'],'new');self.assertEqual(updated['voice_asset_id'],self.asset['id'])
        self.assertEqual(store.read_json(root/'config.json'),config)
        self.assertEqual((root/'input/voiceover.flac').read_bytes(),self.source.read_bytes())

    def test_digitized_plan_remains_valid_after_revoicing(self):
        import planner
        old='Сначала возьмём двадцать граммов соли. Затем добавим два литра воды. После этого всё перемешаем.'
        new=old.replace('двадцать','девятнадцать')
        before=narration.phrases(old);parts=narration.phrases(new)
        timings=[{'text':text,'start':i,'end':i+1} for i,text in enumerate(before)]
        plan=planner.digitize_synced_plan(planner.build_plan(old,{'weights':{'text':100}},'Fixture',duration=3,alignment=timings))
        planner.validate_synced_plan(plan,3)
        ctx={'text':new,'before':before,'parts':parts,'changed':[0]}
        updated=revision.patched_plan(plan,ctx,self.asset)
        planner.validate_synced_plan(updated,3)
        self.assertIn('19 граммов',updated['script'])
        self.assertIn('девятнадцать',updated['spoken_script'])
        self.assertEqual([(f['start'],f['end']) for f in updated['frames']],[(f['start'],f['end']) for f in plan['frames']])

    def test_repeated_sentence_edit_changes_only_its_numbered_occurrence(self):
        ctx={'text':'Changed sentence. Repeated sentence.','before':['Repeated sentence.','Repeated sentence.'],
             'parts':['Changed sentence.','Repeated sentence.'],'changed':[0]}
        plan={'frames':[{'number':1,'sentences':['Repeated sentence.'],'sentence_timings':[{'number':1,'text':'Repeated sentence.','start':0,'end':1}]},
                        {'number':2,'sentences':['Repeated sentence.'],'sentence_timings':[{'number':2,'text':'Repeated sentence.','start':1,'end':2}]}]}
        updated=revision.patched_plan(plan,ctx,self.asset)
        self.assertEqual(updated['frames'][0]['sentences'],['Changed sentence.'])
        self.assertEqual(updated['frames'][1]['sentences'],['Repeated sentence.'])

    def test_revision_proof_is_bound_to_audio_and_exact_script(self):
        job={**self.job,'revision_id':'revision-test'}
        store.atomic_json(narration.root(self.pid)/'job.json',job)
        proof={**self.proof,'source':'revised_takes','revision_id':job['revision_id'],'audio_sha256':store.audio_fingerprint(self.source),'script_sha256':revision.digest(self.oldtext)}
        store.atomic_json(narration.root(self.pid)/'revisions/revision-test/proof.json',proof)
        self.assertEqual(narration_sequence.verify(self.project,self.asset,self.oldtext),proof)
        proof['audio_sha256']='wrong';store.atomic_json(narration.root(self.pid)/'revisions/revision-test/proof.json',proof)
        self.assertIsNone(narration_sequence.verify(self.project,self.asset,self.oldtext))
