"""Daily forecast and current outdoor temperature for one selected location."""

import datetime
import threading
import time
from zoneinfo import ZoneInfo

import requests

ZONE = ZoneInfo("Europe/Stockholm")


def condition(code, is_day=True):
    if code == 0:
        return "sunny" if is_day else "clear-night"
    if code in (1, 2):
        return "partlycloudy"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if code in (71, 73, 75, 77, 85, 86):
        return "snowy"
    if code in (95, 96, 99):
        return "lightning-rainy"
    return "rainy"


def search_cities(query):
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 100:
        raise ValueError("Skriv minst två tecken i stadens namn.")
    response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": query.strip(), "count": 8, "language": "sv", "format": "json"},
        timeout=(5, 15),
    )
    response.raise_for_status()
    return [
        {
            "name": ", ".join(filter(None, [row["name"], row.get("admin1"), row.get("country")])),
            "latitude": row["latitude"],
            "longitude": row["longitude"],
        }
        for row in response.json().get("results", [])
    ]


class Forecast:
    def __init__(self, config, settings=None):
        self.config = config
        self.settings = settings
        self.lock = threading.Lock()
        self.value = None
        self.current = None
        self.updated = 0
        self.loaded_key = None
        self.changed = threading.Event()

    def preferences(self):
        return (
            self.settings.snapshot()
            if self.settings
            else {"weather_source": "ha", "weather_entity": "weather.forecast_home"}
        )

    def key(self):
        p = self.preferences()
        return tuple(
            p.get(k)
            for k in (
                "weather_source",
                "weather_entity",
                "weather_city",
                "weather_latitude",
                "weather_longitude",
            )
        )

    def snapshot(self):
        with self.lock:
            matching = self.loaded_key == self.key()
            today = datetime.datetime.now(ZONE).date().isoformat()
            p = self.preferences()
            return {
                "today": self.value
                if matching and self.value and self.value["date"] == today
                else None,
                "current_temperature": self.current if matching else None,
                "updated": self.updated,
                "stale": not matching or time.time() - self.updated > 3600,
                "location": p.get("weather_city", "")
                if p["weather_source"] == "open_meteo"
                else "Home Assistant",
                "source": p["weather_source"],
                "attribution": "Open-Meteo.com · CC BY 4.0"
                if p["weather_source"] == "open_meteo"
                else "Home Assistant",
            }

    def refresh(self):
        key = self.key()
        p = self.preferences()
        today = datetime.datetime.now(ZONE).date()
        if p["weather_source"] == "open_meteo":
            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": p["weather_latitude"],
                    "longitude": p["weather_longitude"],
                    "current": "temperature_2m,is_day,weather_code",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                    "timezone": str(ZONE),
                    "forecast_days": 2,
                },
                timeout=(5, 20),
            )
            r.raise_for_status()
            data = r.json()
            daily = data["daily"]
            i = daily["time"].index(today.isoformat())
            value = {
                "date": today.isoformat(),
                "condition": condition(daily["weather_code"][i]),
                "temperature": daily["temperature_2m_max"][i],
                "templow": daily["temperature_2m_min"][i],
                "precipitation": daily["precipitation_sum"][i],
                "wind_speed": daily["wind_speed_10m_max"][i],
            }
            current = data["current"]["temperature_2m"]
        else:
            entity = p["weather_entity"]
            headers = {"Authorization": "Bearer " + self.config["ha_token"]}
            r = requests.post(
                self.config["ha_url"] + "/api/services/weather/get_forecasts?return_response",
                headers=headers,
                json={"entity_id": entity, "type": "daily"},
                timeout=(5, 20),
            )
            r.raise_for_status()
            rows = r.json()["service_response"][entity]["forecast"]
            row = next(
                (
                    x
                    for x in rows
                    if datetime.datetime.fromisoformat(x["datetime"]).astimezone(ZONE).date()
                    == today
                ),
                None,
            )
            value = (
                {
                    "date": today.isoformat(),
                    **{
                        k: row.get(k)
                        for k in (
                            "condition",
                            "temperature",
                            "templow",
                            "precipitation",
                            "wind_speed",
                        )
                    },
                }
                if row
                else None
            )
            r = requests.get(
                self.config["ha_url"] + "/api/states/" + entity, headers=headers, timeout=(5, 15)
            )
            r.raise_for_status()
            attrs = r.json()["attributes"]
            current = attrs.get("temperature")
            if attrs.get("temperature_unit") == "°F":
                if isinstance(current, (int, float)):
                    current = (current - 32) * 5 / 9
                if value:
                    for field in ("temperature", "templow"):
                        if isinstance(value[field], (int, float)):
                            value[field] = (value[field] - 32) * 5 / 9
        with self.lock:
            if key == self.key():
                self.value, self.current, self.loaded_key, self.updated = (
                    value,
                    current,
                    key,
                    time.time(),
                )

    def loop(self):
        while True:
            self.changed.clear()
            try:
                self.refresh()
            except (requests.RequestException, ValueError, KeyError, TypeError):
                pass
            self.changed.wait(900)
