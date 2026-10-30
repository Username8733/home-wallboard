"""Validated, atomic, device-local preferences. Credentials never live here."""

import copy
import json
import pathlib
import re
import threading

from site_config import load_config
from sound_catalog import SOUNDS

MAX_LIGHTS = 9
DEFAULTS = {
    **{
        "outdoor_temperature_source": "sensor",
        "outdoor_temperature_entity": "sensor.outdoor_temperature",
        "indoor_temperature_entity": "sensor.indoor_temperature",
        "weather_source": "ha",
        "weather_entity": "weather.forecast_home",
        "weather_city": "",
        "weather_latitude": None,
        "weather_longitude": None,
        "photo_source": "immich",
        "photo_album": "default",
        "night_mode_enabled": False,
        "night_start": "22:00",
        "night_end": "07:00",
        "theme": "auto",
        "language": "sv",
        "time_format": "24h",
        "show_help_text": False,
        "idle_seconds": 90,
        "screen_mode": "photos",
        "slide_seconds": 20,
        "timer_sound": "chime",
        "timer_outputs": ["tablet"],
        "timer_volume": 70,
        "active_brightness": 78,
        "idle_brightness": 18,
        "presence_enabled": True,
        "keyboard_auto": True,
        "show_weather": True,
        "show_home": True,
        "show_people": True,
        "show_lights": True,
        "show_temperatures": True,
        "show_photos": True,
        "start_dashboard": "home",
        "lights": ["light.living_room"],
    },
    **load_config().get("initial_settings", {}),
}


class SettingsStore:
    def __init__(self, path, initial=None):
        self.allowed_lights = None
        self.path = pathlib.Path(path)
        self.lock = threading.RLock()
        self.value = copy.deepcopy(DEFAULTS)
        if initial:
            self.value.update(initial)
        try:
            self.value = self.validate(json.loads(self.path.read_text()))
        except (OSError, ValueError, TypeError):
            pass

    def validate(self, patch):
        if not isinstance(patch, dict) or set(patch) - set(DEFAULTS):
            raise ValueError("Inställningarna innehåller okända fält.")
        value = copy.deepcopy(self.value)
        value.update(patch)
        for key, lo, hi in [
            ("idle_seconds", 15, 3600),
            ("slide_seconds", 5, 300),
            ("active_brightness", 20, 100),
            ("idle_brightness", 1, 60),
            ("timer_volume", 0, 100),
        ]:
            if type(value[key]) is not int or not lo <= value[key] <= hi:
                raise ValueError(f"{key}: ange ett heltal mellan {lo} och {hi}.")
        if value["idle_brightness"] > value["active_brightness"]:
            raise ValueError("Viloljuset får inte vara starkare än den aktiva ljusstyrkan.")
        for key in [k for k, v in DEFAULTS.items() if type(v) is bool]:
            if type(value[key]) is not bool:
                raise ValueError("Ogiltigt val för " + key)
        for field in ("night_start", "night_end"):
            if not isinstance(value[field], str) or not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", value[field]
            ):
                raise ValueError("Ange nattlägets tider som HH:MM.")
        if value["night_start"] == value["night_end"]:
            raise ValueError("Nattlägets start och slut måste vara olika tider.")
        if not isinstance(value["theme"], str) or value["theme"] not in {
            "auto",
            "morning",
            "day",
            "evening",
            "night",
            "dark",
        }:
            raise ValueError("Välj ett tema från listan.")
        if not isinstance(value["language"], str) or value["language"] not in {"sv", "en"}:
            raise ValueError("Välj svenska eller engelska.")
        if not isinstance(value["time_format"], str) or value["time_format"] not in {"24h", "12h"}:
            raise ValueError("Välj 12- eller 24-timmarsformat.")
        if value["outdoor_temperature_source"] not in {"sensor", "weather"} or value[
            "weather_source"
        ] not in {"ha", "open_meteo"}:
            raise ValueError("Välj en giltig temperatur- och väderkälla.")
        for k in ("outdoor_temperature_entity", "indoor_temperature_entity"):
            if not isinstance(value[k], str) or not re.fullmatch(r"sensor\.[a-z0-9_]+", value[k]):
                raise ValueError("Välj en temperaturgivare från listan.")
        if not isinstance(value["weather_entity"], str) or not re.fullmatch(
            r"weather\.[a-z0-9_]+", value["weather_entity"]
        ):
            raise ValueError("Välj en väderentitet.")
        if not isinstance(value["weather_city"], str) or len(value["weather_city"]) > 200:
            raise ValueError("Välj en stad från sökresultatet.")
        if value["weather_source"] == "open_meteo":
            for k, lo, hi in [("weather_latitude", -90, 90), ("weather_longitude", -180, 180)]:
                if type(value[k]) not in (int, float) or not lo <= value[k] <= hi:
                    raise ValueError("Sök och välj en stad för väderprognosen.")
            if not value["weather_city"]:
                raise ValueError("Välj en stad för väderprognosen.")
        if value["photo_source"] not in ["immich", "local", "icloud", "google"]:
            raise ValueError("Välj en giltig bildkälla.")
        if type(value["photo_album"]) is not str or not re.fullmatch(
            r"[a-zA-Z0-9_.:-]{1,200}", value["photo_album"]
        ):
            raise ValueError("Välj ett giltigt album.")
        if type(value["timer_sound"]) is not str or value["timer_sound"] not in SOUNDS:
            raise ValueError("Välj en giltig ljudsignal.")
        outputs = value["timer_outputs"]
        if (
            not isinstance(outputs, list)
            or not outputs
            or any(type(e) is not str or e not in {"tablet", "sonos"} for e in outputs)
            or len(outputs) != len(set(outputs))
        ):
            raise ValueError("Välj plattan, Högtalaren eller båda för timerljudet.")
        if value["screen_mode"] not in ["photos", "dim", "keep_on"]:
            raise ValueError("Välj ett giltigt viloläge.")
        if value["start_dashboard"] not in ["home", "planner", "security", "music"]:
            raise ValueError("Välj en giltig startvy.")
        lights = value["lights"]
        if (
            not isinstance(lights, list)
            or any(
                type(e) is not str
                or not re.fullmatch(r"(?:light|group)\.[a-z0-9_]+", e)
                or self.allowed_lights is not None
                and e not in self.allowed_lights
                for e in lights
            )
            or len(lights) != len(set(lights))
        ):
            raise ValueError("Välj lampor från listan.")
        if len(lights) > MAX_LIGHTS:
            raise ValueError(f"Välj högst {MAX_LIGHTS} lampor eller lampgrupper.")
        if value["show_lights"] and not lights:
            raise ValueError("Välj minst en lampa eller dölj belysningen.")
        return value

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.value)

    def save(self, patch):
        with self.lock:
            value = self.validate(patch)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            tmp.chmod(0o600)
            tmp.replace(self.path)
            self.value = value
            return self.snapshot()
