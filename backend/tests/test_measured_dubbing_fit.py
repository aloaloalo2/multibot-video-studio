import copy
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dubbing_fit


class MeasuredFitTest(unittest.TestCase):
    def test_rechecks_padding_after_render_changes_boundary_silence(self):
        items=[{'index':n,'start':n*5,'speed':1.,'fitted_length':5.,
                'edge_silence':{'leading':.1,'trailing':.1,'speed':1.}} for n in range(2)]
        original=copy.deepcopy(items);calls=[]
        def render(item,speed):
            calls.append((item['index'],speed))
            item['edge_silence']={'leading':0.,'trailing':0.,'speed':speed}
            return 5/speed+.04
        result=dubbing_fit.fit_measured(items,9.9,render)
        self.assertLessEqual(sum(x['fitted_length'] for x in result)+.05,9.9)
        self.assertGreater(len(calls),2)
        self.assertLessEqual(dubbing_fit.centered_schedule(result,9.9)[-1]['end'],9.9)
        self.assertEqual(items,original)

    def test_corrects_atempo_discrepancy_using_actual_output_and_only_available_headroom(self):
        # The inverse-duration estimate fits, while the encoded local takes do not.
        items = [
            {'index': 0, 'text': 'unchanged at cap', 'speed': dubbing_fit.MAX_SPEED, 'fitted_length': 8.9},
            {'index': 1, 'text': 'second complete take', 'speed': 1.0, 'fitted_length': 10.08},
            {'index': 2, 'text': 'third complete take', 'speed': 1.0, 'fitted_length': 10.08},
        ]
        original = copy.deepcopy(items)
        calls = []

        def render(item, speed):
            calls.append((item['index'], speed))
            return 10 / speed + .08  # fixed overlap/windowing difference from theory

        result = dubbing_fit.fit_measured(items, 28.85, render)
        self.assertLessEqual(sum(x['fitted_length'] for x in result) + .1, 28.85)
        self.assertEqual(result[0], original[0])
        self.assertEqual({n for n, _ in calls}, {1, 2})
        self.assertTrue(all(1 <= s <= dubbing_fit.MAX_SPEED for _, s in calls))
        self.assertEqual(items, original)
        self.assertEqual([x['text'] for x in result], [x['text'] for x in original])
        self.assertLessEqual(len(calls), 6)

    def test_fit_already_within_budget_does_not_render(self):
        render = Mock()
        result = dubbing_fit.fit_measured([{'speed': .92, 'fitted_length': 4}], 5, render)
        self.assertEqual(result, [{'speed': .92, 'fitted_length': 4}])
        render.assert_not_called()

    def test_no_speed_headroom_fails_without_render_or_cut(self):
        render = Mock()
        with self.assertRaisesRegex(RuntimeError, 'при межі 15%'):
            dubbing_fit.fit_measured([{'speed': dubbing_fit.MAX_SPEED, 'fitted_length': 5.1}], 5, render)
        render.assert_not_called()

    def test_unresponsive_duration_is_measured_again_but_bounded_to_three_passes(self):
        calls = []
        def render(item, speed):
            calls.append(speed)
            return 10.01
        with self.assertRaisesRegex(RuntimeError, 'Усі аудіофрагменти збережені'):
            dubbing_fit.fit_measured([{'speed': .92, 'fitted_length': 10.01}], 10, render)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(a < b <= dubbing_fit.MAX_SPEED for a, b in zip([.92] + calls, calls)))

    def test_invalid_measured_duration_never_passes(self):
        for duration in [None, 0, -1, math.nan, math.inf]:
            with self.subTest(duration=duration), self.assertRaises(RuntimeError):
                dubbing_fit.fit_measured([{'speed': 1, 'fitted_length': 5}], 4.9,
                                        lambda item, speed: duration)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg needed')
    def test_real_ffmpeg_multiple_short_takes_are_measured_and_fit_without_clipping(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rate = 48000
            files = []
            items = []
            rendered = {}
            calls = []
            for n, length in enumerate([.8, 1.1, .9, 1.3]):
                path = root / f'{n}.wav'
                dubbing_fit.command(['-f', 'lavfi', '-i',
                                     f'sine=frequency={220+n*41}:duration={length}', '-ar', rate, path])
                files.append(path)
                items.append({'index': n, 'speed': 1., 'fitted_length': length, 'start': n})

            def render(item, speed):
                calls.append((item['index'], speed))
                pcm = dubbing_fit.command(['-i', files[item['index']], '-af', f'atempo={speed:.6f}',
                                          '-ac', 1, '-ar', rate, '-f', 'f32le', 'pipe:1'])
                rendered[item['index']] = np.frombuffer(pcm, dtype='<f4')
                return len(rendered[item['index']]) / rate

            total = 4.17  # includes three 50 ms gaps; requires actual local acceleration
            result = dubbing_fit.fit_measured(items, total, render)
            placed = dubbing_fit.centered_schedule(result, total)
            self.assertLessEqual(placed[-1]['end'], total)
            self.assertEqual(len(rendered), 4)
            for item in placed:
                self.assertAlmostEqual(item['fitted_length'], len(rendered[item['index']]) / rate)
                self.assertGreater(item['fitted_length'], items[item['index']]['fitted_length'] * .9)
                self.assertLessEqual(item['speed'], dubbing_fit.MAX_SPEED)
                self.assertGreater(float(np.max(np.abs(rendered[item['index']]))), .05)
            self.assertTrue(all(path.is_file() for path in files))
            self.assertLessEqual(len(calls), 12)


if __name__ == '__main__':
    unittest.main()
