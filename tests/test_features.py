"""Offline tests use generated photos and fake providers, never personal accounts."""

import base64
import hashlib
import io
import json
import pathlib
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from photo_library import PhotoLibrary
from PIL import Image
from settings_store import SettingsStore
from temperatures import catalog, reading, snapshot
from weather_forecast import Forecast, search_cities


def response(body):
    result = Mock()
    result.json.return_value = body
    result.raise_for_status.return_value = None
    return result


class WeatherTests(unittest.TestCase):
    def test_temperature_catalog_units_and_invalid_values(self):
        states = {
            "sensor.outside": {"state": "50", "attributes": {"unit_of_measurement": "°F"}},
            "sensor.inside": {"state": "294.15", "attributes": {"unit_of_measurement": "K"}},
            "sensor.unavailable": {
                "state": "unavailable",
                "attributes": {"device_class": "temperature"},
            },
            "sensor.humidity": {"state": "40", "attributes": {"unit_of_measurement": "%"}},
        }
        self.assertEqual(len(catalog(states)), 3)
        self.assertEqual(reading(states, "sensor.outside"), 10)
        self.assertAlmostEqual(reading(states, "sensor.inside"), 21)
        self.assertIsNone(reading(states, "sensor.unavailable"))
        states["sensor.inside"]["state"] = "nan"
        self.assertIsNone(reading(states, "sensor.inside"))

    def test_temperature_names_include_room_and_unassigned_entity(self):
        states = {
            "sensor.kitchen": {
                "state": "21",
                "attributes": {"friendly_name": "Temperatur", "device_class": "temperature"},
            },
            "sensor.bedroom": {
                "state": "20",
                "attributes": {"friendly_name": "Temperatur", "device_class": "temperature"},
            },
            "sensor.unassigned": {
                "state": "19",
                "attributes": {"friendly_name": "Temperatur", "device_class": "temperature"},
            },
        }
        options = catalog(states, {"sensor.kitchen": "Kök", "sensor.bedroom": "Sovrum"})
        self.assertEqual(options["sensor.kitchen"], "Temperatur · Kök")
        self.assertEqual(options["sensor.bedroom"], "Temperatur · Sovrum")
        self.assertIn("sensor.unassigned", options["sensor.unassigned"])
        self.assertIn("Rum saknas", options["sensor.unassigned"])

    def test_weather_temperature_uses_forecast_and_hides_stale(self):
        cfg = {
            "outdoor_temperature_source": "weather",
            "indoor_temperature_entity": "sensor.inside",
        }
        forecast = {"current_temperature": 8.5, "stale": False, "location": "Selected city"}
        self.assertEqual(snapshot({}, cfg, forecast, False)["outdoor"], 8.5)
        forecast["stale"] = True
        self.assertIsNone(snapshot({}, cfg, forecast, True)["outdoor"])

    def test_city_selection_validation_and_persistence(self):
        with tempfile.TemporaryDirectory() as root:
            store = SettingsStore(pathlib.Path(root) / "settings.json")
            with self.assertRaises(ValueError):
                store.save({"weather_source": "open_meteo"})
            store.save(
                {
                    "weather_source": "open_meteo",
                    "weather_city": "Test city",
                    "weather_latitude": 59.3,
                    "weather_longitude": 18.1,
                    "outdoor_temperature_source": "weather",
                }
            )
            self.assertEqual(SettingsStore(store.path).snapshot()["weather_city"], "Test city")
            with self.assertRaises(ValueError):
                store.save({"weather_latitude": float("nan")})
            with self.assertRaises(ValueError):
                store.save({"indoor_temperature_entity": "../config"})

    def test_city_search_and_forecast_same_coordinates(self):
        with tempfile.TemporaryDirectory() as root:
            store = SettingsStore(pathlib.Path(root) / "settings.json")
            store.save(
                {
                    "weather_source": "open_meteo",
                    "weather_city": "Selected city",
                    "weather_latitude": 59.3,
                    "weather_longitude": 18.1,
                }
            )
            forecast = Forecast({}, store)
            import datetime

            date = (
                datetime.datetime.now(__import__("zoneinfo").ZoneInfo("Europe/Stockholm"))
                .date()
                .isoformat()
            )
            data = {
                "current": {"temperature_2m": 7.8},
                "daily": {
                    "time": [date],
                    "weather_code": [2],
                    "temperature_2m_max": [12],
                    "temperature_2m_min": [5],
                    "precipitation_sum": [0],
                    "wind_speed_10m_max": [14],
                },
            }
            with patch("weather_forecast.requests.get", return_value=response(data)) as get:
                forecast.refresh()
                self.assertEqual(get.call_args.kwargs["params"]["latitude"], 59.3)
                self.assertEqual(forecast.snapshot()["current_temperature"], 7.8)
                self.assertEqual(forecast.snapshot()["today"]["temperature"], 12)
            store.save({"weather_city": "Another city", "weather_latitude": 60.0})
            self.assertIsNone(forecast.snapshot()["today"])
            self.assertTrue(forecast.snapshot()["stale"])
        with patch(
            "weather_forecast.requests.get",
            return_value=response(
                {
                    "results": [
                        {"name": "City", "country": "Country", "latitude": 12, "longitude": 34}
                    ]
                }
            ),
        ):
            self.assertEqual(search_cities("City")[0]["latitude"], 12)


class PrivatePhotoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.settings = SettingsStore(self.root / "settings.json")
        self.library = PhotoLibrary(
            {
                "immich_url": "https://photos.example.invalid",
                "immich_api_key": "test",
                "album_id": "default",
            },
            self.settings,
            self.root / "cache",
            root=self.root,
        )
        self.library.catalog_time = 10**12
        self.private = self.library.private
        self.client = {
            "installed": {
                "client_id": "example.apps.googleusercontent.com",
                "client_secret": "test-client-secret",
            }
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_google_oauth_pkce_state_one_use_and_no_secret_in_url(self):
        self.private.google_configure(self.client)
        params = parse_qs(urlparse(self.private.google_start()).query)
        self.assertNotIn("client_secret", params)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        verifier = self.private.oauth["verifier"]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        self.assertEqual(params["code_challenge"], [challenge])
        with self.assertRaises(ValueError):
            self.private.google_callback("wrong-state", "code")
        with patch(
            "private_photos.requests.post",
            return_value=response(
                {"access_token": "test-access", "refresh_token": "test-refresh", "expires_in": 3600}
            ),
        ) as post:
            self.private.google_callback(params["state"][0], "code")
            self.assertEqual(post.call_args.kwargs["data"]["code_verifier"], verifier)
        with self.assertRaises(ValueError):
            self.private.google_callback(params["state"][0], "code")
        text = json.dumps(self.private.snapshot()) + json.dumps(self.library.options())
        self.assertNotIn("test-access", text)
        self.assertNotIn("test-client-secret", text)
        self.assertEqual((self.private.root / "connections.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.private.root.stat().st_mode & 0o777, 0o700)

    def test_oauth_expiry_and_refresh(self):
        self.private.google_configure(self.client)
        self.private.google_start()
        self.private.oauth["expires"] = time.time() - 1
        with self.assertRaises(ValueError):
            self.private.google_callback(self.private.oauth["state"], "code")
        self.private.data["google_token"] = {
            "access_token": "expired",
            "refresh_token": "refresh",
            "expires_at": 0,
        }
        with patch(
            "private_photos.requests.post",
            return_value=response({"access_token": "new-access", "expires_in": 3600}),
        ):
            self.assertEqual(self.private.google_token(), "new-access")
        self.assertEqual(self.private.data["google_token"]["refresh_token"], "refresh")

    def test_private_google_import_without_any_public_link(self):
        with patch.object(
            self.private,
            "google_request",
            return_value=response(
                {
                    "id": "fake-session",
                    "pickerUri": "https://photos.google.com/picker/session",
                    "pollingConfig": {"pollInterval": "8s"},
                }
            ),
        ):
            self.assertTrue(self.private.google_picker("Private album").endswith("/autoclose"))
            self.assertEqual(self.private.picker["interval"], 8)
        self.private.picker = {
            "id": "fake-session",
            "name": "Private album",
            "interval": 5,
            "next_poll": 0,
        }
        self.private.data["google_token"] = {
            "access_token": "test-access",
            "expires_at": time.time() + 3600,
        }
        out = io.BytesIO()
        Image.new("RGB", (30, 20), "blue").save(out, "JPEG")
        photo = {
            "id": "image-1",
            "mediaFile": {
                "mimeType": "image/jpeg",
                "baseUrl": "https://lh3.googleusercontent.com/private-image",
            },
        }
        with (
            patch.object(
                self.private,
                "google_request",
                side_effect=[
                    response({"mediaItemsSet": True}),
                    response({"mediaItems": [photo]}),
                    response({}),
                ],
            ),
            patch("private_photos.requests.get") as get,
            patch("private_photos.image_bytes", return_value=out.getvalue()),
        ):
            self.private.google_import()
            self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer test-access")
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
        albums = self.library.options()["albums"]["google"]
        self.assertEqual(len(albums), 1)
        self.assertTrue(albums[0]["private"])
        self.settings.save({"photo_source": "google", "photo_album": albums[0]["id"]})
        photos = self.library.refresh()
        self.assertEqual(len(photos), 1)
        self.assertFalse(self.library.links)
        self.assertTrue((self.library.cache / photos[0]["file"]).is_file())
        self.private.disconnect("google")
        self.assertFalse(self.private.google_albums)
        self.assertNotIn("google_token", self.private.data)

    def test_private_download_rejects_untrusted_host(self):
        with self.assertRaises(ValueError):
            self.library.image_url("https://evil.example/image", "google")
        with self.assertRaises(ValueError):
            self.library.image_url("https://127.0.0.1/image", "icloud")

    def test_icloud_two_factor_and_album_catalog_without_public_share(self):
        apple = Mock()
        apple.requires_2fa = True
        apple.requires_2sa = False
        from pyicloud.services.photos import AlbumContainer

        family = Mock()
        family.id = "private-album-id"
        family.name = "Family"
        family.fullname = "Family"
        hidden = Mock()
        hidden.id = "hidden-id"
        hidden.name = "Hidden"
        hidden.fullname = "Hidden"
        apple.photos.albums = AlbumContainer([family, hidden])
        apple.is_trusted_session = False
        apple.validate_2fa_code.return_value = True
        with patch("pyicloud.PyiCloudService", return_value=apple) as constructor:
            self.private.apple_login("account@example.invalid", "test-password")
            self.assertEqual(self.private.snapshot()["icloud"]["state"], "two_factor")
            self.assertFalse(constructor.call_args.kwargs["locate"])
            apple.requires_2fa = False
            self.private.apple_verify("123456")
        self.assertEqual(self.private.snapshot()["icloud"]["state"], "connected")
        self.assertEqual(len(self.library.options()["albums"]["icloud"]), 1)
        self.assertTrue(self.library.options()["albums"]["icloud"][0]["private"])
        self.assertFalse(self.library.links)
        apple.trust_session.assert_called_once()
        root_library = Mock()
        apple.photos.libraries = {"root": root_library}
        self.private.apple_catalog(refresh=True)
        root_library.refresh_albums.assert_called_once()


if __name__ == "__main__":
    unittest.main()
