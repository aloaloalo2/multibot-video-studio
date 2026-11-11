import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store,production

class ProjectListReadOnlyTests(unittest.TestCase):
    def test_listing_from_a_helper_without_server_activity_never_stops_live_production(self):
        project={'id':'a'*24,'production_request':{'status':'in_progress','frames':95}}
        with patch.object(production,'ACTIVE',set()),patch.object(production,'settle') as settle,patch.object(store,'listed_plan',return_value=None),patch.object(store,'made_frames',return_value=[]):
            row=store.production_state(project)
        settle.assert_not_called()
        self.assertEqual(row['status'],'in_progress')
        self.assertEqual(project['production_request']['status'],'in_progress')
