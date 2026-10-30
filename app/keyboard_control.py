"""Narrow D-Bus control of the kiosk user's installed Onboard keyboard."""

import os
import subprocess
import threading
import time


class KeyboardControl:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = {"available": False, "visible": False, "height": 400}
        self.env = dict(
            os.environ, DBUS_SESSION_BUS_ADDRESS=f"unix:path=/run/user/{os.getuid()}/bus"
        )

    def call(self, method, *args):
        try:
            # Do not let status polling auto-start Onboard before the graphical session
            # can supply its fullscreen window-manager options.
            owner = subprocess.run(
                [
                    "/usr/bin/gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.freedesktop.DBus",
                    "--object-path",
                    "/org/freedesktop/DBus",
                    "--method",
                    "org.freedesktop.DBus.NameHasOwner",
                    "org.onboard.Onboard",
                ],
                env=self.env,
                text=True,
                capture_output=True,
                timeout=2,
            )
            if owner.returncode or "true" not in owner.stdout.lower():
                return False, ""
            r = subprocess.run(
                [
                    "/usr/bin/gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.onboard.Onboard",
                    "--object-path",
                    "/org/onboard/Onboard/Keyboard",
                    "--method",
                    method,
                    *args,
                ],
                env=self.env,
                text=True,
                capture_output=True,
                timeout=2,
            )
            return r.returncode == 0, r.stdout
        except (OSError, subprocess.TimeoutExpired):
            return False, ""

    def set_visible(self, visible):
        ok, _ = self.call("org.onboard.Onboard.Keyboard." + ("Show" if visible else "Hide"))
        with self.lock:
            self.value["available"] = ok
            if ok:
                self.value["visible"] = visible
        return ok

    def snapshot(self):
        with self.lock:
            return dict(self.value)

    def poll(self):
        while True:
            ok, out = self.call(
                "org.freedesktop.DBus.Properties.Get", "org.onboard.Onboard.Keyboard", "Visible"
            )
            with self.lock:
                self.value.update(available=ok, visible=ok and "true" in out.lower())
            time.sleep(1)
