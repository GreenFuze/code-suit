from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from suitcode.core.change_models import ChangeTarget
from suitcode.core.repository import Repository
from suitcode.core.tests.models import RelatedTestTarget
from suitcode.core.workspace import Workspace
from suitcode.providers.provider_roles import ProviderRole


def test_go_provider_exposes_components_tests_and_actions(go_repository) -> None:
    assert go_repository.provider_ids == ('go',)
    assert go_repository.provider_roles['go'] == frozenset({ProviderRole.ARCHITECTURE, ProviderRole.TEST})

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


def test_go_runtime_capabilities_and_build_targets(go_repository) -> None:
    provider = go_repository.get_provider('go')
    test_caps = provider.get_test_runtime_capabilities()
    action_caps = provider.get_action_runtime_capabilities()

    assert test_caps.discovery.availability.value == 'available'
    assert test_caps.execution.availability.value == 'available'
    assert action_caps.builds.availability.value == 'available'
    assert action_caps.runners.availability.value == 'unavailable'

    build_targets = go_repository.list_build_targets()
    assert [item.action_id for item in build_targets] == ['action:go:build:example.com/acme/go-demo/cmd/app']


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
    assert support.provider_ids == ('go',)

    repository = Workspace(repo_root).repositories[0]
    package_manager_ids = [item.id for item in repository.arch.get_package_managers() if item.id.startswith('pkgmgr:go:')]
    assert 'pkgmgr:go:root' in package_manager_ids
    assert any(item.startswith('pkgmgr:go:plugins/') for item in package_manager_ids)
    assert repository.list_actions()
