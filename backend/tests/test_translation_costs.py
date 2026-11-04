import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import translation_costs

class TranslationCostsTest(unittest.TestCase):
    def test_categories_models_and_deduplication_use_saved_actual_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);run=root/'translation-attempts'/'one';run.mkdir(parents=True)
            for n,(request,model,prompt,cost) in enumerate([
                ('a','minimax/m','You translate the narration',.02),
                ('b','minimax/m','Translate this YouTube video title',.001),
                ('c','minimax/m','Independently compare EVERY translation',.003),
                ('d','deepseek/m','Revise only this ONE narration phrase',.004),
                ('d','deepseek/m','Revise only this ONE narration phrase',.004)]):
                (run/f'{n}.json').write_text(json.dumps({'request_id':request,'requested_model':model,
                    'messages':[{'content':prompt}],'usage':{'cost':cost}}))
            result=translation_costs.breakdown(root)
            self.assertAlmostEqual(result['total_usd'],.028)
            self.assertEqual(result['categories'],{'translation':.02,'title':.001,'checks':.003,'repairs':.004})
            self.assertEqual(result['models'],{'minimax/m':.024,'deepseek/m':.004})
            self.assertEqual(result['requests'],4)
            self.assertNotIn('messages',result)

    def test_missing_legacy_logs_are_explicitly_unattributed(self):
        with tempfile.TemporaryDirectory() as folder:
            result=translation_costs.breakdown(Path(folder),.15)
            self.assertEqual(result['categories']['unattributed'],.15)
            self.assertEqual(result['total_usd'],.15)
            self.assertEqual(result['models'],{})
