"""Common device identity and availability."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class WallboardEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, hub, key):
        super().__init__(hub)
        self.key = key
        self._attr_unique_id = hub.entry.data["device_id"] + "_" + key
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.entry.data["device_id"])},
            name=hub.entry.title,
            manufacturer="Home Wallboard",
            model="Linux touch dashboard",
            sw_version="0.3.0",
        )

    @property
    def available(self):
        return self.coordinator.online

    @property
    def prefs(self):
        return self.coordinator.data.get("settings", {})

    @property
    def status(self):
        return self.coordinator.data.get("status", {})
