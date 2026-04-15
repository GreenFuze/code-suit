from __future__ import annotations

import json
from multiprocessing.connection import Client, Connection, Listener
from typing import Any

from suitcode.runtime.endpoint import transport_address
from suitcode.runtime.errors import CoordinatorProtocolError, CoordinatorUnavailableError


def connect(endpoint_uri: str) -> Connection:
    family, address = transport_address(endpoint_uri)
    try:
        return Client(address, family=family)
    except OSError as exc:
        raise CoordinatorUnavailableError(f"unable to connect to coordinator endpoint `{endpoint_uri}`") from exc


def listen(endpoint_uri: str) -> Listener:
    family, address = transport_address(endpoint_uri)
    return Listener(address, family=family)


def send_payload(connection: Connection, payload: dict[str, Any]) -> None:
    try:
        connection.send_bytes(json.dumps(payload).encode("utf-8"))
    except (OSError, ValueError) as exc:
        raise CoordinatorUnavailableError("failed to send coordinator request") from exc


def receive_payload(connection: Connection) -> dict[str, Any]:
    try:
        raw = connection.recv_bytes()
    except EOFError as exc:
        raise CoordinatorUnavailableError("coordinator connection closed unexpectedly") from exc
    except OSError as exc:
        raise CoordinatorUnavailableError("failed to receive coordinator response") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorProtocolError("coordinator payload was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise CoordinatorProtocolError("coordinator payload must be a JSON object")
    return payload
