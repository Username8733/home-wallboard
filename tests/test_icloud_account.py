"""Account management reads existing configuration without migrating credentials."""

import copy
import json
import threading
import unittest
from unittest.mock import Mock, patch

from icloud_account import ICloudAccount


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.photos = Mock()
        self.photos.lock = threading.RLock()
        self.photos.data = {
            "icloud": {"username": "account@example.invalid", "password": "private-photo-password"}
        }
        self.photos.snapshot.return_value = {"icloud": {"state": "connected", "message": ""}}
        self.planner = Mock(base="https://ha.example.invalid", prefix="/api/hassio_ingress/test")
        self.planner.ingress.return_value = "private-session-cookie"
        self.account = ICloudAccount(self.planner, self.photos)
        self.session = {
            "csrf": "private-csrf-token",
            "configured": True,
            "ready": True,
            "appleId": "account@example.invalid",
            "calendarId": "current",
            "timezone": "Europe/Stockholm",
        }
        self.sources = {
            "sources": [
                {
                    "id": "icloud",
                    "selected": ["current"],
                    "calendars": [
                        {
                            "id": "current",
                            "name": "Family",
                            "url": "https://private.example.invalid",
                            "password": "not-public",
                        }
                    ],
                }
            ]
        }

    def test_status_reads_only_and_never_returns_secrets(self):
        self.account.call = Mock(
            side_effect=[copy.deepcopy(self.session), copy.deepcopy(self.sources)]
        )
        body = self.account.snapshot()
        serialized = json.dumps(body)
        self.assertTrue(body["calendar"]["configured"])
        self.assertEqual(body["calendar"]["selected"], ["current"])
        self.assertFalse(body["account_mismatch"])
        for private in [
            "private-csrf-token",
            "private-photo-password",
            "not-public",
            "https://private.example.invalid",
        ]:
            self.assertNotIn(private, serialized)
        self.assertEqual(
            [call.args[:2] for call in self.account.call.call_args_list],
            [("GET", "api/session"), ("GET", "api/v2/sources")],
        )

    def test_calendar_outage_keeps_photo_connection_available(self):
        import requests

        self.account.call = Mock(side_effect=requests.ConnectionError())
        status = self.account.snapshot()
        self.assertFalse(status["calendar"]["available"])
        self.assertEqual(status["photos"]["state"], "connected")
        self.assertEqual(status["apple_id"], "account@example.invalid")

    def test_account_mismatch_is_visible_without_replacing_any_connection(self):
        self.photos.data["icloud"]["username"] = "another@example.invalid"
        self.account.call = Mock(
            side_effect=[copy.deepcopy(self.session), copy.deepcopy(self.sources)]
        )
        self.assertTrue(self.account.snapshot()["account_mismatch"])
        self.assertEqual(self.photos.data["icloud"]["username"], "another@example.invalid")

    def test_same_account_reconnect_preserves_calendar_and_enabled_state(self):
        self.account.calendar_status = Mock(
            return_value={
                "apple_id": "account@example.invalid",
                "calendar_id": "current",
                "selected": ["current"],
                "timezone": "Europe/Stockholm",
            }
        )
        self.account.call = Mock(
            return_value={
                "calendars": [{"id": "current", "name": "Family"}, {"id": "second", "name": "Work"}]
            }
        )
        self.account.snapshot = Mock(return_value={"ok": True})
        self.account.command(
            {
                "action": "connect",
                "username": "account@example.invalid",
                "password": "new-app-password",
            }
        )
        calls = self.account.call.call_args_list
        self.assertEqual(calls[0].args[:2], ("POST", "api/connection"))
        self.assertEqual(
            calls[1].args,
            ("POST", "api/selection", {"calendarId": "current", "timezone": "Europe/Stockholm"}),
        )
        self.assertEqual(
            calls[2].args,
            (
                "PUT",
                "api/v2/sources/icloud",
                {"selected": ["current"], "timezone": "Europe/Stockholm"},
            ),
        )

    def test_invalid_selection_and_unknown_actions_do_not_write(self):
        self.account.calendar_status = Mock(
            return_value={"calendars": [{"id": "current", "name": "Family"}]}
        )
        self.account.call = Mock()
        for body in [{"action": "select", "calendar": "forged"}, {"action": "unknown"}]:
            with self.assertRaises(ValueError):
                self.account.command(body)
        self.account.call.assert_not_called()
        with self.assertRaises(ValueError):
            self.account.command({"action": "connect", "username": "bad", "password": "short"})

    def test_disconnect_calendar_does_not_disconnect_photos(self):
        before = copy.deepcopy(self.photos.data)
        self.account.call = Mock(return_value={})
        self.account.snapshot = Mock(return_value={"ok": True})
        self.account.command({"action": "disconnect"})
        self.account.call.assert_called_once_with("DELETE", "api/connection")
        self.assertEqual(self.photos.data, before)
        self.photos.disconnect.assert_not_called()

    def test_internal_csrf_and_cookie_are_sent_only_to_fixed_ingress(self):
        session = Mock(status_code=200)
        session.json.return_value = {"csrf": "private-csrf"}
        result = Mock(status_code=200)
        result.json.return_value = {"configured": True}
        with patch("icloud_account.requests.request", side_effect=[session, result]) as request:
            self.account.call(
                "POST",
                "api/connection",
                {"username": "account@example.invalid", "password": "app-password-value"},
            )
            headers = request.call_args.kwargs["headers"]
            self.assertEqual(headers["X-Hemma-CSRF"], "private-csrf")
            self.assertEqual(headers["Cookie"], "ingress_session=private-session-cookie")
            self.assertFalse(request.call_args.kwargs["allow_redirects"])
        with self.assertRaises(ValueError):
            self.account.call("GET", "https://evil.example.invalid/")


if __name__ == "__main__":
    unittest.main()
