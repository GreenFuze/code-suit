from __future__ import annotations

import os
from pathlib import Path

from suitcode.analytics.errors import AnalyticsError


class AnalyticsSettings:
    def __init__(
        self,
        *,
        global_root: Path,
        repo_subdir: str,
        max_file_bytes: int,
    ) -> None:
        self.global_root = global_root.expanduser().resolve()
        self.repo_subdir = repo_subdir.strip().replace("\\", "/")
        self.max_file_bytes = max_file_bytes
        if not self.repo_subdir:
            raise AnalyticsError("repo_subdir must not be empty")
        if self.max_file_bytes < 1024:
            raise AnalyticsError("max_file_bytes must be >= 1024")

    @classmethod
    def from_env(cls) -> "AnalyticsSettings":
        global_root_raw = os.getenv("SUITCODE_ANALYTICS_GLOBAL_ROOT", "~/.suitcode/analytics")
        repo_subdir = os.getenv("SUITCODE_ANALYTICS_REPO_SUBDIR", ".suit/analytics")
        max_file_bytes_raw = os.getenv("SUITCODE_ANALYTICS_MAX_FILE_BYTES", "10485760")
        try:
            max_file_bytes = int(max_file_bytes_raw)
        except ValueError as exc:
            raise AnalyticsError("SUITCODE_ANALYTICS_MAX_FILE_BYTES must be an integer") from exc
        return cls(
            global_root=Path(global_root_raw),
            repo_subdir=repo_subdir,
            max_file_bytes=max_file_bytes,
        )

