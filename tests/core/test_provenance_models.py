from __future__ import annotations

import pytest

from suitcode.core.intelligence_models import ComponentDependencyEdge, DependencyRef
from suitcode.core.models import Component, EntityInfo, ExternalPackage, FileInfo, PackageManager, Runner, TestDefinition as RawTestDefinition
from suitcode.core.models.graph_types import ComponentKind, ProgrammingLanguage
from suitcode.core.models import TestDefinition as CoreTestDefinition
from suitcode.core.models.graph_types import TestFramework as CoreTestFramework
from suitcode.core.provenance import ConfidenceMode, ProvenanceEntry, SourceKind
from suitcode.core.provenance_summary import (
    is_authoritative_provenance,
    merge_provenance_paths,
    preferred_source_kind,
    preferred_source_tool,
    summarize_related_provenance,
)
from suitcode.core.provenance_builders import heuristic_provenance, lsp_delta_provenance, lsp_provenance, manifest_node_provenance, manifest_provenance, ownership_provenance, quality_tool_provenance
from suitcode.core.provenance_builders import lsp_location_provenance
from suitcode.core.code.models import CodeLocation
from suitcode.providers.quality_models import QualityDiagnostic, QualityEntityDelta, QualityFileResult
from suitcode.core.tests.models import DiscoveredTestDefinition


def test_provenance_entry_rejects_empty_summary() -> None:
    with pytest.raises(ValueError):
        ProvenanceEntry(
            confidence_mode=ConfidenceMode.AUTHORITATIVE,
            source_kind=SourceKind.MANIFEST,
            evidence_summary="  ",
        )


def test_provenance_entry_normalizes_repository_relative_paths() -> None:
    entry = manifest_provenance(
        evidence_summary="from manifest",
        evidence_paths=("src\\pkg\\__init__.py",),
    )

    assert entry.evidence_paths == ("src/pkg/__init__.py",)


def test_provenance_summary_helpers_merge_and_prioritize_sources() -> None:
    entries = (
        heuristic_provenance(
            evidence_summary="heuristic test fallback",
            evidence_paths=("tests/test_example.py",),
        ),
        lsp_provenance(
            source_tool="basedpyright",
            evidence_summary="lsp symbols",
            evidence_paths=("src/example.py", "tests/test_example.py"),
        ),
        manifest_provenance(
            evidence_summary="manifest metadata",
            evidence_paths=("pyproject.toml",),
        ),
    )

    assert merge_provenance_paths(entries) == ("tests/test_example.py", "src/example.py", "pyproject.toml")
    assert is_authoritative_provenance(entries) is True
    assert preferred_source_kind(entries) == SourceKind.LSP
    assert preferred_source_tool(entries) == "basedpyright"


def test_summarize_related_provenance_fails_on_empty_input() -> None:
    with pytest.raises(ValueError):
        summarize_related_provenance(tuple(), "summary")


def test_discovered_test_definition_rejects_non_test_provenance() -> None:
    with pytest.raises(ValueError):
        DiscoveredTestDefinition(
            test_definition=CoreTestDefinition(
                id="test:x",
                name="x",
                framework=CoreTestFramework.OTHER,
                provenance=(
                    heuristic_provenance(
                        evidence_summary="derived from test fixture heuristics",
                        evidence_paths=("tests/example.test.ts",),
                    ),
                ),
            ),
            provenance=(
                manifest_provenance(
                    evidence_summary="derived from package manifest metadata",
                    evidence_paths=("package.json",),
                ),
            ),
        )


def test_dependency_ref_rejects_lsp_provenance() -> None:
    with pytest.raises(ValueError):
        DependencyRef(
            target_id="component:x",
            target_kind="component",
            dependency_scope="runtime",
            provenance=(
                ProvenanceEntry(
                    confidence_mode=ConfidenceMode.AUTHORITATIVE,
                    source_kind=SourceKind.LSP,
                    source_tool="basedpyright",
                    evidence_summary="from lsp",
                    evidence_paths=("src/x.py",),
                ),
            ),
        )


def test_component_dependency_edge_rejects_lsp_provenance() -> None:
    with pytest.raises(ValueError):
        ComponentDependencyEdge(
            source_component_id="component:x",
            target_id="component:y",
            target_kind="component",
            dependency_scope="runtime",
            provenance=(
                ProvenanceEntry(
                    confidence_mode=ConfidenceMode.AUTHORITATIVE,
                    source_kind=SourceKind.LSP,
                    source_tool="basedpyright",
                    evidence_summary="from lsp",
                    evidence_paths=("src/x.py",),
                ),
            ),
        )


def test_raw_nodes_require_provenance() -> None:
    with pytest.raises(ValueError):
        Component(
            id="component:x",
            name="x",
            component_kind=ComponentKind.PACKAGE,
            language=ProgrammingLanguage.PYTHON,
        )

    with pytest.raises(ValueError):
        FileInfo(
            id="file:src/x.py",
            name="src/x.py",
            repository_rel_path="src/x.py",
            owner_id="component:x",
        )

    with pytest.raises(ValueError):
        EntityInfo(
            id="entity:src/x.py:function:f:1-1",
            name="f",
            repository_rel_path="src/x.py",
            entity_kind="function",
        )


def test_entity_provenance_requires_lsp() -> None:
    with pytest.raises(ValueError):
        EntityInfo(
            id="entity:src/x.py:function:f:1-1",
            name="f",
            repository_rel_path="src/x.py",
            entity_kind="function",
            provenance=(
                ownership_provenance(
                    evidence_summary="assigned by ownership fixture",
                    evidence_paths=("src/x.py",),
                ),
            ),
        )


def test_external_package_provenance_rejects_lsp() -> None:
    with pytest.raises(ValueError):
        ExternalPackage(
            id="external:x",
            name="x",
            provenance=(
                lsp_provenance(
                    source_tool="basedpyright",
                    evidence_summary="discovered from lsp",
                    evidence_paths=("src/x.py",),
                ),
            ),
        )


def test_runner_provenance_rejects_ownership_only() -> None:
    with pytest.raises(ValueError):
        Runner(
            id="runner:x",
            name="x",
            argv=("x",),
            provenance=(
                ownership_provenance(
                    evidence_summary="assigned by ownership fixture",
                    evidence_paths=("src/x.py",),
                ),
            ),
        )


def test_public_raw_nodes_accept_valid_provenance() -> None:
    component = Component(
        id="component:x",
        name="x",
        component_kind=ComponentKind.PACKAGE,
        language=ProgrammingLanguage.PYTHON,
        provenance=(
            manifest_provenance(
                evidence_summary="derived from pyproject metadata",
                evidence_paths=("pyproject.toml",),
            ),
        ),
    )
    package_manager = PackageManager(
        id="pkgmgr:python:root",
        name="python",
        manager="python",
        provenance=(
            manifest_node_provenance(
                evidence_summary="derived from project package-management metadata",
                evidence_paths=("pyproject.toml",),
            ),
        ),
    )
    test_definition = RawTestDefinition(
        id="test:x",
        name="x",
        framework=CoreTestFramework.OTHER,
        provenance=(
            heuristic_provenance(
                evidence_summary="derived from test fixture heuristics",
                evidence_paths=("tests/test_x.py",),
            ),
        ),
    )

    assert component.provenance
    assert package_manager.provenance
    assert test_definition.provenance


def test_quality_models_require_shared_provenance() -> None:
    with pytest.raises(ValueError):
        QualityDiagnostic(tool="ruff", severity="warning", message="issue", provenance=tuple())

    with pytest.raises(ValueError):
        QualityEntityDelta(provenance=tuple())

    with pytest.raises(ValueError):
        QualityFileResult(
            repository_rel_path="src/x.py",
            tool="ruff",
            operation="lint",
            changed=False,
            success=True,
            applied_fixes=False,
            content_sha_before="before",
            content_sha_after="after",
            entity_delta=QualityEntityDelta(
                provenance=(
                    lsp_delta_provenance(
                        source_tool="basedpyright",
                        evidence_summary="delta from lsp",
                        evidence_paths=("src/x.py",),
                    ),
                ),
            ),
            provenance=tuple(),
        )


def test_quality_models_reject_missing_required_quality_or_lsp_provenance() -> None:
    with pytest.raises(ValueError):
        QualityDiagnostic(
            tool="ruff",
            severity="warning",
            message="issue",
            provenance=(
                lsp_delta_provenance(
                    source_tool="basedpyright",
                    evidence_summary="wrong provenance kind",
                    evidence_paths=("src/x.py",),
                ),
            ),
        )


def test_code_location_requires_lsp_provenance() -> None:
    with pytest.raises(ValueError, match="CodeLocation.provenance must not be empty"):
        CodeLocation(
            repository_rel_path="src/example.py",
            line_start=1,
            column_start=1,
            provenance=tuple(),
        )

    with pytest.raises(ValueError, match="CodeLocation must include lsp provenance"):
        CodeLocation(
            repository_rel_path="src/example.py",
            line_start=1,
            column_start=1,
            provenance=(
                ownership_provenance(
                    evidence_summary="ownership only",
                    evidence_paths=("src/example.py",),
                ),
            ),
        )

    location = CodeLocation(
        repository_rel_path="src/example.py",
        line_start=1,
        line_end=2,
        column_start=1,
        column_end=4,
        provenance=(
            lsp_location_provenance(
                source_tool="basedpyright",
                repository_rel_path="src/example.py",
                operation="definition",
            ),
        ),
    )

    assert location.provenance[0].source_kind.value == "lsp"

    with pytest.raises(ValueError):
        QualityEntityDelta(
            provenance=(
                quality_tool_provenance(
                    source_tool="ruff",
                    evidence_summary="wrong provenance kind",
                    evidence_paths=("src/x.py",),
                ),
            ),
        )

    with pytest.raises(ValueError):
        QualityFileResult(
            repository_rel_path="src/x.py",
            tool="ruff",
            operation="lint",
            changed=False,
            success=True,
            applied_fixes=False,
            diagnostics=(
                QualityDiagnostic(
                    tool="ruff",
                    severity="warning",
                    message="issue",
                    provenance=(
                        quality_tool_provenance(
                            source_tool="ruff",
                            evidence_summary="diagnostic",
                            evidence_paths=("src/x.py",),
                        ),
                    ),
                ),
            ),
            entity_delta=QualityEntityDelta(
                provenance=(
                    lsp_delta_provenance(
                        source_tool="basedpyright",
                        evidence_summary="delta from lsp",
                        evidence_paths=("src/x.py",),
                    ),
                ),
            ),
            content_sha_before="before",
            content_sha_after="after",
            provenance=(
                quality_tool_provenance(
                    source_tool="ruff",
                    evidence_summary="missing lsp provenance",
                    evidence_paths=("src/x.py",),
                ),
            ),
        )
