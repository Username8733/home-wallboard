from homeassistant.components.number import NumberEntity, NumberMode

from .const import NUMBERS
from .entity import WallboardEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([WallboardNumber(entry.runtime_data, key) for key in NUMBERS])


class WallboardNumber(WallboardEntity, NumberEntity):
    def __init__(self, hub, key):
        super().__init__(hub, key)
        minimum, maximum, unit, *_ = NUMBERS[key]
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = unit
        self._attr_mode = NumberMode.SLIDER if unit == "%" else NumberMode.BOX

    @property
    def native_value(self):
        return self.prefs.get(self.key)

    async def async_set_native_value(self, value):
        await self.coordinator.preferences({self.key: int(value)})
