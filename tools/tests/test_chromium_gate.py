import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[2] / "razgon-plugin/razgon-2d-studio-plugin/skills/make-2d-video/kit"
sys.path.insert(0, str(KIT / "tools"))
import chromium_gate  # noqa: E402


class ChromiumGateTest(unittest.TestCase):
    def test_at_most_the_slots_render_at_once_and_the_rest_wait(self):
        root = Path(tempfile.mkdtemp())
        lock, live, peak, done = threading.Lock(), [0], [0], []

        def render(n):
            with chromium_gate.slot(root):
                with lock:
                    live[0] += 1; peak[0] = max(peak[0], live[0])
                time.sleep(.15)
                with lock:
                    live[0] -= 1
            done.append(n)

        with patch.object(chromium_gate, "SLOTS", 2), patch.object(chromium_gate, "WAIT", .02):
            threads = [threading.Thread(target=render, args=(n,)) for n in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5)
        self.assertEqual(peak[0], 2)
        self.assertEqual(sorted(done), list(range(6)))

    def test_a_failed_render_frees_its_slot(self):
        root = Path(tempfile.mkdtemp())
        with patch.object(chromium_gate, "SLOTS", 1):
            with self.assertRaises(RuntimeError):
                with chromium_gate.slot(root):
                    raise RuntimeError("render.mjs failed")
            with chromium_gate.slot(root) as number:
                self.assertEqual(number, 0)


if __name__ == "__main__":
    unittest.main()
