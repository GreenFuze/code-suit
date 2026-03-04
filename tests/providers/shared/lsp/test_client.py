from __future__ import annotations

import io
import json
from pathlib import Path

from suitcode.providers.shared.lsp.client import LspClient


def _message(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


class _FakeProcess:
    def __init__(self, responses: bytes) -> None:
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(responses)

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


def test_lsp_client_ignores_interleaved_notifications_while_waiting_for_response() -> None:
    process = _FakeProcess(
        _message({"jsonrpc": "2.0", "method": "window/logMessage", "params": {"type": 3, "message": "loading"}})
        + _message({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})
        + _message({"jsonrpc": "2.0", "method": "telemetry/event", "params": {"name": "progress"}})
        + _message({"jsonrpc": "2.0", "id": 2, "result": []})
    )
    client = LspClient(("fake-server",), Path('.'), process=process)

    client.initialize(Path('.'))
    symbols = client.workspace_symbol('Workspace')

    assert symbols == tuple()


def test_lsp_client_document_symbol_opens_and_closes_file(tmp_path: Path) -> None:
    source_file = tmp_path / "example.py"
    source_file.write_text("class Example:\n    pass\n", encoding="utf-8")
    process = _FakeProcess(
        _message({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})
        + _message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": [
                    {
                        "name": "Example",
                        "kind": 5,
                        "location": {
                            "uri": source_file.resolve().as_uri(),
                            "range": {
                                "start": {"line": 0, "character": 0},
                                "end": {"line": 1, "character": 8},
                            },
                        },
                    }
                ],
            }
        )
    )
    client = LspClient(("fake-server",), tmp_path, process=process)

    client.initialize(tmp_path)
    symbols = client.document_symbol(source_file)

    payload = process.stdin.getvalue().decode("utf-8")
    assert symbols[0].name == "Example"
    assert '"method": "textDocument/didOpen"' in payload
    assert '"method": "textDocument/didClose"' in payload


def test_lsp_client_definition_and_references_open_and_close_file(tmp_path: Path) -> None:
    source_file = tmp_path / "example.py"
    source_file.write_text("value = 1\n", encoding="utf-8")
    process = _FakeProcess(
        _message({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})
        + _message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "uri": source_file.resolve().as_uri(),
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 5},
                    },
                },
            }
        )
        + _message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": [
                    {
                        "uri": source_file.resolve().as_uri(),
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 0, "character": 5},
                        },
                    }
                ],
            }
        )
    )
    client = LspClient(("fake-server",), tmp_path, process=process)

    client.initialize(tmp_path)
    definition = client.definition(source_file, 1, 1)
    references = client.references(source_file, 1, 1, include_declaration=True)

    payload = process.stdin.getvalue().decode("utf-8")
    assert definition[0].uri == source_file.resolve().as_uri()
    assert len(references) == 1
    assert payload.count('"method": "textDocument/didOpen"') == 2
    assert payload.count('"method": "textDocument/didClose"') == 2
    assert '"method": "textDocument/definition"' in payload
    assert '"method": "textDocument/references"' in payload
