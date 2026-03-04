from __future__ import annotations

from typing import Sequence, TypeVar

from suitcode.mcp.errors import McpValidationError
from suitcode.mcp.models import ListResult


T = TypeVar("T")


class PaginationPolicy:
    DEFAULT_LIMIT = 50
    MAX_LIMIT = 200

    def normalize(self, limit: int | None = None, offset: int = 0) -> tuple[int, int]:
        normalized_limit = self.DEFAULT_LIMIT if limit is None else limit
        if normalized_limit <= 0:
            raise McpValidationError("limit must be > 0")
        if normalized_limit > self.MAX_LIMIT:
            raise McpValidationError(f"limit must be <= {self.MAX_LIMIT}")
        if offset < 0:
            raise McpValidationError("offset must be >= 0")
        return normalized_limit, offset

    def paginate(self, items: Sequence[T], limit: int | None = None, offset: int = 0) -> ListResult[T]:
        normalized_limit, normalized_offset = self.normalize(limit, offset)
        total = len(items)
        page = tuple(items[normalized_offset : normalized_offset + normalized_limit])
        truncated = normalized_offset + normalized_limit < total
        next_offset = normalized_offset + normalized_limit if truncated else None
        return ListResult[T](
            items=page,
            limit=normalized_limit,
            offset=normalized_offset,
            total=total,
            truncated=truncated,
            next_offset=next_offset,
        )
