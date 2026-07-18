"""Human and machine-readable command results."""

from __future__ import annotations

import json
from typing import Any


def envelope(command: str, data: Any) -> dict[str, Any]:
    return {"schema": 1, "command": command, "status": "ok", "data": data}


def emit(command: str, data: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(envelope(command, data), indent=2, sort_keys=True))
        return
    if isinstance(data, list):
        for item in data:
            print(f"{item['id']}\t{item.get('title', '')}")
    elif isinstance(data, dict):
        for key, value in data.items():
            print(f"{key}: {value}")
    else:
        print(data)
