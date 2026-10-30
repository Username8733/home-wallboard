"""One iCloud settings entry with separate Calendar and Photos permissions.

Calendar credentials remain in Family Planner's private store; photo credentials
remain in the tablet's private store. No credential export or implicit relogin.
"""

import threading

import requests


class ICloudAccount:
    PATHS = {
        "api/session",
        "api/v2/sources",
        "api/calendars",
        "api/connection",
        "api/selection",
        "api/v2/sources/icloud",
    }

    def __init__(self, planner, photos):
        self.planner = planner
        self.photos = photos
        self.lock = threading.Lock()
        self.calendar_cache = []

    def call(self, method, path, body=None):
        if path not in self.PATHS or method not in {"GET", "POST", "PUT", "DELETE"}:
            raise ValueError("Ogiltig kontoåtgärd.")
        session = self.planner.ingress()
        headers = {"Cookie": "ingress_session=" + session, "Origin": self.planner.base}
        if method != "GET":
            token = self.call("GET", "api/session").get("csrf")
            if not isinstance(token, str) or not token:
                raise ValueError("Kalenderanslutningen kunde inte verifieras. Försök igen.")
            headers["X-Hemma-CSRF"] = token
        response = requests.request(
            method,
            self.planner.base + self.planner.prefix + "/" + path,
            headers=headers,
            json=body,
            timeout=(5, 35),
            allow_redirects=False,
        )
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Kalenderanslutningen gav ett oväntat svar.")
        if response.status_code >= 400:
            raise ValueError(data.get("error", "Kalenderanslutningen kunde inte nås."))
        return data

    def calendar_status(self):
        session = self.call("GET", "api/session")
        sources = self.call("GET", "api/v2/sources").get("sources", [])
        primary = next((source for source in sources if source.get("id") == "icloud"), {})
        # Only public calendar metadata, never CSRF, URLs or app passwords.
        with self.lock:
            calendars = {
                c["id"]: {"id": c["id"], "name": c.get("name", "iCloud")}
                for c in self.calendar_cache
            }
        for calendar in primary.get("calendars", []):
            calendars.setdefault(
                calendar["id"], {"id": calendar["id"], "name": calendar.get("name", "iCloud")}
            )
        return {
            "configured": bool(session.get("configured")),
            "ready": bool(session.get("ready")),
            "apple_id": session.get("appleId", ""),
            "calendars": list(calendars.values()),
            "selected": primary.get("selected", []),
            "calendar_id": session.get("calendarId", ""),
            "timezone": session.get("timezone", "Europe/Stockholm"),
        }

    def snapshot(self):
        try:
            calendar = {**self.calendar_status(), "available": True, "error": ""}
        except (requests.RequestException, ValueError, KeyError, TypeError):
            calendar = {
                "available": False,
                "configured": False,
                "ready": False,
                "apple_id": "",
                "calendars": [],
                "selected": [],
                "error": "Kalenderanslutningen kunde inte nås.",
            }
        with self.photos.lock:
            photo_id = self.photos.data.get("icloud", {}).get("username", "")
        status = self.photos.snapshot()["icloud"]
        calendar_id = calendar["apple_id"]
        return {
            "apple_id": calendar_id or photo_id,
            "calendar": calendar,
            "photos": {**status, "apple_id": photo_id},
            "account_mismatch": bool(
                calendar_id
                and photo_id
                and calendar_id.strip().casefold() != photo_id.strip().casefold()
            ),
        }

    def command(self, body):
        action = body.get("action")
        if action == "connect":
            username, password = body.get("username"), body.get("password")
            if (
                not isinstance(username, str)
                or "@" not in username
                or len(username) > 254
                or not isinstance(password, str)
                or not 12 <= len(password.strip()) <= 1024
            ):
                raise ValueError("Ange Apple-konto och ett appspecifikt lösenord för kalendern.")
            before = self.calendar_status()
            result = self.call(
                "POST",
                "api/connection",
                {"username": username.strip(), "password": password.strip()},
            )
            calendars = [
                {"id": c["id"], "name": c.get("name", "iCloud")}
                for c in result.get("calendars", [])
            ]
            with self.lock:
                self.calendar_cache = calendars
            # Reauthorizing the same account must retain its calendar and enabled state.
            old_id = before.get("calendar_id")
            if (
                before["apple_id"].strip().casefold() == username.strip().casefold()
                and old_id
                and any(c["id"] == old_id for c in calendars)
            ):
                self.call(
                    "POST", "api/selection", {"calendarId": old_id, "timezone": before["timezone"]}
                )
                self.call(
                    "PUT",
                    "api/v2/sources/icloud",
                    {"selected": before["selected"], "timezone": before["timezone"]},
                )
        elif action == "refresh":
            data = self.call("GET", "api/calendars")
            with self.lock:
                self.calendar_cache = [
                    {"id": c["id"], "name": c.get("name", "iCloud")}
                    for c in data.get("calendars", [])
                ]
        elif action == "select":
            calendar = body.get("calendar")
            if not isinstance(calendar, str) or not calendar or len(calendar) > 200:
                raise ValueError("Välj en kalender från listan.")
            status = self.calendar_status()
            if not any(c["id"] == calendar for c in status["calendars"]):
                raise ValueError("Välj en kalender från listan.")
            self.call(
                "PUT",
                "api/v2/sources/icloud",
                {"selected": [calendar], "timezone": status.get("timezone", "Europe/Stockholm")},
            )
        elif action == "disconnect":
            self.call("DELETE", "api/connection")
            with self.lock:
                self.calendar_cache = []
        else:
            raise ValueError("Ogiltig kontoåtgärd.")
        return self.snapshot()
