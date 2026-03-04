from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from suitcode.providers.python.quality_models import PythonLintRunResult, PythonQualityDiagnostic, PythonResolvedTool
from suitcode.providers.python.quality_service import PythonQualityService
from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol


class _MissingToolResolver:
    def resolve(self, file_path: Path) -> PythonResolvedTool:
        raise ValueError('ruff was not found for repository')


class _FakeToolResolver:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    def resolve(self, file_path: Path) -> PythonResolvedTool:
        return PythonResolvedTool(
            tool='ruff',
            executable_path=self._repository_root / '.venv' / 'Scripts' / ('ruff.cmd' if os.name == 'nt' else 'ruff'),
        )


class _FakeFileSymbolService:
    def __init__(self, responses: list[tuple[PythonWorkspaceSymbol, ...]]) -> None:
        self._responses = responses

    def get_file_symbols(self, repository_rel_path: str) -> tuple[PythonWorkspaceSymbol, ...]:
        return self._responses.pop(0)


class _FakeRuffRunner:
    def run_check(self, tool: PythonResolvedTool, file_path: Path, is_fix: bool) -> PythonLintRunResult:
        if is_fix:
            file_path.write_text(
                "def build_repository_id(name: str) -> str:\n    return f'fixed:{name}'\n",
                encoding='utf-8',
            )
        return PythonLintRunResult(
            diagnostics=(PythonQualityDiagnostic(tool='ruff', severity='warning', message='warning', line_start=1),),
            message='linted',
        )

    def run_format(self, tool: PythonResolvedTool, file_path: Path):
        file_path.write_text(
            "def format_repository_id(name: str) -> str:\n    return f'formatted:{name}'\n",
            encoding='utf-8',
        )
        return type('RunResult', (), {'message': 'formatted'})()


class _SequentialFileSymbolService:
    def __init__(self, responses: list[tuple[PythonWorkspaceSymbol, ...]]) -> None:
        self._responses = responses

    def get_file_symbols(self, repository_rel_path: str) -> tuple[PythonWorkspaceSymbol, ...]:
        return self._responses.pop(0)


def _symbol(name: str, line_start: int, line_end: int) -> PythonWorkspaceSymbol:
    return PythonWorkspaceSymbol(
        name=name,
        kind='function',
        repository_rel_path='src/acme/core/repository.py',
        line_start=line_start,
        line_end=line_end,
        column_start=1,
        column_end=10,
        container_name=None,
        signature=None,
    )


def _write_fake_tool(repo_root: Path, tool_name: str, script_body: str) -> None:
    bin_dir = repo_root / '.venv' / ('Scripts' if os.name == 'nt' else 'bin')
    bin_dir.mkdir(parents=True, exist_ok=True)
    script_path = bin_dir / f'{tool_name}.py'
    script_path.write_text(script_body, encoding='utf-8')
    if os.name == 'nt':
        wrapper_path = bin_dir / f'{tool_name}.cmd'
        wrapper_path.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0{tool_name}.py" %*\r\n', encoding='utf-8')
    else:
        wrapper_path = bin_dir / tool_name
        wrapper_path.write_text(f'#!{sys.executable}\n{script_body}', encoding='utf-8')
        wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IEXEC)


def _install_ruff(repo_root: Path) -> None:
    _write_fake_tool(
        repo_root,
        'ruff',
        (
            'import json, pathlib, sys\n'
            'args = sys.argv[1:]\n'
            "mode = args[0]\n"
            'target = pathlib.Path(args[-1])\n'
            "if mode == 'format':\n"
            "    target.write_text(\"def formatted() -> str:\\n    return 'formatted'\\n\", encoding='utf-8')\n"
            "    print(f'formatted {target}')\n"
            "    sys.exit(0)\n"
            "if '--fix' in args:\n"
            "    target.write_text(\"def fixed() -> str:\\n    return 'fixed'\\n\", encoding='utf-8')\n"
            "payload = [{\"code\": \"F401\", \"message\": \"warning\", \"location\": {\"row\": 1, \"column\": 1}, \"end_location\": {\"row\": 1, \"column\": 2}}]\n"
            'print(json.dumps(payload))\n'
            'sys.exit(1)\n'
        ),
    )


def test_quality_service_raises_when_ruff_is_missing(python_repository) -> None:
    service = PythonQualityService(python_repository, tool_resolver=_MissingToolResolver())

    with pytest.raises(ValueError, match='ruff was not found'):
        service.format_file('src/acme/core/repository.py')


def test_quality_service_format_file_returns_compact_result_with_delta(python_repository) -> None:
    target_file = python_repository.root / 'src' / 'acme' / 'core' / 'repository.py'
    target_file.write_text("def old() -> str:\n    return 'old'\n", encoding='utf-8')
    service = PythonQualityService(
        python_repository,
        tool_resolver=_FakeToolResolver(python_repository.root),
        ruff_runner=_FakeRuffRunner(),
        file_symbol_service=_FakeFileSymbolService([(_symbol('old', 1, 2),), (_symbol('format_repository_id', 1, 2),)]),
    )

    result = service.format_file('src/acme/core/repository.py')

    assert result.operation == 'format'
    assert result.tool == 'ruff'
    assert result.changed is True
    assert result.applied_fixes is True
    assert [item.name for item in result.entity_delta.added] == ['format_repository_id']
    assert [item.name for item in result.entity_delta.removed] == ['old']


def test_quality_service_lint_file_supports_fix_mode_and_diagnostics(python_repository) -> None:
    target_file = python_repository.root / 'src' / 'acme' / 'core' / 'repository.py'
    target_file.write_text("def build_repository_id( name: str ) -> str:\n    return name\n", encoding='utf-8')
    service = PythonQualityService(
        python_repository,
        tool_resolver=_FakeToolResolver(python_repository.root),
        ruff_runner=_FakeRuffRunner(),
        file_symbol_service=_FakeFileSymbolService([(_symbol('build_repository_id', 1, 2),), (_symbol('build_repository_id', 1, 2),)]),
    )

    result = service.lint_file('src/acme/core/repository.py', is_fix=True)

    assert result.operation == 'lint'
    assert result.tool == 'ruff'
    assert result.changed is True
    assert result.applied_fixes is True
    assert result.diagnostics[0].message == 'warning'


def test_quality_service_executes_real_stubbed_ruff(python_repository) -> None:
    _install_ruff(python_repository.root)
    target_file = python_repository.root / 'src' / 'acme' / 'core' / 'repository.py'
    target_file.write_text("def broken( ) -> str:\n    return 'bad'\n", encoding='utf-8')

    format_service = PythonQualityService(
        python_repository,
        file_symbol_service=_SequentialFileSymbolService([(_symbol('broken', 1, 2),), (_symbol('formatted', 1, 2),)]),
    )
    format_result = format_service.format_file('src/acme/core/repository.py')

    assert format_result.changed is True
    assert format_result.tool == 'ruff'
    assert format_result.applied_fixes is True
    assert 'formatted' in target_file.read_text(encoding='utf-8')

    lint_service = PythonQualityService(
        python_repository,
        file_symbol_service=_SequentialFileSymbolService([(_symbol('formatted', 1, 2),), (_symbol('fixed', 1, 2),)]),
    )
    lint_result = lint_service.lint_file('src/acme/core/repository.py', is_fix=True)

    assert lint_result.changed is True
    assert lint_result.tool == 'ruff'
    assert lint_result.applied_fixes is True
    assert lint_result.diagnostics[0].rule_id == 'F401'
    assert 'fixed' in target_file.read_text(encoding='utf-8')
