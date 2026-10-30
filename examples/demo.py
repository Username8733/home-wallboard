"""Read-only, synthetic demo. Never imports the production server or connects to services."""

import argparse
import copy
import json
import os
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
# Import only generic preference definitions, with an explicit, nonexistent config path.
# Do not read /etc/wallboard/config.json, even when this demo runs on a real wallboard.
os.environ["WALLBOARD_CONFIG"] = str(ROOT / "examples" / ".no-private-config.json")
sys.path.insert(0, str(ROOT / "app"))
from settings_store import DEFAULTS  # noqa: E402
from sound_catalog import SOUNDS  # noqa: E402

app = Flask(__name__, static_folder=str(ROOT / "app/static"))
LIGHTS = {
    "light.living_ceiling": "Ceiling lights",
    "light.living_lamp": "Reading lamp",
    "light.living_shelf": "Shelf lighting",
    "light.kitchen_ceiling": "Ceiling lights",
    "light.kitchen_counter": "Counter lights",
    "light.dining": "Pendant lights",
    "light.hallway": "Hallway lights",
    "light.bedroom": "Bedside lamps",
    "light.garden": "Garden lights",
}
ROOMS = dict(
    zip(
        LIGHTS,
        ["Living room"] * 3 + ["Kitchen"] * 2 + ["Dining room", "Hallway", "Bedroom", "Garden"],
    )
)
PREFS = {
    **copy.deepcopy(DEFAULTS),
    "language": "en",
    "theme": "day",
    "lights": list(LIGHTS),
    "weather_city": "London (demo)",
    "photo_album": "demo",
    "show_help_text": False,
    "night_mode_enabled": False,
    "keyboard_auto": False,
}
PATHS = json.loads((ROOT / "app/static/vendor/mdi-paths.json").read_text())
STATES = {
    entity: {
        "entity_id": entity,
        "state": "on" if n in [0, 2, 3, 5] else "off",
        "attributes": {
            "friendly_name": name,
            "brightness": 180,
            "hs_color": [35, 60],
            "color_temp_kelvin": 3000,
        },
    }
    for n, (entity, name) in enumerate(LIGHTS.items())
}
for entity, value in {
    "alarm_control_panel.home": "disarmed",
    "binary_sensor.front_door": "off",
    "binary_sensor.back_door": "off",
    "binary_sensor.smoke": "off",
    "binary_sensor.alex": "on",
    "binary_sensor.sam": "on",
    "binary_sensor.jamie": "off",
}.items():
    STATES[entity] = {"entity_id": entity, "state": value, "attributes": {}}
MUSIC = {
    "entity_id": "media_player.demo",
    "name": "Living room speaker",
    "state": "playing",
    "title": "Morning Light",
    "artist": "Demo Ensemble",
    "album": "Quiet Moments",
    "online": True,
    "volume": 0.25,
    "shuffle": False,
    "repeat": "off",
    "art": "/demo/cover.svg",
}
CAMERAS = [
    {"entity_id": "camera." + key, "name": name, "state": "idle", "motion": "off"}
    for key, name in [("front", "Front door"), ("garden", "Garden"), ("garage", "Garage")]
]
PHOTO_SOURCES = {
    "albums": {
        p: [{"id": "demo", "name": "Demo landscapes"}]
        for p in ["immich", "local", "icloud", "google"]
    },
    "connections": {},
}
DEMO_STATE = dict(
    demo="synthetic-public-data-v1",
    home_entities={
        "alarm": "alarm_control_panel.home",
        "doors": {"binary_sensor.front_door": "Front door", "binary_sensor.back_door": "Back door"},
    },
    people_entities={name: "binary_sensor." + name.lower() for name in ["Alex", "Sam", "Jamie"]},
    people=["Alex", "Sam", "Jamie"],
    smoke_entities=["binary_sensor.smoke"],
    temperatures={"outdoor": 19, "indoor": 21.4},
    settings=PREFS,
    states=STATES,
    lights=LIGHTS,
    light_rooms=ROOMS,
    light_icons={
        entity: {
            "icon": "mdi:lightbulb",
            "path": PATHS.get("mdi:lightbulb", PATHS.get("lightbulb", "")),
        }
        for entity in LIGHTS
    },
    light_controls={
        entity: {
            "brightness": True,
            "color": True,
            "temperature": True,
            "min_kelvin": 2000,
            "max_kelvin": 6500,
        }
        for entity in LIGHTS
    },
    timer={"status": "idle", "remaining": 0, "duration": 0, "generation": 1},
    keyboard={"available": False, "visible": False, "height": 340},
    fire={"active": False, "online": True, "alarms": []},
    security={
        "online": True,
        "alarm": "disarmed",
        "lock": "locked",
        "doors": [
            {"entity_id": "binary_sensor.front_door", "name": "Front door", "state": "off"},
            {"entity_id": "binary_sensor.back_door", "name": "Back door", "state": "off"},
        ],
        "cameras": CAMERAS,
    },
    forecast={
        "location": "London (demo)",
        "stale": False,
        "today": {
            "condition": "partlycloudy",
            "temperature": 22,
            "templow": 13,
            "precipitation": 0,
            "wind_speed": 8,
        },
    },
    photo_library={"source": "immich", "source_name": "Immich", "online": True},
    music={"player": MUSIC, "playing": MUSIC},
    photos=[{"id": "demo-" + str(i), "file": "landscape.svg"} for i in range(3)],
    photos_updated=1,
    ha_online=True,
    immich_online=True,
    camera_ok=True,
    mode="active",
    brightness=78,
)


@app.get("/")
def index():
    return send_from_directory(ROOT / "app/static", "index.html")


@app.get("/api/state")
def state():
    return jsonify(DEMO_STATE)


@app.get("/api/settings")
def settings():
    return jsonify(
        settings=PREFS,
        defaults=PREFS,
        lights=LIGHTS,
        light_rooms=ROOMS,
        max_lights=9,
        sounds=SOUNDS,
        photo_sources=PHOTO_SOURCES,
        temperature_sensors={
            "sensor.indoor_temperature": "Temperature · Living room",
            "sensor.outdoor_temperature": "Temperature · Garden",
        },
        weather_entities={"weather.forecast_home": "Demo weather"},
    )


@app.post("/api/wake")
@app.post("/api/control/view")
def noop():
    return jsonify(ok=True)


@app.post("/api/keyboard")
def keyboard():
    return jsonify(keyboard=DEMO_STATE["keyboard"])


@app.get("/api/music/browse")
def music_browse():
    return jsonify(
        title="Demo playlists",
        context=None,
        items=[
            {"id": str(n), "title": name, "kind": "playlist", "expand": False, "play": True}
            for n, name in enumerate(
                [
                    "Morning mix",
                    "Quiet evenings",
                    "Weekend favourites",
                    "Focus and flow",
                    "Dinner with friends",
                    "Late night jazz",
                ]
            )
        ],
    )


@app.get("/api/music/queue")
def queue():
    return jsonify(
        total=6,
        active=True,
        limited=False,
        items=[
            {
                "id": str(n),
                "index": n,
                "title": name,
                "artist": "Demo Ensemble",
                "duration": 200 + n * 15,
                "current": n == 1,
            }
            for n, name in enumerate(
                [
                    "A New Day",
                    "Morning Light",
                    "Open Windows",
                    "Slow Sunday",
                    "Golden Hour",
                    "Home Again",
                ]
            )
        ],
    )


def drawing(kind):
    if kind == "cover":
        shapes = '<rect width="960" height="600" fill="#152940"/><circle cx="480" cy="300" r="190" fill="#e6aa66"/><circle cx="480" cy="300" r="130" fill="#d47b72"/><path d="M0 450Q300 180 960 430V600H0" fill="#426b86"/><text x="480" y="140" text-anchor="middle" fill="white" font-family="sans-serif" font-size="38">QUIET MOMENTS</text><text x="480" y="540" text-anchor="middle" fill="white" font-family="sans-serif" font-size="24">DEMO ENSEMBLE</text>'
    else:
        shapes = '<rect width="960" height="600" fill="#b2d9f2"/><circle cx="730" cy="130" r="60" fill="#fff1bb"/><path d="M0 380L260 100L580 450L780 180L960 390V600H0" fill="#8aa7b2"/><path d="M0 460L300 290L660 490L960 350V600H0" fill="#477b75"/><path d="M0 540Q430 420 960 520V600H0" fill="#294f59"/>'
        if kind == "camera":
            shapes += '<text x="40" y="555" fill="white" font-family="sans-serif" font-size="30">DEMO CAMERA · FICTIONAL SCENE</text>'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="600" viewBox="0 0 960 600">'
        + shapes
        + "</svg>"
    )


@app.get("/demo/<name>.svg")
@app.get("/photo/<name>.svg")
def artwork(name):
    return Response(drawing("cover" if name == "cover" else "landscape"), mimetype="image/svg+xml")


@app.get("/api/camera/<entity>/image")
def camera(entity):
    return Response(drawing("camera"), mimetype="image/svg+xml")


@app.errorhandler(404)
@app.errorhandler(405)
def read_only(_error):
    return jsonify(error="Read-only demo. No devices or services are connected."), 403


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18990)
    app.run(host="127.0.0.1", port=parser.parse_args().port, debug=False)
