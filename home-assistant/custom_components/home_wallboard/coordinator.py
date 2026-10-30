"""Push coordinator for an authenticated outbound tablet connection."""

import asyncio
import logging
import time
import uuid
from datetime import timedelta

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .protocol import seal

_LOGGER = logging.getLogger(__name__)


class WallboardCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, config_entry=entry, name=entry.title)
        self.entry = entry
        self.connection = None
        self.subscription = None
        self.last_seen = 0
        self.pending = {}
        self.seen = {}
        self.command_lock = asyncio.Lock()
        self.data = {"settings": {}, "catalog": {}, "status": {}}
        self.stop_timer = async_track_time_interval(hass, self.check_online, timedelta(seconds=5))
        self.was_online = False

    @property
    def online(self):
        return self.connection is not None and time.monotonic() - self.last_seen < 25

    @callback
    def check_online(self, _now):
        if self.was_online != self.online:
            self.was_online = self.online
            self.async_set_updated_data(dict(self.data))

    @callback
    def disconnect(self, connection):
        if self.connection is connection:
            self.connection = None
            self.last_seen = 0
            self.check_online(None)
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(HomeAssistantError("Wallboard disconnected"))

    @callback
    def report(self, snapshot, reply=None):
        if not isinstance(snapshot, dict) or not all(
            isinstance(snapshot.get(key), dict) for key in ["settings", "catalog", "status"]
        ):
            raise ValueError("Invalid snapshot")
        self.last_seen = time.monotonic()
        self.was_online = True
        self.async_set_updated_data(snapshot)
        if (
            isinstance(reply, dict)
            and (future := self.pending.get(reply.get("request_id"))) is not None
            and not future.done()
        ):
            if reply.get("ok"):
                future.set_result(reply.get("result", {}))
            else:
                future.set_exception(HomeAssistantError(str(reply.get("error", "Command failed"))))

    async def request(self, action, data=None):
        async with self.command_lock:
            if not self.online:
                raise HomeAssistantError("Wallboard is offline")
            request_id = uuid.uuid4().hex
            future = self.hass.loop.create_future()
            self.pending[request_id] = future
            try:
                self.connection.send_event(
                    self.subscription,
                    {
                        "kind": "command",
                        "request_id": request_id,
                        "envelope": seal(
                            self.entry.data["pairing_key"],
                            self.entry.data["device_id"],
                            request_id,
                            {"action": action, "data": data or {}},
                        ),
                    },
                )
                return await asyncio.wait_for(future, timeout=65)
            except TimeoutError as error:
                raise HomeAssistantError("Wallboard did not respond in time") from error
            finally:
                self.pending.pop(request_id, None)

    async def preferences(self, patch):
        patch = dict(patch)
        if patch.get("photo_source") and patch["photo_source"] != self.data["settings"].get(
            "photo_source"
        ):
            albums = self.data["catalog"].get("photo_albums", {}).get(patch["photo_source"], [])
            if not albums:
                raise HomeAssistantError("Connect this photo source and add an album first")
            patch.setdefault("photo_album", albums[0]["id"])
        return await self.request("settings", patch)
