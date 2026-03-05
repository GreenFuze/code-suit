from __future__ import annotations

from suitcode.core.provenance import ConfidenceMode, ProvenanceEntry, SourceKind


def is_authoritative_test_provenance(provenance: tuple[ProvenanceEntry, ...]) -> bool:
    return any(entry.confidence_mode == ConfidenceMode.AUTHORITATIVE for entry in provenance)


def summarize_test_provenance_kind(provenance: tuple[ProvenanceEntry, ...]) -> SourceKind:
    if not provenance:
        raise ValueError("test provenance must not be empty")
    for entry in provenance:
        if entry.source_kind in {SourceKind.TEST_TOOL, SourceKind.HEURISTIC}:
            return entry.source_kind
    return provenance[0].source_kind


def summarize_test_provenance_tool(provenance: tuple[ProvenanceEntry, ...]) -> str | None:
    if not provenance:
        raise ValueError("test provenance must not be empty")
    for entry in provenance:
        if entry.source_tool is not None:
            return entry.source_tool
    return None
