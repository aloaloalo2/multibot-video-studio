import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import writer_context


class WriterContextTest(unittest.TestCase):
    def test_only_duplicate_rule_paragraphs_are_removed_and_current_wishes_stay_exact(self):
        rule='Always retain every specific current channel instruction, including all numbers and the language of the author.'
        context={'author_writing_rules':'# Global\n\n'+rule,'channel_script_rules':'# Channel\n\n'+rule+'\n\nA unique local instruction.',
                 'script_wishes':rule,'channel_agent_rules':rule,'studio_word_blacklist':[]}
        original=copy.deepcopy(context);small,metrics=writer_context.compact(context)
        self.assertEqual(context,original);self.assertIn(rule,small['author_writing_rules'])
        self.assertNotIn(rule,small['channel_script_rules']);self.assertIn('A unique local instruction.',small['channel_script_rules'])
        self.assertEqual(small['script_wishes'],rule);self.assertEqual(small['channel_agent_rules'],rule)
        self.assertEqual(small['studio_word_blacklist'],[]);self.assertEqual(metrics['duplicate_paragraphs'],1)
        self.assertGreater(metrics['saved_characters'],0)

    def test_complete_topic_history_is_merged_without_truncation_or_lost_subjects(self):
        titles=[f'Topic {i}' for i in range(200)]
        rows=[{'title':title,'subject':f'Subject {i}'} for i,title in enumerate(titles)]
        context={'previous_titles':titles,'previous_suggestions':titles,'previous_topic_history':rows+[{'title':'Topic 0','subject':'Other historical label'}]}
        small,metrics=writer_context.compact(context)
        self.assertEqual(len(small['topic_exclusions']),201)
        self.assertTrue(all(any(row['title']==title for row in small['topic_exclusions']) for title in titles))
        self.assertIn({'title':'Topic 0','subject':'Other historical label'},small['topic_exclusions'])
        self.assertGreater(metrics['saved_characters'],0)

    def test_distinct_line_structure_and_code_indentation_are_not_merged(self):
        lines='A specific instruction needs its exact source structure and every qualifier to remain available.\n    A nested condition follows.'
        context={'author_writing_rules':lines,'channel_script_rules':lines.replace('\n    ',' '),'previous_titles':None}
        small,metrics=writer_context.compact(context)
        self.assertEqual(small['author_writing_rules'],lines);self.assertEqual(small['channel_script_rules'],context['channel_script_rules'])
        self.assertEqual(metrics['duplicate_paragraphs'],0)
