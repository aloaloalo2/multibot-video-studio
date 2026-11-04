"""Model selection and concurrent request routing. All provider calls are mocked."""
import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import languages
import store


class TranslationModelsTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.pid = 'a' * 24
        for mock in (
            patch.object(store, 'project_dir', side_effect=lambda pid: self.root / pid),
            patch.object(store, 'load_project', side_effect=lambda pid: {'id': pid}),
            patch.object(languages, 'overview', side_effect=lambda pid: languages.load_state(pid)),
            patch.object(languages, 'key', return_value='test-key'),
            patch.object(languages, 'thumbnail_options', return_value={'add_flag': False}),
        ):
            mock.start()
            self.addCleanup(mock.stop)
        languages.ACTIVE.clear()
        self.addCleanup(languages.ACTIVE.clear)

    def test_selection_is_per_language_and_does_not_touch_existing_text_or_voice(self):
        languages.save_state(self.pid, {'languages': {'uk': {'voice': {'made_at': 123}, 'translate_cost': .02}}})
        path = languages.work_dir(self.pid, 'uk') / 'text.txt'
        path.parent.mkdir(parents=True)
        path.write_text('Наявний переклад.')
        model = 'minimax/minimax-m3.1-flash'
        result = languages.set_translation_model(self.pid, 'uk', model)
        self.assertEqual(result['languages']['uk']['voice'], {'made_at': 123})
        self.assertEqual(result['languages']['uk']['translate_cost'], .02)
        self.assertEqual(path.read_text(), 'Наявний переклад.')
        self.assertEqual(languages.translation_model(self.pid, 'uk'), model)
        self.assertEqual(languages.translation_model(self.pid, 'es'), languages.DEFAULT_TRANSLATION_MODEL)
        self.assertEqual(languages.translation_model('b' * 24, 'uk'), languages.DEFAULT_TRANSLATION_MODEL)

    def test_minimax_is_default_without_overriding_explicit_deepseek_or_history(self):
        historical = {'translation_model': languages.DEEPSEEK_TRANSLATION_MODEL,
                      'translated_model': languages.DEEPSEEK_TRANSLATION_MODEL, 'translate_cost': .02}
        languages.save_state(self.pid, {'languages': {'uk': historical}})
        with patch.object(languages, 'request') as request:
            self.assertEqual(languages.translation_model(self.pid, 'es'), 'minimax/minimax-m3.1-flash')
            self.assertEqual(languages.translation_model(self.pid, 'uk'), languages.DEEPSEEK_TRANSLATION_MODEL)
            self.assertEqual(languages.load_state(self.pid)['languages']['uk'], historical)
            request.assert_not_called()

    def test_legacy_job_without_model_keeps_deepseek(self):
        with languages.translation_trace(self.pid, 'uk', {}):
            self.assertEqual(languages.TRANSLATION_CONTEXT.value['model'], languages.DEEPSEEK_TRANSLATION_MODEL)

    def test_retired_glm_selection_resolves_to_minimax_without_rewriting_history(self):
        historical = {'translation_model': 'z-ai/glm-5.3-flash',
                      'translated_model': 'z-ai/glm-5.3-flash', 'translate_cost': .07}
        languages.save_state(self.pid, {'languages': {'es': historical}})
        self.assertEqual(languages.translation_model(self.pid, 'es'), 'minimax/minimax-m3.1-flash')
        self.assertNotIn('z-ai/glm-5.3-flash', languages.TRANSLATION_MODELS)
        self.assertEqual(languages.load_state(self.pid)['languages']['es'], historical)

    def test_translation_prompt_prioritizes_natural_meaning_over_raw_counts(self):
        prompt = languages.translator('es')
        self.assertIn('digits in the source become longer spoken words', prompt)
        self.assertIn('natural spoken rhythm', prompt)
        self.assertNotIn('three percent', prompt)
        self.assertNotIn('five percent', prompt)
        self.assertNotIn('report failure', prompt)
        self.assertNotIn('fit its allotted time', prompt)

    def test_only_own_voice_lane_blocks_selection(self):
        model = 'minimax/minimax-m3.1-flash'
        languages.ACTIVE.update({f'{self.pid}|es|voice', f'{self.pid}|uk|thumbnail', f'{"b" * 24}|uk|voice'})
        languages.set_translation_model(self.pid, 'uk', model)
        languages.ACTIVE.add(f'{self.pid}|uk|voice')
        with self.assertRaises(store.StudioError):
            languages.set_translation_model(self.pid, 'uk', languages.DEFAULT_TRANSLATION_MODEL)

    def test_unknown_model_fails_before_request(self):
        for value in ('other/model', 'z-ai/glm-5.3-flash', '', None, ['bad']):
            with self.subTest(value=value), self.assertRaises(store.StudioError):
                languages.set_translation_model(self.pid, 'uk', value)
        with patch.object(languages, 'request') as request:
            with self.assertRaises(store.StudioError):
                with languages.translation_trace(self.pid, 'uk', {'translation_model': 'other/model'}):
                    languages.ask([])
            request.assert_not_called()

    def test_start_pins_selection_without_starting_any_provider_work(self):
        selected = 'minimax/minimax-m3.1-flash'
        languages.set_translation_model(self.pid, 'uk', selected)
        with patch.object(languages, 'source', return_value={'script': 'Source'}), patch.object(languages.threading, 'Thread') as thread:
            job = languages.start(self.pid, 'translate', 'uk')
        self.assertEqual(job['translation_model'], selected)
        self.assertEqual(thread.call_args.kwargs['args'][-1]['translation_model'], selected)
        # Even if a later version of the setting differs, this saved run keeps its original model.
        languages.update(self.pid, lambda data: data['languages']['uk'].update(translation_model=languages.DEEPSEEK_TRANSLATION_MODEL))
        self.assertEqual(job['translation_model'], selected)

    def test_parallel_models_use_their_own_reasoning_and_return_actual_cost(self):
        barrier = threading.Barrier(len(languages.TRANSLATION_MODELS))
        calls = []
        def request(url, body, headers, what):
            payload = json.loads(body)
            calls.append(payload)
            return json.dumps({'choices': [{'message': {'content': payload['model']}, 'finish_reason': 'stop'}],
                               'usage': {'cost': .0123}}).encode()
        def run(model):
            with languages.translation_trace(self.pid, 'uk', {'translation_model': model}):
                barrier.wait(timeout=5)
                result = languages.ask([{'role': 'user', 'content': model}], 300)
            self.assertIsNone(getattr(languages.TRANSLATION_CONTEXT, 'value', None))
            return result
        with patch.object(languages, 'request', side_effect=request), patch.object(languages, 'record_translation'), ThreadPoolExecutor(max_workers=3) as pool:
            futures = {model: pool.submit(run, model) for model in languages.TRANSLATION_MODELS}
            for model, future in futures.items():
                self.assertEqual(future.result(timeout=10), (model, .0123))
        for call in calls:
            self.assertEqual(call['reasoning'], languages.TRANSLATION_MODELS[call['model']]['reasoning'])
            self.assertEqual(call['max_tokens'], 300 if call['model'] == languages.DEEPSEEK_TRANSLATION_MODEL else 4096)
            self.assertEqual(call['messages'][0]['content'], call['model'])

    def test_mandatory_reasoning_error_does_not_retry_without_effort_or_switch_model(self):
        for model in ('minimax/minimax-m3.1-flash',):
            with self.subTest(model=model), languages.translation_trace(self.pid, 'uk', {'translation_model': model}):
                with patch.object(languages, 'request', side_effect=RuntimeError('OpenRouter: помилка 400')) as request:
                    with self.assertRaises(RuntimeError):
                        languages.ask([])
                    self.assertEqual(request.call_count, 1)

    def test_nested_trace_restores_outer_model(self):
        first, second = list(languages.TRANSLATION_MODELS)[:2]
        with languages.translation_trace(self.pid, 'uk', {'translation_model': first}):
            with languages.translation_trace(self.pid, 'es', {'translation_model': second}):
                self.assertEqual(languages.TRANSLATION_CONTEXT.value['model'], second)
            self.assertEqual(languages.TRANSLATION_CONTEXT.value['model'], first)
        self.assertIsNone(getattr(languages.TRANSLATION_CONTEXT, 'value', None))

    def test_api_route_saves_only_the_requested_project_language_model(self):
        import app
        handler = object.__new__(app.Handler)
        handler.json_response = lambda data: data
        model = 'minimax/minimax-m3.1-flash'
        with patch.object(languages, 'start', side_effect=AssertionError('selection must not generate')):
            result = handler.route_mutation('POST', f'/api/projects/{self.pid}/languages/pl/translation-model', {'model': model})
        self.assertEqual(result['languages']['pl']['translation_model'], model)


if __name__ == '__main__':
    unittest.main()
