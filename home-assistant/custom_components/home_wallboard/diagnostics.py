async def async_get_config_entry_diagnostics(hass, entry):
    hub = entry.runtime_data
    return {
        "integration_version": "0.3.0",
        "online": hub.online,
        "device_version": hub.data.get("version"),
        "catalog_sizes": {key: len(value) for key, value in hub.data.get("catalog", {}).items()},
    }
