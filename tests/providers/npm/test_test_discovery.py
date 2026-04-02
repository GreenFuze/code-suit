from __future__ import annotations

from pathlib import Path

from suitcode.core.tests.models import TestDiscoveryMethod
from suitcode.providers.npm.test_discovery import NpmTestDiscoverer
from suitcode.providers.shared.package_json.workspace import PackageJsonWorkspaceLoader


class _FakeJestRunner:
    def __init__(self, files: tuple[str, ...]) -> None:
        self._files = files

    def list_test_files(self, package_root: str) -> tuple[str, ...]:
        return self._files


class _FakeVitestRunner:
    def __init__(self, files: tuple[str, ...]) -> None:
        self._files = files

    def list_test_files(self, package_root: str) -> tuple[str, ...]:
        return self._files


class _FailingJestResolver:
    def resolve_jest(self) -> Path:
        raise ValueError('jest missing')

    def resolve_vitest(self) -> Path:
        raise ValueError('vitest missing')


class _StaticJestResolver:
    def __init__(self, executable: Path) -> None:
        self._executable = executable

    def resolve_jest(self) -> Path:
        return self._executable

    def resolve_vitest(self) -> Path:
        return self._executable


class _StaticVitestResolver:
    def __init__(self, executable: Path) -> None:
        self._executable = executable

    def resolve_jest(self) -> Path:
        return self._executable

    def resolve_vitest(self) -> Path:
        return self._executable


def test_npm_test_discovery_uses_authoritative_jest_when_available(npm_fixture_root: Path) -> None:
    workspace = PackageJsonWorkspaceLoader().load(npm_fixture_root)
    package = next(item for item in workspace.packages if item.manifest.name == '@monorepo/core')
    discoverer = NpmTestDiscoverer(
        tool_resolver_factory=lambda repository_root: _StaticJestResolver(repository_root / 'node_modules' / '.bin' / 'jest'),
        jest_runner_factory=lambda repository_root, executable: _FakeJestRunner(('packages/core/src/index.test.ts',)),
    )

    analysis = discoverer.discover(package)

    assert analysis is not None
    assert analysis.discovery_method == TestDiscoveryMethod.AUTHORITATIVE_JEST_LIST_TESTS
    assert analysis.discovery_tool == 'jest'
    assert analysis.test_files == ('packages/core/src/index.test.ts',)
    assert analysis.evidence_paths == ('packages/core/package.json', 'packages/core/src/index.test.ts')


def test_npm_test_discovery_falls_back_to_heuristic_when_jest_is_unavailable(npm_fixture_root: Path) -> None:
    workspace = PackageJsonWorkspaceLoader().load(npm_fixture_root)
    package = next(item for item in workspace.packages if item.manifest.name == '@monorepo/core')
    discoverer = NpmTestDiscoverer(
        tool_resolver_factory=lambda repository_root: _FailingJestResolver(),
    )

    analysis = discoverer.discover(package)

    assert analysis is not None
    assert analysis.discovery_method == TestDiscoveryMethod.HEURISTIC_MANIFEST_GLOB
    assert analysis.discovery_tool is None
    assert 'packages/core/src/index.test.ts' in analysis.test_files
    assert analysis.evidence_paths[0] == 'packages/core/package.json'


def test_npm_test_discovery_uses_authoritative_vitest_when_available(tmp_path: Path) -> None:
    repo_root = tmp_path / "vitest-repo"
    (repo_root / "packages" / "ui" / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        '{ "private": true, "workspaces": ["packages/*"] }',
        encoding="utf-8",
    )
    (repo_root / "packages" / "ui" / "package.json").write_text(
        '{ "name": "@demo/ui", "scripts": { "test": "vitest run" } }',
        encoding="utf-8",
    )
    (repo_root / "packages" / "ui" / "src" / "Widget.test.tsx").write_text("export {};\n", encoding="utf-8")
    workspace = PackageJsonWorkspaceLoader().load(repo_root)
    package = next(item for item in workspace.packages if item.manifest.name == '@demo/ui')
    discoverer = NpmTestDiscoverer(
        tool_resolver_factory=lambda repository_root: _StaticVitestResolver(repository_root / 'node_modules' / '.bin' / 'vitest'),
        vitest_runner_factory=lambda repository_root, executable: _FakeVitestRunner(('packages/ui/src/Widget.test.tsx',)),
    )

    analysis = discoverer.discover(package)

    assert analysis is not None
    assert analysis.discovery_method == TestDiscoveryMethod.AUTHORITATIVE_VITEST_LIST_TESTS
    assert analysis.discovery_tool == 'vitest'
    assert analysis.test_files == ('packages/ui/src/Widget.test.tsx',)
    assert analysis.evidence_paths == ('packages/ui/package.json', 'packages/ui/src/Widget.test.tsx')


def test_npm_test_discovery_falls_back_to_heuristic_when_vitest_is_unavailable(tmp_path: Path) -> None:
    repo_root = tmp_path / "vitest-fallback"
    (repo_root / "packages" / "ui" / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        '{ "private": true, "workspaces": ["packages/*"] }',
        encoding="utf-8",
    )
    (repo_root / "packages" / "ui" / "package.json").write_text(
        '{ "name": "@demo/ui", "scripts": { "test": "vitest run" } }',
        encoding="utf-8",
    )
    (repo_root / "packages" / "ui" / "src" / "Widget.test.tsx").write_text("export {};\n", encoding="utf-8")
    workspace = PackageJsonWorkspaceLoader().load(repo_root)
    package = next(item for item in workspace.packages if item.manifest.name == '@demo/ui')
    discoverer = NpmTestDiscoverer(
        tool_resolver_factory=lambda repository_root: _FailingJestResolver(),
    )

    analysis = discoverer.discover(package)

    assert analysis is not None
    assert analysis.discovery_method == TestDiscoveryMethod.HEURISTIC_MANIFEST_GLOB
    assert analysis.discovery_tool is None
    assert 'packages/ui/src/Widget.test.tsx' in analysis.test_files
