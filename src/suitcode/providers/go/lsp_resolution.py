from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from suitcode.providers.shared.lsp.resolver import ExecutableResolver


class GoplsResolver:
    MANAGED_GOPLS_VERSION = "v0.21.1"

    def __init__(self, executable_path: str | None = None) -> None:
        self._executable_path = executable_path
        self._resolver = ExecutableResolver()

    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        root = repository_root.expanduser().resolve()
        error_message = (
            f"gopls was not found for repository `{root}`. Install `gopls`, configure an explicit executable path, "
            "or allow SuitCode managed cached provisioning when the Go toolchain is available."
        )
        try:
            executable = self._resolver.resolve_candidate(
                explicit_path=self._executable_path,
                local_candidates=self._local_candidates(root),
                path_candidates=self._path_candidates(),
                error_message=error_message,
            )
            return (executable,)
        except ValueError:
            managed = self._resolve_managed_gopls(root)
            if managed is None:
                raise ValueError(error_message)
            return (managed,)

    def _resolve_managed_gopls(self, repository_root: Path) -> str | None:
        go_executable = shutil.which("go")
        if go_executable is None:
            return None
        managed_root = self._managed_toolchain_root()
        bin_name = "gopls.exe" if os.name == "nt" else "gopls"
        managed_binary = managed_root / "bin" / bin_name
        ready_marker = managed_root / ".ready"
        if managed_binary.exists() and ready_marker.exists():
            return str(managed_binary.resolve())

        managed_binary.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["GOBIN"] = str(managed_binary.parent.resolve())
        subprocess.run(
            (go_executable, "install", f"golang.org/x/tools/gopls@{self.MANAGED_GOPLS_VERSION}"),
            cwd=repository_root,
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if not managed_binary.exists():
            return None
        ready_marker.write_text("ok\n", encoding="utf-8")
        return str(managed_binary.resolve())

    def _local_candidates(self, repository_root: Path) -> tuple[Path, ...]:
        names = ["gopls"]
        if os.name == "nt":
            names = ["gopls.exe", "gopls.cmd", *names]
        candidates = [repository_root / "bin" / name for name in names]
        candidates.extend((repository_root / ".suit" / "tools" / name) for name in names)
        return tuple(candidates)

    @staticmethod
    def _path_candidates() -> tuple[str, ...]:
        if os.name == "nt":
            return ("gopls.exe", "gopls.cmd", "gopls")
        return ("gopls",)

    def _managed_toolchain_root(self) -> Path:
        cache_base = os.environ.get("SUITCODE_TOOL_CACHE_DIR")
        if cache_base:
            base = Path(cache_base).expanduser()
        elif os.name == "nt":
            base = Path(os.environ.get("LocalAppData", Path.home() / "AppData" / "Local"))
        else:
            base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return base / "SuitCode" / "tools" / "gopls" / f"gopls-{self.MANAGED_GOPLS_VERSION}"
