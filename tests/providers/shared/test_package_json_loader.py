from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.providers.shared.package_json.loader import PackageJsonLoader


FIXTURE_ROOT = Path("tests/test_repos/npm")


def test_package_json_loader_reads_root_manifest() -> None:
    manifest = PackageJsonLoader().load(FIXTURE_ROOT / "package.json")
    assert manifest.name == "npm-complex-monorepo"
    assert manifest.workspaces[0] == "packages/*"


def test_package_json_loader_fails_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="package.json not found"):
        PackageJsonLoader().load(tmp_path / "package.json")
