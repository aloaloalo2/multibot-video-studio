import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import eleven_api
import languages
import translation_budget


class VoiceCostReceiptsTest(unittest.TestCase):
    def test_user_allowance_survives_offline_catalogue_and_does_not_change_other_models(self):
        with patch.object(eleven_api,'model',side_effect=RuntimeError('offline')):
            self.assertEqual(languages.price('elevenlabs','x'*40029,'eleven_v4_turbo'),10407.54)
        with patch.object(eleven_api,'model',return_value={'credits_per_char':1}):
            self.assertEqual(languages.price('elevenlabs','x'*100,'eleven_v4'),100)

    def test_receipts_are_separate_from_estimates_and_partial_receipts_are_not_totals(self):
        job={}
        requests=[{'status':'complete','estimated_cost':26,'actual_cost':22},
                  {'status':'complete','estimated_cost':52,'actual_cost':44}]
        languages.record_voice_cost(job,requests)
        self.assertEqual((job['cost'],job['actual_cost'],job['estimated_cost'],job['cost_estimated']),(66,66,78,False))
        requests[1]['actual_cost']=None
        languages.record_voice_cost(job,requests)
        self.assertEqual((job['cost'],job['actual_cost'],job['cost_estimated']),(78,None,True))
        languages.record_voice_cost(job,[])
        self.assertEqual((job['cost'],job['actual_cost'],job['takes']),(0,0,0))

    def test_invalid_provider_headers_are_not_claimed_as_spending(self):
        self.assertEqual(eleven_api.SpeechAudio(b'a',{'character-cost':'12'}).credits,12)
        for value in (None,'nan','inf','-1','bad'):
            self.assertIsNone(eleven_api.SpeechAudio(b'a',{'character-cost':value}).credits)

    def test_number_expansion_does_not_select_an_equivalent_phrase_for_shortening(self):
        original=['In 2017.','x'*100,'y'*100]
        translated=['In dos mil diecisiete.','x'*120,'y'*100]
        plan=translation_budget.number_refinement_plan('\n'.join(original),translated,original,'en','es')
        self.assertEqual(plan['ids'],[1])
        self.assertEqual(plan['direction'],'shorten')
        good=translation_budget.number_refinement_plan('In 2017.',['In dos mil diecisiete.'],['In 2017.'],'en','es')
        self.assertEqual(good['ids'],[])

    def test_year_audit_catches_a_changed_century_and_misspelled_number(self):
        self.assertEqual(translation_budget.missing_source_years('On March 13, 1989, after 1859.',
            'En mil ochocientos ochenta y nueve, después de mil ochocientos cincuenta y nueve.', 'es'),['1989'])
        self.assertEqual(translation_budget.missing_source_years('In 1969.',
            'En mil novecent sesenta y nueve.', 'es'),['1969'])
        self.assertEqual(translation_budget.missing_source_years('In 1969.',
            'En mil novecientos sesenta y nueve.', 'es'),[])


if __name__=='__main__':unittest.main()
