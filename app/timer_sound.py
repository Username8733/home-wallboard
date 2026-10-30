"""Independent timer sound targets: local tablet, Högtalaren, or both."""

import logging
import os
import pathlib
import subprocess
import time

from sound_catalog import SOUNDS


class TimerSound:
    def __init__(
        self,
        timer,
        fire_active,
        volume=lambda: 100,
        outputs=lambda: ["tablet"],
        announce=None,
        sound=lambda: "chime",
    ):
        self.sound = sound
        self.timer = timer
        self.fire_active = fire_active
        self.volume = volume
        self.outputs = outputs
        self.announce = announce
        self.process = None
        self.preview_process = None
        self.played = False
        self.completed = set()
        self.last_attempt = 0
        self.last_preview = -10

    @staticmethod
    def validate_outputs(outputs):
        if (
            not isinstance(outputs, list)
            or not outputs
            or any(type(x) is not str or x not in {"tablet", "sonos"} for x in outputs)
            or len(outputs) != len(set(outputs))
        ):
            raise ValueError("Välj plattan, Högtalaren eller båda.")
        return outputs

    def play(self, volume, sound=None):
        sound = self.sound() if sound is None else sound
        if type(sound) is not str or sound not in SOUNDS:
            raise ValueError("Välj en giltig ljudsignal.")
        if type(volume) is not int or not 0 <= volume <= 100:
            raise ValueError("Välj en ljudvolym mellan 0 och 100 %.")
        if volume == 0:
            return None
        runtime = "/run/user/" + str(os.getuid())
        env = dict(
            os.environ, XDG_RUNTIME_DIR=runtime, PULSE_SERVER="unix:" + runtime + "/pulse/native"
        )
        return subprocess.Popen(
            [
                "/usr/bin/paplay",
                "--volume=" + str(round(65536 * volume / 100)),
                "--client-name=Wallboard Timer",
                "--stream-name=Timer klar",
                str(pathlib.Path(__file__).parent / "static" / SOUNDS[sound]["file"]),
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def preview(self, volume, outputs=None, sound=None):
        sound = self.sound() if sound is None else sound
        if type(sound) is not str or sound not in SOUNDS:
            raise ValueError("Välj en giltig ljudsignal.")
        outputs = self.validate_outputs(self.outputs() if outputs is None else outputs)
        if type(volume) is not int or not 0 <= volume <= 100:
            raise ValueError("Välj en ljudvolym mellan 0 och 100 %.")
        if self.fire_active():
            raise ValueError("Provlyssning är avstängd under brandlarm.")
        if (
            time.monotonic() - self.last_preview < 2.5
            or self.preview_process
            and self.preview_process.poll() is None
        ):
            raise ValueError("Vänta tills provljudet spelat klart.")
        self.last_preview = time.monotonic()
        if "tablet" in outputs:
            self.preview_process = self.play(volume, sound)
        if "sonos" in outputs and volume and self.announce:
            self.announce(volume, sound)

    def poll(self):
        finished = self.timer.snapshot()["status"] == "finished"
        fire = self.fire_active()
        if fire and self.preview_process and self.preview_process.poll() is None:
            self.preview_process.terminate()
        if self.process and self.process.poll() is None and (not finished or fire):
            self.process.terminate()
        if self.process and self.process.poll() is not None:
            if self.process.returncode != 0:
                self.completed.discard("tablet")
            self.process = None
        if not finished:
            self.completed.clear()
            self.played = False
        outputs = self.validate_outputs(self.outputs())
        self.played = set(outputs) <= self.completed
        if not finished or fire or self.played or time.monotonic() - self.last_attempt < 5:
            return
        self.last_attempt = time.monotonic()
        volume = self.volume()
        sound = self.sound()
        for output in outputs:
            if output in self.completed:
                continue
            try:
                if volume:
                    if output == "tablet":
                        self.process = self.play(volume, sound)
                    elif self.announce:
                        self.announce(volume, sound)
                    else:
                        raise RuntimeError("Sonos announcement unavailable")
                self.completed.add(output)
            except Exception:
                logging.warning("Timer sound target %s unavailable; retrying", output)
        self.played = set(outputs) <= self.completed

    def loop(self):
        while True:
            try:
                self.poll()
            except Exception:
                logging.exception("Timer sound unavailable; retrying")
            time.sleep(0.3)
