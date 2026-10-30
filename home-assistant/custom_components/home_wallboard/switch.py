from homeassistant.components.switch import SwitchEntity

from .const import SWITCHES
from .entity import WallboardEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([WallboardSwitch(entry.runtime_data, key) for key in [*SWITCHES, "screen"]])


class WallboardSwitch(WallboardEntity, SwitchEntity):
    @property
    def is_on(self):
        return (
            self.status.get("mode") not in {"night", "screen_off"}
            if self.key == "screen"
            else self.prefs.get(self.key, False)
        )

    async def async_turn_on(self, **kwargs):
        if self.key == "screen":
            await self.coordinator.request("wake")
        else:
            await self.coordinator.preferences({self.key: True})

    async def async_turn_off(self, **kwargs):
        if self.key == "screen":
            await self.coordinator.request("sleep")
        else:
            await self.coordinator.preferences({self.key: False})
