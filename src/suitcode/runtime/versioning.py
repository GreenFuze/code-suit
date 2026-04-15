from __future__ import annotations

from pathlib import Path

from importlib import metadata


PROTOCOL_VERSION = "1"


def build_version() -> str:
    package_root = Path(__file__).resolve().parents[1]
    latest_mtime_ns = max(
        (path.stat().st_mtime_ns for path in package_root.rglob("*.py")),
        default=0,
    )
    try:
        package_version = metadata.version("suitcode")
    except metadata.PackageNotFoundError:
        package_version = "0.0.0"
    return f"{package_version}:{latest_mtime_ns}"

