from __future__ import annotations

from suitcode.core.change_models import ChangeTarget
from suitcode.core.workspace import Workspace


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

    provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[attr-defined]

    impact = repository.analyze_change(ChangeTarget(repository_rel_path="packages/core/src/index.ts"))

    assert impact.target_kind == "file"
    assert impact.owner.id == "component:npm:@monorepo/core"
    assert impact.primary_component is not None
    assert impact.primary_component.id == "component:npm:@monorepo/core"
    assert impact.component_context is not None
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
