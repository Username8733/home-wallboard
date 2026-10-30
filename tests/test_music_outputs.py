"""Speaker changes must bind commands and queue actions to the selected MA player."""

import json
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

from music import PLAYER, Music

OTHER = "media_player.office"
GROUP = "media_player.group"


def state(name, kind="player", status="idle", **attributes):
    return {
        "state": status,
        "attributes": {"friendly_name": name, "mass_player_type": kind, **attributes},
    }


class MusicOutputsTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "ha_url": "http://ha",
            "ha_token": "private",
            "ma_url": "http://ma",
            "ma_token": "private",
        }
        self.states = {
            PLAYER: state("Default"),
            OTHER: state("Office"),
            GROUP: state("All", "group"),
            "media_player.tv": {"state": "on", "attributes": {"friendly_name": "TV"}},
            "media_player.offline": state("Offline", status="unavailable"),
        }

    def test_selection_is_validated_persisted_and_does_not_control_playback(self):
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / "player.json"
            music = Music(self.config, path)
            music.service = Mock()
            self.assertEqual(music.player, PLAYER)
            music.select_player(OTHER, self.states)
            self.assertEqual(Music(self.config, path).player, OTHER)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), {"player": OTHER})
            music.service.assert_not_called()
            for invalid in [
                "media_player.tv",
                "media_player.offline",
                "media_player.unknown",
                "http://evil",
                None,
                [],
            ]:
                with self.assertRaises(ValueError):
                    music.select_player(invalid, self.states)
            with self.assertRaises(ValueError):
                music.select_player(PLAYER, self.states, online=False)
            self.assertEqual(music.player, OTHER)

    def test_controls_and_browsing_use_selected_player_and_reject_old_client(self):
        music = Music(self.config)
        music.select_player(OTHER, self.states)
        music.service = Mock(return_value={"service_response": {OTHER: {"children": []}}})
        music.browse(category="playlists")
        self.assertEqual(music.service.call_args.args[1]["entity_id"], OTHER)
        music.command({"action": "volume", "value": 0.1, "player": OTHER})
        self.assertEqual(music.service.call_args.args[1], {"entity_id": OTHER, "volume_level": 0.1})
        music.service.reset_mock()
        with self.assertRaises(ValueError):
            music.command({"action": "play", "player": PLAYER})
        music.service.assert_not_called()

    def test_switch_invalidates_queue_and_rejects_foreign_queue_item(self):
        music = Music(self.config)
        music.queue_cache = (10**12, {"player": PLAYER, "items": ["old"]})
        music.queue_actions = {"old": {"queue": "old-q", "item": "track", "player": PLAYER}}
        music.select_player(OTHER, self.states)
        self.assertEqual(music.queue_actions, {})
        music.queue_actions = {"old": {"queue": "old-q", "item": "track", "player": PLAYER}}
        music.service = Mock(
            return_value={"service_response": {OTHER: {"queue_id": "office-q", "items": 0}}}
        )
        with self.assertRaises(ValueError):
            music.command({"action": "queue_item", "id": "old"})
        music.service.assert_not_called()
        with patch("music.requests.post") as post:
            post.return_value.json.return_value = []
            result = music.queue()
        self.assertEqual(result["player"], OTHER)
        self.assertEqual(music.service.call_args.args[1]["entity_id"], OTHER)

    def test_no_active_queue_is_empty_without_failing_or_contacting_ha(self):
        music = Music(self.config)
        music.service = Mock()
        with patch("music.requests.post") as post:
            result = music.queue(self.states)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["player"], PLAYER)
        self.assertFalse(result["active"])
        music.service.assert_not_called()
        post.assert_not_called()

    def test_queue_reads_ma_directly_using_selected_entity_queue(self):
        music = Music(self.config)
        music.select_player(OTHER, self.states)
        self.states[OTHER]["attributes"]["active_queue"] = "office-queue"
        music.service = Mock()
        with patch("music.requests.post") as post:
            first, second = Mock(), Mock()
            first.json.return_value = {"queue_id": "office-queue", "active": False, "items": 0}
            second.json.return_value = []
            post.side_effect = [first, second]
            result = music.queue(self.states)
            self.assertEqual(
                post.call_args_list[0].kwargs["json"]["args"], {"queue_id": "office-queue"}
            )
        self.assertEqual(result["player"], OTHER)
        music.service.assert_not_called()

    def test_snapshot_lists_groups_and_prioritizes_selected_playback(self):
        music = Music(self.config)
        self.states[PLAYER] = state(
            "Default", status="playing", media_title="Other song", media_artist="Other artist"
        )
        self.states[OTHER] = state(
            "Office", status="playing", media_title="Office song", media_artist="Artist"
        )
        music.select_player(OTHER, self.states)
        public = music.snapshot(self.states, True)
        self.assertEqual(public["player"]["entity_id"], OTHER)
        self.assertEqual(public["player"]["title"], "Office song")
        self.assertEqual(public["playing"]["entity_id"], OTHER)
        self.assertTrue(next(row for row in public["outputs"] if row["id"] == GROUP)["group"])
        self.assertNotIn("media_player.tv", [row["id"] for row in public["outputs"]])
        self.assertNotIn("private", str(public))
        del self.states[OTHER]
        self.assertFalse(music.snapshot(self.states, True)["player"]["online"])
