from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping


_SENSITIVE_KEY_MARKERS = (
    "token",
    "password",
    "passwd",
    "secret",
    "authorization",
    "cookie",
    "api_key",
    "access_key",
    "private_key",
    "refresh_token",
)


def redact_arguments(arguments: Mapping[str, Any], *, max_string_length: int = 512, max_items: int = 50) -> dict[str, object]:
    def _redact(key: str | None, value: Any) -> object:
        if key is not None and _is_sensitive_key(key):
            return "<redacted>"

        if isinstance(value, Path):
            return _truncate_string(str(value), max_string_length)
        if isinstance(value, str):
            return _truncate_string(value, max_string_length)
        if isinstance(value, bool | int | float) or value is None:
            return value
        if isinstance(value, Mapping):
            items: dict[str, object] = {}
            for idx, (inner_key, inner_value) in enumerate(value.items()):
                if idx >= max_items:
                    items["__truncated__"] = True
                    break
                items[str(inner_key)] = _redact(str(inner_key), inner_value)
            return items
        if isinstance(value, tuple | list | set):
            output: list[object] = []
            for idx, item in enumerate(value):
                if idx >= max_items:
                    output.append("<truncated>")
                    break
                output.append(_redact(None, item))
            return output
        return _truncate_string(repr(value), max_string_length)

    return {str(key): _redact(str(key), value) for key, value in arguments.items()}


def fingerprint_arguments(arguments_redacted: Mapping[str, object]) -> str:
    serialized = json.dumps(arguments_redacted, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)


def _truncate_string(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."

