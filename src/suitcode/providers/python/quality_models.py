from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol


@dataclass(frozen=True)
class PythonResolvedTool:
    tool: str
    executable_path: Path


@dataclass(frozen=True)
class PythonQualityDiagnostic:
    tool: str
    severity: str
    message: str
    line_start: int | None = None
    line_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    rule_id: str | None = None


@dataclass(frozen=True)
class PythonQualityEntityDelta:
    added: tuple[PythonWorkspaceSymbol, ...] = field(default_factory=tuple)
    removed: tuple[PythonWorkspaceSymbol, ...] = field(default_factory=tuple)
    updated: tuple[PythonWorkspaceSymbol, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PythonQualityOperationResult:
    repository_rel_path: str
    tool: str
    operation: str
    changed: bool
    success: bool
    message: str | None
    diagnostics: tuple[PythonQualityDiagnostic, ...]
    entity_delta: PythonQualityEntityDelta
    applied_fixes: bool
    content_sha_before: str
    content_sha_after: str


@dataclass(frozen=True)
class PythonLintRunResult:
    diagnostics: tuple[PythonQualityDiagnostic, ...]
    message: str | None = None


@dataclass(frozen=True)
class PythonFormatRunResult:
    message: str | None = None
