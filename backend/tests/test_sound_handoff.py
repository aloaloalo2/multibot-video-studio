"""Inspect actual author handoffs with model calls replaced; no generation or paid requests."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_runtime
import director
import production
import razgon_export
import sound_settings
import store


class SoundHandoffTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.channel = self.root / 'Channel'
        (self.channel / 'Episode').mkdir(parents=True)
        self.animated = False
        self.project = {'id': 'a'*24, 'channel_id': 'b'*16, 'name': 'Episode',
                        'episode_path': str(self.channel / 'Episode'), 'tracks': [{'id': 'base', 'clips': []}],
                        'production_request': {'id': 'request', 'frames': 3, 'total_frames': 3, 'start': 0, 'end': 6}}
        self.plan = {'frames': [{'number': n, 'start': (n-1)*2, 'end': n*2} for n in range(1,4)]}
        for item in (patch.object(store, 'DATA_ROOT', self.root / 'data'),
                     patch.object(store, 'YOUTUBE_ROOT', self.root),
                     patch.object(store, 'get_channel_folder', return_value=self.channel),
                     patch.object(store, 'project_dir', return_value=self.root),
                     patch.object(store, 'load_project', side_effect=lambda pid: copy.deepcopy(self.project)),
                     patch.object(store, 'save_project', side_effect=lambda value: self.project.update(value)),
                     patch.object(store, 'load_project_plan', return_value=self.plan),
                     patch.object(store, 'made_frames', return_value=[]),
                     patch.object(store, 'project_animated', side_effect=lambda project: self.animated),
                     patch.object(director, 'channel_memory', return_value='')):
            item.start(); self.addCleanup(item.stop)
        self.addCleanup(agent_runtime.JOBS.clear)
        self.addCleanup(production.ACTIVE.clear)

    def save_sound(self, value):
        store.atomic_json(store.channel_settings_path(self.channel), {'sound': value})

    def test_director_gets_latest_saved_sound_instead_of_project_snapshot(self):
        self.project['settings'] = {'sound': {'music': {'enabled': True}}}
        for animated in (False, True):
            self.animated = animated
            for enabled in (False, True):
                self.save_sound({'music': {'enabled': enabled, 'generate': enabled},
                                 'effects': {'enabled': False}, 'library': {'enabled': False, 'ids': []}})
                with patch.object(director, 'claude', return_value=(1, {'result': 'Audit only'})) as model:
                    director.run(self.project['id'], Path('unused-claude'))
                text = model.call_args.args[1]
                self.assertIn('ЗВУК РОЛИКА', text)
                self.assertIn('Використовуй фонову музику' if enabled else 'Музика вимкнена', text)
                self.assertIn('Звукові ефекти й атмосферу вимкнено', text)

    def test_creation_batches_get_sound_workflow_and_repairs_preserve_existing_audio(self):
        self.save_sound({'music': {'enabled': True}, 'effects': {'categories': ['notification']}})
        for animated in (False, True):
            self.animated = animated
            for repair in (False, True):
                self.project['production_request'] = {'id': 'request', 'frames': 3, 'total_frames': 3, 'start': 0, 'end': 6,
                    **({'repair_frames': [2], 'task_notes': 'Change the picture'} if repair else {})}
                with patch.object(production, 'drawn', return_value=True), \
                     patch.object(production.production_quality, 'check', return_value={'passed': True, 'errors': []}), \
                     patch.object(production.production_context, 'write', return_value=(self.root/'context.json', 'Audit map')), \
                     patch.object(production.logo_layer, 'place'), patch.object(production.razgon_sound, 'start'), \
                     patch.object(director, 'claude', return_value=(0, {'result': 'Audit complete'})) as model:
                    production.run(self.project['id'], Path('unused-claude'))
                self.assertTrue(model.called)
                text = model.call_args.args[1]
                self.assertIn('ЗВУК РОЛИКА', text)
                self.assertEqual('Це правка кадрів: наявний звук збережи' in text, repair)
                self.assertEqual('після створення кадрів один раз використай /ops' in text, not repair)

    def test_studio_agent_gets_current_choices_in_both_plan_modes(self):
        for mode in ('director', 'direct'):
            for enabled in (False, True):
                self.save_sound({'music': {'enabled': enabled}, 'effects': {'enabled': False}, 'library': {'enabled': False}})
                agent_runtime.JOBS[self.project['id']] = {'status': 'queued'}
                with patch.object(store, 'project_plan_mode', return_value=mode), \
                     patch.object(agent_runtime.agent_storage, 'get_conversation', return_value={'messages': []}), \
                     patch.object(agent_runtime.agent_storage, 'get_memory', return_value=''), \
                     patch.object(agent_runtime.agent_storage, 'add_message'), \
                     patch.object(agent_runtime.agent_openrouter, 'chat', return_value={'content': 'Audit only'}) as model:
                    agent_runtime.worker(self.project['id'], 'Audit', {}, False, Mock(), 'high')
                self.assertEqual(agent_runtime.JOBS[self.project['id']]['status'], 'complete')
                text = model.call_args.args[1][0]['content']
                self.assertIn('Використовуй фонову музику' if enabled else 'Музика вимкнена', text)

    def test_examples_only_suggest_enabled_work_and_selected_sound_names(self):
        self.save_sound({'music': {'enabled': False}, 'effects': {'enabled': False}, 'library': {'enabled': False}})
        text = sound_settings.instructions(self.project)
        self.assertNotIn('"op": "soundtrack"', text)
        self.save_sound({'music': {'enabled': True, 'generate': False}, 'effects': {'categories': ['tick']}})
        text = sound_settings.instructions(self.project)
        example = json.loads(text.split('операцію soundtrack: ', 1)[1].split('. Постав події', 1)[0])
        self.assertFalse(example['music'])
        self.assertEqual(example['cues'], [{'name': 'tick', 't': 12.5}])

    def test_export_handoff_includes_current_channel_choices(self):
        choice = {'music': {'enabled': False}, 'effects': {'enabled': False}, 'library': {'enabled': False, 'ids': []}}
        self.save_sound(choice)
        with patch.object(store, 'razgon_link', return_value={'project': str(self.root)}), \
             patch.object(razgon_export.razgon_live, 'link', return_value={'project': self.root}), \
             patch.object(razgon_export, 'canonicalize_legacy_blocks'), \
             patch.object(razgon_export, '_film', return_value={'clips': {'1': None}}):
            spec = razgon_export.export_job(self.project)
        self.assertEqual(spec['sound_policy'], {'sound': choice, 'animated': False})


if __name__ == '__main__':
    unittest.main()
