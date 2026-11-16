"""The shared forgiving reader of model answers (backend/model_json.py, 16 November 2026 stability pass)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_json
import translation_recovery as recovery


class LoadsTest(unittest.TestCase):
    def test_every_wrapping_seen_from_the_models_is_read(self):
        for text in ['{"a":1}', '```json\n{"a":1}\n```', '```JSON\n{"a":1}\n```', '```\n{"a":1}', '{"a":1}\n```',
                     'JSON\n{"a":1}', 'Here you go: {"a":1}', '{"a":1}\nHope this helps.', '  \n{"a":1}  ']:
            self.assertEqual(model_json.loads(text), {"a": 1}, text)

    def test_kinds_skip_values_of_another_shape(self):
        self.assertEqual(model_json.loads('Lines ["x"] then {"a":1}', kinds=(dict,)), {"a": 1})
        self.assertEqual(model_json.loads('Answer: ["x","y"]', kinds=(list,)), ["x", "y"])

    def test_no_json_or_an_unfinished_one_is_an_error(self):
        for text in ['', 'no json here', '{"a":', None]:
            with self.assertRaises(ValueError):
                model_json.loads(text)

    def test_a_refused_object_is_not_replaced_by_one_nested_inside_it(self):
        with self.assertRaises(ValueError):
            model_json.loads('{"id":1,"id":2,"inner":{"ok":true}}', object_pairs_hook=recovery._unique_object)


class DocumentsTest(unittest.TestCase):
    def test_jsonl_and_several_objects_with_words_around(self):
        self.assertEqual(model_json.documents('{"a":1}\n{"b":2}'), [{"a": 1}, {"b": 2}])
        self.assertEqual(model_json.documents('Result:\n{"a":1}\n{"b":2}\nEnd.'), [{"a": 1}, {"b": 2}])
        with self.assertRaises(ValueError):
            model_json.documents('nothing')

    def test_words_between_a_draft_and_its_correction_keep_both(self):
        # the old reader of Opus answers took the last object here; the first version of this one lost the answer
        self.assertEqual(model_json.documents('{"a":0}\n\nWait, fix:\n{"a":1}'), [{"a": 0}, {"a": 1}])
        self.assertEqual(model_json.documents('{"a":1}\nNote: see [1].'), [{"a": 1}, [1]])
        import episode_ideas
        self.assertEqual(episode_ideas.unpack('{"a":0}\n\nWait, fix:\n{"a":1}'), {"a": 1})
        self.assertEqual(recovery.answers('{"20":"text"}\nNote: see [1].', [20])[0], {20: 'text'})


if __name__ == "__main__":
    unittest.main()
