from __future__ import annotations

import pytest

from suitcode.mcp.models import ListResult, LocationView, ProviderDescriptorView, ProvenanceView, RenderEdgeView
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


def test_component_dependency_edge_view_model() -> None:
    from suitcode.mcp.models import ComponentDependencyEdgeView

    view = ComponentDependencyEdgeView(
        source_component_id="component:a",
        target_id="component:b",
        target_kind="component",
        dependency_scope="runtime",
        provenance=tuple(),
    )
    assert view.source_component_id == "component:a"


def test_location_view_serializes_with_span_and_compressed_provenance() -> None:
    view = LocationView(
        path="server/internal/http/review_controller.go",
        line_start=420,
        line_end=420,
        column_start=30,
        column_end=35,
        symbol_id=None,
        provenance=(
            ProvenanceView(
                confidence_mode="authoritative",
                source_kind="lsp",
                source_tool="gopls",
                evidence_summary="derived from gopls reference location resolution",
                evidence_paths=("server/internal/http/review_controller.go",),
                owner_path="server/internal/http/review_controller.go",
            ),
        ),
    )

    payload = view.model_dump()

    assert payload["path"] == "server/internal/http/review_controller.go"
    assert payload["span"] == "server/internal/http/review_controller.go:420"
    assert "line_start" not in payload
    assert "column_start" not in payload
    assert "symbol_id" not in payload
    assert tuple(payload["provenance"]) == (
        {
            "confidence_mode": "authoritative",
            "source_kind": "lsp",
            "source_tool": "gopls",
        },
    )


def test_render_edge_view_serializes_multi_line_span() -> None:
    view = RenderEdgeView(
        path="server/frontend/src/pages/GamePlayerPage.tsx",
        line_start=12,
        column_start=4,
        prop_names=("game",),
        has_spread_props=False,
        provenance=tuple(),
    )

    payload = view.model_dump()

    assert payload["path"] == "server/frontend/src/pages/GamePlayerPage.tsx"
    assert payload["span"] == "server/frontend/src/pages/GamePlayerPage.tsx:12"
    assert "line_start" not in payload
