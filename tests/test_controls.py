import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

from lighting import validate_light_control
from music import PLAYER, SONOS, Music
from settings_store import SettingsStore
from timer_sound import TimerSound


class Features(unittest.TestCase):
    def test_supported_controls_and_bounds(self):
        color = {
            "attributes": {
                "supported_color_modes": ["color_temp", "xy"],
                "min_color_temp_kelvin": 2200,
                "max_color_temp_kelvin": 6000,
            }
        }
        self.assertEqual(
            validate_light_control({"entity_id": "light.test", "brightness_pct": 30}, color),
            {"brightness_pct": 30},
        )
        for b in [{"hs_color": [120, 80]}, {"color_temp_kelvin": 3000}]:
            self.assertEqual(validate_light_control(b, color), b)
        for b in [
            {"brightness_pct": 101},
            {"brightness_pct": True},
            {"hs_color": [float("nan"), 20]},
            {"hs_color": [361, 50]},
            {"color_temp_kelvin": 1000},
            {"hs_color": [0, 0], "color_temp_kelvin": 3000},
            {"effect": "evil"},
        ]:
            with self.assertRaises(ValueError):
                validate_light_control(b, color)
        with self.assertRaises(ValueError):
            validate_light_control(
                {"brightness_pct": 30}, {"attributes": {"supported_color_modes": ["onoff"]}}
            )

    def test_output_settings_persist(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "settings.json"
            store = SettingsStore(p)
            for outputs in [["tablet"], ["sonos"], ["tablet", "sonos"]]:
                store.save({"timer_outputs": outputs})
                self.assertEqual(SettingsStore(p).snapshot()["timer_outputs"], outputs)
            for outputs in [[], ["evil"], ["sonos", "sonos"], "sonos", [True]]:
                with self.assertRaises(ValueError):
                    store.save({"timer_outputs": outputs})

    def test_both_outputs_and_one_failure_does_not_replay_other(self):
        timer = Mock()
        timer.snapshot.return_value = {"status": "finished"}
        announce = Mock(side_effect=[RuntimeError(), None])
        sound = TimerSound(timer, lambda: False, lambda: 25, lambda: ["tablet", "sonos"], announce)
        process = Mock()
        process.poll.return_value = None
        with (
            patch.object(sound, "play", return_value=process) as local,
            patch("timer_sound.time.monotonic", side_effect=[100, 100, 106, 106]),
        ):
            sound.poll()
            self.assertEqual(local.call_count, 1)
            sound.poll()
            self.assertEqual(local.call_count, 1)
            self.assertEqual(announce.call_count, 2)
            self.assertTrue(sound.played)

    def test_sonos_announcement_and_volume_are_fixed(self):
        music = Music({"ha_url": "http://ha", "ha_token": "test"})
        music.service = Mock()
        music.announce(17)
        payload = music.service.call_args.args[1]
        self.assertEqual(payload["entity_id"], SONOS)
        self.assertTrue(payload["announce"])
        self.assertEqual(payload["extra"], {"volume": 17})
        self.assertEqual(payload["media_content_id"], "http://ha/local/wallboard-timer-chime.wav")

    def test_queue_public_fields(self):
        music = Music(
            {"ha_url": "http://ha", "ha_token": "test", "ma_url": "http://ma", "ma_token": "secret"}
        )
        music.service = Mock(
            return_value={
                "service_response": {
                    PLAYER: {
                        "queue_id": "queue",
                        "items": 1,
                        "current_index": 0,
                        "current_item": None,
                        "active": True,
                    }
                }
            }
        )
        with patch("music.requests.post") as call:
            call.return_value.json.return_value = [
                {
                    "queue_item_id": "item1",
                    "name": "Track",
                    "index": 0,
                    "duration": 120,
                    "streamdetails": {"token": "secret"},
                    "image": "signed-url",
                    "media_item": {"name": "Song", "artists": [{"name": "Artist"}]},
                }
            ]
            q = music.queue()
            self.assertEqual(q["items"][0]["artist"], "Artist")
            self.assertTrue(q["items"][0]["current"])
            self.assertNotIn("secret", str(q))
            self.assertNotIn("signed-url", str(q))
            self.assertEqual(call.call_args.kwargs["json"]["command"], "player_queues/items")


if __name__ == "__main__":
    unittest.main()
