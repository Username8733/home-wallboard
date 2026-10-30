"""Outbound-only HA control agent. No listener, broker or shell commands."""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import websocket
from control_protocol import pairing_proof, unseal

BASE = "http://127.0.0.1:8090"


class ControlAgent:
    def __init__(self, config):
        self.config = config
        self.device_id = config.get("ha_control_device_id", "")
        self.secret = config.get("ha_control_secret", "")
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ha-control")
        self.send_lock = threading.Lock()
        self.connection = None
        self.counter = 10
        self.seen = {}
        self.report_now = threading.Event()
        self.status = {"configured": bool(self.device_id and self.secret), "connected": False}

    def send(self, kind, **body):
        with self.send_lock:
            self.counter += 1
            if self.connection:
                self.connection.send(
                    json.dumps(
                        {"id": self.counter, "type": kind, "device_id": self.device_id, **body}
                    )
                )

    def snapshot(self):
        response = requests.get(BASE + "/api/control/snapshot", timeout=(2, 10))
        response.raise_for_status()
        return response.json()

    def report(self, reply=None):
        body = {"snapshot": self.snapshot()}
        if reply is not None:
            body["reply"] = reply
        self.send("home_wallboard/report", **body)

    def command(self, event, connection):
        request_id = event.get("request_id", "")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 64:
            return
        reply = {"request_id": request_id, "ok": False}
        try:
            if request_id in self.seen:
                raise ValueError("Repeated command rejected")
            command = unseal(self.secret, self.device_id, request_id, event["envelope"])
            self.seen[request_id] = time.time()
            self.seen = {
                key: stamp for key, stamp in self.seen.items() if time.time() - stamp < 300
            }
            if self.connection is not connection:
                return
            response = requests.post(
                BASE + "/api/control/command",
                headers={"Origin": BASE},
                json=command,
                timeout=(3, 55),
            )
            result = response.json()
            if not response.ok:
                raise ValueError(result.get("error", "Command failed"))
            reply.update(ok=True, result=result)
        except ValueError as error:
            reply["error"] = str(error)[:400]
        except Exception:
            reply["error"] = "Wallboard control request could not be completed."
        if self.connection is connection:
            try:
                self.report(reply)
            except Exception:
                self.report_now.set()

    def loop(self):
        if not self.status["configured"]:
            return
        while True:
            connection = None
            try:
                url = (
                    self.config["ha_url"].replace("http://", "ws://").replace("https://", "wss://")
                    + "/api/websocket"
                )
                connection = websocket.create_connection(url, timeout=10)
                connection.recv()
                connection.send(
                    json.dumps({"type": "auth", "access_token": self.config["ha_token"]})
                )
                if json.loads(connection.recv()).get("type") != "auth_ok":
                    raise ValueError("HA authentication failed")
                connection.send(
                    json.dumps(
                        {
                            "id": 1,
                            "type": "home_wallboard/agent",
                            "device_id": self.device_id,
                            **pairing_proof(self.secret, self.device_id),
                        }
                    )
                )
                result = json.loads(connection.recv())
                if not result.get("success"):
                    raise ValueError("HA control integration is not paired")
                self.connection = connection
                self.status["connected"] = True
                connection.settimeout(1)
                last_report = 0
                while True:
                    if time.monotonic() - last_report >= 5 or self.report_now.is_set():
                        self.report_now.clear()
                        self.report()
                        last_report = time.monotonic()
                    try:
                        message = json.loads(connection.recv())
                    except websocket.WebSocketTimeoutException:
                        continue
                    if message.get("type") == "event" and message.get("id") == 1:
                        self.executor.submit(self.command, message.get("event", {}), connection)
                    elif message.get("type") == "result" and message.get("success") is False:
                        raise ValueError("HA rejected a control report")
            except Exception:
                logging.warning("HA control link unavailable; retrying")
            finally:
                self.status["connected"] = False
                if self.connection is connection:
                    self.connection = None
                if connection:
                    connection.close()
            time.sleep(5)
