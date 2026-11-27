import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import montage_context as context
import author_rules
import director
import store


class MontageContextTest(unittest.TestCase):
    def test_only_writing_sections_are_removed_and_unknown_requirements_survive(self):
        source = ('General standing instruction.\n\n## Сценарии и зачины\nWrite four openings.\n'
                  '## PNG и экранный текст\nKeep arrows attached.\n'
                  '## Неизвестное требование\nKeep this unique wish.\n')
        result = context.sections(source)
        self.assertNotIn('Write four openings', result)
        for text in ['General standing instruction', 'Keep arrows attached', 'Keep this unique wish']:
            self.assertIn(text, result)

    def test_only_frame_production_skips_upstream_director_and_writer_history(self):
        text='## Карта ролика в VideoKey Studio\nHistorical director task.\n## Монтаж\nPlace the props accurately.'
        self.assertIn('Historical director task',context.sections(text))
        self.assertEqual(context.sections(text,production=True),'## Монтаж\nPlace the props accurately.')

    def test_current_channel_and_shared_rules_are_deduplicated_without_touching_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shared = '## Монтаж\nKeep the complete unique instruction.\n'
            (root/'AGENTS.md').write_text(shared + '## Сценарии\nOnly the writer needs this.\n')
            own = root/'channel.md'
            own.write_text(shared + '## Особое правило\nPreserve exact author wording.\n')
            project = {'episode_path':str(root/'channel'/'episode')}
            with patch.object(store,'YOUTUBE_ROOT',root), patch.object(store,'channel_rules_source',return_value=own):
                result = context.rules(project)
            self.assertEqual(result.count('Keep the complete unique instruction.'), 1)
            self.assertIn('Preserve exact author wording.', result)
            self.assertNotIn('Only the writer', result)
            self.assertIn('Only the writer', (root/'AGENTS.md').read_text())

    def test_montage_memory_does_not_change_writer_memory_or_lose_visual_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'what-if-scripts.md').write_text('## Сценарии What If\nOnly openings.\n')
            (root/'what-if-frames.md').write_text('## Кадры What If\nKeep natural proportions.\n')
            with patch.object(author_rules,'MEMORY',root):
                writer=author_rules.claude_memory('What If')
                montage=author_rules.claude_memory('What If',montage_only=True)
            self.assertIn('Only openings',writer)
            self.assertNotIn('Only openings',montage)
            self.assertIn('Keep natural proportions',montage)

    def test_commands_have_concrete_scope_without_shell_chains_or_permission_bypass(self):
        with patch('frame_progress.razgon_project',return_value=Path('/workspace/a film')), \
             patch.object(store,'load_project_plan',return_value={'frames':[{'number':4},{'number':7}]}):
            result=context.commands({'id':'fixture'},[4,7])
        commands=[s for s in result.splitlines() if s.startswith('python3 ')]
        checks=[s for s in result.splitlines() if s.startswith('nice -n 10 node ')]
        # the pictures are looked at once at the end of the film: a batch places its frames and runs the free checks
        self.assertEqual(len(commands),1);self.assertEqual(len(checks),3)
        self.assertTrue(any("--jump-check" in c for c in checks))
        self.assertIn('4,7',commands[0])
        for command in commands+checks:
            self.assertNotIn('&&',command)
            self.assertNotIn(';',command)
            self.assertNotIn('bypass',command)
        self.assertIn("'/workspace/a film'",commands[0])

    def test_mixed_commands_only_review_and_place_razgon_frames(self):
        plan={'frames':[{'number':1,'format':'animation'}, {'number':2,'format':'razgon_2d'},
                        {'number':3,'format':'photo'}]}
        with patch('frame_progress.razgon_project',return_value=Path('/workspace/mixed')), \
             patch.object(store,'load_project_plan',return_value=plan):
            result=context.commands({'id':'fixture'},[1,2,3])
            native=context.commands({'id':'fixture'},[1,3])
            repair=context.commands({'id':'fixture'},[3],repair=True)
        self.assertNotIn('transitions fixture',repair)
        self.assertIn('review fixture --frames 3',repair)
        self.assertIn('--logic-check',result);self.assertNotIn('frame_review.py',result)
        self.assertIn('transitions fixture --frames 1,2,3',result)
        self.assertNotIn('sheets --frames 1,2,3',result)
        self.assertIn('review fixture --frames 1,3',native)
        self.assertNotIn('frame_review.py',native)


class FrameBriefFilterTest(unittest.TestCase):
    """The frame agent gets only the standing rules of frames and of its own channel (user, 15 November 2026)."""
    def test_other_stages_other_channels_and_photo_rules_are_left_out(self):
        import montage_context as mc
        self.assertFalse(mc.for_frames('## Перезапуск студії тільки через studio_restart.py', 'What If', True))
        self.assertFalse(mc.for_frames('## Шесть PNG на одном листе для Алексея и Валентина', 'What If', True))
        self.assertTrue(mc.for_frames('## Шесть PNG на одном листе для Алексея и Валентина', 'Алексей Горбунов', False))
        self.assertFalse(mc.for_frames('## Непрерывный зум каждой фотографии на 20%', 'КОСМОС', True))
        # replaced for every channel: the director sets each move, `place` without --motion stays still (8 November 2026)
        self.assertFalse(mc.for_frames('## Непрерывный зум каждой фотографии на 20%', 'Karl Brenners Werkstatt', False))
        self.assertTrue(mc.for_frames('## Центральный текст в такт голосу', 'КОСМОС', True))


class StageFilterTest(unittest.TestCase):
    def test_channels_named_in_the_first_sentence_keep_their_rule(self):
        import montage_context as mc
        part = ('## Боковое движение фото, 22 октября 2026 года\n\nПоследнее прямое указание пользователя только для Алексея '
                'Горбунова и Валентина Чичваркина: большинство фотографий плавно движется.')
        self.assertTrue(mc.for_frames(part.splitlines()[0], 'Алексей Горбунов', False, part))
        self.assertFalse(mc.for_frames(part.splitlines()[0], 'Космос PRO', False, part))
        general = '## Быстрое производство\n\nПрямое уточнение пользователя для всех каналов: ускорять производство.'
        self.assertTrue(mc.for_frames(general.splitlines()[0], 'Космос PRO', False, general))

    def test_grouping_sentences_stays_with_the_director_only(self):
        import montage_context as mc
        heading = '## Объединение коротких фраз в один кадр, 17 октября 2026 года'
        self.assertFalse(mc.for_frames(heading, 'Karl Brenners Werkstatt', False))
        self.assertTrue(mc.for_frames(heading, 'Karl Brenners Werkstatt', False, planning=True))

