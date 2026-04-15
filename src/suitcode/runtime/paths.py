from __future__ import annotations

import hashlib
import os
from pathlib import Path


def runtime_dir_for_project(project_root: Path) -> Path:
    return project_root / ".suit" / "runtime"


def status_path_for_project(project_root: Path) -> Path:
    return runtime_dir_for_project(project_root) / "coordinator.json"


def discovery_path_for_project(project_root: Path) -> Path:
    return status_path_for_project(project_root)


def endpoint_runtime_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LocalAppData", Path.home() / "AppData" / "Local")) / "SuitCode" / "runtime"
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "suitcode"
    cache_dir = os.environ.get("XDG_CACHE_HOME")
    if cache_dir:
        return Path(cache_dir) / "suitcode" / "runtime"
    return Path.home() / ".cache" / "suitcode" / "runtime"


def project_hash(project_root: Path) -> str:
    return hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:16]


def bootstrap_lock_path_for_project(project_root: Path) -> Path:
    return endpoint_runtime_dir() / "locks" / f"suitcode-{project_hash(project_root)}.lock"
