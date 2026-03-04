from __future__ import annotations

from suitcode.providers.python.file_inventory import PythonOwnedFileInventoryBuilder
from suitcode.providers.python.workspace_analyzer import PythonWorkspaceAnalyzer
from suitcode.providers.shared.pyproject import PyProjectWorkspaceLoader


def test_file_inventory_assigns_runner_overrides_and_top_level_component_owner(python_repo_root) -> None:
    manifest = PyProjectWorkspaceLoader().load(python_repo_root)
    analyzer = PythonWorkspaceAnalyzer(python_repo_root, manifest)
    files = PythonOwnedFileInventoryBuilder().build(
        python_repo_root,
        analyzer.analyze_components(),
        analyzer.analyze_runners(),
        analyzer.analyze_package_managers(),
    )

    owners = {item.repository_rel_path: item.owner_id for item in files}
    assert owners['src/acme/core/repository.py'] == 'component:python:acme'
    assert owners['src/acme/mcp/server.py'] == 'runner:python:acme-server'
    assert owners['src/acme/providers/python/__init__.py'] == 'runner:python:acme-admin'
