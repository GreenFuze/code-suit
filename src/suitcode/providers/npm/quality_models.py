from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol


@dataclass(frozen=True)
class NpmResolvedTool:
    tool: str
    executable_path: Path
    config_path: Path


@dataclass(frozen=True)
class NpmQualityDiagnostic:
    tool: str
    severity: str
    message: str
    line_start: int | None = None
    line_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    rule_id: str | None = None


@dataclass(frozen=True)
class NpmQualityEntityDelta:
    added: tuple[NpmWorkspaceSymbol, ...] = field(default_factory=tuple)
    removed: tuple[NpmWorkspaceSymbol, ...] = field(default_factory=tuple)
    updated: tuple[NpmWorkspaceSymbol, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NpmQualityOperationResult:
    repository_rel_path: str
    tool: str
    operation: str
    changed: bool
    success: bool
    message: str | None
    diagnostics: tuple[NpmQualityDiagnostic, ...]
    entity_delta: NpmQualityEntityDelta
    applied_fixes: bool
    content_sha_before: str
    content_sha_after: str


@dataclass(frozen=True)
class NpmLintRunResult:
    diagnostics: tuple[NpmQualityDiagnostic, ...]
    message: str | None = None


@dataclass(frozen=True)
class NpmFormatRunResult:
    message: str | None = None
