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
        self.assertEqual(len(commands),3)
        for command in commands:
            self.assertIn('4,7',command)
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
        self.assertIn('--frames 2 --scale',result)
        self.assertIn('transitions fixture --frames 1,2,3',result)
        self.assertNotIn('sheets --frames 1,2,3',result)
        self.assertIn('review fixture --frames 1,3',native)
        self.assertNotIn('frame_review.py',native)
