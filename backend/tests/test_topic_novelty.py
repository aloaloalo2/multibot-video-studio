import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import topic_novelty as novelty
import episode_ideas as ideas
import writer_context

NEW = [
 {'title':'What If Humans Could Live Forever?', 'premise':'consequences of biological immortality'},
 {'title':'What If Gravity Suddenly Doubled on Earth?', 'premise':'a global increase in gravitational strength'},
 {'title':'Could Your Memories Be Sold to Strangers?', 'premise':'the trade and transfer of personal memories'},
 {'title':'The Night Every Ocean Turned Into Fresh Water!', 'premise':'a sudden removal of ocean salinity'},
 {'title':'What Happens When the Sun Becomes Silent?', 'premise':'the disappearance of solar magnetic activity'},
]

class TopicNoveltyTest(unittest.TestCase):
 def test_slot_substitution_is_rejected_across_languages_and_channels(self):
  pairs=[('What If You Ate Only Bread for a Year?','What If You Ate Only Honey for a Year?'),
         ('Що якщо ти їстимеш лише хліб щодня?','Що якщо ти їстимеш лише мед щодня?'),
         ('Was passiert wenn du nur Brot isst?','Was passiert wenn du nur Eis isst?'),
         ('These 5 mistakes destroy your winter tyres!','These 7 mistakes destroy your winter tyres!'),
         ('What If All Bees Disappeared Forever?','What If All Mosquitoes Disappeared Forever?')]
  for a,b in pairs:
   with self.subTest(a=a):self.assertTrue(novelty.slot_rewrite(a,b))
  self.assertFalse(novelty.slot_rewrite(NEW[0]['title'],NEW[1]['title']))
  self.assertFalse(novelty.slot_rewrite('What If Earth Stopped Spinning?','What If Earth Lost Its Oxygen?'))

 def test_old_title_without_premise_still_blocks_food_substitution(self):
  ctx={'previous_titles':['What If You Ate Only Bread for a Year?']}
  candidates=[{'title':'What If You Ate Only Honey for a Year?'},*NEW[1:]]
  with self.assertRaisesRegex(ValueError,'задум'):
   ideas.validate_titles({'ideas':candidates},ctx)

 def test_same_premise_is_blocked_despite_completely_different_wording(self):
  ctx={'previous_titles':[], 'previous_topic_history':[{'title':'Old topic','premise':'consequences of an exclusive single food diet'}]}
  candidates=[{'title':'Could a Honey Diet Change Your Body?', 'premise':'Consequences of an exclusive single food diet'},*NEW[1:]]
  with self.assertRaisesRegex(ValueError,'задум'):ideas.validate_titles({'ideas':candidates},ctx)
  self.assertEqual(ideas.validate_titles({'ideas':NEW},{'previous_titles':[]}),[{**r,'uk':''} for r in NEW])

 def test_one_batch_cannot_contain_two_variants_of_the_same_experiment(self):
  candidates=[{'title':'What If You Ate Only Honey for a Year?'}, {'title':'What If You Ate Only Bread for a Year?'},*NEW[2:]]
  with self.assertRaises(ValueError):ideas.validate_titles({'ideas':candidates},{'previous_titles':[]})

 def test_unused_premises_survive_history_reload_and_prompt_compaction(self):
  row={'title':'What If You Ate Only Bread for a Year?','subject':'bread diet','premise':'consequences of an exclusive single food diet'}
  with tempfile.TemporaryDirectory() as folder,patch.object(ideas,'path',return_value=Path(folder)/'episode-ideas.json'):
   self.assertEqual(ideas.suggestion_history('channel',{'ideas':[row]}),[row])
   self.assertEqual(ideas.suggestion_history('channel'),[row])
  context={'previous_titles':[row['title']], 'previous_suggestions':[row['title']], 'previous_topic_history':[row]}
  compact,_=writer_context.compact(context)
  self.assertIn(row,compact.get('topic_exclusions',compact.get('previous_topic_history',[])))
  self.assertIn('exclusive single food diet',ideas.TOPIC_PROMPT)
