"""Wire security and screen safety for remote Home Assistant control."""

import json
import pathlib
import unittest

from control_protocol import pairing_proof, seal, unseal, verify_proof
from cryptography.exceptions import InvalidTag
from display_policy import display_state
from settings_store import DEFAULTS


class ControlProtocolTests(unittest.TestCase):
    secret = "a-test-only-key-with-at-least-32-characters"

    def test_pairing_is_bound_to_device_time_and_single_nonce(self):
        proof = pairing_proof(self.secret, "test_tablet", 1000)
        seen = {}
        self.assertTrue(verify_proof(self.secret, "test_tablet", proof, seen, 1010))
        self.assertFalse(verify_proof(self.secret, "test_tablet", proof, seen, 1010))
        self.assertFalse(verify_proof(self.secret, "other_tablet", proof, {}, 1010))
        self.assertFalse(verify_proof(self.secret, "test_tablet", proof, {}, 1061))
        self.assertNotIn(self.secret, json.dumps(proof))

    def test_encrypted_account_command_round_trip_and_binding(self):
        body = {"action": "icloud_photo_login", "data": {"password": "only-a-test-password"}}
        envelope = seal(self.secret, "test_tablet", "request1", body, 1000)
        self.assertEqual(unseal(self.secret, "test_tablet", "request1", envelope, 1001), body)
        self.assertNotIn("only-a-test-password", json.dumps(envelope))
        for secret, device, request in [
            ("wrong-key", "test_tablet", "request1"),
            (self.secret, "other", "request1"),
            (self.secret, "test_tablet", "other"),
        ]:
            with self.assertRaises(InvalidTag):
                unseal(secret, device, request, envelope, 1001)
        with self.assertRaises(ValueError):
            unseal(self.secret, "test_tablet", "request1", envelope, 1091)
        with self.assertRaises(ValueError):
            seal(self.secret, "test_tablet", "request1", {"large": "x" * 66000})

    def test_random_nonce_and_tamper_rejection(self):
        first = seal(self.secret, "tablet", "request", {"action": "wake"})
        second = seal(self.secret, "tablet", "request", {"action": "wake"})
        self.assertNotEqual(first, second)
        first["ciphertext"] = ("A" if first["ciphertext"][0] != "A" else "B") + first["ciphertext"][
            1:
        ]
        with self.assertRaises(InvalidTag):
            unseal(self.secret, "tablet", "request", first)

    def test_protocol_copies_are_identical(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        self.assertEqual(
            (root / "app/control_protocol.py").read_bytes(),
            (root / "home-assistant/custom_components/home_wallboard/protocol.py").read_bytes(),
        )

    def test_remote_screen_off_never_hides_fire_or_finished_timer(self):
        cfg = dict(DEFAULTS)
        self.assertEqual(display_state(cfg, True, manual_sleep=True)["mode"], "screen_off")
        self.assertEqual(display_state(cfg, True, fire=True, manual_sleep=True)["mode"], "active")
        self.assertEqual(
            display_state(cfg, True, timer_finished=True, manual_sleep=True)["mode"], "active"
        )


class ControlAgentTests(unittest.TestCase):
    def test_replayed_command_is_not_executed_twice(self):
        from unittest.mock import Mock, patch

        from control_agent import ControlAgent

        agent = ControlAgent(
            {"ha_control_device_id": "tablet", "ha_control_secret": ControlProtocolTests.secret}
        )
        connection = object()
        agent.connection = connection
        agent.report = Mock()
        event = {
            "request_id": "unique1",
            "envelope": seal(
                ControlProtocolTests.secret, "tablet", "unique1", {"action": "wake", "data": {}}
            ),
        }
        response = Mock(ok=True)
        response.json.return_value = {"ok": True}
        try:
            with patch("control_agent.requests.post", return_value=response) as post:
                agent.command(event, connection)
                agent.command(event, connection)
                self.assertEqual(post.call_count, 1)
                self.assertEqual(post.call_args.kwargs["json"], {"action": "wake", "data": {}})
                self.assertFalse(agent.report.call_args.args[0]["ok"])
        finally:
            agent.executor.shutdown()

    def test_untrusted_or_disconnected_command_cannot_reach_local_api(self):
        from unittest.mock import Mock, patch

        from control_agent import ControlAgent

        agent = ControlAgent(
            {"ha_control_device_id": "tablet", "ha_control_secret": ControlProtocolTests.secret}
        )
        connection = object()
        agent.connection = connection
        agent.report = Mock()
        event = {
            "request_id": "unique1",
            "envelope": seal("wrong-pairing-key", "tablet", "unique1", {"action": "wake"}),
        }
        try:
            with patch("control_agent.requests.post") as post:
                agent.command(event, connection)
                post.assert_not_called()
                self.assertFalse(agent.report.call_args.args[0]["ok"])
                event = {
                    "request_id": "unique2",
                    "envelope": seal(
                        ControlProtocolTests.secret, "tablet", "unique2", {"action": "wake"}
                    ),
                }
                agent.connection = None
                agent.command(event, connection)
                post.assert_not_called()
        finally:
            agent.executor.shutdown()
