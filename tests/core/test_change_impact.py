from __future__ import annotations

from suitcode.core.change_models import ChangeTarget
from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import (
    FileRelationshipKind,
    FileRelationshipRef,
    InvariantAccessKind,
    InvariantFindingKind,
    InvariantFindingRef,
    RenderEdgeKind,
    RenderEdgeRef,
    StaticFlowEdgeKind,
    StaticFlowEdgeRef,
)
from suitcode.core.provenance_builders import dependency_graph_provenance, lsp_location_provenance
from suitcode.core.workspace import Workspace


def _make_mixed_go_npm_repo(repo_root):
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "server" / "internal" / "db").mkdir(parents=True)
    (repo_root / "server" / "go.mod").write_text(
        "module example.com/mixed/server\n\ngo 1.22\n",
        encoding="utf-8",
    )
    (repo_root / "server" / "internal" / "db" / "repo.go").write_text(
        "package db\n\nfunc Name() string { return \"db\" }\n",
        encoding="utf-8",
    )
    (repo_root / "server" / "internal" / "db" / "repo_test.go").write_text(
        "package db\n\nimport \"testing\"\n\nfunc TestName(t *testing.T) { _ = Name() }\n",
        encoding="utf-8",
    )
    (repo_root / "server" / "frontend" / "src").mkdir(parents=True)
    (repo_root / "server" / "frontend" / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "server" / "frontend" / "src" / "index.tsx").write_text(
        "export const App = () => null;\n",
        encoding="utf-8",
    )
    return repo_root


def test_change_impact_for_npm_file_target(npm_repo_root) -> None:
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
            return (
                ("packages/core/src/index.ts", 1, 13, 1, 2),
                ("packages/utils/src/index.ts", 7, 9, 1, 2),
            )

    class _FakeRelationshipService:
        def get_file_relationships(self, repository_rel_path: str) -> tuple[FileRelationshipRef, ...]:
            assert repository_rel_path == "packages/core/src/index.ts"
            return (
                FileRelationshipRef(
                    repository_rel_path="packages/utils/src/index.ts",
                    relationship_kind=FileRelationshipKind.IMPORTED_BY,
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="resolved import edge",
                            evidence_paths=("packages/core/src/index.ts", "packages/utils/src/index.ts"),
                        ),
                    ),
                ),
            )

    class _FakeRenderEdgeService:
        def get_file_render_edges(self, repository_rel_path: str) -> tuple[RenderEdgeRef, ...]:
            assert repository_rel_path == "packages/core/src/index.ts"
            return (
                RenderEdgeRef(
                    repository_rel_path="packages/ui/src/Button.tsx",
                    relationship_kind=RenderEdgeKind.RENDERS,
                    line_start=12,
                    column_start=5,
                    prop_names=("label",),
                    has_spread_props=False,
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="resolved JSX render edge",
                            evidence_paths=("packages/core/src/index.ts", "packages/ui/src/Button.tsx"),
                        ),
                    ),
                ),
            )

    class _FakeStaticAnalysisService:
        def get_file_analysis(self, repository_rel_path: str):
            assert repository_rel_path == "packages/core/src/index.ts"
            findings = (
                InvariantFindingRef(
                    repository_rel_path="packages/core/src/index.ts",
                    finding_kind=InvariantFindingKind.MAYBE_MISSING_FIELD_ACCESS,
                    access_kind=InvariantAccessKind.METHOD_CALL,
                    line_start=15,
                    column_start=7,
                    field_name="status",
                    subject_label="integration",
                    declared_type="string | undefined",
                    producer_site_count=0,
                    producer_sites_preview=tuple(),
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="deterministic TS analysis found maybe-missing field access",
                            evidence_paths=("packages/core/src/index.ts",),
                        ),
                    ),
                ),
            )
            flows = (
                StaticFlowEdgeRef(
                    repository_rel_path="packages/core/src/index.ts",
                    edge_kind=StaticFlowEdgeKind.PRODUCES_VALUE_FOR,
                    line_start=18,
                    column_start=5,
                    source_label="toStateMap",
                    target_label="setState",
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="deterministic TS analysis found local flow edge",
                            evidence_paths=("packages/core/src/index.ts",),
                        ),
                    ),
                ),
            )
            return findings, flows

    provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[attr-defined]
    provider._file_relationship_service = _FakeRelationshipService()  # type: ignore[attr-defined]
    provider._render_edge_service = _FakeRenderEdgeService()  # type: ignore[attr-defined]
    provider._static_analysis_service = _FakeStaticAnalysisService()  # type: ignore[attr-defined]

    impact = repository.analyze_change(ChangeTarget(repository_rel_path="packages/core/src/index.ts"))

    assert impact.target_kind == "file"
    assert impact.owner.id == "component:npm:@monorepo/core"
    assert impact.primary_component is not None
    assert impact.primary_component.id == "component:npm:@monorepo/core"
    assert impact.component_context is not None
    assert impact.dependency_files == tuple()
    assert [item.repository_rel_path for item in impact.dependent_files] == ["packages/utils/src/index.ts"]
    assert [item.repository_rel_path for item in impact.render_children] == ["packages/ui/src/Button.tsx"]
    assert impact.render_children[0].prop_names == ("label",)
    assert impact.render_parents == tuple()
    assert [item.field_name for item in impact.invariant_findings] == ["status"]
    assert [item.target_label for item in impact.local_flow_edges] == ["setState"]
    assert any(component.id == "component:npm:@monorepo/utils" for component in impact.dependent_components)
    assert any(test.related_test.test_definition.id == "test:npm:@monorepo/core" for test in impact.related_tests)
    assert impact.quality_gates
    assert impact.evidence.total_edges >= 1
    assert impact.evidence.counts_by_kind["target_owner"] == 1
    assert impact.evidence.edges_preview
    assert impact.provenance


def test_change_impact_for_npm_owner_target(npm_repo_root) -> None:
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

    impact = repository.analyze_change(ChangeTarget(owner_id="component:npm:@monorepo/core"))

    assert impact.target_kind == "owner"
    assert impact.owner.id == "component:npm:@monorepo/core"
    assert impact.file_context is None
    assert impact.symbol_context is None
    assert impact.component_context is not None
    assert impact.evidence.counts_by_kind["target_owner"] == 1
    assert isinstance(impact.related_runners, tuple)


def test_change_impact_for_python_symbol_target(python_repo_root) -> None:
    repository = Workspace(python_repo_root).repositories[0]
    provider = repository.get_provider("python")

    class _FakeFileSymbolService:
        def list_file_symbols(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
            return (
                type(
                    "FakeSymbol",
                    (),
                    {
                        "name": "RepositoryManager",
                        "kind": "class",
                        "repository_rel_path": "src/acme/core/repository.py",
                        "line_start": 1,
                        "line_end": 7,
                        "column_start": 1,
                        "column_end": 2,
                        "container_name": None,
                        "signature": "class RepositoryManager",
                    },
                )(),
            )

        def find_definition(self, repository_rel_path: str, line: int, column: int):
            return (("src/acme/core/repository.py", 1, 7, 1, 2),)

        def find_references(self, repository_rel_path: str, line: int, column: int, include_definition: bool = False):
            return (("src/acme/core/repository.py", 1, 7, 1, 2),)

    provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[attr-defined]

    impact = repository.analyze_change(
        ChangeTarget(symbol_id="entity:src/acme/core/repository.py:class:RepositoryManager:1-7")
    )

    assert impact.target_kind == "symbol"
    assert impact.symbol_context is not None
    assert impact.owner.id == "component:python:acme"
    assert impact.primary_component is not None
    assert impact.primary_component.id == "component:python:acme"
    assert impact.dependent_components == tuple()
    assert impact.related_tests
    assert impact.quality_gates
    assert impact.evidence.total_edges >= 1
    assert impact.evidence.counts_by_kind["target_owner"] == 1
    assert impact.provenance


def test_change_impact_rejects_unknown_target(npm_repo_root) -> None:
    repository = Workspace(npm_repo_root).repositories[0]

    try:
        repository.analyze_change(ChangeTarget(owner_id="missing"))
    except ValueError as exc:
        assert "unknown owner id" in str(exc)
    else:
        raise AssertionError("expected analyze_change to fail for unknown owner")


def test_change_impact_routes_quality_gates_to_owning_provider_in_mixed_repo(tmp_path) -> None:
    repository = Workspace(_make_mixed_go_npm_repo(tmp_path / "mixed")).repositories[0]

    impact = repository.analyze_change(ChangeTarget(repository_rel_path="server/internal/db/repo.go"))

    assert impact.owner.id == "component:go:example.com/mixed/server/internal/db"
    assert [item.related_test.test_definition.id for item in impact.related_tests] == [
        "test:go:example.com/mixed/server/internal/db"
    ]
    assert impact.quality_gates == tuple()


def test_change_impact_dedupes_implementation_provenance_paths(go_repository) -> None:
    class _FakeCode:
        def __init__(self, wrapped) -> None:
            self._wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def get_file_implementation_locations(self, repository_rel_path: str):
            provenance = (lsp_location_provenance("gopls", "cmd/app/main.go", "implementation"),)
            return (
                CodeLocation(
                    repository_rel_path="cmd/app/main.go",
                    line_start=5,
                    line_end=5,
                    column_start=1,
                    column_end=10,
                    provenance=provenance,
                ),
                CodeLocation(
                    repository_rel_path="cmd/app/main.go",
                    line_start=8,
                    line_end=8,
                    column_start=1,
                    column_end=10,
                    provenance=provenance,
                ),
            )

    repository = go_repository
    repository._code = _FakeCode(repository.code)

    impact = repository.analyze_change(ChangeTarget(repository_rel_path="internal/service/service.go"))

    implementation_provenance = [
        item
        for item in impact.provenance
        if item.source_kind.value == "lsp"
        and "implementation candidate" in item.evidence_summary
    ]
    assert len(implementation_provenance) == 1
    assert implementation_provenance[0].evidence_paths == (
        "internal/service/service.go",
        "cmd/app/main.go",
    )
