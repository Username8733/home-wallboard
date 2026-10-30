import datetime

from homeassistant.components.time import TimeEntity

from .const import TIMES
from .entity import WallboardEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([WallboardTime(entry.runtime_data, key) for key in TIMES])


class WallboardTime(WallboardEntity, TimeEntity):
    @property
    def native_value(self):
        value = self.prefs.get(self.key)
        return datetime.time.fromisoformat(value) if value else None

    async def async_set_value(self, value):
        await self.coordinator.preferences({self.key: value.strftime("%H:%M")})
