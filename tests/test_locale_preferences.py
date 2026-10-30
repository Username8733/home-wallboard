"""Device locale choices must persist without changing shared calendar preferences."""

import copy
import pathlib
import tempfile
import unittest

from planner import PlannerProxy
from settings_store import SettingsStore


class LocalePreferencesTests(unittest.TestCase):
    def test_document_uses_standards_mode(self):
        page = pathlib.Path(__file__).resolve().parents[1] / "app/static/index.html"
        self.assertTrue(page.read_text().lstrip().lower().startswith("<!doctype html>"))

    def test_validation_and_reload(self):
        with tempfile.TemporaryDirectory() as root:
            store = SettingsStore(pathlib.Path(root) / "settings.json")
            self.assertEqual(store.snapshot()["language"], "sv")
            self.assertFalse(store.snapshot()["show_help_text"])
            saved = store.save(
                {
                    "language": "en",
                    "time_format": "12h",
                    "show_help_text": True,
                    "night_start": "00:15",
                    "night_end": "12:30",
                }
            )
            self.assertEqual(SettingsStore(store.path).snapshot(), saved)
            for patch in [{"language": "de"}, {"time_format": "13h"}, {"show_help_text": "yes"}]:
                with self.assertRaises(ValueError):
                    store.save(patch)

    def test_planner_locale_is_local_and_shared_fields_are_preserved_on_write(self):
        proxy = PlannerProxy({"ha_url": "https://ha.example.invalid", "ha_token": "test"})
        proxy.device_preferences = lambda: {"language": "en", "time_format": "12h"}
        shared = {
            "revision": 4,
            "state": {
                "people": [],
                "preferences": {"language": "sv", "timeFormat": "24h", "calendarMode": "mixed"},
            },
        }
        result = proxy.localize_state(copy.deepcopy(shared))
        self.assertEqual(result["state"]["preferences"]["language"], "en")
        self.assertEqual(result["state"]["preferences"]["timeFormat"], "12h")
        outgoing = proxy.preserve_shared_locale(result)
        self.assertEqual(outgoing, shared)
        self.assertEqual(
            proxy.localize_state(copy.deepcopy(shared))["state"]["preferences"]["language"], "en"
        )

    def test_new_empty_planner_and_uninitialized_write(self):
        proxy = PlannerProxy({"ha_url": "https://ha.example.invalid", "ha_token": "test"})
        proxy.device_preferences = lambda: {"language": "sv", "time_format": "12h"}
        with self.assertRaises(ValueError):
            proxy.preserve_shared_locale({"state": {"preferences": {}}})
        proxy.localize_state({"state": None})
        result = proxy.preserve_shared_locale(
            {"state": {"preferences": {"language": "sv", "timeFormat": "12h"}}}
        )
        self.assertEqual(result["state"]["preferences"], {"language": "en", "timeFormat": "24h"})


if __name__ == "__main__":
    unittest.main()
