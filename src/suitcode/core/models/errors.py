from __future__ import annotations

from pathlib import Path


class GraphError(Exception):
    def __init__(
        self,
        message: str,
        *,
        remediation: str,
        db_path: Path | None = None,
        logs_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.remediation = remediation
        self.db_path = db_path
        self.logs_path = logs_path

    def __str__(self) -> str:
        bits = [self.message, f"remediation={self.remediation}"]
        if self.db_path is not None:
            bits.append(f"db_path={self.db_path}")
        if self.logs_path is not None:
            bits.append(f"logs_path={self.logs_path}")
        return " | ".join(bits)


class GraphIntegrityError(GraphError):
    pass


class GraphStoreError(GraphError):
    pass


class GraphQueryLimitError(GraphError):
    pass


class GraphNotFoundError(GraphError):
    pass


class GraphScopeError(GraphError):
    pass
