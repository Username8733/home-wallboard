"""Pairing and protected, non-persistent account configuration dialogs."""

import json
import re

try:
    import probatio as vol
except ImportError:
    import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import DOMAIN


def text(password=False, multiline=False):
    return selector.TextSelector(
        selector.TextSelectorConfig(
            type=selector.TextSelectorType.PASSWORD if password else selector.TextSelectorType.TEXT,
            multiline=multiline,
        )
    )


def choices(rows, multiple=False):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=rows, multiple=multiple, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


class WallboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        users = await self.hass.auth.async_get_users()
        options = [
            {"value": user.id, "label": user.name or user.id}
            for user in users
            if user.is_active and not user.system_generated
        ]
        if user_input is not None:
            if not re.fullmatch(r"[a-z0-9_]{1,60}", user_input["device_id"]):
                errors["device_id"] = "invalid_device"
            elif len(user_input["pairing_key"]) < 32:
                errors["pairing_key"] = "short_key"
            elif user_input["agent_user_id"] not in {u["value"] for u in options}:
                errors["agent_user_id"] = "invalid_user"
            else:
                await self.async_set_unique_id(user_input["device_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input["name"], data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="Wallboard"): text(),
                    vol.Required("device_id", default="surface_go"): text(),
                    vol.Required("agent_user_id"): choices(options),
                    vol.Required("pairing_key"): text(password=True),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return WallboardOptionsFlow()


class WallboardOptionsFlow(config_entries.OptionsFlow):
    def __init__(self):
        self.cities = []
        self.provider = None
        self.calendars = []
        self.picker_url = ""

    @property
    def hub(self):
        return self.config_entry.runtime_data

    async def async_step_init(self, user_input=None):
        if not self.hub.online:
            return self.async_abort(reason="not_connected")
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "lights",
                "weather",
                "photos",
                "icloud_photos",
                "icloud_2fa",
                "icloud_calendar",
                "icloud_calendar_selection",
                "google_configure",
                "google_photos",
                "local_album",
            ],
        )

    async def async_step_lights(self, user_input=None):
        errors = {}
        catalog = self.hub.data["catalog"]
        prefs = self.hub.data["settings"]
        rooms = catalog.get("light_rooms", {})
        lights = catalog.get("lights", {})
        options = [
            {"value": key, "label": name + " · " + rooms.get(key, "—")}
            for key, name in sorted(
                lights.items(), key=lambda item: (rooms.get(item[0], ""), item[1])
            )
        ]
        if user_input is not None:
            if len(user_input["lights"]) > 9:
                errors["base"] = "too_many_lights"
            else:
                try:
                    await self.hub.preferences({"lights": user_input["lights"]})
                    return self.async_create_entry(title="", data={})
                except HomeAssistantError:
                    errors["base"] = "command_failed"
        return self.async_show_form(
            step_id="lights",
            data_schema=vol.Schema(
                {vol.Required("lights", default=prefs.get("lights", [])): choices(options, True)}
            ),
            errors=errors,
        )

    async def async_step_weather(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                result = await self.hub.request("weather_search", {"q": user_input["city"]})
                self.cities = result["cities"]
                if self.cities:
                    return await self.async_step_weather_city()
                errors["base"] = "no_results"
            except HomeAssistantError:
                errors["base"] = "command_failed"
        return self.async_show_form(
            step_id="weather", data_schema=vol.Schema({vol.Required("city"): text()}), errors=errors
        )

    async def async_step_weather_city(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                city = self.cities[int(user_input["city"])]
                await self.hub.preferences(
                    {
                        "weather_source": "open_meteo",
                        "weather_city": city["name"],
                        "weather_latitude": city["latitude"],
                        "weather_longitude": city["longitude"],
                    }
                )
                return self.async_create_entry(title="", data={})
            except (HomeAssistantError, ValueError, IndexError):
                errors["base"] = "command_failed"
        return self.async_show_form(
            step_id="weather_city",
            data_schema=vol.Schema(
                {
                    vol.Required("city"): choices(
                        [
                            {"value": str(i), "label": city["name"]}
                            for i, city in enumerate(self.cities)
                        ]
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_photos(self, user_input=None):
        if user_input is not None:
            self.provider = user_input["source"]
            return await self.async_step_photo_album()
        return self.async_show_form(
            step_id="photos",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "source", default=self.hub.data["settings"].get("photo_source", "immich")
                    ): choices(["immich", "local", "icloud", "google"])
                }
            ),
        )

    async def async_step_photo_album(self, user_input=None):
        errors = {}
        albums = self.hub.data["catalog"].get("photo_albums", {}).get(self.provider, [])
        if not albums:
            return self.async_abort(reason="no_albums")
        if user_input is not None:
            try:
                await self.hub.preferences(
                    {"photo_source": self.provider, "photo_album": user_input["album"]}
                )
                return self.async_create_entry(title="", data={})
            except HomeAssistantError:
                errors["base"] = "command_failed"
        return self.async_show_form(
            step_id="photo_album",
            data_schema=vol.Schema(
                {
                    vol.Required("album"): choices(
                        [{"value": a["id"], "label": a["name"]} for a in albums]
                    )
                }
            ),
            errors=errors,
        )

    async def account_form(self, step, action, user_input, schema):
        errors = {}
        if user_input is not None:
            try:
                await self.hub.request(action, user_input)
                return self.async_create_entry(title="", data={})
            except HomeAssistantError:
                errors["base"] = "command_failed"
        return self.async_show_form(step_id=step, data_schema=vol.Schema(schema), errors=errors)

    async def async_step_icloud_photos(self, user_input=None):
        return await self.account_form(
            "icloud_photos",
            "icloud_photo_login",
            user_input,
            {vol.Required("username"): text(), vol.Required("password"): text(password=True)},
        )

    async def async_step_icloud_2fa(self, user_input=None):
        return await self.account_form(
            "icloud_2fa",
            "icloud_photo_2fa",
            user_input,
            {vol.Required("code"): text(password=True)},
        )

    async def async_step_icloud_calendar(self, user_input=None):
        body = {**user_input, "action": "connect"} if user_input is not None else None
        return await self.account_form(
            "icloud_calendar",
            "icloud_calendar",
            body,
            {vol.Required("username"): text(), vol.Required("password"): text(password=True)},
        )

    async def async_step_icloud_calendar_selection(self, user_input=None):
        errors = {}
        if user_input is None:
            try:
                result = await self.hub.request("icloud_calendar", {"action": "refresh"})
                self.calendars = result["calendar"]["calendars"]
            except HomeAssistantError:
                return self.async_abort(reason="calendar_unavailable")
        else:
            try:
                await self.hub.request(
                    "icloud_calendar", {"action": "select", "calendar": user_input["calendar"]}
                )
                return self.async_create_entry(title="", data={})
            except HomeAssistantError:
                errors["base"] = "command_failed"
        if not self.calendars:
            return self.async_abort(reason="calendar_unavailable")
        return self.async_show_form(
            step_id="icloud_calendar_selection",
            data_schema=vol.Schema(
                {
                    vol.Required("calendar"): choices(
                        [{"value": c["id"], "label": c["name"]} for c in self.calendars]
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_google_configure(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self.hub.request("google_configure", json.loads(user_input["client_secret"]))
                return self.async_create_entry(title="", data={})
            except (HomeAssistantError, ValueError, TypeError):
                errors["base"] = "command_failed"
        return self.async_show_form(
            step_id="google_configure",
            data_schema=vol.Schema({vol.Required("client_secret"): text(multiline=True)}),
            errors=errors,
        )

    async def async_step_google_photos(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                result = await self.hub.request("google_pick", {"name": user_input["name"]})
                self.picker_url = result["url"]
                return await self.async_step_google_import()
            except HomeAssistantError:
                errors["base"] = "command_failed"
        return self.async_show_form(
            step_id="google_photos",
            data_schema=vol.Schema({vol.Required("name"): text()}),
            errors=errors,
        )

    async def async_step_google_import(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self.hub.request("google_import")
                return self.async_create_entry(title="", data={})
            except HomeAssistantError:
                errors["base"] = "command_failed"
        return self.async_show_form(
            step_id="google_import",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"url": self.picker_url},
        )

    async def async_step_local_album(self, user_input=None):
        return await self.account_form(
            "local_album", "local_album", user_input, {vol.Required("name"): text()}
        )
