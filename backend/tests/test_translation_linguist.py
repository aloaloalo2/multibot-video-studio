import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import translation_linguist as linguist
import translation_budget
import translation_recovery as recovery


class LinguistTest(unittest.TestCase):
    def setUp(self):
        self.ledger={};self.calls=[];self.saves=[]
        self.options=dict(index=3,language='es',language_name='Spanish',source='In 2014, researchers studied baby mice.',
            current='En dos mil catorce estudiaron ratones.',issue='Disputed wording',context={},ledger=self.ledger,
            save=lambda:self.saves.append(json.loads(json.dumps(self.ledger))),validate=lambda x:bool(x) and not any(c.isdigit() for c in x),
            linguist_model='deepseek',translation_model='minimax')

    def run_decisions(self,answers):
        def request(model,messages,tokens):
            self.calls.append((model,messages,tokens));return json.dumps(answers.pop(0))
        return linguist.resolve(**self.options,request=request)

    def test_correct_phrase_is_kept_and_saved_decision_is_reused_without_another_request(self):
        choice={'id':3,'action':'keep','reason':'Faithful native wording.'}
        self.assertEqual(self.run_decisions([choice]),self.options['current'])
        self.assertEqual(self.run_decisions([]),self.options['current'])
        self.assertEqual(len(self.calls),1)

    def test_linguist_repairs_only_the_disputed_phrase_and_reuses_spelled_out_year(self):
        text=self.run_decisions([{'id':3,'action':'replace','text':'En 2014 estudiaron crías de ratón.','reason':'Removed corrupted token.'}])
        self.assertEqual(text,'En dos mil catorce estudiaron crías de ratón.')
        sent=json.loads(self.calls[0][1][1]['content']);self.assertEqual(sent['id'],3)
        self.assertNotIn('full_script',sent)

    def test_linguist_can_delegate_once_and_review_or_repair_the_returned_phrase(self):
        text=self.run_decisions([{'id':3,'action':'retranslate','reason':'Use a fresh natural translation.'},
            {'3':'En dos mil catorce investigaron ratones.'},
            {'id':3,'action':'replace','text':'En dos mil catorce estudiaron crías de ratón.','reason':'Preserve baby mice.'}])
        self.assertEqual(text,'En dos mil catorce estudiaron crías de ratón.')
        self.assertEqual([x[0] for x in self.calls],['deepseek','minimax','deepseek'])
        self.assertEqual(self.run_decisions([]),text)

    def test_uncertain_request_is_not_charged_again_on_resume(self):
        def timeout(*args):raise RuntimeError('Provider unavailable')
        with self.assertRaisesRegex(RuntimeError,'Provider unavailable'):linguist.resolve(**self.options,request=timeout)
        self.assertEqual(self.ledger['3']['status'],'requested')
        with self.assertRaises(linguist.Unresolved):self.run_decisions([])
        self.assertEqual(self.calls,[])

    def test_wrong_year_or_foreign_language_cannot_be_approved_by_supervisor(self):
        self.options['validate']=lambda text:not translation_budget.missing_source_years(self.options['source'],text,'es')
        with self.assertRaises(linguist.Unresolved):
            self.run_decisions([{'id':3,'action':'replace','text':'En dos mil quince estudiaron ratones.','reason':'Fine'}])
        self.assertEqual(self.ledger['3']['status'],'blocked')

    def test_number_restoration_does_not_guess_unknown_values_or_ambiguous_forms(self):
        self.assertEqual(linguist.restore_number_words('En 2015.','En dos mil catorce.','es'),'En 2015.')
        self.assertEqual(linguist.restore_number_words('En 2014.','En dos mil catorce.','es'),'En dos mil catorce.')

    def test_contradictory_checker_evidence_is_not_an_error_or_an_approval(self):
        answer=json.dumps({'ok':False,'ids':[0,1],'issues':[{'id':1,'reason':"Actually correct. No error."}]})
        self.assertEqual(recovery.audit_evidence(answer,[0,1]),({},[0]))
        with self.assertRaises(recovery.InvalidAudit):
            recovery.audit_evidence(json.dumps({'ok':False,'ids':[1],'issues':[{'id':1,'reason':'No error.'}]}),[1])

    def test_ukrainian_compound_years_keep_exact_values_in_the_numeric_guard(self):
        for text in ['Навесні двохтисячного року.','Навесні двотисячного року.']:
            self.assertEqual(translation_budget.missing_source_years('In 2000.',text,'uk'),[])
        self.assertEqual(translation_budget.missing_source_years('In 2009.',"Двохтисячного дев’ятого року.",'uk'),[])
        self.assertEqual(translation_budget.missing_source_years('In 2000.','Весной две тысячи первого года.','ru'),['2000'])

    def test_saved_linguist_decision_survives_a_studio_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            identity={'source_units':['Source'],'model':'m'}
            draft=recovery.Draft(folder,identity);draft.seed(['Translated'])
            record={'fingerprint':'a'*64,'status':'resolved','value':'Translated','decision':{'action':'keep'}}
            draft.save(linguist={'0':record})
            self.assertEqual(recovery.Draft(folder,identity).data['linguist'],{'0':record})


if __name__=='__main__':unittest.main()
