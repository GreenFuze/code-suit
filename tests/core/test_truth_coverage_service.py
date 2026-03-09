from __future__ import annotations

import pytest

from suitcode.core.change_models import ChangeTarget
from suitcode.core.truth_coverage_models import (
    TruthAvailability,
    TruthCoverageByDomain,
    TruthCoverageSummary,
)
from suitcode.core.truth_coverage_service import TruthCoverageService
from suitcode.core.workspace import Workspace
from suitcode.providers.runtime_capability_models import (
    CodeRuntimeCapabilities,
    QualityRuntimeCapabilities,
    RuntimeCapability,
    RuntimeCapabilityAvailability,
)
from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance


def _runtime_capability(capability_id: str, availability: str, source_kind: str, source_tool: str, reason: str | None = None):
    return RuntimeCapability(
        capability_id=capability_id,
        availability=RuntimeCapabilityAvailability(availability),
        source_kind=SourceKind(source_kind),
        source_tool=source_tool,
        reason=reason,
        provenance=(
            derived_summary_provenance(
                source_kind=SourceKind(source_kind),
                source_tool=source_tool,
                evidence_summary=reason or capability_id,
                evidence_paths=tuple(),
            ),
        ),
    )


def test_truth_coverage_model_requires_domain_consistency() -> None:
    with pytest.raises(ValueError):
        TruthCoverageByDomain(
            domain="architecture",
            total_entities=1,
            authoritative_count=1,
            derived_count=0,
            heuristic_count=0,
            unavailable_count=1,
            availability="available",
            source_kind_mix={"manifest": 1},
            source_tool_mix={},
            action_capabilities={},
        )


def test_truth_coverage_summary_requires_all_domains(npm_repo_root) -> None:
    repository = Workspace(npm_repo_root).repositories[0]
    provenance = repository.get_truth_coverage().provenance
    with pytest.raises(ValueError):
        TruthCoverageSummary(
            scope_kind="repository",
            scope_id=repository.id,
            domains=tuple(),
            overall_authoritative_count=0,
            overall_derived_count=0,
            overall_heuristic_count=0,
            overall_unavailable_count=0,
            overall_availability="unavailable",
            provenance=provenance,
        )


def test_repository_truth_coverage_for_npm(monkeypatch, npm_repo_root) -> None:
    repository = Workspace(npm_repo_root).repositories[0]
    provider = repository.get_provider("npm")
    monkeypatch.setattr(
        provider,
        "get_code_runtime_capabilities",
        lambda: CodeRuntimeCapabilities(
            symbol_search=_runtime_capability("npm.code.symbol_search", "available", "lsp", "typescript-language-server"),
            symbols_in_file=_runtime_capability("npm.code.symbols_in_file", "available", "lsp", "typescript-language-server"),
            definitions=_runtime_capability("npm.code.definitions", "available", "lsp", "typescript-language-server"),
            references=_runtime_capability("npm.code.references", "available", "lsp", "typescript-language-server"),
        ),
    )
    monkeypatch.setattr(
        provider,
        "get_quality_runtime_capabilities",
        lambda repository_rel_paths=None: QualityRuntimeCapabilities(
            lint=_runtime_capability("npm.quality.lint", "available", "quality_tool", "eslint"),
            format=_runtime_capability("npm.quality.format", "available", "quality_tool", "prettier"),
        ),
    )

    truth = repository.get_truth_coverage()
    domains = {item.domain.value: item for item in truth.domains}

    assert truth.scope_kind == "repository"
    assert domains["architecture"].availability == TruthAvailability.AVAILABLE
    assert domains["code"].availability == TruthAvailability.AVAILABLE
    assert domains["tests"].availability in {TruthAvailability.AVAILABLE, TruthAvailability.DEGRADED}
    assert domains["quality"].execution_available is True
    assert domains["actions"].action_capabilities == {
        "tests": True,
        "builds": True,
        "runners": True,
    }


def test_repository_truth_coverage_degrades_when_code_runtime_missing(monkeypatch, python_repo_root) -> None:
    repository = Workspace(python_repo_root).repositories[0]
    provider = repository.get_provider("python")
    monkeypatch.setattr(
        provider,
        "get_code_runtime_capabilities",
        lambda: CodeRuntimeCapabilities(
            symbol_search=_runtime_capability("python.code.symbol_search", "degraded", "lsp", "basedpyright", "basedpyright is unavailable"),
            symbols_in_file=_runtime_capability("python.code.symbols_in_file", "degraded", "lsp", "basedpyright", "basedpyright is unavailable"),
            definitions=_runtime_capability("python.code.definitions", "degraded", "lsp", "basedpyright", "basedpyright is unavailable"),
            references=_runtime_capability("python.code.references", "degraded", "lsp", "basedpyright", "basedpyright is unavailable"),
        ),
    )
    monkeypatch.setattr(
        provider,
        "get_quality_runtime_capabilities",
        lambda repository_rel_paths=None: QualityRuntimeCapabilities(
            lint=_runtime_capability("python.quality.lint", "available", "quality_tool", "ruff"),
            format=_runtime_capability("python.quality.format", "available", "quality_tool", "ruff"),
        ),
    )

    truth = repository.get_truth_coverage()
    code_domain = next(item for item in truth.domains if item.domain.value == "code")

    assert code_domain.availability == TruthAvailability.DEGRADED
    assert code_domain.unavailable_count == 4
    assert code_domain.degraded_reason == "basedpyright is unavailable"


def test_change_truth_coverage_is_attached_to_change_analysis(monkeypatch, npm_repo_root) -> None:
    repository = Workspace(npm_repo_root).repositories[0]
    provider = repository.get_provider("npm")

    class _FakeFileSymbolService:
        def list_file_symbols(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
            return (
                type(
                    "FakeSymbol",
                    (),
                    {
                        "name": "Core",
                        "kind": "class",
                        "repository_rel_path": "packages/core/src/index.ts",
                        "line_start": 1,
                        "line_end": 13,
                        "column_start": 1,
                        "column_end": 2,
                        "container_name": None,
                        "signature": "class Core",
                    },
                )(),
            )

        def find_definition(self, repository_rel_path: str, line: int, column: int):
            return (("packages/core/src/index.ts", 1, 13, 1, 2),)

        def find_references(self, repository_rel_path: str, line: int, column: int, include_definition: bool = False):
            return (("packages/core/src/index.ts", 1, 13, 1, 2),)

    provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        provider,
        "get_code_runtime_capabilities",
        lambda: CodeRuntimeCapabilities(
            symbol_search=_runtime_capability("npm.code.symbol_search", "available", "lsp", "typescript-language-server"),
            symbols_in_file=_runtime_capability("npm.code.symbols_in_file", "available", "lsp", "typescript-language-server"),
            definitions=_runtime_capability("npm.code.definitions", "available", "lsp", "typescript-language-server"),
            references=_runtime_capability("npm.code.references", "available", "lsp", "typescript-language-server"),
        ),
    )
    monkeypatch.setattr(
        provider,
        "get_quality_runtime_capabilities",
        lambda repository_rel_paths=None: QualityRuntimeCapabilities(
            lint=_runtime_capability("npm.quality.lint", "available", "quality_tool", "eslint"),
            format=_runtime_capability("npm.quality.format", "available", "quality_tool", "prettier"),
        ),
    )

    impact = repository.analyze_change(ChangeTarget(repository_rel_path="packages/core/src/index.ts"))

    assert impact.truth_coverage.scope_kind == "change"
    domains = {item.domain.value: item for item in impact.truth_coverage.domains}
    assert domains["architecture"].availability == TruthAvailability.AVAILABLE
    assert domains["code"].availability == TruthAvailability.AVAILABLE
    assert domains["tests"].total_entities >= 1


def test_repository_truth_coverage_is_cached(monkeypatch, python_repo_root) -> None:
    repository = Workspace(python_repo_root).repositories[0]
    service = repository._build_truth_coverage_service()  # type: ignore[attr-defined]
    calls = {"count": 0}
    original = service.repository_truth_coverage

    def _counting():
        calls["count"] += 1
        return original()

    monkeypatch.setattr(service, "repository_truth_coverage", _counting)

    first = repository.get_truth_coverage()
    second = repository.get_truth_coverage()

    assert first == second
    assert calls["count"] == 1
