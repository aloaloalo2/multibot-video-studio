import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production
import store


class PeopleStyleTest(unittest.TestCase):
    """A channel chooses how people look in its pictures (user, 5 November 2026)."""

    def rules(self, settings, kind='animated'):
        with mock.patch.object(store, "get_channel_folder", return_value=Path("/nowhere")), \
             mock.patch.object(store, "read_json", return_value=settings):
            return production.people_rules({"channel_id": "c", 'project_kind':kind})

    def test_universal_projects_exclude_stickmen_even_with_a_legacy_stickman_choice(self):
        for settings in ({},{'people_style':'stickman'},{'people_style':'real'}):
            self.assertIs(self.rules(settings,'regular')['rule'],production.PEOPLE_REAL)
        self.assertIs(self.rules({'people_style':'real_older'},'regular')['rule'],production.PEOPLE_REAL_OLDER)

    def test_stick_figures_stay_the_default(self):
        for settings in ({}, {"people_style": "doodle"}):
            rules = self.rules(settings)
            self.assertIs(rules["rule"], production.PEOPLE)
            self.assertIn("без живих людей", rules["stock"])

    def test_disabled_stickmen_override_legacy_picture_choice_only_for_future_prompts(self):
        settings={'people_style':'stickman','animation':{'allow_stickmen':False}}
        self.assertIs(self.rules(settings)['rule'],production.PEOPLE_REAL)
        settings['animation']['allow_stickmen']=True
        self.assertIs(self.rules(settings)['rule'],production.PEOPLE)

    def test_real_people_for_a_channel_that_asks(self):
        rules = self.rules({"people_style": "real"})
        self.assertIs(rules["rule"], production.PEOPLE_REAL)
        self.assertIn("телефон", rules["rule"])
        self.assertNotIn("60+", rules["rule"])
        self.assertNotIn("лише стикмени", rules["check"])
        older = self.rules({"people_style": "real_older"})
        self.assertIn("60+", older["rule"])
        self.assertIn("телефон", older["rule"])
        self.assertIn("старшого віку", older["stock"])

    def test_settings_refuse_an_unknown_style(self):
        store.validate_settings({"weights": {"text": 100}, "people_style": "real"})
        with self.assertRaises(store.StudioError):
            store.validate_settings({"weights": {"text": 100}, "people_style": "cartoon"})


if __name__ == "__main__":
    unittest.main()
