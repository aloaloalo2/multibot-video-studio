"""Whole HeyGen narrations, original and translated, take their turn first come first served."""
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import heygen_voice


class QueueTest(unittest.TestCase):
    def setUp(self):
        heygen_voice.JOB_QUEUE.clear()
        self.addCleanup(heygen_voice.JOB_QUEUE.clear)

    def test_narrations_run_one_at_a_time_in_the_order_they_came(self):
        order, heard = [], {}
        heygen_voice.queue_wait('narration:a')   # the first one goes at once
        def later(owner):
            heygen_voice.queue_wait(owner, lambda ahead: heard.setdefault(owner, []).append(ahead))
            order.append(owner)
            heygen_voice.queue_leave(owner)
        threads = []
        for owner in ('language:b:pl', 'narration:c'):
            thread = threading.Thread(target=later, args=(owner,));thread.start();threads.append(thread)
            time.sleep(.2)
        self.assertEqual(heygen_voice.queue_ahead('narration:c'), 2)
        self.assertEqual(order, [])
        heygen_voice.queue_leave('narration:a')
        for thread in threads:thread.join(5)
        self.assertEqual(order, ['language:b:pl', 'narration:c'])
        self.assertEqual(heard['language:b:pl'], [1])
        self.assertEqual(heard['narration:c'][0], 2)   # it heard two ahead, then its turn came
        self.assertEqual(heygen_voice.JOB_QUEUE, [])

    def test_a_stop_while_waiting_leaves_the_queue(self):
        heygen_voice.queue_wait('narration:a')
        class Stopped(Exception):pass
        def stop():raise Stopped()
        heygen_voice.STOP.check = stop
        try:
            with self.assertRaises(Stopped):
                heygen_voice.queue_wait('narration:b')
        finally:
            heygen_voice.STOP.check = None
        self.assertEqual(heygen_voice.JOB_QUEUE, ['narration:a'])
        heygen_voice.queue_leave('narration:a')


if __name__ == '__main__':
    unittest.main()
