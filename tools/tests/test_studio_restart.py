import io,sys,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import studio_restart as restart

class StudioRestartTest(unittest.TestCase):
    def test_stop_waits_for_the_old_process_to_exit_after_it_closes_its_listener(self):
        with patch.object(restart.os,'kill',side_effect=[None,None,ProcessLookupError()]) as kill, \
             patch.object(restart,'listener',return_value=None),patch.object(restart.time,'sleep') as sleep:
            self.assertTrue(restart.stop(123))
        self.assertEqual(kill.call_count,3)
        sleep.assert_called_once_with(.25)

    def test_refused_preparation_never_stops_the_running_server(self):
        with patch.object(sys,'argv',['studio_restart.py']),patch.object(restart,'alive',return_value=True), \
             patch.object(restart,'busy_work',return_value=[]),patch.object(restart,'listener',return_value=123), \
             patch.object(restart,'prepare',side_effect=SystemExit('busy')),patch.object(restart,'stop') as stop:
            with self.assertRaises(SystemExit):restart.main()
        stop.assert_not_called()

    def test_busy_response_is_not_treated_as_an_old_server(self):
        error=urllib.error.HTTPError('http://localhost',409,'busy',{},io.BytesIO(b'{"error":"Generation is running"}'))
        with patch.object(restart.urllib.request,'urlopen',side_effect=error):
            with self.assertRaisesRegex(SystemExit,'Generation is running'):restart.prepare()
