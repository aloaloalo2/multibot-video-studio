import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import project_costs
import store


class ProjectCostsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/('a'*24);self.root.mkdir()
        project_costs.CACHE.clear()

    def save(self,name,data):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data));return p

    def collect(self,data=None):
        return project_costs.collect(self.root,data or {})

    def test_original_voice_receipts_and_legacy_recovery_are_idempotent(self):
        self.save('narration/receipts/fish.json',{'identity':'fish-1','provider':'fishaudio','amount':.12})
        self.save('narration/receipts/eleven.json',{'identity':'eleven-1','provider':'elevenlabs','amount':100})
        self.save('narration/job.json',{'status':'done','cost_receipts_version':1,'provider':'elevenlabs','estimated_credits':100,'started_at':1})
        data=self.collect();data=self.collect(data)
        totals=project_costs.totals(data,.0002)['providers']
        self.assertEqual(totals['fishaudio']['requests'],1)
        self.assertEqual(totals['fishaudio']['usd'],.12)
        self.assertEqual(totals['elevenlabs']['amount'],100)
        self.assertAlmostEqual(totals['elevenlabs']['usd'],.024)
        self.save('narration/job.json',{'status':'done','provider':'elevenlabs','estimated_credits':20,'started_at':2})
        self.assertEqual(project_costs.totals(self.collect(data),.0002)['providers']['elevenlabs']['amount'],120)

    def test_usage_deduplication_and_claude_reports_are_separate(self):
        receipt={'request_id':'or1','usage':{'cost':.02}}
        self.save('languages/es/translation-attempts/a/1.json',receipt)
        self.save('languages/es/translation-attempts/b/2.json',receipt)
        self.save('agent-conversation.json',{'costs':[{'id':'x','request_id':'image','amount_usd':.04}]})
        self.save('spend/old.json',{'log':'production.log','log_modified':1,'cost_usd':2,'cost_measured':True})
        self.save('spend/new.json',{'log':'production.log','log_modified':2,'cost_usd':3,'cost_measured':True})
        result=project_costs.totals(self.collect())
        self.assertAlmostEqual(result['providers']['openrouter']['usd'],.06)
        self.assertEqual(result['providers']['claude_code']['usd'],3)
        self.assertEqual(result['languages_usd'],.02)

    def test_voice_counts_paid_takes_and_samples_once_through_archiving(self):
        row={'receipt_id':'take1','started_at':10,'status':'complete','actual_cost':40,'estimated_cost':30}
        for folder in ['parts','voice-history/20/parts','sample-parts/30']:
            self.save('languages/es/'+folder+'/request.json',{'provider':'elevenlabs'})
            self.save('languages/es/'+folder+'/requests.json',[row])
        self.save('languages/es/sample-parts/40/request.json',{'provider':'elevenlabs'})
        self.save('languages/es/sample-parts/40/requests.json',[{'receipt_id':'take2','status':'uncertain','estimated_cost':20}])
        result=project_costs.totals(self.collect(),.0002)['providers']['elevenlabs']
        self.assertEqual(result['requests'],2)
        self.assertEqual(result['amount'],60)
        self.assertEqual(result['usd'],.0144)
        self.assertTrue(result['estimated'])

    def test_cache_reuse_has_no_paid_charge_and_missing_receipts_are_not_zero(self):
        self.save('languages/es/parts/request.json',{'provider':'elevenlabs'})
        self.save('languages/es/parts/requests.json',[])
        self.save('languages/es/translation-attempts/a/1.json',{'request_id':'a','usage':{}})
        result=project_costs.totals(self.collect())
        self.assertEqual(result['providers']['elevenlabs']['requests'],0)
        self.assertEqual(result['providers']['openrouter']['unknown'],1)
        self.assertEqual(result['providers']['elevenlabs']['usd'],0)
        self.save('languages/es/parts/requests.json',[{'receipt_id':'paid','status':'complete','actual_cost':20}])
        self.assertIsNone(project_costs.totals(self.collect())['providers']['elevenlabs']['usd'])

    def test_legacy_translation_floor_fills_only_missing_history(self):
        self.save('languages/languages.json',{'languages':{'es':{'translate_cost':.2}}})
        self.save('languages/es/translation-attempts/a/1.json',{'request_id':'r1','usage':{'cost':.1}})
        data=self.collect();self.assertAlmostEqual(project_costs.totals(data)['languages_usd'],.2)
        self.save('languages/es/translation-attempts/a/2.json',{'request_id':'r2','usage':{'cost':.15}})
        self.assertAlmostEqual(project_costs.totals(self.collect(data))['languages_usd'],.25)

    def test_saved_index_retains_costs_after_audio_cleanup_and_updates_started_receipt(self):
        self.save('languages/es/parts/request.json',{'provider':'elevenlabs'})
        p=self.save('languages/es/parts/requests.json',[{'receipt_id':'x','status':'started','estimated_cost':20}])
        data=self.collect()
        p.write_text(json.dumps([{'receipt_id':'x','status':'complete','actual_cost':25,'estimated_cost':20}]))
        data=self.collect(data)
        p.unlink();data=self.collect(data)
        value=project_costs.totals(data,.001)['providers']['elevenlabs']
        self.assertEqual(value['amount'],25)
        self.assertEqual(value['requests'],1)

    def test_summary_persists_and_does_not_reread_unchanged_receipts(self):
        self.save('languages/es/translation-attempts/a/1.json',{'request_id':'r','usage':{'cost':.1}})
        with patch.object(store,'project_dir',return_value=self.root),patch.object(store,'load_project',return_value={}):
            result=project_costs.summary(self.root.name)
            self.assertEqual(result,project_costs.summary(self.root.name))
        saved=json.loads((self.root/'project-costs.json').read_text())
        self.assertEqual(saved['summary']['languages_usd'],.1)
        self.assertNotIn('messages',str(saved))

    def test_editor_receipts_recover_cost_and_replace_pending_identity_once(self):
        path=self.save('script-editing/run/requests/one/receipt.json',
                       {'attempt_id':'pending-one','status':'submitted','cost_usd':None})
        self.save('script-editing/run/requests/cancelled/receipt.json',
                  {'attempt_id':'cancelled','status':'cancelled_before_submission','cost_usd':None})
        data=self.collect()
        self.assertEqual(project_costs.totals(data)['providers']['openrouter']['unknown'],1)
        path.write_text(json.dumps({'attempt_id':'pending-one','request_id':'or-editor-1',
                                    'status':'received','cost_usd':.004}))
        data=self.collect(data);data=self.collect(data)
        result=project_costs.totals(data)['providers']['openrouter']
        self.assertEqual(result['requests'],1)
        self.assertEqual(result['unknown'],0)
        self.assertEqual(result['usd'],.004)

    def test_author_self_review_receipts_keep_api_equivalence_separate_from_cash(self):
        self.save('script-editing/run/author-receipt.json',{'identity':'self-review-one','total_cost_usd':1.2,'incremental_cost_usd':.7})
        self.save('script-editing/legacy/requests/one/receipt.json',{'attempt_id':'legacy','request_id':'or-editor','status':'received','cost_usd':.003})
        data=self.collect();data=self.collect(data)
        result=project_costs.totals(data)['providers']
        self.assertEqual(result['claude_code']['usd'],.7)
        self.assertEqual(result['claude_code']['requests'],1)
        self.assertEqual(result['openrouter']['usd'],.003)

    def test_both_whole_script_phase_receipts_recover_increments_once(self):
        self.save('script-editing/run/author-receipts/main.json',{'identity':'review-main','total_cost_usd':1.4,'incremental_cost_usd':.2})
        self.save('script-editing/run/author-receipts/refinement.json',{'identity':'review-refine','total_cost_usd':1.5,'incremental_cost_usd':.1})
        self.save('script-editing/run/author-receipt.json',{'identity':'review-refine','total_cost_usd':1.5,'incremental_cost_usd':.1})
        data=self.collect();data=self.collect(data)
        result=project_costs.totals(data)['providers']['claude_code']
        self.assertEqual(result['requests'],2)
        self.assertAlmostEqual(result['usd'],.3)
