from homeassistant.components.button import ButtonEntity

from .const import BUTTONS
from .entity import WallboardEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([WallboardButton(entry.runtime_data, key) for key in BUTTONS])


class WallboardButton(WallboardEntity, ButtonEntity):
    async def async_press(self):
        await self.coordinator.request(self.key)
