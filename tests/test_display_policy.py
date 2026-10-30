"""Time boundaries, safety overrides and durable appearance preferences."""

import datetime
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from display_policy import ScreenPower, display_state, night_scheduled
from settings_store import SettingsStore


def instant(hour, minute=0, day="2026-10-30"):
    return (
        datetime.datetime.fromisoformat(f"{day}T{hour:02}:{minute:02}:00")
        .replace(tzinfo=ZoneInfo("Europe/Stockholm"))
        .timestamp()
    )


class DisplayPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SettingsStore(pathlib.Path(self.temp.name) / "settings.json")
        self.cfg = self.store.save(
            {"night_mode_enabled": True, "night_start": "22:00", "night_end": "07:00"}
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_overnight_exact_boundaries_and_disabled(self):
        for hour, minute, expected in [
            (21, 59, False),
            (22, 0, True),
            (0, 0, True),
            (6, 59, True),
            (7, 0, False),
        ]:
            self.assertEqual(night_scheduled(self.cfg, instant(hour, minute)), expected)
        self.cfg["night_mode_enabled"] = False
        self.assertFalse(night_scheduled(self.cfg, instant(23)))

    def test_same_day_interval_and_swedish_daylight_saving(self):
        self.cfg.update(night_start="13:00", night_end="14:00")
        self.assertTrue(night_scheduled(self.cfg, instant(13, 30)))
        self.assertFalse(night_scheduled(self.cfg, instant(14)))
        self.cfg.update(night_start="22:00", night_end="07:00")
        for day in ["2026-03-29", "2026-10-25"]:
            self.assertTrue(night_scheduled(self.cfg, instant(3, 30, day)))
            self.assertFalse(night_scheduled(self.cfg, instant(7, 0, day)))

    def test_presence_and_keep_on_cannot_override_night(self):
        self.cfg["screen_mode"] = "keep_on"
        result = display_state(self.cfg, active=True, now=instant(23))
        self.assertEqual(result["mode"], "night")
        self.assertEqual(result["level"], 0)

    def test_alarm_timer_and_temporary_touch_override(self):
        now = instant(23)
        fire = display_state(self.cfg, False, fire=True, now=now)
        self.assertEqual((fire["mode"], fire["level"]), ("active", 1))
        self.assertEqual(
            display_state(self.cfg, False, timer_finished=True, now=now)["mode"], "active"
        )
        self.assertEqual(
            display_state(self.cfg, False, wake_until=now + 120, now=now)["mode"], "active"
        )
        self.assertEqual(display_state(self.cfg, True, wake_until=now, now=now)["mode"], "night")
        self.assertNotEqual(display_state(self.cfg, False, now=instant(7))["mode"], "night")

    def test_preferences_persist_and_reject_invalid_times_and_themes(self):
        self.store.save({"theme": "dark"})
        loaded = SettingsStore(self.store.path).snapshot()
        self.assertEqual(loaded["theme"], "dark")
        self.assertTrue(loaded["night_mode_enabled"])
        for patch_value in [
            {"night_start": "24:00"},
            {"night_end": "7:00"},
            {"night_end": "22:00"},
            {"theme": "invalid"},
            {"night_mode_enabled": "yes"},
        ]:
            with self.assertRaises(ValueError):
                self.store.save(patch_value)

    def test_dpms_transitions_and_bounded_rechecks(self):
        power = ScreenPower()
        with patch("display_policy.subprocess.run", return_value=Mock(returncode=0)) as run:
            power.set_off(True, 10)
            self.assertEqual(run.call_args.args[0], ["/usr/bin/xset", "dpms", "force", "off"])
            power.set_off(True, 11)
            self.assertEqual(run.call_count, 2)
            power.set_off(False, 11)
            self.assertEqual(run.call_args.args[0], ["/usr/bin/xset", "-dpms"])
            self.assertFalse(power.off)


if __name__ == "__main__":
    unittest.main()
