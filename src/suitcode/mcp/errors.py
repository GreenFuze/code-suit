from __future__ import annotations


class SuitMcpError(ValueError):
    pass


class McpNotFoundError(SuitMcpError):
    pass


class McpValidationError(SuitMcpError):
    pass


class McpUnsupportedRepositoryError(SuitMcpError):
    pass


class McpConflictError(SuitMcpError):
    pass
