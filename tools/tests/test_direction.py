import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('direction_cli', TOOLS / 'direction.py')
direction = importlib.util.module_from_spec(spec)
spec.loader.exec_module(direction)


class DirectionToolTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.rz = self.root/'project'
        for name in ['story', 'build', 'timeline']:
            (self.rz/name).mkdir(parents=True)
        self.project = {'id':'p'*24, 'channel_id':'c'*16, 'project_kind':'animated',
                        'name':'Fixture', 'episode_path':str(self.root/'Channel/Episode')}
        self.plan = {'script_sha256':'speech','frames':[{'number':1}],
                     'timing':{'status':'audio_synced','audio':{'duration':12,'sha256':'voice'},
                               'sentences':[{'start':0,'end':12,'text':'The ship drifts past the distant planet.'}]}}
        self.config = {'duration':12,'fps':25,'music':{'enabled':False},
                       'sfx':{'enabled':False,'allowed_names':[]}}
        self.original = '{"duration": 12, "shots": []}\n'
        (self.rz/'story/shots.json').write_text(self.original)
        (self.rz/'config.json').write_text(json.dumps(self.config))
        (self.rz/'story/studio_frames.json').write_text('{}')
        self.words = []
        self.packet = direction.contract.source(self.plan,self.config,self.words)
        self.file = self.rz/'story/direction.json'
        self.draft = {'source_signature':self.packet['signature'], 'bible':'One continuous orbital take.',
                      'shots':[{'id':'s1','first_sentence':1,'last_sentence':1,'episode':'E1','set':'orbit',
                                'scene':'The small ship passes the blue planet.'}], 'music':[]}
        self.file.write_text(json.dumps(self.draft))
        self.studio = SimpleNamespace(url='http://fixture', project=Mock(side_effect=lambda pid:copy.deepcopy(self.project)),
                                      plan=Mock(side_effect=lambda pid:copy.deepcopy(self.plan)))
        self.packet_for_impl=direction.packet_for
        for p in (patch.object(direction.store,'project_dir',return_value=self.root),
                  patch.object(direction,'workspace',return_value=self.rz),
                  patch.object(direction,'packet_for',side_effect=lambda *args:(copy.deepcopy(self.packet),self.words))):
            p.start();self.addCleanup(p.stop)
        direction.store.atomic_json(self.root/'director-context.json',self.packet)

    def test_one_apply_checks_once_and_imports_once_without_generators_or_model_calls(self):
        def imported(args):
            self.plan.update(frame_source='razgon-direction',frames=[{'number':1,'start':0,'end':12}])
        with patch.object(direction,'staged_check',return_value='0 FAIL') as check, \
             patch.object(direction.bridge,'plan_from_direction',side_effect=imported) as publish:
            direction.apply(self.studio,self.project['id'],self.file)
            direction.apply(self.studio,self.project['id'],self.file)
        check.assert_called_once()
        publish.assert_called_once()
        self.assertFalse((self.rz/'story/gen_shots.py').exists())
        self.assertFalse((self.rz/'story/gen_sound.py').exists())
        self.assertTrue((self.root/'director-apply.json').is_file())

    def test_dry_run_and_failed_check_preserve_all_original_files_and_timeline(self):
        for dry_run, failure in [(True,None),(False,ValueError('bad continuity'))]:
            with patch.object(direction,'staged_check',return_value='ok',side_effect=failure), \
                 patch.object(direction.bridge,'plan_from_direction') as publish:
                if failure:
                    with self.assertRaises(ValueError):direction.apply(self.studio,self.project['id'],self.file,dry_run=dry_run)
                else: direction.apply(self.studio,self.project['id'],self.file,dry_run=dry_run)
                publish.assert_not_called()
            self.assertEqual((self.rz/'story/shots.json').read_text(),self.original)
            self.assertFalse((self.rz/'story/beats.json').exists())

    def test_generated_direction_imports_through_the_real_bridge(self):
        self.project.update(fps=25, tracks=[{'id':'base','clips':[]}],scene_groups=[])
        self.plan['frames']=[{'number':1,'start':0,'end':12,'format':'razgon_2d',
            'sentences':[self.plan['timing']['sentences'][0]['text']],
            'sentence_timings':[{'number':1,**self.plan['timing']['sentences'][0]}]}]
        link={'project_id':self.project['id'],'studio_url':'http://fixture','fps':25,'duration':12,
              'script_sha256':'speech','frames':copy.deepcopy(self.plan['frames'])}
        (self.rz/'story/studio_frames.json').write_text(json.dumps(link))
        def call(method, path, body=None):
            if method=='POST' and path.endswith('/plan'):
                self.plan.clear();self.plan.update(copy.deepcopy(body['plan']))
                return {}
            if path=='/api/channels':return {'channels':[]}
            return {'project':copy.deepcopy(self.project),'production':{'plan_ready':True}}
        def batch(project, actions):
            clips=project['tracks'][0]['clips']
            for n, action in enumerate(actions):
                value=action['payload']
                if action['type']=='add_clip':clips.append({**value,'id':'clip'+str(n)})
                elif action['type']=='group_clips':project['scene_groups'].append(value)
            self.project.update(copy.deepcopy(project))
            return project
        self.studio.call=Mock(side_effect=call)
        self.studio.batch=Mock(side_effect=batch)
        with patch.object(direction,'staged_check',return_value='0 FAIL'), \
             patch.object(direction.bridge,'Studio',return_value=self.studio):
            direction.apply(self.studio,self.project['id'],self.file)
        self.assertEqual(self.plan['frame_source'],'razgon-direction')
        self.assertEqual(self.plan['frames'][0]['sentences'],[self.plan['timing']['sentences'][0]['text']])
        self.assertEqual(self.plan['frames'][0]['end'],12)
        self.assertEqual(self.project['tracks'][0]['clips'][0]['kind'],'animation')
        self.assertEqual(len(self.project['scene_groups']),1)

    def test_source_change_before_or_during_checks_never_commits_or_imports(self):
        changed={**self.packet,'signature':'changed'}
        for values in ([changed],[self.packet,changed]):
            with patch.object(direction,'packet_for',side_effect=[(v,self.words) for v in values]), \
                 patch.object(direction,'staged_check',return_value='ok'), \
                 patch.object(direction.bridge,'plan_from_direction') as publish:
                with self.assertRaises(ValueError):direction.apply(self.studio,self.project['id'],self.file)
                publish.assert_not_called()
            self.assertEqual((self.rz/'story/shots.json').read_text(),self.original)

    def test_live_channel_style_change_invalidates_a_packet_before_workspace_sync(self):
        style={'style':'neon','assets':True,'allow_stickmen':False}
        original=(self.rz/'config.json').read_bytes()
        with patch.object(direction.store,'get_channel_folder',return_value=self.root/'Channel'), \
             patch.object(direction.store,'read_channel_settings',side_effect=lambda *args:{
                 'animation':copy.deepcopy(style),'sound':{'music':{'enabled':False},'effects':{'enabled':False}}}):
            first,_=self.packet_for_impl(self.project,self.plan,self.rz)
            style['style']='care'
            second,_=self.packet_for_impl(self.project,self.plan,self.rz)
        self.assertNotEqual(first['signature'],second['signature'])
        self.assertEqual((self.rz/'config.json').read_bytes(),original)

    def test_active_frame_work_and_existing_direction_are_not_rebuilt(self):
        self.project['production_request']={'status':'in_progress'}
        with patch.object(direction.bridge,'prepare') as prepare:
            with self.assertRaisesRegex(ValueError,'працює'):
                direction.apply(self.studio,self.project['id'],self.file)
            with self.assertRaises(ValueError): direction.prepare(self.studio,self.project['id'])
            prepare.assert_not_called()
        self.project.pop('production_request')
        self.plan.update(frame_source='razgon-direction')
        with patch.object(direction,'staged_check') as check, \
             patch.object(direction.bridge,'plan_from_direction') as publish:
            with self.assertRaisesRegex(ValueError,'прийнятий'):
                direction.apply(self.studio,self.project['id'],self.file)
            check.assert_not_called()
            publish.assert_not_called()
        with patch.object(direction.bridge,'prepare') as prepare:
            with self.assertRaises(ValueError): direction.prepare(self.studio,self.project['id'])
            prepare.assert_not_called()

    def test_prepare_returns_one_complete_packet_without_writing_author_direction(self):
        with patch.object(direction.bridge,'prepare') as prepare:
            result=direction.prepare(self.studio,self.project['id'])
        prepare.assert_called_once()
        self.assertEqual(result,self.root/'director-context.txt')
        text=result.read_text()
        self.assertEqual(text.count(self.plan['timing']['sentences'][0]['text']),1)
        self.assertEqual((self.rz/'story/shots.json').read_text(),self.original)
        self.assertEqual(json.loads(self.file.read_text()),self.draft)

    def test_staged_validation_does_not_render_or_write_to_the_live_story(self):
        self.config.update(music={'enabled':False,'generate':False})
        compiled=direction.contract.compile_direction(self.draft,self.packet,self.words)
        with patch.object(direction.bridge,'check_project',return_value=[]), \
             patch.object(direction.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='0 FAIL',stderr='')) as run:
            result=direction.staged_check(self.rz,compiled)
        self.assertEqual(result,'0 FAIL')
        command=run.call_args.args[0]
        self.assertTrue(command[1].endswith('/tools/direction_check.py'))
        self.assertNotEqual(Path(command[-1]),self.rz)
        self.assertNotIn('render.mjs',command)
        self.assertEqual((self.rz/'story/shots.json').read_text(),self.original)

    def test_partial_disk_write_rolls_back_previous_files_exactly(self):
        a,b=self.root/'a.txt',self.root/'b.txt'
        a.write_text('old\n');b.write_text('before')
        original=direction.store.atomic_text
        def write(path,value):
            if path==b:raise OSError('disk full')
            return original(path,value)
        with patch.object(direction.store,'atomic_text',side_effect=write):
            with self.assertRaises(OSError):direction.commit_files({a:'new',b:'other'})
        self.assertEqual(a.read_text(),'old\n')
        self.assertEqual(b.read_text(),'before')
