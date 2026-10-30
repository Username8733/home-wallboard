"""Home Wallboard integration: authenticated push and standard HA controls."""

import json

try:
    import probatio as vol
except ImportError:
    import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import callback

from .const import DOMAIN, PLATFORMS
from .coordinator import WallboardCoordinator
from .protocol import verify_proof


async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})
    websocket_api.async_register_command(hass, subscribe_agent)
    websocket_api.async_register_command(hass, agent_report)
    return True


async def async_setup_entry(hass, entry):
    hub = WallboardCoordinator(hass, entry)
    entry.runtime_data = hub
    hass.data.setdefault(DOMAIN, {})[entry.data["device_id"]] = hub
    entry.async_on_unload(hub.stop_timer)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hub = entry.runtime_data
        hub.disconnect(hub.connection)
        hass.data[DOMAIN].pop(entry.data["device_id"], None)
    return unloaded


@websocket_api.websocket_command(
    {
        "type": "home_wallboard/agent",
        vol.Required("device_id"): str,
        vol.Required("timestamp"): int,
        vol.Required("nonce"): str,
        vol.Required("signature"): str,
    }
)
@callback
def subscribe_agent(hass, connection, msg):
    hub = hass.data.get(DOMAIN, {}).get(msg["device_id"])
    if (
        hub is None
        or connection.user is None
        or connection.user.id != hub.entry.data["agent_user_id"]
        or not verify_proof(hub.entry.data["pairing_key"], msg["device_id"], msg, hub.seen)
    ):
        connection.send_error(msg["id"], "unauthorized", "Invalid wallboard pairing")
        return
    hub.connection = connection
    hub.subscription = msg["id"]
    connection.subscriptions[msg["id"]] = lambda: hub.disconnect(connection)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        "type": "home_wallboard/report",
        vol.Required("device_id"): str,
        vol.Required("snapshot"): dict,
        vol.Optional("reply"): dict,
    }
)
@callback
def agent_report(hass, connection, msg):
    hub = hass.data.get(DOMAIN, {}).get(msg["device_id"])
    if (
        hub is None
        or hub.connection is not connection
        or connection.user.id != hub.entry.data["agent_user_id"]
    ):
        connection.send_error(msg["id"], "unauthorized", "Agent is not paired")
        return
    if len(json.dumps(msg)) > 200000:
        connection.send_error(msg["id"], "invalid_format", "Report too large")
        return
    try:
        hub.report(msg["snapshot"], msg.get("reply"))
    except (ValueError, TypeError):
        connection.send_error(msg["id"], "invalid_format", "Invalid report")
        return
    connection.send_result(msg["id"])
