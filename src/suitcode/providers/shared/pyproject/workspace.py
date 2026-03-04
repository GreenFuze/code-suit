from __future__ import annotations

from pathlib import Path

from suitcode.providers.shared.pyproject.loader import PyProjectLoader
from suitcode.providers.shared.pyproject.models import PyProjectManifest


class PyProjectWorkspaceLoader:
    def __init__(self, manifest_loader: PyProjectLoader | None = None) -> None:
        self._manifest_loader = manifest_loader or PyProjectLoader()

    def load(self, repository_root: Path) -> PyProjectManifest:
        root = repository_root.expanduser().resolve()
        return self._manifest_loader.load(root / "pyproject.toml")
