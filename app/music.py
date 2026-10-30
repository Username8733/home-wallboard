"""Narrow Music Assistant controls; HA credentials and artwork URLs stay on the device."""

import hashlib
import json
import os
import pathlib
import re
import threading
import time

import requests
from flask import Response, abort
from site_config import load_config

PLAYER = load_config().get("music_player", "media_player.music")
SONOS = load_config().get("announcement_player", "media_player.speaker")
CATEGORIES = {
    "artists": "Artister",
    "albums": "Album",
    "tracks": "Låtar",
    "playlists": "Spellistor",
    "radio": "Radio",
    "podcasts": "Podcasts",
    "audiobooks": "Ljudböcker",
}


class Music:
    def __init__(self, config, selection_path=None):
        self.config = config
        self.ma_base = config.get("ma_url", "").rstrip("/")
        self.ma_token = config.get("ma_token")
        self.base = config["ha_url"].rstrip("/")
        self.headers = {"Authorization": "Bearer " + config["ha_token"]}
        self.items = {}
        self.lock = threading.RLock()
        self.art_cache = {}
        self.selection_path = pathlib.Path(selection_path) if selection_path else None
        self._player = PLAYER
        if self.selection_path:
            try:
                saved = json.loads(self.selection_path.read_text())["player"]
                if isinstance(saved, str) and re.fullmatch(r"media_player\.[a-z0-9_]+", saved):
                    self._player = saved
            except (OSError, ValueError, KeyError, TypeError):
                pass

    @property
    def player(self):
        with self.lock:
            return self._player

    @staticmethod
    def is_music_player(entity, state):
        return entity.startswith("media_player.") and (
            entity == PLAYER
            or state.get("attributes", {}).get("mass_player_type") in {"player", "group"}
        )

    def outputs(self, states, online=True):
        rows = []
        for entity, state in states.items():
            if not self.is_music_player(entity, state):
                continue
            attrs = state.get("attributes", {})
            rows.append(
                {
                    "id": entity,
                    "name": attrs.get("friendly_name", entity),
                    "group": attrs.get("mass_player_type") == "group",
                    "online": online and state.get("state") not in {None, "unknown", "unavailable"},
                }
            )
        known = {row["id"] for row in rows}
        for entity in {PLAYER, self.player} - known:
            rows.append(
                {
                    "id": entity,
                    "name": self.config.get("music_player_name", "Relax")
                    if entity == PLAYER
                    else entity,
                    "group": False,
                    "online": False,
                }
            )
        return sorted(rows, key=lambda row: (row["id"] != PLAYER, row["name"].casefold()))

    def select_player(self, entity, states, online=True):
        available = {row["id"] for row in self.outputs(states, online) if row["online"]}
        if not isinstance(entity, str) or entity not in available:
            raise ValueError("Välj en tillgänglig högtalare i Music Assistant.")
        with self.lock:
            if self.selection_path:
                self.selection_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.selection_path.with_suffix(".tmp")
                temporary.write_text(json.dumps({"player": entity}))
                temporary.chmod(0o600)
                os.replace(temporary, self.selection_path)
            self._player = entity
            self.queue_cache = (0, {})
            self.queue_actions = {}
        return entity

    def service(self, service, data, response=False):
        r = requests.post(
            self.base + "/api/services/" + service + ("?return_response" if response else ""),
            headers=self.headers,
            json=data,
            timeout=(5, 45),
        )
        r.raise_for_status()
        return r.json()

    def item(self, item):
        uri = item.get("media_content_id", "")
        kind = item.get("media_class", "")
        if not isinstance(uri, str) or len(uri) > 2048 or uri.startswith("media-source:"):
            return None
        if uri not in CATEGORIES and not (
            "://" in uri
            and kind
            in {
                "artist",
                "album",
                "track",
                "playlist",
                "music",
                "podcast",
                "audiobook",
                "directory",
                "episode",
            }
        ):
            return None
        key = hashlib.sha256(
            (uri + "|" + item.get("media_content_type", "music")).encode()
        ).hexdigest()[:24]
        with self.lock:
            if len(self.items) > 15000:
                self.items.clear()
            self.items[key] = {
                "uri": uri,
                "type": item.get("media_content_type", "music"),
                "play": bool(item.get("can_play")),
                "expand": bool(item.get("can_expand")),
            }
        return {
            "id": key,
            "title": item.get("title", "Musik"),
            "kind": kind,
            "play": bool(item.get("can_play")),
            "expand": bool(item.get("can_expand")),
        }

    def browse(self, key=None, query=None, category=None):
        player = self.player
        data = {"entity_id": player}
        if query:
            if not isinstance(query, str) or not 2 <= len(query.strip()) <= 160:
                raise ValueError("Skriv 2–160 tecken att söka efter.")
            data["search_query"] = query.strip()
            raw = self.service("media_player/search_media", data, True)["service_response"][player]
            children = raw.get("result", [])
            title = "Sökresultat"
        else:
            if category:
                if category not in CATEGORIES:
                    raise ValueError("Okänd kategori.")
                uri = category
                typ = "music_assistant"
            elif key:
                with self.lock:
                    item = self.items.get(key)
                if not item or not item["expand"]:
                    raise ValueError("Öppna biblioteket på nytt. Valet har gått ut.")
                uri = item["uri"]
                typ = item["type"]
            else:
                uri = ""
                typ = "music_assistant"
            data.update(media_content_id=uri, media_content_type=typ)
            raw = self.service("media_player/browse_media", data, True)["service_response"][player]
            children = raw.get("children", [])
            title = CATEGORIES.get(uri, raw.get("title", "Bibliotek"))
        return {
            "title": title,
            "context": self.item(raw) if not query else None,
            "items": [x for c in children if (x := self.item(c)) is not None],
        }

    def queue_info(self, player, states=None):
        if states is None:
            return self.service("music_assistant/get_queue", {"entity_id": player}, True)[
                "service_response"
            ][player]
        queue_id = states.get(player, {}).get("attributes", {}).get("active_queue")
        if not queue_id:
            return None
        if not self.ma_token:
            raise ValueError("Musikkön är inte ansluten till Music Assistant.")
        response = requests.post(
            self.ma_base + "/api",
            headers={"Authorization": "Bearer " + self.ma_token},
            json={"command": "player_queues/get", "args": {"queue_id": queue_id}},
            timeout=(5, 20),
        )
        response.raise_for_status()
        queue = response.json()
        if not isinstance(queue, dict) or queue.get("queue_id") != queue_id:
            raise ValueError("Musikkön kunde inte läsas.")
        return queue

    def command(self, body, states=None):
        player = self.player
        if body.get("player", player) != player:
            raise ValueError("Högtalaren har ändrats. Försök igen.")
        action = body.get("action")
        data = {"entity_id": player}
        allowed = {
            "play": "media_play",
            "pause": "media_pause",
            "next": "media_next_track",
            "previous": "media_previous_track",
            "volume": "volume_set",
            "shuffle": "shuffle_set",
            "repeat": "repeat_set",
        }
        if action == "queue_item":
            key = body.get("id")
            with self.lock:
                entry = getattr(self, "queue_actions", {}).get(key)
            if not entry or entry.get("player", player) != player:
                raise ValueError("Kön har ändrats. Uppdatera kön och välj låten igen.")
            current = self.queue_info(player, states)
            if not current or current["queue_id"] != entry["queue"]:
                raise ValueError("Kön har ändrats. Uppdatera kön.")
            r = requests.post(
                self.ma_base + "/api",
                headers={"Authorization": "Bearer " + self.ma_token},
                json={
                    "command": "player_queues/play_index",
                    "args": {"queue_id": entry["queue"], "index": entry["item"]},
                },
                timeout=(5, 20),
            )
            r.raise_for_status()
            with self.lock:
                self.queue_cache = (0, {})
            return
        if action == "item":
            with self.lock:
                item = self.items.get(body.get("id"))
            if not item or not item["play"]:
                raise ValueError("Välj musiken i biblioteket igen.")
            enqueue = body.get("enqueue", "play")
            if enqueue not in {"play", "add"}:
                raise ValueError("Ogiltigt köval.")
            data.update(
                media_content_id=item["uri"], media_content_type=item["type"], enqueue=enqueue
            )
            service = "play_media"
        elif action in allowed:
            service = allowed[action]
            if action == "volume":
                value = body.get("value")
                if type(value) not in (int, float) or not 0 <= value <= 1:
                    raise ValueError("Ogiltig volym.")
                data["volume_level"] = value
            elif action == "shuffle":
                if type(body.get("value")) is not bool:
                    raise ValueError("Ogiltigt blandningsval.")
                data["shuffle"] = body["value"]
            elif action == "repeat":
                if body.get("value") not in {"off", "all", "one"}:
                    raise ValueError("Ogiltig repetition.")
                data["repeat"] = body["value"]
        else:
            raise ValueError("Okänt musikkommando.")
        self.service("media_player/" + service, data)

    def announce(self, volume, sound="chime"):
        if type(volume) is not int or not 0 <= volume <= 100:
            raise ValueError("Ogiltig ljudvolym.")
        from sound_catalog import SOUNDS

        if type(sound) is not str or sound not in SOUNDS:
            raise ValueError("Ogiltig ljudsignal.")
        filename = (
            "wallboard-timer-chime.wav" if sound == "chime" else "wallboard-timer-" + sound + ".wav"
        )
        if volume:
            self.service(
                "media_player/play_media",
                {
                    "entity_id": SONOS,
                    "media_content_id": self.base + "/local/" + filename,
                    "media_content_type": "music",
                    "announce": True,
                    "extra": {"volume": volume},
                },
            )

    def queue(self, states=None):
        player = self.player
        with self.lock:
            if (
                hasattr(self, "queue_cache")
                and time.time() - self.queue_cache[0] < 5
                and self.queue_cache[1].get("player") == player
            ):
                return self.queue_cache[1]
        q = self.queue_info(player, states)
        if q is None:
            result = {
                "player": player,
                "items": [],
                "total": 0,
                "current_index": None,
                "active": False,
                "limited": False,
            }
            with self.lock:
                self.queue_cache = (time.time(), result)
                self.queue_actions = {}
            return result
        if not self.ma_token:
            raise ValueError("Musikkön är inte ansluten till Music Assistant.")
        r = requests.post(
            self.ma_base + "/api",
            headers={"Authorization": "Bearer " + self.ma_token},
            json={
                "command": "player_queues/items",
                "args": {"queue_id": q["queue_id"], "limit": 500, "offset": 0},
            },
            timeout=(5, 20),
        )
        r.raise_for_status()
        items = r.json()
        if not isinstance(items, list):
            raise ValueError("Musikkön kunde inte läsas.")
        rows = []
        actions = {}
        current_item = q.get("current_item") or {}
        for n, item in enumerate(items):
            media = item.get("media_item") or {}
            index = n
            key = hashlib.sha256(
                (q["queue_id"] + "|" + item["queue_item_id"]).encode()
            ).hexdigest()[:24]
            actions[key] = {"player": player, "queue": q["queue_id"], "item": item["queue_item_id"]}
            rows.append(
                {
                    "id": key,
                    "index": index,
                    "title": media.get("name") or item.get("name", "Musik"),
                    "artist": ", ".join(a.get("name", "") for a in media.get("artists", [])),
                    "duration": item.get("duration") or 0,
                    "current": item.get("queue_item_id") == current_item.get("queue_item_id")
                    if current_item.get("queue_item_id")
                    else index == q.get("current_index"),
                }
            )
        result = {
            "player": player,
            "items": rows,
            "total": q.get("items", len(rows)),
            "current_index": q.get("current_index"),
            "active": q.get("active", False),
            "limited": q.get("items", 0) > len(rows),
        }
        with self.lock:
            self.queue_cache = (time.time(), result)
            self.queue_actions = actions
        return result

    def snapshot(self, states, online):
        player = self.player
        primary = states.get(player, {})
        sonos = states.get(SONOS, {})
        # Preserve metadata for playback started directly on the default Sonos speaker.
        current = (
            sonos
            if player == PLAYER
            and primary.get("state") != "playing"
            and sonos.get("state") == "playing"
            else primary
        )

        def public(entity, s):
            a = s.get("attributes", {})
            stamp = hashlib.sha256(
                str(a.get("entity_picture_local") or a.get("entity_picture") or "").encode()
            ).hexdigest()[:16]
            return {
                "entity_id": entity,
                "name": a.get("friendly_name", entity),
                "state": s.get("state", "unavailable"),
                "title": a.get("media_title", ""),
                "artist": a.get("media_artist", ""),
                "album": a.get("media_album_name", ""),
                "volume": a.get("volume_level", 0),
                "shuffle": a.get("shuffle", False),
                "repeat": a.get("repeat", "off"),
                "art": "/api/music/art/" + entity + "?v=" + stamp
                if a.get("entity_picture_local") or a.get("entity_picture")
                else None,
            }

        control = public(SONOS if current is sonos else player, current)
        control["entity_id"] = player
        control["name"] = primary.get("attributes", {}).get("friendly_name") or (
            self.config.get("music_player_name", "Relax") if player == PLAYER else player
        )
        control["online"] = online and primary.get("state") not in {None, "unavailable", "unknown"}
        playing = []
        if online:
            for entity, s in states.items():
                a = s.get("attributes", {})
                if (
                    entity.startswith("media_player.")
                    and s.get("state") == "playing"
                    and (
                        entity in {PLAYER, SONOS}
                        or self.is_music_player(entity, s)
                        or a.get("app_id") == "music_assistant"
                    )
                    and a.get("media_title")
                    and a.get("media_artist")
                ):
                    playing.append(public(entity, s))
        playing.sort(
            key=lambda x: (
                x["entity_id"] != player,
                x["entity_id"] not in {PLAYER, SONOS},
                x["entity_id"] != PLAYER,
                x["entity_id"],
            )
        )
        return {
            "player": control,
            "outputs": self.outputs(states, online),
            "playing": playing[0] if playing else None,
        }

    def artwork(self, entity, states):
        if entity not in states:
            abort(404)
        a = states[entity].get("attributes", {})
        if (
            entity not in {PLAYER, SONOS}
            and not self.is_music_player(entity, states[entity])
            and a.get("app_id") != "music_assistant"
        ):
            abort(404)
        # Fixed HA endpoint: never follow browser supplied URLs or send the token elsewhere.
        key = (entity, a.get("entity_picture_local") or a.get("entity_picture"))
        if not key[1]:
            abort(404)
        with self.lock:
            cached = self.art_cache.get(key)
        if not cached or time.time() - cached[0] > 300:
            r = requests.get(
                self.base + "/api/media_player_proxy/" + entity,
                headers=self.headers,
                timeout=(5, 15),
                allow_redirects=False,
            )
            if r.status_code != 200 or not r.headers.get("Content-Type", "").startswith("image/"):
                abort(502)
            if len(r.content) > 10 * 1024 * 1024:
                abort(502)
            cached = (time.time(), r.content, r.headers["Content-Type"])
            with self.lock:
                if len(self.art_cache) > 16:
                    self.art_cache.clear()
                self.art_cache[key] = cached
        return Response(cached[1], content_type=cached[2])
