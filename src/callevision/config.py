"""Load YAML configuration."""

from pathlib import Path
from typing import Any

import yaml


_DEFAULTS: dict[str, Any] = {
    "mqtt": {
        "host": "localhost",
        "port": 1883,
        "username": None,
        "password": None,
        "client_id": "callevision-bridge",
    },
    "paths": {
        "runtime_pages": str(Path(__file__).parent.parent.parent / "runtime" / "pages"),
        "templates": str(Path(__file__).parent.parent.parent / "templates"),
    },
    "teletext": {
        "service_name": "callevision-teletext",
        "reload_debounce_ms": 750,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load(path: str | Path) -> dict[str, Any]:
    with open(path) as f:
        user = yaml.safe_load(f) or {}
    return _deep_merge(_DEFAULTS, user)
