"""Scheduled screen-off policy, independent of the dashboard color theme."""

import datetime
import os
import subprocess
import time
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Stockholm")


def night_scheduled(settings, now=None):
    if not settings["night_mode_enabled"]:
        return False
    now = time.time() if now is None else now
    local = datetime.datetime.fromtimestamp(now, ZONE)
    minute = local.hour * 60 + local.minute
    start, end = (
        int(value[:2]) * 60 + int(value[3:])
        for value in (settings["night_start"], settings["night_end"])
    )
    return start <= minute < end if start < end else minute >= start or minute < end


def display_state(
    settings, active, fire=False, timer_finished=False, wake_until=0, now=None, manual_sleep=False
):
    now = time.time() if now is None else now
    scheduled = night_scheduled(settings, now)
    if fire:
        mode, level = "active", 1.0
    elif manual_sleep and not timer_finished:
        mode, level = "screen_off", 0.0
    elif scheduled and not timer_finished and now >= wake_until:
        mode, level = "night", 0.0
    elif active or timer_finished or scheduled:
        mode, level = "active", settings["active_brightness"] / 100
    else:
        mode = "slideshow" if settings["screen_mode"] == "photos" else "dim"
        level = settings["idle_brightness"] / 100
    return {
        "mode": mode,
        "level": level,
        "night_scheduled": scheduled,
        "temporary_wake": scheduled and now < wake_until,
    }


class ScreenPower:
    """DPMS plus a zero backlight; normal kiosk operation keeps idle DPMS disabled."""

    def __init__(self):
        self.off = None
        self.attempted = 0
        self.env = dict(os.environ, DISPLAY=":0", XAUTHORITY="/home/wallboard/.Xauthority")

    def set_off(self, off, now=None):
        now = time.monotonic() if now is None else now
        if (self.off is None and now - self.attempted < 2) or (
            self.off == off and (not off or now - self.attempted < 2)
        ):
            return
        self.attempted = now
        commands = (
            [["+dpms"], ["dpms", "force", "off"]] if off else [["dpms", "force", "on"], ["-dpms"]]
        )
        try:
            for args in commands:
                result = subprocess.run(
                    ["/usr/bin/xset", *args],
                    env=self.env,
                    capture_output=True,
                    timeout=2,
                    check=False,
                )
                if result.returncode:
                    self.off = None
                    return
            self.off = off
        except (OSError, subprocess.TimeoutExpired):
            self.off = None
