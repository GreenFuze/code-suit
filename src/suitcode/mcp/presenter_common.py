from __future__ import annotations

from suitcode.core.provenance import ProvenanceEntry
from suitcode.mcp.models import ProvenanceView
from suitcode.providers.provider_roles import ProviderRole


def sorted_role_values(roles: frozenset[ProviderRole]) -> tuple[str, ...]:
    return tuple(sorted(role.value for role in roles))


def provenance_view(provenance: ProvenanceEntry) -> ProvenanceView:
    return ProvenanceView(
        confidence_mode=provenance.confidence_mode.value,
        source_kind=provenance.source_kind.value,
        source_tool=provenance.source_tool,
        evidence_summary=provenance.evidence_summary,
        evidence_paths=provenance.evidence_paths,
    )


def provenance_views(items: tuple[ProvenanceEntry, ...]) -> tuple[ProvenanceView, ...]:
    return tuple(provenance_view(item) for item in items)


def compact_provenance_views(
    items: tuple[ProvenanceEntry, ...],
    *,
    max_entries: int = 3,
    max_paths: int = 5,
) -> tuple[ProvenanceView, ...]:
    return tuple(
        ProvenanceView(
            confidence_mode=item.confidence_mode.value,
            source_kind=item.source_kind.value,
            source_tool=item.source_tool,
            evidence_summary=item.evidence_summary,
            evidence_paths=item.evidence_paths[:max_paths],
        )
        for item in items[:max_entries]
    )
