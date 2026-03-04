from __future__ import annotations

import json
from pathlib import Path

from suitcode.providers.shared.lsp.errors import LspProtocolError
from suitcode.providers.shared.lsp.messages import LspDocumentSymbol, LspLocation, LspWorkspaceSymbol
from suitcode.providers.shared.lsp.process import LanguageServerProcess
from suitcode.providers.shared.lsp.protocol import LspProtocolParser


class LspClient:
    def __init__(
        self,
        command: tuple[str, ...],
        cwd: Path,
        process: LanguageServerProcess | None = None,
        parser: LspProtocolParser | None = None,
        initialization_options: dict[str, object] | None = None,
    ) -> None:
        self._process = process or LanguageServerProcess(command, cwd)
        self._parser = parser or LspProtocolParser()
        self._next_request_id = 1
        self._initialized = False
        self._initialization_options = initialization_options

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
                "initializationOptions": self._initialization_options or {},
            },
        )
        self._notify("initialized", {})
        self._initialized = True

    def workspace_symbol(self, query: str) -> tuple[LspWorkspaceSymbol, ...]:
        payload = self._request("workspace/symbol", {"query": query})
        return self._parser.parse_workspace_symbols(payload)

    def document_symbol(self, file_path: Path) -> tuple[LspDocumentSymbol, ...]:
        resolved = file_path.resolve()
        payload = self._request_for_open_document(resolved, "textDocument/documentSymbol", {"textDocument": {"uri": resolved.as_uri()}})
        return self._parser.parse_document_symbols(payload)

    def definition(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        resolved = file_path.resolve()
        payload = self._request_for_open_document(
            resolved,
            "textDocument/definition",
            {"textDocument": {"uri": resolved.as_uri()}, "position": self._lsp_position(line, column)},
        )
        return self._parser.parse_locations(payload)

    def references(
        self,
        file_path: Path,
        line: int,
        column: int,
        include_declaration: bool = False,
    ) -> tuple[LspLocation, ...]:
        resolved = file_path.resolve()
        payload = self._request_for_open_document(
            resolved,
            "textDocument/references",
            {
                "textDocument": {"uri": resolved.as_uri()},
                "position": self._lsp_position(line, column),
                "context": {"includeDeclaration": include_declaration},
            },
        )
        return self._parser.parse_locations(payload)

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
        while True:
            response = self._read_message()
            if not isinstance(response, dict):
                raise LspProtocolError("language server response must be an object")
            if response.get("id") != request_id:
                continue
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

    def _request_for_open_document(self, file_path: Path, method: str, params: object) -> object:
        self._notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": file_path.as_uri(),
                    "languageId": self._language_id_for_path(file_path),
                    "version": 1,
                    "text": file_path.read_text(encoding="utf-8"),
                }
            },
        )
        try:
            return self._request(method, params)
        finally:
            self._notify("textDocument/didClose", {"textDocument": {"uri": file_path.as_uri()}})

    @staticmethod
    def _lsp_position(line: int, column: int) -> dict[str, int]:
        if line < 1 or column < 1:
            raise ValueError("line and column must be >= 1")
        return {"line": line - 1, "character": column - 1}

    def _language_id_for_path(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == ".py":
            return "python"
        if suffix in {".ts", ".mts", ".cts"}:
            return "typescript"
        if suffix == ".tsx":
            return "typescriptreact"
        if suffix in {".js", ".mjs", ".cjs"}:
            return "javascript"
        if suffix == ".jsx":
            return "javascriptreact"
        return "plaintext"

    def __enter__(self) -> "LspClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()
