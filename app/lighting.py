"""Discover controllable lamps and groups containing only lamps."""


def light_catalog(snapshot):
    def is_light(entity, seen=frozenset()):
        if entity.startswith("light."):
            return True
        if not entity.startswith("group.") or entity in seen:
            return False
        members = snapshot.get(entity, {}).get("attributes", {}).get("entity_id", [])
        return (
            isinstance(members, list)
            and bool(members)
            and all(is_light(e, seen | {entity}) for e in members)
        )

    return dict(
        sorted(
            (
                (e, x.get("attributes", {}).get("friendly_name", e))
                for e, x in snapshot.items()
                if is_light(e)
            ),
            key=lambda x: x[1].casefold(),
        )
    )


def light_rooms(snapshot, entity_areas):
    def rooms(entity, seen=frozenset()):
        if entity in seen:
            return set()
        if entity_areas.get(entity):
            return {entity_areas[entity]}
        members = snapshot.get(entity, {}).get("attributes", {}).get("entity_id", [])
        return (
            set().union(*(rooms(e, seen | {entity}) for e in members))
            if isinstance(members, list) and members
            else set()
        )

    return {e: ", ".join(sorted(rooms(e))) or "Rum saknas i HA" for e in light_catalog(snapshot)}


class LightAreas:
    def __init__(self, config):
        self.config = config
        self.entities = {}
        self.icons = {}

    def refresh(self):
        import json

        import websocket

        c = self.config
        w = websocket.create_connection(
            c["ha_url"].replace("http:", "ws:").replace("https:", "wss:") + "/api/websocket",
            timeout=20,
        )
        try:
            w.recv()
            w.send(json.dumps({"type": "auth", "access_token": c["ha_token"]}))
            if json.loads(w.recv()).get("type") != "auth_ok":
                raise ValueError("HA authentication failed")
            data = []
            for i, kind in enumerate(["area", "device", "entity"], 1):
                w.send(json.dumps({"id": i, "type": "config/" + kind + "_registry/list"}))
                r = json.loads(w.recv())
                if not r.get("success"):
                    raise ValueError("HA registry not available")
                data.append(r["result"])
            areas = {a["area_id"]: a["name"] for a in data[0]}
            devices = {d["id"]: d.get("area_id") for d in data[1]}
            self.entities = {
                e["entity_id"]: areas.get(e.get("area_id") or devices.get(e.get("device_id")), "")
                for e in data[2]
                if e["entity_id"].startswith(("light.", "group.", "sensor."))
            }
            self.icons = {
                e["entity_id"]: e.get("icon") or e.get("original_icon")
                for e in data[2]
                if e["entity_id"].startswith(("light.", "group."))
                and (e.get("icon") or e.get("original_icon"))
            }
        finally:
            w.close()

    def loop(self):
        import logging
        import time

        while True:
            try:
                self.refresh()
            except Exception:
                logging.warning("Could not refresh HA light areas; retaining cached rooms")
            time.sleep(300)


def light_icons(snapshot, registry_icons, paths):
    result = {}
    for entity in light_catalog(snapshot):
        icon = (
            registry_icons.get(entity)
            or snapshot[entity].get("attributes", {}).get("icon")
            or "mdi:lightbulb"
        )
        if icon not in paths:
            icon = "mdi:lightbulb"
        result[entity] = {"icon": icon, "path": paths[icon]}
    return result


def control_capabilities(state):
    a = state.get("attributes", {})
    modes = set(a.get("supported_color_modes", []))
    return {
        "brightness": bool(modes - {"onoff", "unknown"}),
        "color": bool(modes & {"hs", "xy", "rgb", "rgbw", "rgbww"}),
        "temperature": "color_temp" in modes,
        "min_kelvin": a.get("min_color_temp_kelvin", 2000),
        "max_kelvin": a.get("max_color_temp_kelvin", 6500),
    }


def validate_light_control(body, state):
    if not isinstance(body, dict) or set(body) - {
        "entity_id",
        "brightness_pct",
        "hs_color",
        "color_temp_kelvin",
    }:
        raise ValueError("Ogiltigt lampkommando.")
    patch = {k: v for k, v in body.items() if k != "entity_id"}
    cap = control_capabilities(state)
    if not patch or "hs_color" in patch and "color_temp_kelvin" in patch:
        raise ValueError("Välj ett giltigt reglage.")
    if "brightness_pct" in patch:
        v = patch["brightness_pct"]
        if not cap["brightness"] or type(v) is not int or not 1 <= v <= 100:
            raise ValueError("Lampan saknar dimring eller ljusstyrkan är ogiltig.")
    if "hs_color" in patch:
        v = patch["hs_color"]
        if (
            not cap["color"]
            or not isinstance(v, list)
            or len(v) != 2
            or any(type(x) not in (float, int) for x in v)
            or not 0 <= v[0] <= 360
            or not 0 <= v[1] <= 100
        ):
            raise ValueError("Lampan saknar färgstöd eller färgen är ogiltig.")
    if "color_temp_kelvin" in patch:
        v = patch["color_temp_kelvin"]
        if (
            not cap["temperature"]
            or type(v) is not int
            or not cap["min_kelvin"] <= v <= cap["max_kelvin"]
        ):
            raise ValueError(
                "Lampan saknar färgtemperatur eller värdet ligger utanför lampans intervall."
            )
    return patch
