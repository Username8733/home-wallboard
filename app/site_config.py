"""Installation-specific entities belong in a private config, never in source."""

import json
import os
from pathlib import Path


def load_config():
    path = Path(os.environ.get("WALLBOARD_CONFIG", "/etc/wallboard/config.json"))
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Wallboard configuration must be a JSON object.")
    return value
