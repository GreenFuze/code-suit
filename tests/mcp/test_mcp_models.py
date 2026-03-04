from __future__ import annotations

import pytest

from suitcode.mcp.models import ListResult, ProviderDescriptorView
from suitcode.mcp.pagination import PaginationPolicy


def test_list_result_rejects_extra_fields() -> None:
    with pytest.raises(Exception):
        ProviderDescriptorView(
            provider_id="npm",
            display_name="npm",
            build_systems=("npm",),
            programming_languages=("javascript",),
            supported_roles=("architecture",),
            extra="nope",
        )


def test_pagination_policy_returns_truncation_metadata() -> None:
    result = PaginationPolicy().paginate((1, 2, 3), limit=2, offset=0)

    assert result.items == (1, 2)
    assert result.total == 3
    assert result.truncated is True
    assert result.next_offset == 2
