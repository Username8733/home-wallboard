from homeassistant.components.select import SelectEntity

from .const import DYNAMIC, ENUMS
from .entity import WallboardEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([WallboardSelect(entry.runtime_data, key) for key in [*ENUMS, *DYNAMIC]])


class WallboardSelect(WallboardEntity, SelectEntity):
    def choices(self):
        if self.key in ENUMS:
            return {x: x for x in ENUMS[self.key][0]}
        catalog = self.coordinator.data.get("catalog", {})
        if self.key == "photo_album":
            rows = catalog.get("photo_albums", {}).get(self.prefs.get("photo_source"), [])
            raw = {r["id"]: r["name"] for r in rows}
        else:
            raw = catalog.get(DYNAMIC[self.key][0], {})
        choices = {}
        counts = {}
        for value, label in sorted(raw.items(), key=lambda item: (item[1].casefold(), item[0])):
            counts[label] = counts.get(label, 0) + 1
            text = label if counts[label] == 1 else f"{label} ({counts[label]})"
            choices[text] = value
        return choices

    @property
    def options(self):
        return list(self.choices())

    @property
    def current_option(self):
        if self.key == "active_dashboard":
            value = self.status.get("dashboard")
        elif self.key == "timer_outputs":
            outputs = self.prefs.get("timer_outputs", [])
            value = "both" if len(outputs) == 2 else outputs[0] if outputs else None
        else:
            value = self.prefs.get(self.key)
        return next((label for label, raw in self.choices().items() if raw == value), None)

    async def async_select_option(self, option):
        value = self.choices()[option]
        if self.key == "active_dashboard":
            await self.coordinator.request("dashboard", {"page": value})
        elif self.key == "timer_outputs":
            await self.coordinator.preferences(
                {"timer_outputs": ["tablet", "sonos"] if value == "both" else [value]}
            )
        else:
            await self.coordinator.preferences({self.key: value})
