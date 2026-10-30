"""Temperature catalog and display values, kept separate from HA raw states."""

import math


def catalog(states, entity_areas=None):
    entity_areas = entity_areas or {}
    result = {}
    for entity, data in sorted(states.items()):
        attrs = data.get("attributes", {})
        if not entity.startswith("sensor.") or not (
            attrs.get("device_class") == "temperature"
            or attrs.get("unit_of_measurement") in {"°C", "°F", "K"}
        ):
            continue
        name = attrs.get("friendly_name", entity)
        room = entity_areas.get(entity)
        result[entity] = name + " · " + room if room else name + " · Rum saknas i HA · " + entity
    return dict(sorted(result.items(), key=lambda item: item[1].casefold()))


def reading(states, entity):
    data = states.get(entity, {})
    try:
        value = float(data["state"])
        if not math.isfinite(value):
            return None
    except (ValueError, TypeError, KeyError):
        return None
    unit = data.get("attributes", {}).get("unit_of_measurement", "°C")
    return (value - 32) * 5 / 9 if unit == "°F" else value - 273.15 if unit == "K" else value


def snapshot(states, settings, forecast, online):
    if settings["outdoor_temperature_source"] == "weather":
        outside = None if forecast.get("stale", True) else forecast.get("current_temperature")
    else:
        outside = reading(states, settings["outdoor_temperature_entity"]) if online else None
    inside = reading(states, settings["indoor_temperature_entity"]) if online else None
    return {
        "outdoor": outside,
        "indoor": inside,
        "unit": "°C",
        "outdoor_source": settings["outdoor_temperature_source"],
        "weather_location": forecast.get("location", ""),
    }
