"""Public examples and screenshot tooling must never touch real household services."""

import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ):
        spec.loader.exec_module(module)
    return module


class PublicDemoTests(unittest.TestCase):
    def test_demo_is_english_synthetic_and_rejects_production_operations(self):
        with patch("requests.request", side_effect=AssertionError("No external services allowed")):
            demo = load("public_demo", ROOT / "examples/demo.py")
            client = demo.app.test_client()
            state = client.get("/api/state").get_json()
            self.assertEqual(state["demo"], "synthetic-public-data-v1")
            self.assertEqual(state["settings"]["language"], "en")
            self.assertEqual(len(state["lights"]), 9)
            for path in [
                "/api/light/control",
                "/api/control/command",
                "/api/music/control",
                "/api/accounts/icloud/calendar",
                "/api/settings",
            ]:
                self.assertEqual(
                    client.post(path, json={"password": "test-password-only"}).status_code, 403
                )
            self.assertEqual(client.get("/api/accounts/icloud").status_code, 403)
            self.assertNotIn("ha_token", str(state))

    def test_screenshot_capture_refuses_production_data(self):
        tool = load("public_capture", ROOT / "scripts/capture_screenshots.py")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("requests.get", return_value=Mock(json=lambda: {"settings": {"language": "en"}})),
            patch("subprocess.Popen") as start,
        ):
            with self.assertRaisesRegex(ValueError, "refusing to capture"):
                tool.capture("/unused-browser", pathlib.Path(directory), "http://127.0.0.1:8090")
            start.assert_not_called()

    def test_screenshot_capture_refuses_external_hosts(self):
        tool = load("public_capture", ROOT / "scripts/capture_screenshots.py")
        with tempfile.TemporaryDirectory() as directory, patch("requests.get") as get:
            with self.assertRaisesRegex(ValueError, "local synthetic demo"):
                tool.capture("/unused-browser", pathlib.Path(directory), "https://example.invalid")
            get.assert_not_called()
