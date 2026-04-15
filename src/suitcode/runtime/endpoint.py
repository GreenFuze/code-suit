from __future__ import annotations

import os
from multiprocessing.connection import Client, Listener
from pathlib import Path

from suitcode.runtime.models import TransportKind
from suitcode.runtime.paths import endpoint_runtime_dir, project_hash


def endpoint_uri_for_project(project_root: Path) -> tuple[TransportKind, str]:
    project_id = project_hash(project_root)
    if os.name == "nt":
        pipe_name = f"\\\\.\\pipe\\suitcode-{project_id}"
        return TransportKind.PIPE, f"pipe://{pipe_name}"
    runtime_dir = endpoint_runtime_dir()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    socket_path = runtime_dir / f"suitcode-{project_id}.sock"
    return TransportKind.UNIX, f"unix://{socket_path}"


def transport_address(endpoint_uri: str) -> tuple[str, str]:
    if endpoint_uri.startswith("pipe://"):
        return "AF_PIPE", endpoint_uri.removeprefix("pipe://")
    if endpoint_uri.startswith("unix://"):
        return "AF_UNIX", endpoint_uri.removeprefix("unix://")
    raise ValueError(f"unsupported endpoint uri `{endpoint_uri}`")


def listen_on_endpoint(endpoint_uri: str) -> Listener:
    family, address = transport_address(endpoint_uri)
    if family == "AF_UNIX":
        socket_path = Path(address)
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        if socket_path.exists():
            try:
                connection = Client(address, family=family)
            except OSError:
                socket_path.unlink(missing_ok=True)
            else:
                connection.close()
                raise OSError(f"coordinator endpoint `{endpoint_uri}` is already active")
    return Listener(address, family=family)


def cleanup_endpoint(endpoint_uri: str) -> None:
    family, address = transport_address(endpoint_uri)
    if family == "AF_UNIX":
        Path(address).unlink(missing_ok=True)
