from homeassistant.components.sensor import SensorEntity

from .const import SENSORS
from .entity import WallboardEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([WallboardSensor(entry.runtime_data, key) for key in SENSORS])


class WallboardSensor(WallboardEntity, SensorEntity):
    @property
    def native_value(self):
        if self.key == "selected_lights":
            return len(self.prefs.get("lights", []))
        if self.key == "location":
            return (
                self.prefs.get("weather_city")
                if self.prefs.get("weather_source") == "open_meteo"
                else "Home Assistant"
            )
        return self.status.get(self.key)

    @property
    def native_unit_of_measurement(self):
        return "%" if self.key == "brightness" else None
