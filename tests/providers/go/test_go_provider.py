from __future__ import annotations

import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from suitcode.core.change_models import ChangeTarget
from suitcode.core.intelligence_models import FileRelationshipKind
from suitcode.core.repository import Repository
from suitcode.core.tests.models import RelatedTestTarget
from suitcode.core.workspace import Workspace
from suitcode.providers.go.implementation_service import GoImplementationAnchor, GoImplementationService
from suitcode.providers.provider_roles import ProviderRole


def test_go_provider_exposes_components_tests_and_actions(go_repository) -> None:
    assert go_repository.provider_ids == ('go',)
    assert go_repository.provider_roles['go'] == frozenset({ProviderRole.ARCHITECTURE, ProviderRole.CODE, ProviderRole.TEST})

    components = go_repository.arch.get_components()
    component_ids = {item.id for item in components}
    assert component_ids == {
        'component:go:example.com/acme/go-demo/cmd/app',
        'component:go:example.com/acme/go-demo/internal/service',
        'component:go:example.com/acme/go-demo/pkg/util',
    }

    tests = go_repository.tests.get_discovered_tests()
    assert [item.test_definition.id for item in tests] == ['test:go:example.com/acme/go-demo/internal/service']

    actions = go_repository.list_actions()
    action_ids = {item.id for item in actions}
    assert 'action:go:test:example.com/acme/go-demo/internal/service' in action_ids
    assert 'action:go:build:example.com/acme/go-demo/cmd/app' in action_ids


def test_go_related_tests_and_minimum_verified_change_set(go_repository) -> None:
    related = go_repository.tests.get_related_tests(RelatedTestTarget(repository_rel_path='internal/service/service.go'))
    assert [item.test_definition.id for item in related] == ['test:go:example.com/acme/go-demo/internal/service']

    minimum = go_repository.get_minimum_verified_change_set(ChangeTarget(repository_rel_path='internal/service/service.go'))
    assert [item.target.test_definition.id for item in minimum.tests] == ['test:go:example.com/acme/go-demo/internal/service']
    assert minimum.build_targets == tuple()


def test_go_file_relationships_are_projected_from_component_dependency_graph(go_repository) -> None:
    dependency_files = go_repository.code.get_file_relationships(
        'internal/service/service.go',
        relationship_kind=FileRelationshipKind.IMPORTS,
    )
    dependent_files = go_repository.code.get_file_relationships(
        'internal/service/service.go',
        relationship_kind=FileRelationshipKind.IMPORTED_BY,
    )

    assert [item.repository_rel_path for item in dependency_files] == ['pkg/util/util.go']
    assert [item.repository_rel_path for item in dependent_files] == ['cmd/app/main.go']
    assert all(item.provenance for item in dependency_files)
    assert all(item.provenance for item in dependent_files)


def test_go_runtime_capabilities_and_build_targets(go_repository) -> None:
    provider = go_repository.get_provider('go')
    code_caps = provider.get_code_runtime_capabilities()
    test_caps = provider.get_test_runtime_capabilities()
    action_caps = provider.get_action_runtime_capabilities()

    assert code_caps.structural_symbols is not None
    assert code_caps.structural_symbols.availability.value == 'available'
    assert code_caps.implementations.availability.value in {'available', 'degraded'}
    assert test_caps.discovery.availability.value == 'available'
    assert test_caps.execution.availability.value == 'available'
    assert action_caps.builds.availability.value == 'available'
    assert action_caps.runners.availability.value == 'unavailable'

    build_targets = go_repository.list_build_targets()
    assert [item.action_id for item in build_targets] == ['action:go:build:example.com/acme/go-demo/cmd/app']


def test_go_provider_loads_external_modules_lazily_and_reuses_baseline_analysis(
    go_repo_root: Path,
    monkeypatch,
) -> None:
    original_run = subprocess.run
    baseline_calls: list[tuple[str, ...]] = []
    external_calls: list[tuple[str, ...]] = []

    def _counting_run(argv, *args, **kwargs):
        argv_tuple = tuple(argv)
        if argv_tuple[:5] == ("go", "list", "-buildvcs=false", "-json", "./..."):
            baseline_calls.append(argv_tuple)
        if argv_tuple[:6] == ("go", "list", "-buildvcs=false", "-m", "-json", "all"):
            external_calls.append(argv_tuple)
        return original_run(argv, *args, **kwargs)

    monkeypatch.setattr("suitcode.providers.go.workspace_analyzer.subprocess.run", _counting_run)

    repository = Workspace(go_repo_root).repositories[0]

    assert repository.arch.get_package_managers()
    assert repository.arch.get_package_managers()
    assert len(baseline_calls) == 1
    assert len(external_calls) == 0

    assert isinstance(repository.arch.get_external_packages(), tuple)
    assert isinstance(repository.arch.get_external_packages(), tuple)
    assert len(baseline_calls) == 1
    assert len(external_calls) == 1


def test_go_provider_returns_tier_one_structural_symbols_without_gopls(go_provider) -> None:
    def _unexpected_semantic_call(*args, **kwargs):
        raise AssertionError("Tier 1 structural symbol lookup must not call gopls-backed symbol service")

    go_provider._file_symbol_service = type(
        "_UnexpectedFileSymbolService",
        (),
        {"list_file_symbols": _unexpected_semantic_call},
    )()

    symbols = go_provider.list_structural_symbols_in_file("internal/service/service.go")

    assert [item.name for item in symbols] == ["BuildMessage"]
    assert symbols[0].entity_kind == "function"
    assert symbols[0].provenance[0].source_kind.value == "syntax"
    assert symbols[0].provenance[0].source_tool == "go/parser"


def test_go_provider_exposes_interface_implementation_candidates(tmp_path: Path) -> None:
    repo_root = tmp_path / "go-impl"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "go.mod").write_text("module example.com/impldemo\n\ngo 1.26\n", encoding="utf-8")
    (repo_root / "internal" / "service").mkdir(parents=True)
    (repo_root / "internal" / "impl").mkdir(parents=True)
    (repo_root / "cmd" / "app").mkdir(parents=True)
    (repo_root / "internal" / "service" / "service.go").write_text(
        (
            "package service\n\n"
            "type Greeter interface {\n"
            "\tGreet(name string) string\n"
            "}\n\n"
            "type Service struct {\n"
            "\tgreeter Greeter\n"
            "}\n\n"
            "func New(greeter Greeter) Service {\n"
            "\treturn Service{greeter: greeter}\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (repo_root / "internal" / "impl" / "greeter.go").write_text(
        (
            "package impl\n\n"
            "type RealGreeter struct{}\n\n"
            "func (RealGreeter) Greet(name string) string {\n"
            "\treturn \"hello, \" + name\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (repo_root / "cmd" / "app" / "main.go").write_text(
        (
            "package main\n\n"
            "import (\n"
            "\t\"example.com/impldemo/internal/impl\"\n"
            "\t\"example.com/impldemo/internal/service\"\n"
            ")\n\n"
            "func main() {\n"
            "\t_ = service.New(impl.RealGreeter{})\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    repository = Workspace(repo_root).repositories[0]
    locations = repository.code.get_file_implementation_locations("internal/service/service.go")

    assert any(item.repository_rel_path == "internal/impl/greeter.go" for item in locations)


def test_go_implementation_service_reuses_one_lsp_session_per_file() -> None:
    class _FakeSession:
        def __init__(self) -> None:
            self.definition_calls = 0
            self.implementation_calls = 0

        def find_definition(self, repository_rel_path: str, line: int, column: int):
            self.definition_calls += 1
            return (("internal/contracts/contracts.go", 1, 3, 1, 10),)

        def list_file_symbols(self, repository_rel_path: str):
            return (
                SimpleNamespace(
                    line_start=1,
                    line_end=3,
                    column_start=1,
                    column_end=10,
                    kind="interface",
                ),
            )

        def find_implementations(self, repository_rel_path: str, line: int, column: int):
            self.implementation_calls += 1
            return (("internal/impl/greeter.go", 5, 5, 1, 20),)

    class _FakeSymbolService:
        def __init__(self) -> None:
            self.open_session_calls = 0
            self.session = _FakeSession()

        @contextmanager
        def open_session(self):
            self.open_session_calls += 1
            yield self.session

    service = GoImplementationService(
        repository_root=Path(r"C:\repo"),
        attachment_root=Path(r"C:\repo"),
        attachment_root_rel_path="",
        symbol_service=_FakeSymbolService(),
    )
    service._anchors_cache["internal/service/service.go"] = (
        GoImplementationAnchor("internal/service/service.go", 10, 5, "type_usage"),
        GoImplementationAnchor("internal/service/service.go", 15, 5, "type_usage"),
    )

    locations = service.get_file_implementation_locations("internal/service/service.go")
    second_locations = service.get_file_implementation_locations("internal/service/service.go")

    assert locations == (("internal/impl/greeter.go", 5, 5, 1, 20),)
    assert second_locations == locations
    assert service._symbol_service.open_session_calls == 1
    assert service._symbol_service.session.definition_calls == 2
    assert service._symbol_service.session.implementation_calls == 2


def test_mixed_npm_and_single_go_module_root_is_supported(tmp_path: Path, npm_fixture_root: Path) -> None:
    repo_root = tmp_path / 'npm-go'
    shutil.copytree(npm_fixture_root, repo_root)
    (repo_root / '.git').mkdir()

    workspace = Workspace(repo_root)
    repository = workspace.repositories[0]

    assert repository.provider_ids == ('go', 'npm', 'python')
    assert repository.supports_role(ProviderRole.ARCHITECTURE) is True
    go_components = [item.id for item in repository.arch.get_components() if item.id.startswith('component:go:')]
    assert go_components == ['component:go:native-addon']


def test_go_work_is_deferred_but_multi_module_roots_without_go_work_are_supported(tmp_path: Path) -> None:
    go_work_root = tmp_path / 'go-work'
    go_work_root.mkdir()
    (go_work_root / '.git').mkdir()
    (go_work_root / 'go.work').write_text('go 1.26\n', encoding='utf-8')
    assert Repository.support_for_path(go_work_root).provider_ids == tuple()

    multi_root = tmp_path / 'multi-go'
    (multi_root / '.git').mkdir(parents=True)
    (multi_root / 'a').mkdir()
    (multi_root / 'b').mkdir()
    (multi_root / 'a' / 'go.mod').write_text('module example.com/a\n\ngo 1.26\n', encoding='utf-8')
    (multi_root / 'a' / 'main.go').write_text('package main\nfunc main() {}\n', encoding='utf-8')
    (multi_root / 'b' / 'go.mod').write_text('module example.com/b\n\ngo 1.26\n', encoding='utf-8')
    (multi_root / 'b' / 'service.go').write_text('package b\nfunc Name() string { return "b" }\n', encoding='utf-8')

    support = Repository.support_for_path(multi_root)
    assert support.provider_ids == ('go',)

    repository = Workspace(multi_root).repositories[0]
    package_manager_ids = [item.id for item in repository.arch.get_package_managers() if item.id.startswith('pkgmgr:go:')]
    assert package_manager_ids == ['pkgmgr:go:a', 'pkgmgr:go:b']
    assert repository.get_file_owner('a/go.mod').owner.id == 'pkgmgr:go:a'
    assert repository.get_file_owner('b/go.mod').owner.id == 'pkgmgr:go:b'
    assert [item.action_id for item in repository.list_build_targets()] == ['action:go:build:example.com/a']


def test_real_multi_module_repo_support_if_available() -> None:
    repo_root = Path(r'C:\src\github.com\GreenFuze\MyGamesAnywhere\server')
    if not repo_root.exists():
        pytest.skip('local MyGamesAnywhere server repo is unavailable')

    support = Repository.support_for_path(repo_root)
    assert support.provider_ids == ('go', 'markdown', 'npm', 'openapi')

    repository = Workspace(repo_root).repositories[0]
    package_manager_ids = [item.id for item in repository.arch.get_package_managers() if item.id.startswith('pkgmgr:go:')]
    assert 'pkgmgr:go:root' in package_manager_ids
    assert any(item.startswith('pkgmgr:go:plugins/') for item in package_manager_ids)
    assert repository.list_actions()
