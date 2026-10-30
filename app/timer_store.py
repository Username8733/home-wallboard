"""One persistent local countdown. Expiry stays visible until acknowledged."""

import json
import math
import pathlib
import threading
import time


class TimerStore:
    def __init__(self, path, clock=time.time):
        self.path = pathlib.Path(path)
        self.clock = clock
        self.lock = threading.RLock()
        self.value = {"status": "idle", "duration": 300, "remaining": 300, "deadline": None}
        try:
            v = json.loads(self.path.read_text())
            if (
                v["status"] in {"idle", "running", "paused", "finished"}
                and type(v["duration"]) is int
                and 1 <= v["duration"] <= 86400
                and type(v["remaining"]) in (int, float)
                and 0 <= v["remaining"] <= 86400
                and (
                    v["deadline"] is None
                    or type(v["deadline"]) in (int, float)
                    and math.isfinite(v["deadline"])
                )
                and (v["status"] != "running" or v["deadline"] is not None)
            ):
                self.value = v
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.value))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def snapshot(self):
        with self.lock:
            if self.value["status"] == "running" and self.value["deadline"] <= self.clock():
                self.value.update(status="finished", remaining=0, deadline=None)
                self.persist()
            v = dict(self.value)
            v["remaining"] = (
                max(0, v["deadline"] - self.clock()) if v["status"] == "running" else v["remaining"]
            )
            v["server_now"] = self.clock()
            return v

    def command(self, body):
        if not isinstance(body, dict):
            raise ValueError("Ogiltigt timerkommando.")
        with self.lock:
            self.snapshot()
            action = body.get("action")
            v = self.value
            if action == "start":
                seconds = body.get("seconds")
                if type(seconds) is not int or not 1 <= seconds <= 86400:
                    raise ValueError("Välj en tid mellan 1 sekund och 24 timmar.")
                v.update(
                    status="running",
                    duration=seconds,
                    remaining=seconds,
                    deadline=self.clock() + seconds,
                )
            elif action == "pause" and v["status"] == "running":
                v.update(
                    status="paused", remaining=max(0, v["deadline"] - self.clock()), deadline=None
                )
            elif action == "resume" and v["status"] == "paused":
                v.update(status="running", deadline=self.clock() + v["remaining"])
            elif action in {"reset", "dismiss"}:
                v.update(status="idle", remaining=v["duration"], deadline=None)
            else:
                raise ValueError("Timerkommandot kan inte användas nu.")
            self.persist()
            return self.snapshot()
