"""Focused regression tests for the Oct 30 wallboard changes; no real device writes."""

import hashlib
import io
import json
import pathlib
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

from music import PLAYER, Music
from photo_library import PhotoLibrary
from PIL import Image
from settings_store import SettingsStore
from sound_catalog import SOUNDS
from timer_sound import TimerSound


class Features(unittest.TestCase):
    def library(self, d):
        store = SettingsStore(pathlib.Path(d) / "settings.json")
        library = PhotoLibrary(
            {"immich_url": "http://im", "immich_api_key": "test", "album_id": "original"},
            store,
            pathlib.Path(d) / "cache",
            root=d,
        )
        library.catalog_time = 10**12
        return library, store

    def test_local_album_selection_cache_and_upload(self):
        with tempfile.TemporaryDirectory() as d:
            lib, store = self.library(d)
            album = lib.create_folder("Familj")
            out = io.BytesIO()
            Image.new("RGB", (80, 60), "red").save(out, "PNG")
            self.assertEqual(lib.upload(album["id"], [io.BytesIO(out.getvalue())]), 1)
            store.save({"photo_source": "local", "photo_album": album["id"]})
            lib.validate_selection(store.snapshot())
            items = lib.refresh()
            self.assertEqual(len(items), 1)
            self.assertEqual(lib.cached(), items)
            self.assertTrue((lib.cache / items[0]["file"]).exists())
            with self.assertRaises(ValueError):
                lib.create_folder("../private")
            with self.assertRaises(ValueError):
                lib.local_folder("../private")
            with self.assertRaises(ValueError):
                lib.upload(album["id"], [io.BytesIO(b"not an image")])
            store.save({"photo_source": "google", "photo_album": "missing"})
            self.assertEqual(lib.cached(), [])

    def test_shared_link_safety_and_google_parser(self):
        valid = "https://photos.google.com/share/album?key=secret"
        self.assertEqual(PhotoLibrary.check_link("google", valid), valid)
        for url in [
            "http://photos.google.com/share/id",
            "https://127.0.0.1/share/id",
            "https://photos.google.com.evil.test/share/id",
            "https://user:pass@photos.google.com/share/id",
            "https://photos.google.com:8000/share/id",
        ]:
            with self.assertRaises(ValueError):
                PhotoLibrary.check_link("google", url)
        with self.assertRaises(ValueError):
            PhotoLibrary.image_url("https://127.0.0.1/private", "google")
        payload = [
            [
                ["image1", ["https://lh3.googleusercontent.com/test", 1600, 900]],
                ["avatar", ["https://lh3.googleusercontent.com/avatar", 48, 48]],
            ]
        ]
        result = PhotoLibrary.google_items(
            'AF_initDataCallback({key:"ds:1",data:' + json.dumps(payload) + ",sideChannel:{}})"
        )
        self.assertEqual([x["id"] for x in result], ["image1"])

    def test_icloud_protocol_and_private_link_storage(self):
        with tempfile.TemporaryDirectory() as d:
            lib, _ = self.library(d)
            url = "https://www.icloud.com/sharedalbum/sv-se/#B0aABCDEFG12345"
            stream = {
                "photos": [
                    {
                        "photoGuid": "photo1",
                        "dateCreated": "2026-01-02T12:00:00Z",
                        "derivatives": {"1": {"checksum": "sum", "width": "1200", "height": "900"}},
                    }
                ]
            }
            assets = {
                "items": {"sum": {"url_location": "1", "url_path": "/image.jpg"}},
                "locations": {"1": {"hosts": ["cvws.icloud-content.com"]}},
            }
            with patch("photo_library.requests.post") as post:
                first = Mock(status_code=200)
                first.json.return_value = stream
                second = Mock(status_code=200)
                second.json.return_value = assets
                post.side_effect = [first, second]
                items = lib.shared_items("icloud", url)
                self.assertEqual(items[0]["url"], "https://cvws.icloud-content.com/image.jpg")
            with patch.object(lib, "shared_items", return_value=items):
                record = lib.add_shared("icloud", "Album", url)
            self.assertEqual(lib.links_file.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("ABCDEFG", json.dumps(lib.options()))
            self.assertEqual(record["count"], 1)

    def test_all_five_audio_assets_and_preferences(self):
        self.assertEqual(len(SOUNDS), 5)
        digests = set()
        for name, sound in SOUNDS.items():
            p = pathlib.Path(__file__).resolve().parents[1] / "app/static" / sound["file"]
            digests.add(hashlib.sha256(p.read_bytes()).hexdigest())
            with wave.open(str(p)) as audio:
                self.assertEqual(audio.getframerate(), 48000)
                self.assertGreater(audio.getnframes(), 48000)
        self.assertEqual(len(digests), 5)
        with tempfile.TemporaryDirectory() as d:
            store = SettingsStore(pathlib.Path(d) / "prefs.json")
            for name in SOUNDS:
                store.save({"timer_sound": name})
                self.assertEqual(SettingsStore(store.path).snapshot()["timer_sound"], name)
            with self.assertRaises(ValueError):
                store.save({"timer_sound": "../file"})
        sound = TimerSound(Mock(), lambda: False, sound=lambda: "gong")
        with patch("timer_sound.subprocess.Popen") as play:
            sound.play(20)
            self.assertTrue(play.call_args.args[0][-1].endswith("timer-gong.wav"))

    def test_click_queue_uses_item_id_not_changed_position(self):
        music = Music(
            {
                "ha_url": "http://ha",
                "ha_token": "test",
                "ma_url": "http://ma",
                "ma_token": "private",
            }
        )
        music.queue_actions = {"opaque": {"queue": "q1", "item": "track-id"}}
        music.service = Mock(return_value={"service_response": {PLAYER: {"queue_id": "q1"}}})
        with patch("music.requests.post") as post:
            music.command({"action": "queue_item", "id": "opaque"})
            self.assertEqual(
                post.call_args.kwargs["json"]["args"], {"queue_id": "q1", "index": "track-id"}
            )
        with self.assertRaises(ValueError):
            music.command({"action": "queue_item", "id": "forged"})


if __name__ == "__main__":
    unittest.main()
