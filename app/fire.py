"""Latch real alarm signals until their own sensor explicitly reports clear."""

import json
import pathlib
import threading
import time

from site_config import load_config

DETECTORS = load_config().get("detectors", {})


class FireMonitor:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.lock = threading.RLock()
        self.active = {}
        try:
            self.active = {
                k: v for k, v in json.loads(self.path.read_text()).items() if k in DETECTORS
            }
        except (OSError, ValueError):
            pass

    def update(self, states):
        with self.lock:
            changed = False
            for entity in DETECTORS:
                value = states.get(entity, {}).get("state")
                if value == "on" and entity not in self.active:
                    self.active[entity] = time.time()
                    changed = True
                elif value == "off" and entity in self.active:
                    del self.active[entity]
                    changed = True
            if changed:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.active))
                tmp.replace(self.path)

    def status(self, states, online):
        with self.lock:
            alarms = []
            for entity, started in sorted(self.active.items(), key=lambda item: item[1]):
                d = DETECTORS[entity]
                button = d["mute"]
                value = states.get(entity, {}).get("state")
                available = bool(
                    online
                    and value == "on"
                    and button
                    and states.get(button, {}).get("state") not in {None, "unavailable", "unknown"}
                )
                reason = (
                    "Anslutningen till HA saknas"
                    if not online
                    else "Aktuell detektorstatus saknas"
                    if value != "on"
                    else "Tystning av brandvarnaren stöds inte via kameran"
                    if not button
                    else "Detektorns tystningsknapp är otillgänglig"
                    if not available
                    else ""
                )
                alarms.append(
                    {
                        "entity_id": entity,
                        "name": d["name"],
                        "kind": d["kind"],
                        "since": started,
                        "confirmed": online and value == "on",
                        "mute_available": available,
                        "mute_reason": reason,
                    }
                )
            return {"active": bool(alarms), "alarms": alarms, "online": online}
