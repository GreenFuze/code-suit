from __future__ import annotations

import json
from pathlib import Path

from suitcode.providers.shared.lsp.errors import LspProtocolError
from suitcode.providers.shared.lsp.messages import LspWorkspaceSymbol
from suitcode.providers.shared.lsp.process import LanguageServerProcess
from suitcode.providers.shared.lsp.protocol import LspProtocolParser


class LspClient:
    def __init__(
        self,
        command: tuple[str, ...],
        cwd: Path,
        process: LanguageServerProcess | None = None,
        parser: LspProtocolParser | None = None,
    ) -> None:
        self._process = process or LanguageServerProcess(command, cwd)
        self._parser = parser or LspProtocolParser()
        self._next_request_id = 1
        self._initialized = False

    def initialize(self, root_path: Path) -> None:
        if self._initialized:
            return
        self._process.start()
        root = root_path.expanduser().resolve()
        self._request(
            "initialize",
            {
                "processId": None,
                "rootUri": root.as_uri(),
                "capabilities": {},
                "workspaceFolders": [{"uri": root.as_uri(), "name": root.name}],
            },
        )
        self._notify("initialized", {})
        self._initialized = True

    def workspace_symbol(self, query: str) -> tuple[LspWorkspaceSymbol, ...]:
        payload = self._request("workspace/symbol", {"query": query})
        return self._parser.parse_workspace_symbols(payload)

    def shutdown(self) -> None:
        if not self._initialized:
            self._process.stop()
            return
        try:
            self._request("shutdown", None)
            self._notify("exit", None)
        finally:
            self._process.stop()
            self._initialized = False

    def _request(self, method: str, params: object) -> object:
        request_id = self._next_request_id
        self._next_request_id += 1
        self._write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        response = self._read_message()
        if not isinstance(response, dict):
            raise LspProtocolError("language server response must be an object")
        if response.get("id") != request_id:
            raise LspProtocolError(f"language server response id mismatch for method `{method}`")
        if "error" in response and response["error"] is not None:
            raise LspProtocolError(f"language server returned an error for `{method}`: {response['error']}")
        return response.get("result")

    def _notify(self, method: str, params: object) -> None:
        self._write_message({"jsonrpc": "2.0", "method": method, "params": params})

    def _write_message(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._process.stdin.write(header)
        self._process.stdin.write(body)
        self._process.stdin.flush()

    def _read_message(self) -> object:
        content_length: int | None = None
        while True:
            line = self._process.stdout.readline()
            if line == b"":
                raise LspProtocolError("unexpected EOF while reading language server response")
            if line in (b"\r\n", b"\n"):
                break
            header = line.decode("ascii").strip()
            if header.lower().startswith("content-length:"):
                content_length = int(header.split(":", 1)[1].strip())
        if content_length is None:
            raise LspProtocolError("language server response is missing Content-Length header")
        body = self._process.stdout.read(content_length)
        if len(body) != content_length:
            raise LspProtocolError("language server response body was truncated")
        return json.loads(body.decode("utf-8"))

    def __enter__(self) -> "LspClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()
