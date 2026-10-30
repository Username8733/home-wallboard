from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .const import BINARY
from .entity import WallboardEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([WallboardBinary(entry.runtime_data, key) for key in BINARY])


class WallboardBinary(WallboardEntity, BinarySensorEntity):
    @property
    def available(self):
        return True if self.key == "online" else self.coordinator.online

    @property
    def device_class(self):
        return (
            BinarySensorDeviceClass.CONNECTIVITY
            if self.key != "fire_active"
            else BinarySensorDeviceClass.SMOKE
        )

    @property
    def is_on(self):
        return self.coordinator.online if self.key == "online" else bool(self.status.get(self.key))
