"""Display-only security inventory; camera access remains on the local server."""

import json
import posixpath
import re
import threading
import time

import requests
import websocket
from flask import Response, abort
from site_config import load_config

SECURITY = load_config().get("security", {})

CAMERAS = SECURITY.get("cameras", {})
DOORS = SECURITY.get("doors", {})
LOCK = SECURITY.get("lock", "lock.front_door")
ALARM = SECURITY.get("alarm", "alarm_control_panel.home")
ENTITIES = set(CAMERAS) | {c["motion"] for c in CAMERAS.values()} | set(DOORS) | {LOCK, ALARM}


def public_states(states):
    # HA camera attributes contain bearer-like access tokens and signed URLs.
    return {
        entity: (
            {
                "entity_id": entity,
                "state": s["state"],
                "attributes": {"friendly_name": CAMERAS[entity]["name"]},
            }
            if entity in CAMERAS
            else s
        )
        for entity, s in states.items()
    }


def summary(states, online):
    def value(e):
        return states.get(e, {}).get("state", "unknown") if online else "unknown"

    return {
        "online": online,
        "alarm": value(ALARM),
        "lock": value(LOCK),
        "doors": [{"entity_id": e, "name": name, "state": value(e)} for e, name in DOORS.items()],
        "cameras": [
            {"entity_id": e, "name": c["name"], "state": value(e), "motion": value(c["motion"])}
            for e, c in CAMERAS.items()
        ],
    }


class CameraProxy:
    def __init__(self, config):
        self.base = config["ha_url"].rstrip("/")
        self.token = config["ha_token"]
        self.headers = {"Authorization": "Bearer " + self.token}
        self.hls_paths = {}
        self.hls_lock = threading.Lock()
        self.camera_locks = {}
        self.image_cache = {}
        self.image_locks = {}

    def image(self, entity):
        if entity not in CAMERAS:
            abort(404)
        with self.hls_lock:
            guard = self.image_locks.setdefault(entity, threading.Lock())
        with guard:
            cached = self.image_cache.get(entity)
            if cached and time.time() - cached[0] < 1:
                return Response(cached[1], content_type=cached[2])
            return self.fetch_image(entity)

    def fetch_image(self, entity):
        try:
            r = requests.get(
                self.base + "/api/camera_proxy/" + entity,
                headers=self.headers,
                params={"width": 640, "height": 360},
                timeout=(5, 18),
            )
            if r.status_code != 200 or not r.headers.get("Content-Type", "").startswith("image/"):
                abort(502)
            self.image_cache[entity] = (time.time(), r.content, r.headers["Content-Type"])
            return Response(r.content, content_type=r.headers["Content-Type"])
        except requests.RequestException:
            abort(502)

    def stream(self, entity):
        if entity not in CAMERAS:
            abort(404)
        try:
            r = requests.get(
                self.base + "/api/camera_proxy_stream/" + entity,
                headers=self.headers,
                params={"interval": 1},
                stream=True,
                timeout=(5, 20),
            )
            if r.status_code != 200 or not r.headers.get("Content-Type", "").startswith(
                "multipart/"
            ):
                r.close()
                abort(502)
        except requests.RequestException:
            abort(502)

        def chunks():
            try:
                for part in r.iter_content(1024):
                    if part:
                        yield part
            except requests.RequestException:
                pass
            finally:
                r.close()

        return Response(chunks(), content_type=r.headers["Content-Type"])

    def hls_prefix(self, entity):
        with self.hls_lock:
            guard = self.camera_locks.setdefault(entity, threading.Lock())
        with guard:
            cached = self.hls_paths.get(entity)
            if cached and time.time() - cached[1] < 180:
                return cached[0]
            w = websocket.create_connection(
                self.base.replace("http://", "ws://").replace("https://", "wss://")
                + "/api/websocket",
                timeout=20,
            )
            try:
                w.recv()
                w.send(json.dumps({"type": "auth", "access_token": self.token}))
                if json.loads(w.recv())["type"] != "auth_ok":
                    raise RuntimeError("HA authentication failed")
                w.send(
                    json.dumps(
                        {"id": 1, "type": "camera/stream", "entity_id": entity, "format": "hls"}
                    )
                )
                r = json.loads(w.recv())
                if not r.get("success"):
                    raise RuntimeError("Camera video unavailable")
                url = r["result"]["url"]
                if not re.fullmatch(r"/api/hls/[A-Za-z0-9_-]+/master_playlist\.m3u8", url):
                    raise RuntimeError("Unexpected HLS path")
                prefix = posixpath.dirname(url)
                self.hls_paths[entity] = (prefix, time.time())
                return prefix
            finally:
                w.close()

    def hls(self, entity, file, query):
        if entity not in CAMERAS:
            abort(404)
        if file not in {"master_playlist.m3u8", "playlist.m3u8", "init.mp4"} and not re.fullmatch(
            r"segment/\d+(?:\.\d+)?\.m4s", file
        ):
            abort(404)
        params = {}
        for key, value in query.items():
            if key in {"_HLS_msn", "_HLS_part"} and re.fullmatch(r"\d{1,10}", value):
                params[key] = value
            elif key == "_HLS_skip" and value in {"YES", "v2"}:
                params[key] = value
            else:
                abort(400)
        try:
            prefix = self.hls_prefix(entity)
            r = requests.get(
                self.base + prefix + "/" + file,
                headers=self.headers,
                params=params,
                timeout=(5, 25),
            )
            if r.status_code != 200:
                self.hls_paths.pop(entity, None)
                abort(502)
            content = r.content
            if file.endswith(".m3u8"):
                local = "/api/camera/" + entity + "/hls/"
                text = r.text.replace(self.base + prefix + "/", local).replace(prefix + "/", local)
                content = text.encode()
            return Response(
                content, content_type=r.headers.get("Content-Type", "application/octet-stream")
            )
        except (
            requests.RequestException,
            websocket.WebSocketException,
            RuntimeError,
            OSError,
            ValueError,
            KeyError,
        ):
            abort(502)
