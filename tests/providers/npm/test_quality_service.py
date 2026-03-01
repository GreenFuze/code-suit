from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from suitcode.providers.npm.quality_models import (
    NpmLintRunResult,
    NpmQualityDiagnostic,
    NpmResolvedTool,
)
from suitcode.providers.npm.quality_service import NpmQualityService
from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol


class _FakeToolResolver:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    def resolve_linter(self, file_path: Path) -> NpmResolvedTool:
        return NpmResolvedTool(
            tool="eslint",
            executable_path=self._repository_root / "node_modules" / ".bin" / "eslint",
            config_path=self._repository_root / "eslint.config.js",
        )

    def resolve_formatter(self, file_path: Path) -> NpmResolvedTool:
        return NpmResolvedTool(
            tool="prettier",
            executable_path=self._repository_root / "node_modules" / ".bin" / "prettier",
            config_path=self._repository_root / ".prettierrc",
        )


class _FakeFileSymbolService:
    def __init__(self, responses: list[tuple[NpmWorkspaceSymbol, ...]]) -> None:
        self._responses = responses

    def get_file_entities(self, repository_rel_path: str) -> tuple[NpmWorkspaceSymbol, ...]:
        return self._responses.pop(0)


class _FakeEslintRunner:
    def run(self, tool: NpmResolvedTool, file_path: Path, is_fix: bool) -> NpmLintRunResult:
        if is_fix:
            file_path.write_text(
                "export function coreFn(): string {\n  return 'fixed';\n}\n",
                encoding="utf-8",
            )
        return NpmLintRunResult(
            diagnostics=(NpmQualityDiagnostic(tool="eslint", severity="warning", message="warning", line_start=1),),
            message="linted",
        )


class _FakePrettierRunner:
    def run(self, tool: NpmResolvedTool, file_path: Path):
        file_path.write_text(
            "export function formattedFn(): string {\n  return 'formatted';\n}\n",
            encoding="utf-8",
        )
        return type("RunResult", (), {"message": "formatted"})()


class _SequentialFileSymbolService:
    def __init__(self, responses: list[tuple[NpmWorkspaceSymbol, ...]]) -> None:
        self._responses = responses

    def get_file_entities(self, repository_rel_path: str) -> tuple[NpmWorkspaceSymbol, ...]:
        return self._responses.pop(0)


def _symbol(name: str, line_start: int, line_end: int) -> NpmWorkspaceSymbol:
    return NpmWorkspaceSymbol(
        name=name,
        kind="function",
        repository_rel_path="packages/core/src/index.ts",
        line_start=line_start,
        line_end=line_end,
        column_start=1,
        column_end=10,
        container_name=None,
        signature=None,
    )


def _write_fake_tool(repo_root: Path, tool_name: str, script_body: str) -> None:
    bin_dir = repo_root / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    script_path = bin_dir / f"{tool_name}.py"
    script_path.write_text(script_body, encoding="utf-8")
    if os.name == "nt":
        wrapper_path = bin_dir / f"{tool_name}.cmd"
        wrapper_path.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0{tool_name}.py" %*\r\n', encoding="utf-8")
    else:
        wrapper_path = bin_dir / tool_name
        wrapper_path.write_text(f"#!{sys.executable}\n{script_body}", encoding="utf-8")
        wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IEXEC)


def _install_quality_tooling(repo_root: Path) -> None:
    (repo_root / ".prettierrc").write_text("{\"semi\": true}\n", encoding="utf-8")
    (repo_root / "eslint.config.js").write_text("export default [];\n", encoding="utf-8")
    _write_fake_tool(
        repo_root,
        "prettier",
        (
            "import pathlib, sys\n"
            "target = pathlib.Path(sys.argv[-1])\n"
            "target.write_text(\"export function formattedFn(): string {\\n  return 'formatted';\\n}\\n\", encoding='utf-8')\n"
            "print(f'formatted {target}')\n"
        ),
    )
    _write_fake_tool(
        repo_root,
        "eslint",
        (
            "import json, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "fix = '--fix' in args\n"
            "target = pathlib.Path(args[-1])\n"
            "if fix:\n"
            "    target.write_text(\"export function fixedFn(): string {\\n  return 'fixed';\\n}\\n\", encoding='utf-8')\n"
            "payload = [{\"filePath\": str(target), \"messages\": [{\"ruleId\": \"semi\", \"severity\": 1, \"message\": \"warning\", \"line\": 1, \"endLine\": 1, \"column\": 1, \"endColumn\": 2}]}]\n"
            "print(json.dumps(payload))\n"
            "sys.exit(1)\n"
        ),
    )


def test_quality_service_raises_when_no_supported_config_exists(npm_repository) -> None:
    service = NpmQualityService(npm_repository)

    with pytest.raises(ValueError, match="Prettier config"):
        service.format_file("packages/core/src/index.ts")

    with pytest.raises(ValueError, match="ESLint config"):
        service.lint_file("packages/core/src/index.ts", is_fix=False)


def test_quality_service_format_file_returns_compact_result_with_delta(npm_repository) -> None:
    target_file = npm_repository.root / "packages" / "core" / "src" / "index.ts"
    target_file.write_text("export function oldFn(): string { return 'old'; }\n", encoding="utf-8")
    service = NpmQualityService(
        npm_repository,
        tool_resolver=_FakeToolResolver(npm_repository.root),
        prettier_runner=_FakePrettierRunner(),
        file_symbol_service=_FakeFileSymbolService(
            [(_symbol("oldFn", 1, 1),), (_symbol("formattedFn", 1, 3),)]
        ),
    )

    result = service.format_file("packages/core/src/index.ts")

    assert result.operation == "format"
    assert result.tool == "prettier"
    assert result.changed is True
    assert result.applied_fixes is True
    assert [item.name for item in result.entity_delta.added] == ["formattedFn"]
    assert [item.name for item in result.entity_delta.removed] == ["oldFn"]


def test_quality_service_lint_file_supports_fix_mode_and_diagnostics(npm_repository) -> None:
    target_file = npm_repository.root / "packages" / "core" / "src" / "index.ts"
    target_file.write_text("export function coreFn( ) : string { return 'bad'; }\n", encoding="utf-8")
    service = NpmQualityService(
        npm_repository,
        tool_resolver=_FakeToolResolver(npm_repository.root),
        eslint_runner=_FakeEslintRunner(),
        file_symbol_service=_FakeFileSymbolService(
            [(_symbol("coreFn", 1, 1),), (_symbol("coreFn", 1, 3),)]
        ),
    )

    result = service.lint_file("packages/core/src/index.ts", is_fix=True)

    assert result.operation == "lint"
    assert result.tool == "eslint"
    assert result.changed is True
    assert result.applied_fixes is True
    assert result.diagnostics[0].message == "warning"
    assert [item.name for item in result.entity_delta.updated] == ["coreFn"]


def test_quality_service_executes_real_stubbed_formatter_and_linter_with_fix(npm_repository) -> None:
    _install_quality_tooling(npm_repository.root)
    target_file = npm_repository.root / "packages" / "core" / "src" / "index.ts"
    target_file.write_text("export function broken( ) : string { return 'bad'; }\n", encoding="utf-8")

    format_service = NpmQualityService(
        npm_repository,
        file_symbol_service=_SequentialFileSymbolService(
            [(_symbol("broken", 1, 1),), (_symbol("formattedFn", 1, 3),)]
        ),
    )
    format_result = format_service.format_file("packages/core/src/index.ts")

    assert format_result.changed is True
    assert format_result.tool == "prettier"
    assert format_result.applied_fixes is True
    assert "formattedFn" in target_file.read_text(encoding="utf-8")

    lint_service = NpmQualityService(
        npm_repository,
        file_symbol_service=_SequentialFileSymbolService(
            [(_symbol("formattedFn", 1, 3),), (_symbol("fixedFn", 1, 3),)]
        ),
    )
    lint_result = lint_service.lint_file("packages/core/src/index.ts", is_fix=True)

    assert lint_result.changed is True
    assert lint_result.tool == "eslint"
    assert lint_result.applied_fixes is True
    assert lint_result.diagnostics[0].rule_id == "semi"
    assert "fixedFn" in target_file.read_text(encoding="utf-8")
