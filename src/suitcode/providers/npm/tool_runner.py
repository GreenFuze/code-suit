from __future__ import annotations

import json
import subprocess
from importlib import resources
from pathlib import Path

from suitcode.providers.shared.lsp import TypeScriptLanguageServerResolver


class TypeScriptToolTimeoutError(RuntimeError):
    def __init__(
        self,
        *,
        attachment_root: Path,
        script_name: str,
        retry_after_seconds: int = 15,
    ) -> None:
        self.server_name = "typescript-tooling"
        self.attachment_root = str(attachment_root.expanduser().resolve())
        self.state = "degraded"
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"TypeScript tooling probe `{script_name}` timed out for attachment `{self.attachment_root}`; "
            f"retry after {retry_after_seconds}s"
        )


class TypeScriptProbeRunner:
    def __init__(
        self,
        *,
        repository_root: Path,
        attachment_root: Path,
        resolver: TypeScriptLanguageServerResolver | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._attachment_root = attachment_root.expanduser().resolve()
        self._resolver = resolver or TypeScriptLanguageServerResolver()
        self._timeout_seconds = timeout_seconds

    @property
    def attachment_root(self) -> Path:
        return self._attachment_root

    def resolve_node_path(self) -> str:
        return self._resolver.resolve_node_path()

    def resolve_typescript_library_path(self) -> str:
        return self._resolver.resolve_typescript_library_path(self._attachment_root)

    def script_path(self, script_name: str) -> Path:
        return resources.files("suitcode.providers.npm").joinpath(script_name)

    def run_json_probe(
        self,
        *,
        script_name: str,
        command_args: tuple[str, ...],
        error_label: str,
    ) -> object:
        command = (
            self.resolve_node_path(),
            str(self.script_path(script_name)),
            *command_args,
        )
        try:
            result = subprocess.run(
                command,
                cwd=self._attachment_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise TypeScriptToolTimeoutError(
                attachment_root=self._attachment_root,
                script_name=script_name,
            ) from exc
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.strip() or exc.stdout.strip() or f"unknown {error_label} error"
            raise ValueError(f"unable to resolve deterministic {error_label}: {message}") from exc
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{error_label} returned invalid JSON") from exc
