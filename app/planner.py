"""Proxy only the existing Family Planner ingress, using the non-admin kiosk user."""

import json
import re
import threading
import time

import requests
import websocket
from flask import Response, abort, request


class PlannerProxy:
    def __init__(self, config):
        self.base = config["ha_url"].rstrip("/")
        self.token = config["ha_token"]
        self.lock = threading.Lock()
        self.session = None
        self.created = 0
        self.prefix = config.get("planner_ingress", "")
        self.device_preferences = None
        self.shared_locale = None

    def localize_state(self, body):
        """Overlay only this kiosk's locale; preserve the shared calendar's preferences."""
        if not self.device_preferences:
            return body
        if not isinstance(body.get("state"), dict):
            with self.lock:
                self.shared_locale = {"language": "en", "timeFormat": "24h"}
            return body
        prefs = body["state"].get("preferences", {})
        with self.lock:
            self.shared_locale = {
                key: prefs.get(key, default)
                for key, default in (("language", "en"), ("timeFormat", "24h"))
            }
        local = self.device_preferences()
        body["state"]["preferences"] = {
            **prefs,
            "language": local["language"],
            "timeFormat": local["time_format"],
        }
        return body

    def preserve_shared_locale(self, body):
        if not self.device_preferences:
            return body
        with self.lock:
            shared = self.shared_locale
        if shared is None:
            raise ValueError("Planner shared preferences have not loaded")
        # PUT /api/state wraps the snapshot under state; never save kiosk-only locale choices.
        snapshot = body.get("state", body)
        if isinstance(snapshot, dict) and isinstance(snapshot.get("preferences"), dict):
            snapshot["preferences"].update(shared)
        return body

    def ingress(self, force=False):
        with self.lock:
            if not force and self.session and time.time() - self.created < 1200:
                return self.session
            w = websocket.create_connection(
                self.base.replace("http://", "ws://").replace("https://", "wss://")
                + "/api/websocket",
                timeout=15,
            )
            try:
                w.recv()
                w.send(json.dumps({"type": "auth", "access_token": self.token}))
                if json.loads(w.recv())["type"] != "auth_ok":
                    raise RuntimeError("HA authentication failed")
                w.send(
                    json.dumps(
                        {
                            "id": 1,
                            "type": "supervisor/api",
                            "endpoint": "/ingress/session",
                            "method": "post",
                        }
                    )
                )
                r = json.loads(w.recv())
                if not r.get("success"):
                    raise RuntimeError("Planner ingress unavailable")
                self.session = r["result"]["session"]
                self.created = time.time()
                return self.session
            finally:
                w.close()

    def response(self, path):
        if not self.prefix:
            abort(503)
        allowed = {
            "",
            "index.html",
            "api/session",
            "api/state",
            "api/v2/sources",
            "api/v2/events",
            "api/calendars",
            "api/events",
            "api/selection",
            "api/connection",
        }
        if path not in allowed and not re.fullmatch(r"api/v2/sources/[a-zA-Z0-9_-]+", path):
            abort(404)
        if len(request.get_data()) > 5_000_000:
            abort(413)
        try:
            payload = request.get_data()
            if path == "api/state" and request.method == "PUT" and self.device_preferences:
                payload = json.dumps(self.preserve_shared_locale(request.get_json())).encode()
            for retry in range(2):
                session = self.ingress(force=bool(retry))
                headers = {"Cookie": "ingress_session=" + session, "Origin": self.base}
                for h in ["Content-Type", "X-Hemma-CSRF"]:
                    if h in request.headers:
                        headers[h] = request.headers[h]
                r = requests.request(
                    request.method,
                    self.base + self.prefix + "/" + path,
                    params=request.args,
                    headers=headers,
                    data=payload,
                    timeout=35,
                    allow_redirects=False,
                )
                if r.status_code not in {401, 403}:
                    break
            if path == "api/state" and request.method == "GET" and r.status_code == 200:
                return Response(
                    json.dumps(self.localize_state(r.json()), ensure_ascii=False),
                    status=200,
                    content_type="application/json",
                )
            # Never propagate ingress credentials or upstream cookies to the browser.
            return Response(
                r.content,
                status=r.status_code,
                content_type=r.headers.get("Content-Type", "application/octet-stream"),
            )
        except (
            requests.RequestException,
            websocket.WebSocketException,
            RuntimeError,
            OSError,
            ValueError,
            TypeError,
        ):
            english = self.device_preferences and self.device_preferences()["language"] == "en"
            return Response(
                "Family Planner is temporarily disconnected. Try again."
                if english
                else "Family Planner är tillfälligt frånkopplad. Försök igen.",
                status=502,
                content_type="text/plain; charset=utf-8",
            )
