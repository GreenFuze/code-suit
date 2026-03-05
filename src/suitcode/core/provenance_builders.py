from __future__ import annotations

from suitcode.core.provenance import ConfidenceMode, ProvenanceEntry, SourceKind


def manifest_provenance(
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
    source_tool: str | None = None,
) -> ProvenanceEntry:
    return ProvenanceEntry(
        confidence_mode=ConfidenceMode.AUTHORITATIVE,
        source_kind=SourceKind.MANIFEST,
        source_tool=source_tool,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def lsp_provenance(
    source_tool: str,
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
) -> ProvenanceEntry:
    return ProvenanceEntry(
        confidence_mode=ConfidenceMode.AUTHORITATIVE,
        source_kind=SourceKind.LSP,
        source_tool=source_tool,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def test_tool_provenance(
    source_tool: str,
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
) -> ProvenanceEntry:
    return ProvenanceEntry(
        confidence_mode=ConfidenceMode.AUTHORITATIVE,
        source_kind=SourceKind.TEST_TOOL,
        source_tool=source_tool,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def heuristic_provenance(
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
) -> ProvenanceEntry:
    return ProvenanceEntry(
        confidence_mode=ConfidenceMode.HEURISTIC,
        source_kind=SourceKind.HEURISTIC,
        source_tool=None,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def ownership_provenance(
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
) -> ProvenanceEntry:
    return ProvenanceEntry(
        confidence_mode=ConfidenceMode.DERIVED,
        source_kind=SourceKind.OWNERSHIP,
        source_tool=None,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def manifest_node_provenance(
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
) -> ProvenanceEntry:
    return derived_summary_provenance(
        source_kind=SourceKind.MANIFEST,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def lsp_node_provenance(
    source_tool: str,
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
) -> ProvenanceEntry:
    return lsp_provenance(
        source_tool=source_tool,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def ownership_node_provenance(
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
) -> ProvenanceEntry:
    return ownership_provenance(
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def derived_summary_provenance(
    source_kind: SourceKind,
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
    source_tool: str | None = None,
) -> ProvenanceEntry:
    return ProvenanceEntry(
        confidence_mode=ConfidenceMode.DERIVED,
        source_kind=source_kind,
        source_tool=source_tool,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def quality_tool_provenance(
    source_tool: str,
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
) -> ProvenanceEntry:
    return ProvenanceEntry(
        confidence_mode=ConfidenceMode.AUTHORITATIVE,
        source_kind=SourceKind.QUALITY_TOOL,
        source_tool=source_tool,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def lsp_delta_provenance(
    source_tool: str,
    evidence_summary: str,
    evidence_paths: tuple[str, ...],
) -> ProvenanceEntry:
    return ProvenanceEntry(
        confidence_mode=ConfidenceMode.DERIVED,
        source_kind=SourceKind.LSP,
        source_tool=source_tool,
        evidence_summary=evidence_summary,
        evidence_paths=evidence_paths,
    )


def lsp_location_provenance(
    source_tool: str,
    repository_rel_path: str,
    operation: str,
) -> ProvenanceEntry:
    if operation not in {"definition", "references"}:
        raise ValueError(f"unsupported lsp location operation: `{operation}`")
    return lsp_provenance(
        source_tool=source_tool,
        evidence_summary=f"derived from {source_tool} {operation} location resolution",
        evidence_paths=(repository_rel_path,),
    )
