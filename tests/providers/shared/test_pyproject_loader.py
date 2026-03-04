from __future__ import annotations

import pytest

from suitcode.providers.shared.pyproject import PyProjectWorkspaceLoader


def test_pyproject_loader_loads_fixture_manifest(python_fixture_root) -> None:
    manifest = PyProjectWorkspaceLoader().load(python_fixture_root)

    assert manifest.project is not None
    assert manifest.project.name == 'acme-platform'
    assert manifest.build_system is not None
    assert manifest.build_system.build_backend == 'setuptools.build_meta'
    assert manifest.project.scripts['acme-server'] == 'acme.mcp.server:main'
    assert 'pytest' in manifest.tool


def test_pyproject_loader_rejects_invalid_toml(tmp_path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    (repo_root / 'pyproject.toml').write_text("[project\nname='broken'\n", encoding='utf-8')

    with pytest.raises(ValueError, match='invalid TOML'):
        PyProjectWorkspaceLoader().load(repo_root)
