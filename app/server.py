import json
import logging
import pathlib
import threading
import time
import uuid

import requests
import security
import temperatures
import websocket
from control_agent import ControlAgent
from display_policy import ScreenPower, display_state, night_scheduled
from fire import DETECTORS, FireMonitor
from flask import Flask, Response, abort, jsonify, request, send_from_directory
from icloud_account import ICloudAccount
from keyboard_control import KeyboardControl
from lighting import (
    LightAreas,
    control_capabilities,
    light_catalog,
    light_icons,
    light_rooms,
    validate_light_control,
)
from music import PLAYER, SONOS, Music
from photo_library import SOURCES, PhotoLibrary
from planner import PlannerProxy
from settings_store import DEFAULTS, MAX_LIGHTS, SettingsStore
from site_config import load_config
from sound_catalog import SOUNDS
from timer_sound import TimerSound
from timer_store import TimerStore
from weather_forecast import Forecast, search_cities
from werkzeug.serving import make_server

ROOT = pathlib.Path(__file__).parent
C = load_config()
CACHE = pathlib.Path("/var/lib/wallboard/photos")
CACHE.mkdir(parents=True, exist_ok=True)
app = Flask(__name__, static_folder="static")
logging.basicConfig(level=logging.INFO)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
lock = threading.RLock()
states = {}
ha_updated = 0
ha_error = True
photos = []
photos_updated = 0
immich_error = True
last_touch = time.time()
night_wake_until = 0
brightness = -1
manual_screen_off = False
actual_dashboard = None
remote_view = {"sequence": 0, "page": None}
preference_write_lock = threading.Lock()
mode = "active"
LIGHTS = C.get("lights", {})
PEOPLE = [p["name"] for p in C.get("people", [])]
ENTITIES = (
    set(LIGHTS)
    | {C.get("home", {}).get("alarm", "alarm_control_panel.home")}
    | set(C.get("home", {}).get("doors", {}))
    | {p["entity"] for p in C.get("people", [])}
)
FIRE = FireMonitor("/var/lib/wallboard/fire-latch.json")
PLANNER = PlannerProxy(C)
CAMERA_PROXY = security.CameraProxy(C)
SETTINGS = SettingsStore(
    "/var/lib/wallboard/settings.json", {"idle_seconds": C.get("idle_seconds", 90)}
)
PLANNER.device_preferences = SETTINGS.snapshot
PHOTO_LIBRARY = PhotoLibrary(C, SETTINGS, CACHE)
ICLOUD_ACCOUNT = ICloudAccount(PLANNER, PHOTO_LIBRARY.private)
KEYBOARD = KeyboardControl()
CONTROL_AGENT = ControlAgent(C)
MUSIC = Music(C, selection_path="/var/lib/wallboard/music-player.json")
FORECAST = Forecast(C, SETTINGS)
LIGHT_AREAS = LightAreas(C)
TIMER = TimerStore("/var/lib/wallboard/timer.json")
TIMER_SOUND = TimerSound(
    TIMER,
    lambda: bool(FIRE.status(states, False)["active"]),
    lambda: SETTINGS.snapshot()["timer_volume"],
    lambda: SETTINGS.snapshot()["timer_outputs"],
    MUSIC.announce,
    lambda: SETTINGS.snapshot()["timer_sound"],
)
ICON_PATHS = json.loads((ROOT / "static/vendor/mdi-paths.json").read_text())
ENTITIES.update({PLAYER, SONOS})
ENTITIES.update(security.ENTITIES)
ENTITIES.update(DETECTORS)
ENTITIES.update(d["mute"] for d in DETECTORS.values() if d["mute"])
HA = requests.Session()
HA.headers["Authorization"] = "Bearer " + C["ha_token"]
IM = requests.Session()
IM.headers["x-api-key"] = C["immich_api_key"]


def ha_loop():
    global states, ha_updated, ha_error, LIGHTS
    while True:
        w = None
        try:
            url = (
                C["ha_url"].replace("http://", "ws://").replace("https://", "wss://")
                + "/api/websocket"
            )
            w = websocket.create_connection(url, timeout=12)
            w.recv()
            w.send(json.dumps({"type": "auth", "access_token": C["ha_token"]}))
            if json.loads(w.recv())["type"] != "auth_ok":
                raise RuntimeError("HA authentication failed")
            w.send(json.dumps({"id": 1, "type": "subscribe_entities"}))
            ack = json.loads(w.recv())
            if not ack.get("success"):
                raise RuntimeError("HA state subscription failed")
            # Keep the last snapshot during reconnect; active fire alarms remain latched.
            w.settimeout(10)
            counter = 1
            awaiting_pong = False

            def update(msg):
                global LIGHTS
                if msg.get("type") != "event":
                    return
                event = msg.get("event", {})
                with lock:
                    for entity, data in event.get("a", {}).items():
                        if entity in ENTITIES or entity.startswith(
                            ("light.", "group.", "media_player.", "sensor.", "weather.")
                        ):
                            states[entity] = {
                                "entity_id": entity,
                                "state": data["s"],
                                "attributes": data.get("a", {}),
                            }
                    for entity, diff in event.get("c", {}).items():
                        if entity not in states:
                            continue
                        plus = diff.get("+", {})
                        if "s" in plus:
                            states[entity]["state"] = plus["s"]
                        if "a" in plus:
                            states[entity]["attributes"].update(plus["a"])
                        minus = diff.get("-", {})
                        if isinstance(minus, dict):
                            for attr in minus.get("a", []):
                                states[entity]["attributes"].pop(attr, None)
                    for entity in event.get("r", []):
                        states.pop(entity, None)
                    LIGHTS = light_catalog(states)
                    SETTINGS.allowed_lights = set(LIGHTS) | set(SETTINGS.snapshot()["lights"])
                    FIRE.update(states)

            while True:
                ha_updated = time.time()
                ha_error = False
                try:
                    msg = json.loads(w.recv())
                    awaiting_pong = False
                    update(msg)
                except websocket.WebSocketTimeoutException:
                    if awaiting_pong:
                        raise RuntimeError("HA heartbeat timed out")
                    counter += 1
                    w.send(json.dumps({"id": counter, "type": "ping"}))
                    awaiting_pong = True
        except Exception:
            ha_error = True
            logging.warning("Home Assistant disconnected; retrying")
        finally:
            if w:
                w.close()
        time.sleep(5)


def im_get(path, params=None):
    r = IM.get(C["immich_url"] + "/api" + path, params=params, timeout=25)
    r.raise_for_status()
    return r


def photo_progress(key, items):
    global photos_updated
    with lock:
        if key == PHOTO_LIBRARY.key():
            photos[:] = items
            photos_updated = time.time()


PHOTO_LIBRARY.on_progress = photo_progress


def photo_loop():
    global photos, photos_updated, immich_error
    with lock:
        photos = PHOTO_LIBRARY.cached()
    while True:
        key = PHOTO_LIBRARY.key()
        try:
            items = PHOTO_LIBRARY.refresh(key)
            with lock:
                if key == PHOTO_LIBRARY.key():
                    photos = items
                    photos_updated = time.time()
                immich_error = not PHOTO_LIBRARY.immich_online
        except Exception:
            PHOTO_LIBRARY.failure(key)
            immich_error = not PHOTO_LIBRARY.immich_online
            logging.warning(
                "Could not refresh selected photo source %s; retaining only its cached images",
                key[0],
            )
        PHOTO_LIBRARY.changed.wait(300)
        PHOTO_LIBRARY.changed.clear()


def presence():
    try:
        return json.loads(pathlib.Path("/run/wallboard/presence.json").read_text())
    except (FileNotFoundError, ValueError):
        return {}


def active_state(now=None):
    now = now or time.time()
    p = presence()
    healthy = now - p.get("last_frame", 0) < 15
    cfg = SETTINGS.snapshot()
    # Keep the dashboard usable if the camera fails. Touch always wakes the screen.
    seen = p.get("last_seen", 0) if cfg["presence_enabled"] else 0
    active = (
        TIMER.snapshot()["status"] == "finished"
        or bool(FIRE.status(states, False)["active"])
        or cfg["screen_mode"] == "keep_on"
        or (cfg["presence_enabled"] and not healthy)
        or now - max(last_touch, seen) < cfg["idle_seconds"]
    )
    return active, healthy, p


def current_display(active, cfg):
    return display_state(
        cfg,
        active,
        bool(FIRE.status(states, False)["active"]),
        TIMER.snapshot()["status"] == "finished",
        night_wake_until,
        manual_sleep=manual_screen_off,
    )


def display_loop():
    global mode, brightness
    backlight = pathlib.Path("/sys/class/backlight/intel_backlight")
    maximum = int((backlight / "max_brightness").read_text())
    power = ScreenPower()
    fire_before = False
    previous_mode = None
    while True:
        active, _, _ = active_state()
        cfg = SETTINGS.snapshot()
        fire = FIRE.status(states, False)["active"]
        decision = current_display(active, cfg)
        mode = decision["mode"]
        target = round(maximum * decision["level"])
        if (fire and not fire_before) or (
            mode in {"night", "screen_off"} and previous_mode not in {"night", "screen_off"}
        ):
            threading.Thread(target=KEYBOARD.set_visible, args=(False,), daemon=True).start()
        fire_before = fire
        previous_mode = mode
        try:
            current = int((backlight / "brightness").read_text())
            step = max(1, maximum // 35)
            val = (
                0
                if mode in {"night", "screen_off"}
                else max(target, current - step)
                if current > target
                else min(target, current + step)
            )
            if val != current:
                (backlight / "brightness").write_text(str(val))
            power.set_off(mode in {"night", "screen_off"})
            brightness = round(val / maximum * 100)
        except OSError:
            logging.exception("Brightness adjustment failed")
            time.sleep(10)
        time.sleep(0.1)


@app.before_request
def local_only():
    if request.host.split(":")[0] not in {"127.0.0.1", "localhost"}:
        abort(403)
    if request.method in {"POST", "PUT", "DELETE", "PATCH"} and request.headers.get(
        "Origin"
    ) not in {"http://127.0.0.1:8090", "http://localhost:8090"}:
        abort(403)


@app.after_request
def headers(r):
    r.headers["Cache-Control"] = "no-store"
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-src 'self'; media-src 'self' blob:; frame-ancestors 'none'"
    )
    if request.path.startswith("/planner/"):
        r.headers["X-Frame-Options"] = "SAMEORIGIN"
        r.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data:; connect-src 'self' https://api.open-meteo.com https://geocoding-api.open-meteo.com; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
        )
    return r


@app.get("/")
def index():
    return send_from_directory(ROOT / "static", "index.html")


@app.get("/api/state")
def state():
    with lock:
        active, healthy, p = active_state()
        cfg = SETTINGS.snapshot()
        return jsonify(
            home_entities=C.get("home", {}),
            people_entities={p["name"]: p["entity"] for p in C.get("people", [])},
            smoke_entities=list(DETECTORS),
            temperatures=temperatures.snapshot(
                states, cfg, FORECAST.snapshot(), not ha_error and time.time() - ha_updated < 25
            ),
            photo_library=PHOTO_LIBRARY.snapshot(),
            light_controls={e: control_capabilities(states.get(e, {})) for e in cfg["lights"]},
            light_icons={
                e: i
                for e, i in light_icons(states, LIGHT_AREAS.icons, ICON_PATHS).items()
                if e in cfg["lights"]
            },
            timer=TIMER.snapshot(),
            light_rooms={
                e: r
                for e, r in light_rooms(states, LIGHT_AREAS.entities).items()
                if e in cfg["lights"]
            },
            music=MUSIC.snapshot(states, not ha_error and time.time() - ha_updated < 25),
            forecast=FORECAST.snapshot(),
            settings=cfg,
            keyboard=KEYBOARD.snapshot(),
            security=security.summary(states, not ha_error and time.time() - ha_updated < 25),
            fire=FIRE.status(states, not ha_error and time.time() - ha_updated < 25),
            states=security.public_states(
                {e: x for e, x in states.items() if not e.startswith("media_player.")}
            ),
            ha_online=not ha_error and time.time() - ha_updated < 25,
            ha_updated=ha_updated,
            photos=photos,
            immich_online=not immich_error,
            photos_updated=photos_updated,
            mode=current_display(active, cfg)["mode"],
            display=current_display(active, cfg),
            remote_view=remote_view,
            camera_ok=healthy,
            camera_frames=p.get("frames", 0),
            faces=p.get("faces", 0),
            brightness=brightness,
            lights={e: n for e, n in LIGHTS.items() if e in cfg["lights"]},
            people=PEOPLE,
        )


def save_preferences(patch):
    global last_touch, night_wake_until
    with preference_write_lock:
        candidate = SETTINGS.validate(patch)
        before = PHOTO_LIBRARY.key()
        if PHOTO_LIBRARY.key(candidate) != before:
            PHOTO_LIBRARY.validate_selection(candidate)
        old_settings = SETTINGS.snapshot()
        for field in ("indoor_temperature_entity", "outdoor_temperature_entity"):
            if candidate[field] != old_settings[field] and candidate[
                field
            ] not in temperatures.catalog(states):
                raise ValueError("Välj en temperaturgivare från listan.")
        if (
            candidate["weather_entity"] != old_settings["weather_entity"]
            and candidate["weather_entity"] not in states
        ):
            raise ValueError("Välj en väderentitet från listan.")
        cfg = SETTINGS.save(patch)
        if any(
            old_settings[k] != cfg[k] for k in ("night_mode_enabled", "night_start", "night_end")
        ):
            night_wake_until = 0
        last_touch = time.time()
        if any(old_settings[k] != cfg[k] for k in cfg if k.startswith("weather_")):
            FORECAST.changed.set()
        if PHOTO_LIBRARY.key() != before:
            with lock:
                photos[:] = PHOTO_LIBRARY.cached()
            with PHOTO_LIBRARY.lock:
                PHOTO_LIBRARY.status = {
                    "source": PHOTO_LIBRARY.key()[0],
                    "source_name": SOURCES[PHOTO_LIBRARY.key()[0]],
                    "online": False,
                    "error": "Hämtar bilder från valt album…",
                }
            PHOTO_LIBRARY.changed.set()
        CONTROL_AGENT.report_now.set()
        return cfg


@app.route("/api/settings", methods=["GET", "PUT"])
def settings():
    global last_touch, night_wake_until
    if request.method == "GET":
        return jsonify(
            settings=SETTINGS.snapshot(),
            defaults=DEFAULTS,
            lights=LIGHTS,
            light_rooms=light_rooms(states, LIGHT_AREAS.entities),
            max_lights=MAX_LIGHTS,
            sounds=SOUNDS,
            photo_sources=PHOTO_LIBRARY.options(),
            temperature_sensors=temperatures.catalog(states, LIGHT_AREAS.entities),
            weather_entities={
                e: d.get("attributes", {}).get("friendly_name", e)
                for e, d in states.items()
                if e.startswith("weather.")
            },
        )
    if request.content_length and request.content_length > 16384:
        abort(413)
    try:
        cfg = save_preferences(request.get_json(silent=True))
        return jsonify(settings=cfg)
    except (ValueError, TypeError) as error:
        return jsonify(error=str(error)), 400
    except OSError:
        return jsonify(error="Inställningarna kunde inte sparas. Försök igen."), 500


@app.get("/api/control/snapshot")
def control_snapshot():
    cfg = SETTINGS.snapshot()
    active, healthy, _ = active_state()
    sources = PHOTO_LIBRARY.options(allow_refresh=False)
    with lock:
        snapshot_states = dict(states)
    return jsonify(
        version="0.3.0",
        settings=cfg,
        catalog={
            "lights": LIGHTS,
            "light_rooms": light_rooms(snapshot_states, LIGHT_AREAS.entities),
            "temperature_sensors": temperatures.catalog(snapshot_states, LIGHT_AREAS.entities),
            "weather_entities": {
                e: d.get("attributes", {}).get("friendly_name", e)
                for e, d in snapshot_states.items()
                if e.startswith("weather.")
            },
            "photo_albums": {
                provider: [{"id": a["id"], "name": a["name"]} for a in albums]
                for provider, albums in sources["albums"].items()
            },
        },
        status={
            "mode": current_display(active, cfg)["mode"],
            "brightness": brightness,
            "dashboard": actual_dashboard or cfg["start_dashboard"],
            "camera_ok": healthy,
            "ha_online": not ha_error and time.time() - ha_updated < 25,
            "immich_online": not immich_error,
            "fire_active": bool(FIRE.status(snapshot_states, False)["active"]),
            "photos": len(photos),
        },
    )


@app.post("/api/control/view")
def control_view():
    global actual_dashboard
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or body.get("page") not in {
        "home",
        "planner",
        "security",
        "music",
    }:
        abort(400)
    actual_dashboard = body["page"]
    CONTROL_AGENT.report_now.set()
    return jsonify(ok=True)


@app.post("/api/control/command")
def control_command():
    global manual_screen_off, remote_view, last_touch, night_wake_until
    if request.content_length and request.content_length > 65536:
        abort(413)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400)
    action = body.get("action")
    data = body.get("data", {})
    if not isinstance(data, dict):
        abort(400)
    try:
        if action == "settings":
            return jsonify(settings=save_preferences(data))
        if action == "wake":
            return wake()
        if action == "sleep":
            if FIRE.status(states, False)["active"] or TIMER.snapshot()["status"] == "finished":
                return jsonify(error="An active alarm or finished timer keeps the screen on."), 409
            manual_screen_off = True
            return jsonify(ok=True)
        if action == "dashboard":
            if data.get("page") not in {"home", "planner", "security", "music"}:
                raise ValueError("Invalid dashboard")
            if FIRE.status(states, False)["active"]:
                return jsonify(error="Fire alarm has priority."), 409
            wake()
            remote_view = {"sequence": uuid.uuid4().hex, "page": data["page"]}
            return jsonify(ok=True)
        if action == "refresh":
            return jsonify(ok=True)
        if action == "weather_search":
            return jsonify(cities=search_cities(data.get("q", "")))
        if action == "account_status":
            return jsonify(ICLOUD_ACCOUNT.snapshot())
        if action == "icloud_calendar":
            return jsonify(ICLOUD_ACCOUNT.command(data))
        if action == "icloud_photo_login":
            username, password = data.get("username"), data.get("password")
            if (
                not isinstance(username, str)
                or not isinstance(password, str)
                or not username
                or not password
            ):
                raise ValueError("Enter an Apple account and password.")
            PHOTO_LIBRARY.private.run(
                "icloud", lambda: PHOTO_LIBRARY.private.apple_login(username, password)
            )
            return jsonify(ok=True)
        if action == "icloud_photo_2fa":
            code = data.get("code")
            if not isinstance(code, str) or not __import__("re").fullmatch(r"\d{6}", code):
                raise ValueError("Enter the six-digit code.")
            PHOTO_LIBRARY.private.run("icloud", lambda: PHOTO_LIBRARY.private.apple_verify(code))
            return jsonify(ok=True)
        if action == "google_configure":
            PHOTO_LIBRARY.private.google_configure(data)
            return jsonify(ok=True)
        if action == "google_pick":
            return jsonify(url=PHOTO_LIBRARY.private.google_picker(data.get("name")))
        if action == "google_import":
            PHOTO_LIBRARY.private.run("google", PHOTO_LIBRARY.private.google_import)
            return jsonify(ok=True)
        if action == "local_album":
            return jsonify(album=PHOTO_LIBRARY.create_folder(data.get("name")))
        raise ValueError("Unsupported control action")
    except (ValueError, TypeError) as error:
        return jsonify(error=str(error)), 400
    except (requests.RequestException, KeyError, OSError):
        return jsonify(error="The wallboard request could not be completed."), 502


@app.get("/api/weather/cities")
def weather_cities():
    try:
        return jsonify(cities=search_cities(request.args.get("q", "")))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except requests.RequestException:
        return jsonify(error="Städerna kunde inte hämtas. Försök igen."), 502


@app.get("/api/accounts/icloud")
def icloud_account_status():
    return jsonify(ICLOUD_ACCOUNT.snapshot())


@app.post("/api/accounts/icloud/calendar")
def icloud_calendar_account():
    if request.content_length and request.content_length > 16384:
        abort(413)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400)
    try:
        return jsonify(ICLOUD_ACCOUNT.command(body))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except (requests.RequestException, KeyError, TypeError):
        return jsonify(error="Kalenderanslutningen kunde inte nås."), 502


@app.get("/api/photos/private/status")
def private_photo_status():
    return jsonify(PHOTO_LIBRARY.private.snapshot())


@app.post("/api/photos/private/<source>/<action>")
def private_photo_action(source, action):
    if request.content_length and request.content_length > 32768:
        abort(413)
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        abort(400)
    private = PHOTO_LIBRARY.private
    try:
        if source == "icloud" and action == "login":
            username, password = body.get("username"), body.get("password")
            if (
                not isinstance(username, str)
                or not isinstance(password, str)
                or not username
                or not password
            ):
                raise ValueError("Ange Apple-konto och lösenord.")
            private.run(source, lambda: private.apple_login(username, password))
        elif source == "icloud" and action == "verify":
            code = body.get("code")
            if not isinstance(code, str) or not __import__("re").fullmatch(r"\d{6}", code):
                raise ValueError("Ange sexsiffrig kod.")
            private.run(source, lambda: private.apple_verify(code))
        elif source == "icloud" and action == "refresh":
            if not private.apple:
                raise ValueError("Logga in på iCloud först.")
            private.run(source, lambda: private.apple_catalog(refresh=True))
        elif source == "google" and action == "configure":
            private.google_configure(body)
        elif source == "google" and action == "login":
            return jsonify(url=private.google_start())
        elif source == "google" and action == "pick":
            return jsonify(url=private.google_picker(body.get("name")))
        elif source == "google" and action == "import":
            private.run(source, private.google_import)
        elif source == "google" and action == "cancel":
            if private.operation_lock.locked():
                raise ValueError("Vänta tills bildimporten är klar.")
            private.google_cancel()
        elif source in {"icloud", "google"} and action == "disconnect":
            albums = private.albums()[source]
            private.disconnect(source)
            selected = PHOTO_LIBRARY.key()
            if selected[0] == source and selected[1].startswith("private:"):
                SETTINGS.save({"photo_source": "immich", "photo_album": "default"})
                with lock:
                    photos[:] = PHOTO_LIBRARY.cached()
            for album in albums:
                key = (source, album["id"])
                for item in PHOTO_LIBRARY.cached(key):
                    (CACHE / item["file"]).unlink(missing_ok=True)
                PHOTO_LIBRARY.manifest(key).unlink(missing_ok=True)
            PHOTO_LIBRARY.changed.set()
        else:
            abort(404)
        return jsonify(ok=True, connections=private.snapshot())
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except (requests.RequestException, KeyError, TypeError):
        return jsonify(
            error="Fotoanslutningen kunde inte nås. Kontrollera kontoinställningarna och försök igen."
        ), 502


@app.get("/api/photos/google/callback")
def google_photo_callback():
    try:
        PHOTO_LIBRARY.private.google_callback(request.args.get("state"), request.args.get("code"))
        message = (
            "Google är anslutet. Återgå till wallboardens inställningar och välj privata bilder."
        )
    except (ValueError, requests.RequestException, KeyError, TypeError):
        message = "Google-inloggningen kunde inte slutföras. Stäng fliken och försök igen i wallboardens inställningar."
    english = SETTINGS.snapshot()["language"] == "en"
    if english:
        message = (
            "Google is connected. Return to wallboard Settings and select private photos."
            if message.startswith("Google är anslutet")
            else "Google sign-in could not be completed. Return to Settings and try again."
        )
    link = "Back to wallboard" if english else "Tillbaka till wallboarden"
    return Response(
        '<!doctype html><html lang="'
        + ("en" if english else "sv")
        + '"><meta charset="utf-8"><title>Wallboard · Google Photos</title><h1>Wallboard</h1><p>'
        + message
        + '</p><p><a href="/">'
        + link
        + "</a></p></html>",
        mimetype="text/html",
    )


@app.get("/api/photos/sources")
def photo_sources():
    return jsonify(PHOTO_LIBRARY.options())


@app.post("/api/photos/albums")
def photo_album_add():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400)
    try:
        if body.get("source") == "local":
            result = PHOTO_LIBRARY.create_folder(body.get("name"))
        else:
            result = PHOTO_LIBRARY.add_shared(body.get("source"), body.get("name"), body.get("url"))
        return jsonify(album=result, options=PHOTO_LIBRARY.options())
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except (requests.RequestException, KeyError, TypeError):
        return jsonify(
            error="Albumet kunde inte läsas. Använd en aktiv delningslänk för albumet."
        ), 400


@app.post("/api/photos/upload")
def photo_upload():
    if request.content_length and request.content_length > 100 * 1024 * 1024:
        abort(413)
    try:
        return jsonify(
            count=PHOTO_LIBRARY.upload(request.form.get("album"), request.files.getlist("photos"))
        )
    except ValueError as error:
        return jsonify(error=str(error)), 400


@app.post("/api/keyboard")
def keyboard():
    body = request.get_json(silent=True) or {}
    visible = body.get("visible")
    if type(visible) is not bool:
        return jsonify(error="Ogiltigt tangentbordskommando."), 400
    if visible and FIRE.status(states, False)["active"]:
        return jsonify(error="Tangentbordet är dolt under brandlarm."), 409
    if not KEYBOARD.set_visible(visible):
        return jsonify(error="Tangentbordet kunde inte öppnas. Försök igen."), 503
    return jsonify(keyboard=KEYBOARD.snapshot())


@app.post("/api/wake")
def wake():
    global last_touch, night_wake_until, manual_screen_off
    manual_screen_off = False
    last_touch = time.time()
    if night_scheduled(SETTINGS.snapshot(), last_touch):
        night_wake_until = last_touch + 120
    return jsonify(ok=True)


@app.post("/api/light")
def light():
    global last_touch
    last_touch = time.time()
    body = request.get_json(silent=True) or {}
    entity = body.get("entity_id")
    action = body.get("action")
    if (
        entity not in LIGHTS
        or entity not in SETTINGS.snapshot()["lights"]
        or action not in {"turn_on", "turn_off"}
    ):
        abort(400)
    if ha_error or time.time() - ha_updated > 25:
        abort(503)
    try:
        r = HA.post(
            C["ha_url"] + "/api/services/" + entity.split(".")[0] + "/" + action,
            json={"entity_id": entity},
            timeout=10,
        )
        r.raise_for_status()
        return jsonify(ok=True)
    except requests.RequestException:
        abort(502)


@app.post("/api/light/control")
def light_control():
    global last_touch
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400)
    entity = body.get("entity_id")
    if (
        not isinstance(entity, str)
        or entity not in LIGHTS
        or entity not in SETTINGS.snapshot()["lights"]
        or not entity.startswith("light.")
    ):
        abort(400)
    if FIRE.status(states, False)["active"]:
        abort(409)
    if (
        ha_error
        or time.time() - ha_updated > 25
        or states.get(entity, {}).get("state") not in {"on", "off"}
    ):
        abort(503)
    try:
        patch = validate_light_control(body, states[entity])
    except ValueError as error:
        return jsonify(error=str(error)), 400
    try:
        r = HA.post(
            C["ha_url"] + "/api/services/light/turn_on",
            json={"entity_id": entity, **patch},
            timeout=12,
        )
        r.raise_for_status()
        last_touch = time.time()
        return jsonify(ok=True)
    except requests.RequestException:
        return jsonify(error="Lampan kunde inte ändras. Försök igen."), 502


@app.post("/api/timer/sound-test")
def timer_sound_test():
    if FIRE.status(states, False)["active"]:
        abort(409)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400)
    try:
        TIMER_SOUND.preview(body.get("volume"), body.get("outputs"), body.get("sound"))
        return jsonify(ok=True)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except (OSError, requests.RequestException):
        return jsonify(
            error="Ljudet kunde inte spelas. Kontrollera vald ljudenhet och försök igen."
        ), 503


@app.post("/api/timer")
def timer_control():
    global last_touch
    if FIRE.status(states, False)["active"]:
        abort(409)
    try:
        result = TIMER.command(request.get_json(silent=True))
        last_touch = time.time()
        return jsonify(timer=result)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except OSError:
        return jsonify(error="Timern kunde inte sparas. Försök igen."), 500


@app.get("/api/music/browse")
def music_browse():
    try:
        return jsonify(
            MUSIC.browse(
                request.args.get("id"), request.args.get("q"), request.args.get("category")
            )
        )
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except (requests.RequestException, KeyError):
        return jsonify(error="Music Assistant kunde inte nås. Försök igen."), 502


@app.get("/api/music/queue")
def music_queue():
    try:
        with lock:
            queue_states = dict(states)
        return jsonify(MUSIC.queue(queue_states))
    except (ValueError, KeyError, requests.RequestException):
        return jsonify(error="Musikkön kunde inte hämtas. Försök igen."), 502


@app.post("/api/music/output")
def music_output():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400)
    if FIRE.status(states, False)["active"]:
        abort(409)
    try:
        with lock:
            player = MUSIC.select_player(
                body.get("player"), states, not ha_error and time.time() - ha_updated < 25
            )
        return jsonify(ok=True, player=player)
    except (ValueError, TypeError) as error:
        return jsonify(error=str(error)), 400


@app.post("/api/music/control")
def music_control():
    global last_touch
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400)
    if FIRE.status(states, False)["active"]:
        abort(409)
    if ha_error or time.time() - ha_updated > 25:
        abort(503)
    try:
        with lock:
            if not any(
                row["id"] == MUSIC.player and row["online"] for row in MUSIC.outputs(states)
            ):
                raise ValueError("Välj en tillgänglig högtalare i Music Assistant.")
            command_states = dict(states)
        MUSIC.command(body, command_states)
        last_touch = time.time()
        return jsonify(ok=True)
    except (ValueError, TypeError) as error:
        return jsonify(error=str(error)), 400
    except requests.RequestException:
        return jsonify(error="Uppspelningen kunde inte ändras. Försök igen."), 502


@app.get("/api/music/art/<entity>")
def music_art(entity):
    try:
        return MUSIC.artwork(entity, states)
    except requests.RequestException:
        abort(502)


@app.route("/planner/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
@app.route("/planner/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def planner(path):
    return PLANNER.response(path)


@app.post("/api/fire/mute")
def mute_fire():
    body = request.get_json(silent=True) or {}
    entity = body.get("entity_id")
    if entity not in DETECTORS or body.get("confirmed") is not True:
        abort(400)
    with lock:
        status = FIRE.status(states, not ha_error and time.time() - ha_updated < 25)
        alarm = next((a for a in status["alarms"] if a["entity_id"] == entity), None)
        if not alarm:
            return jsonify(error="Larmsignalen är inte längre aktiv."), 409
        if not alarm["mute_available"]:
            return jsonify(error=alarm["mute_reason"]), 409
        button = DETECTORS[entity]["mute"]
    try:
        r = HA.post(
            C["ha_url"] + "/api/services/button/press", json={"entity_id": button}, timeout=12
        )
        r.raise_for_status()
        return jsonify(
            ok=True,
            message="Tystningskommando skickat. Kontrollera detektorn. Larmvyn visas tills röksignalen upphört.",
        )
    except requests.RequestException:
        return jsonify(
            error="Det gick inte att skicka tystningskommandot. Kontrollera detektorn på plats."
        ), 502


@app.get("/api/camera/<entity>/hls/<path:file>")
def camera_hls(entity, file):
    return CAMERA_PROXY.hls(entity, file, request.args)


@app.get("/api/camera/<entity>/image")
def camera_image(entity):
    return CAMERA_PROXY.image(entity)


@app.get("/api/camera/<entity>/stream")
def camera_stream(entity):
    return CAMERA_PROXY.stream(entity)


@app.get("/photo/<filename>")
def photo(filename):
    with lock:
        if filename not in {p["file"] for p in photos}:
            abort(404)
    return send_from_directory(CACHE, filename)


if __name__ == "__main__":
    for fn in (
        ha_loop,
        photo_loop,
        display_loop,
        KEYBOARD.poll,
        FORECAST.loop,
        LIGHT_AREAS.loop,
        TIMER_SOUND.loop,
        CONTROL_AGENT.loop,
    ):
        threading.Thread(target=fn, daemon=True).start()
    make_server("127.0.0.1", 8090, app, threaded=True).serve_forever()
