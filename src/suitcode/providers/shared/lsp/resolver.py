from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class ExecutableResolver:
    def resolve_candidate(
        self,
        explicit_path: str | None,
        local_candidates: tuple[Path, ...],
        path_candidates: tuple[str, ...],
        error_message: str,
    ) -> str:
        if explicit_path is not None:
            explicit = Path(explicit_path).expanduser()
            if explicit.exists():
                return str(explicit.resolve())
            resolved = shutil.which(explicit_path)
            if resolved is not None:
                return resolved
            raise ValueError(error_message)

        for candidate in local_candidates:
            if candidate.exists():
                return str(candidate.resolve())

        for candidate in path_candidates:
            resolved = shutil.which(candidate)
            if resolved is not None:
                return resolved

        raise ValueError(error_message)


class TypeScriptLanguageServerResolver:
    MANAGED_TYPESCRIPT_LANGUAGE_SERVER_VERSION = "5.1.3"

    def __init__(self, executable_path: str | None = None, tsserver_path: str | None = None) -> None:
        self._executable_path = executable_path
        self._tsserver_path = tsserver_path
        self._resolver = ExecutableResolver()

    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        root = repository_root.expanduser().resolve()
        local_module_command = self._resolve_local_language_server_module_command(root)
        if local_module_command is not None:
            self._resolve_tsserver(root)
            return local_module_command
        managed_module_command = self._resolve_managed_language_server_module_command(root)
        if managed_module_command is not None:
            self._resolve_tsserver(root)
            return managed_module_command
        language_server = self._resolve_language_server(root)
        self._resolve_tsserver(root)
        return (language_server, "--stdio")

    def resolve_initialization_options(self, repository_root: Path) -> dict[str, object]:
        root = repository_root.expanduser().resolve()
        tsserver = self._resolve_tsserver(root)
        return {"tsserver": {"path": tsserver}}

    def resolve_node_path(self) -> str:
        node = self._resolve_node_executable()
        if node is None:
            raise ValueError("node executable was not found for TypeScript tooling")
        return node

    def resolve_typescript_library_path(self, repository_root: Path) -> str:
        root = repository_root.expanduser().resolve()
        local_candidate = root / "node_modules" / "typescript" / "lib" / "typescript.js"
        if local_candidate.exists():
            return str(local_candidate.resolve())
        toolchain_root = self._ensure_managed_toolchain(root)
        managed_candidate = toolchain_root / "node_modules" / "typescript" / "lib" / "typescript.js"
        if managed_candidate.exists():
            return str(managed_candidate.resolve())
        raise ValueError(
            f"typescript library was not found for repository `{root}`. "
            "Install repo-local `typescript`, or allow SuitCode managed cached provisioning."
        )

    def _resolve_language_server(self, repository_root: Path) -> str:
        error_message = (
            "typescript-language-server was not found for repository "
            f"`{repository_root}`. Install `typescript-language-server` and `typescript`, "
            "or configure explicit executable paths. SuitCode also supports managed cached provisioning when Node/npm are available."
        )
        return self._resolver.resolve_candidate(
            explicit_path=self._executable_path,
            local_candidates=self._local_language_server_candidates(repository_root),
            path_candidates=("typescript-language-server", "typescript-language-server.cmd"),
            error_message=error_message,
        )

    def _resolve_tsserver(self, repository_root: Path) -> str:
        local_tsserver = self._resolve_local_or_path_tsserver(repository_root)
        if local_tsserver is not None:
            return local_tsserver
        managed_tsserver = self._resolve_managed_tsserver(repository_root)
        if managed_tsserver is not None:
            return managed_tsserver
        error_message = (
            "tsserver was not found for repository "
            f"`{repository_root}`. Install `typescript`, or configure an explicit tsserver path. "
            "SuitCode also supports managed cached provisioning when Node/npm are available."
        )
        raise ValueError(error_message)

    def _resolve_local_or_path_tsserver(self, repository_root: Path) -> str | None:
        try:
            return self._resolver.resolve_candidate(
                explicit_path=self._tsserver_path,
                local_candidates=self._local_tsserver_candidates(repository_root),
                path_candidates=("tsserver", "tsserver.cmd"),
                error_message="tsserver unavailable",
            )
        except ValueError:
            return None

    def _local_language_server_candidates(self, repository_root: Path) -> tuple[Path, ...]:
        bin_dir = repository_root / "node_modules" / ".bin"
        names = ["typescript-language-server"]
        if os.name == "nt":
            names.insert(0, "typescript-language-server.cmd")
        return tuple(bin_dir / name for name in names)

    def _resolve_local_language_server_module_command(self, repository_root: Path) -> tuple[str, ...] | None:
        node = self._resolve_node_executable()
        if node is None:
            return None
        cli_module = repository_root / "node_modules" / "typescript-language-server" / "lib" / "cli.mjs"
        if not cli_module.exists():
            return None
        return (node, str(cli_module.resolve()), "--stdio")

    def _resolve_managed_language_server_module_command(self, repository_root: Path) -> tuple[str, ...] | None:
        node = self._resolve_node_executable()
        if node is None:
            return None
        toolchain_root = self._ensure_managed_toolchain(repository_root)
        cli_module = toolchain_root / "node_modules" / "typescript-language-server" / "lib" / "cli.mjs"
        if not cli_module.exists():
            return None
        return (node, str(cli_module.resolve()), "--stdio")

    def _resolve_node_executable(self) -> str | None:
        resolved = shutil.which("node")
        if resolved is not None:
            return resolved
        if os.name != "nt":
            return None
        candidates: list[Path] = []
        for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
            base = os.environ.get(env_name)
            if not base:
                continue
            candidates.append(Path(base) / "nodejs" / "node.exe")
        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve())
        return None

    def _local_tsserver_candidates(self, repository_root: Path) -> tuple[Path, ...]:
        candidates = [repository_root / "node_modules" / "typescript" / "lib" / "tsserver.js"]
        if os.name == "nt":
            candidates.append(repository_root / "node_modules" / ".bin" / "tsserver.cmd")
        candidates.append(repository_root / "node_modules" / ".bin" / "tsserver")
        return tuple(candidates)

    def _resolve_managed_tsserver(self, repository_root: Path) -> str | None:
        toolchain_root = self._ensure_managed_toolchain(repository_root)
        candidate = toolchain_root / "node_modules" / "typescript" / "lib" / "tsserver.js"
        if candidate.exists():
            return str(candidate.resolve())
        return None

    def _ensure_managed_toolchain(self, repository_root: Path) -> Path:
        managed_root = self._managed_toolchain_root(repository_root)
        ready_marker = managed_root / ".ready"
        cli_module = managed_root / "node_modules" / "typescript-language-server" / "lib" / "cli.mjs"
        tsserver = managed_root / "node_modules" / "typescript" / "lib" / "tsserver.js"
        if ready_marker.exists() and cli_module.exists() and tsserver.exists():
            return managed_root

        npm = self._resolve_npm_executable()
        if npm is None:
            raise ValueError(
                "npm was not found for managed TypeScript language-server provisioning. "
                f"Install npm or provide repo-local tooling for `{repository_root}`."
            )

        managed_root.mkdir(parents=True, exist_ok=True)
        package_json = managed_root / "package.json"
        package_json.write_text(
            (
                "{\n"
                '  "name": "suitcode-ts-lsp-cache",\n'
                '  "private": true,\n'
                '  "dependencies": {\n'
                f'    "typescript-language-server": "{self.MANAGED_TYPESCRIPT_LANGUAGE_SERVER_VERSION}",\n'
                f'    "typescript": "{self._managed_typescript_version(repository_root)}"\n'
                "  }\n"
                "}\n"
            ),
            encoding="utf-8",
        )
        subprocess.run(
            (
                npm,
                "install",
                "--no-fund",
                "--no-audit",
                "--ignore-scripts",
                "--loglevel=error",
            ),
            cwd=managed_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        ready_marker.write_text("ok\n", encoding="utf-8")
        return managed_root

    def _managed_typescript_version(self, repository_root: Path) -> str:
        local_package_json = repository_root / "node_modules" / "typescript" / "package.json"
        if local_package_json.exists():
            import json

            try:
                raw = json.loads(local_package_json.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return "5.7.3"
            version = raw.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
        return "5.7.3"

    def _managed_toolchain_root(self, repository_root: Path) -> Path:
        cache_base = os.environ.get("SUITCODE_TOOL_CACHE_DIR")
        if cache_base:
            base = Path(cache_base).expanduser()
        elif os.name == "nt":
            base = Path(os.environ.get("LocalAppData", Path.home() / "AppData" / "Local"))
        else:
            base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return (
            base
            / "SuitCode"
            / "tools"
            / "typescript-language-server"
            / f"tsls-{self.MANAGED_TYPESCRIPT_LANGUAGE_SERVER_VERSION}__ts-{self._managed_typescript_version(repository_root)}"
        )

    def _resolve_npm_executable(self) -> str | None:
        candidates = ("npm.cmd", "npm.exe", "npm") if os.name == "nt" else ("npm",)
        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved is not None:
                return resolved
        return None
