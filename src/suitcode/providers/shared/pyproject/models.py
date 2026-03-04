from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PyProjectBuildSystem:
    requires: tuple[str, ...]
    build_backend: str | None


@dataclass(frozen=True)
class PyProjectProject:
    name: str | None
    version: str | None
    dependencies: tuple[str, ...]
    optional_dependencies: dict[str, tuple[str, ...]]
    scripts: dict[str, str]
    gui_scripts: dict[str, str]
    requires_python: str | None


@dataclass(frozen=True)
class PyProjectManifest:
    path: Path
    raw: dict
    build_system: PyProjectBuildSystem | None
    project: PyProjectProject | None
    tool: dict[str, object] = field(default_factory=dict)
