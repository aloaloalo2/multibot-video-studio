"""The completion gate reads local evidence and never renders video or calls models."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import production_quality as quality
import store


class QualityTest(unittest.TestCase):
    def test_malformed_saved_layer_cannot_crash_recovery(self):
        with patch.object(store,'load_project_plan',return_value={'frames':[{'number':1,'format':'animation'}]}), \
                patch.object(quality.montage_ops,'frame_groups',return_value=[{'number':1,'clips':[{'kind':'text','duration':'bad'}]}]):
            result=quality.check({'id':'fixture'},{'frames':1})
        self.assertFalse(result['passed'])
        self.assertIn('Не вдалося перевірити',result['errors'][0])

    def test_native_label_failure_is_reported_for_selected_frame_only(self):
        project={'id':'fixture','fps':25,'width':1920,'height':1080}
        plan={'frames':[{'number':n,'format':'animation'} for n in (1,2)]}
        groups=[{'number':1,'clips':[{'kind':'text','text':'Needs repair','duration':2,'x':1.2,'width':.4}]},
                {'number':2,'clips':[{'kind':'text','text':'Valid','duration':2,'width':.4,'height':.2}]}]
        with patch.object(store,'load_project_plan',return_value=plan), \
                patch.object(quality.montage_ops,'frame_groups',return_value=groups), \
                patch.object(quality.subprocess,'run') as process:
            rejected=quality.check(project,{'frames':2,'review_frames':[1]})
            passed=quality.check(project,{'frames':2,'review_frames':[2]})
        self.assertFalse(rejected['passed'])
        self.assertIn('Кадр 1',rejected['errors'][0])
        self.assertTrue(passed['passed'])
        process.assert_not_called()

    def test_razgon_gate_reads_scoped_receipt_and_fails_closed(self):
        project={'id':'fixture'}
        plan={'frames':[{'number':n,'format':'razgon_2d'} for n in (1,2,3)]}
        with patch.object(store,'load_project_plan',return_value=plan), \
                patch.object(quality.frame_progress,'razgon_project',return_value=Path('/tmp/local-review')), \
                patch.object(quality.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='not reviewed: 2',stderr='')) as process:
            result=quality.check(project,{'frames':3,'review_frames':[2]})
        self.assertFalse(result['passed'])
        self.assertEqual(process.call_args.args[0][-3:],['status','--frames','2'])
        self.assertNotIn('sheets',process.call_args.args[0])
        self.assertEqual(result['visual_review'],[2])

    def test_only_stale_or_missing_visual_review_receipts_allow_targeted_continuation(self):
        plan={'frames':[{'number':n,'format':'razgon_2d'} for n in range(21,31)]}
        for extra,expected in (('',[25]),('  RENDER ERROR  broken scene',[])):
            output='Frames reviewed ok: 10/10\n  changed frames needing fresh stills: 25\n'+extra
            with patch.object(store,'load_project_plan',return_value=plan), \
                 patch.object(quality.frame_progress,'razgon_project',return_value=Path('/tmp/review-fixture')), \
                 patch.object(quality.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout=output,stderr='')):
                result=quality.check({'id':'fixture'},{'frames':30,'review_frames':list(range(21,31))})
            self.assertFalse(result['passed'])
            self.assertEqual(result['pending_review'],expected)
