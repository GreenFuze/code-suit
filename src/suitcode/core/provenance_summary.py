from __future__ import annotations

from collections.abc import Iterable

from suitcode.core.provenance import ConfidenceMode, ProvenanceEntry, SourceKind


def _as_tuple(entries: tuple[ProvenanceEntry, ...] | Iterable[ProvenanceEntry]) -> tuple[ProvenanceEntry, ...]:
    result = tuple(entries)
    if not result:
        raise ValueError("provenance entries must not be empty")
    return result


def merge_provenance_paths(
    entries: tuple[ProvenanceEntry, ...] | Iterable[ProvenanceEntry],
    limit: int = 10,
) -> tuple[str, ...]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    merged: list[str] = []
    for entry in _as_tuple(entries):
        for path in entry.evidence_paths:
            if path not in merged:
                merged.append(path)
    return tuple(merged[:limit])


def is_authoritative_provenance(
    entries: tuple[ProvenanceEntry, ...] | Iterable[ProvenanceEntry],
) -> bool:
    return any(entry.confidence_mode == ConfidenceMode.AUTHORITATIVE for entry in _as_tuple(entries))


def preferred_confidence_mode(
    entries: tuple[ProvenanceEntry, ...] | Iterable[ProvenanceEntry],
) -> ConfidenceMode:
    ordered_entries = _as_tuple(entries)
    if any(entry.confidence_mode == ConfidenceMode.AUTHORITATIVE for entry in ordered_entries):
        return ConfidenceMode.AUTHORITATIVE
    if any(entry.confidence_mode == ConfidenceMode.DERIVED for entry in ordered_entries):
        return ConfidenceMode.DERIVED
    return ConfidenceMode.HEURISTIC


def preferred_source_kind(
    entries: tuple[ProvenanceEntry, ...] | Iterable[ProvenanceEntry],
) -> SourceKind:
    ordered_entries = _as_tuple(entries)
    precedence = (
        SourceKind.TEST_TOOL,
        SourceKind.QUALITY_TOOL,
        SourceKind.LSP,
        SourceKind.MANIFEST,
        SourceKind.DEPENDENCY_GRAPH,
        SourceKind.OWNERSHIP,
        SourceKind.HEURISTIC,
    )
    kinds = {entry.source_kind for entry in ordered_entries}
    for kind in precedence:
        if kind in kinds:
            return kind
    return ordered_entries[0].source_kind


def preferred_source_tool(
    entries: tuple[ProvenanceEntry, ...] | Iterable[ProvenanceEntry],
) -> str | None:
    for entry in _as_tuple(entries):
        if entry.source_tool is not None:
            return entry.source_tool
    return None


def summarize_related_provenance(
    entries: tuple[ProvenanceEntry, ...] | Iterable[ProvenanceEntry],
    evidence_summary: str,
) -> ProvenanceEntry:
    ordered_entries = _as_tuple(entries)
    return ProvenanceEntry(
        confidence_mode=(
            ConfidenceMode.AUTHORITATIVE if is_authoritative_provenance(ordered_entries) else ConfidenceMode.DERIVED
        ),
        source_kind=preferred_source_kind(ordered_entries),
        source_tool=preferred_source_tool(ordered_entries),
        evidence_summary=evidence_summary,
        evidence_paths=merge_provenance_paths(ordered_entries),
    )
