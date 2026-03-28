from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace
from suitcode.providers.go import GoProvider
from suitcode.providers.markdown import MarkdownProvider
from suitcode.providers.npm import NPMProvider
from suitcode.providers.provider_base import ProviderBase
from suitcode.providers.provider_metadata import ProviderAttachmentCandidate
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.python import PythonProvider
from suitcode.providers.registry import BUILTIN_PROVIDER_CLASSES, detect_support_for_root, get_provider_descriptors


def test_provider_registry_contains_go_markdown_npm_and_python_providers() -> None:
    assert BUILTIN_PROVIDER_CLASSES == (GoProvider, MarkdownProvider, NPMProvider, PythonProvider)


def test_workspace_supported_providers_exposes_go_markdown_npm_and_python_descriptors() -> None:
    descriptors = Workspace.supported_providers()

    assert tuple(descriptor.provider_id for descriptor in descriptors) == ('go', 'markdown', 'npm', 'python')


def test_repository_support_for_path_detects_npm_fixture(npm_repo_root: Path) -> None:
    support = Repository.support_for_path(npm_repo_root)

    assert support.is_supported is True
    assert support.provider_ids == ('go', 'npm', 'python')
    assert support.detected_providers[0].provider_id == 'go'
    assert support.detected_providers[0].detected_roles == frozenset(
        {
            ProviderRole.ARCHITECTURE,
            ProviderRole.TEST,
        }
    )
    assert support.detected_providers[1].provider_id == 'npm'
    assert support.detected_providers[1].detected_roles == frozenset(
        {
            ProviderRole.ARCHITECTURE,
            ProviderRole.CODE,
            ProviderRole.TEST,
            ProviderRole.QUALITY,
        }
    )
    assert support.detected_providers[2].provider_id == 'python'
    assert support.detected_providers[2].attachments[0].attachment_root_rel_path == 'tools/codegen'


def test_repository_support_for_path_detects_python_fixture(python_repo_root: Path) -> None:
    support = Repository.support_for_path(python_repo_root)

    assert support.is_supported is True
    assert support.provider_ids == ('python',)
    assert support.detected_providers[0].detected_roles == frozenset(
        {
            ProviderRole.ARCHITECTURE,
            ProviderRole.CODE,
            ProviderRole.TEST,
            ProviderRole.QUALITY,
        }
    )


def test_repository_support_for_path_detects_go_fixture(go_repo_root: Path) -> None:
    support = Repository.support_for_path(go_repo_root)

    assert support.is_supported is True
    assert support.provider_ids == ('go',)
    assert support.detected_providers[0].detected_roles == frozenset(
        {
            ProviderRole.ARCHITECTURE,
            ProviderRole.TEST,
        }
    )


def test_repository_support_for_path_returns_unsupported_for_repo_without_supported_metadata(tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    (repo_root / '.git').mkdir(parents=True)

    support = Repository.support_for_path(repo_root)

    assert support.is_supported is False
    assert support.detected_providers == tuple()


def test_python_detection_raises_for_malformed_pyproject(tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    (repo_root / '.git').mkdir(parents=True)
    (repo_root / 'pyproject.toml').write_text("[project\nname='broken'\n", encoding='utf-8')

    with pytest.raises(ValueError, match='invalid TOML'):
        Repository.support_for_path(repo_root)


def test_mixed_root_detects_nested_standalone_npm_attachment(tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    (repo_root / '.git').mkdir(parents=True)
    server_root = repo_root / 'server'
    server_root.mkdir()
    (server_root / 'go.mod').write_text("module example.com/server\n\ngo 1.22\n", encoding='utf-8')
    frontend_root = server_root / 'frontend'
    frontend_root.mkdir(parents=True)
    (frontend_root / 'package.json').write_text(
        '{"name":"frontend","private":true,"scripts":{"build":"vite build"}}',
        encoding='utf-8',
    )

    support = Repository.support_for_path(repo_root)

    assert support.provider_ids == ('go', 'npm')
    assert support.detected_providers[0].provider_id == 'go'
    assert tuple(item.attachment_root_rel_path for item in support.detected_providers[0].attachments) == ('server',)
    assert support.detected_providers[1].provider_id == 'npm'
    assert tuple(item.attachment_root_rel_path for item in support.detected_providers[1].attachments) == (
        'server/frontend',
    )


def test_markdown_provider_detects_root_markdown_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "roadmap.md").write_text("# Roadmap\n\n- [ ] ship docs\n", encoding="utf-8")

    support = Repository.support_for_path(repo_root)

    assert support.provider_ids == ("markdown",)
    assert support.detected_providers[0].provider_id == "markdown"
    assert tuple(item.attachment_root_rel_path for item in support.detected_providers[0].attachments) == (".",)


def test_registry_rejects_duplicate_provider_ids() -> None:
    class _DuplicateProvider(ProviderBase):
        PROVIDER_ID = 'npm'
        DISPLAY_NAME = 'dup'
        BUILD_SYSTEMS = ('dup',)
        PROGRAMMING_LANGUAGES = ('other',)

        @classmethod
        def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
            return frozenset()

        @classmethod
        def discover_attachments(cls, repository_root: Path):
            return (
                ProviderAttachmentCandidate(
                    provider_id=cls.PROVIDER_ID,
                    attachment_root=repository_root,
                    detected_roles=frozenset({ProviderRole.ARCHITECTURE}),
                ),
            )

    with pytest.raises(ValueError, match='duplicate provider id'):
        get_provider_descriptors((NPMProvider, _DuplicateProvider))


def test_repository_construction_rejects_role_contract_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _BrokenProvider(ProviderBase):
        PROVIDER_ID = 'broken'
        DISPLAY_NAME = 'broken'
        BUILD_SYSTEMS = ('broken',)
        PROGRAMMING_LANGUAGES = ('other',)

        @classmethod
        def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
            return frozenset({ProviderRole.ARCHITECTURE})

        @classmethod
        def discover_attachments(cls, repository_root: Path):
            return (
                ProviderAttachmentCandidate(
                    provider_id=cls.PROVIDER_ID,
                    attachment_root=repository_root,
                    detected_roles=frozenset({ProviderRole.ARCHITECTURE}),
                ),
            )

    repo_root = tmp_path / 'repo'
    (repo_root / '.git').mkdir(parents=True)
    (repo_root / 'pyproject.toml').write_text("[project]\nname='repo'\n", encoding='utf-8')

    monkeypatch.setattr('suitcode.core.repository.BUILTIN_PROVIDER_CLASSES', (_BrokenProvider,))
    monkeypatch.setattr(
        'suitcode.core.repository.detect_support_for_root',
        lambda repository_root: detect_support_for_root(repository_root, (_BrokenProvider,)),
    )
    monkeypatch.setattr('suitcode.core.workspace.get_provider_descriptors', lambda: (_BrokenProvider.descriptor(),))

    with pytest.raises(ValueError, match='does not implement `ArchitectureProviderBase`'):
        Workspace(repo_root)
