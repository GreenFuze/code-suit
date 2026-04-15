from __future__ import annotations

import json
from pathlib import Path

from suitcode.core.intelligence_models import (
    ImplementationFlowStepKind,
    ImplementationFlowStepRef,
    InvariantAccessKind,
    InvariantFindingKind,
    InvariantFindingRef,
    StaticAnalysisSiteRef,
    StaticFlowEdgeKind,
    StaticFlowEdgeRef,
)
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.provenance import SourceKind
from suitcode.providers.shared.lsp import TypeScriptLanguageServerResolver
from suitcode.providers.npm.tool_runner import TypeScriptProbeRunner


class NpmStaticAnalysisService:
    _SUPPORTED_EXTENSIONS = frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})

    def __init__(
        self,
        *,
        repository_root: Path,
        attachment_root: Path,
        resolver: TypeScriptLanguageServerResolver | None = None,
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._attachment_root = attachment_root.expanduser().resolve()
        self._resolver = resolver or TypeScriptLanguageServerResolver()
        self._probe_runner = TypeScriptProbeRunner(
            repository_root=self._repository_root,
            attachment_root=self._attachment_root,
            resolver=self._resolver,
        )
        self._cache: dict[
            str,
            tuple[
                tuple[InvariantFindingRef, ...],
                tuple[StaticFlowEdgeRef, ...],
                tuple[ImplementationFlowStepRef, ...],
            ],
        ] = {}

    def get_file_analysis(
        self,
        repository_rel_path: str,
    ) -> tuple[tuple[InvariantFindingRef, ...], tuple[StaticFlowEdgeRef, ...]]:
        findings, flows, _ = self._get_cached_analysis(repository_rel_path)
        return findings, flows

    def get_file_implementation_flow_steps(
        self,
        repository_rel_path: str,
    ) -> tuple[ImplementationFlowStepRef, ...]:
        _, _, flow_steps = self._get_cached_analysis(repository_rel_path)
        return flow_steps

    def _get_cached_analysis(
        self,
        repository_rel_path: str,
    ) -> tuple[
        tuple[InvariantFindingRef, ...],
        tuple[StaticFlowEdgeRef, ...],
        tuple[ImplementationFlowStepRef, ...],
    ]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        if normalized_path in self._cache:
            return self._cache[normalized_path]
        absolute_path = (self._repository_root / normalized_path).resolve()
        try:
            absolute_path.relative_to(self._attachment_root)
        except ValueError:
            return tuple(), tuple()
        if absolute_path.suffix.lower() not in self._SUPPORTED_EXTENSIONS:
            return tuple(), tuple()
        if not absolute_path.exists() or not absolute_path.is_file():
            raise ValueError(f"file does not exist: `{normalized_path}`")

        payload = self._probe_runner.run_json_probe(
            script_name="ts_static_analysis.cjs",
            command_args=(
                str(self._repository_root),
                str(self._attachment_root),
                str(absolute_path),
                self._probe_runner.resolve_typescript_library_path(),
            ),
            error_label="TS static analysis",
        )

        findings, flows, flow_steps = self._translate_payload(normalized_path, payload)
        self._cache[normalized_path] = (findings, flows, flow_steps)
        return findings, flows, flow_steps

    def _translate_payload(
        self,
        repository_rel_path: str,
        payload: object,
    ) -> tuple[
        tuple[InvariantFindingRef, ...],
        tuple[StaticFlowEdgeRef, ...],
        tuple[ImplementationFlowStepRef, ...],
    ]:
        if not isinstance(payload, dict):
            raise ValueError("TypeScript static-analysis probe returned an invalid payload shape")
        findings_payload = self._coerce_findings(payload.get("invariant_findings"))
        flows_payload = self._coerce_flow_edges(payload.get("local_flow_edges"))
        implementation_flow_payload = self._coerce_implementation_flow_steps(payload.get("implementation_flow_steps"))

        findings = tuple(
            InvariantFindingRef(
                repository_rel_path=edge["path"],
                finding_kind=InvariantFindingKind.MAYBE_MISSING_FIELD_ACCESS,
                access_kind=InvariantAccessKind(edge["access_kind"]),
                line_start=edge["line_start"],
                column_start=edge["column_start"],
                field_name=edge["field_name"],
                subject_label=edge["subject_label"],
                declared_type=edge["declared_type"],
                producer_site_count=len(edge["producer_sites"]),
                producer_sites_preview=tuple(
                    StaticAnalysisSiteRef(
                        repository_rel_path=producer["path"],
                        line_start=producer["line_start"],
                        column_start=producer["column_start"],
                        label=producer["label"],
                        provenance=(
                            derived_summary_provenance(
                                source_kind=SourceKind.DEPENDENCY_GRAPH,
                                source_tool="typescript",
                                evidence_summary=(
                                    f"deterministic TypeScript static analysis identifies local producer `{producer['label']}`"
                                ),
                                evidence_paths=self._producer_evidence_paths(repository_rel_path, producer["path"]),
                            ),
                        ),
                    )
                    for producer in edge["producer_sites"]
                ),
                provenance=(
                    derived_summary_provenance(
                        source_kind=SourceKind.DEPENDENCY_GRAPH,
                        source_tool="typescript",
                        evidence_summary=(
                            f"deterministic TypeScript static analysis shows `{edge['field_name']}` may be missing at access site"
                        ),
                        evidence_paths=self._finding_evidence_paths(repository_rel_path, edge),
                    ),
                ),
            )
            for edge in findings_payload
        )
        flows = tuple(
            StaticFlowEdgeRef(
                repository_rel_path=edge["path"],
                edge_kind=StaticFlowEdgeKind(edge["edge_kind"]),
                line_start=edge["line_start"],
                column_start=edge["column_start"],
                source_label=edge["source_label"],
                target_label=edge["target_label"],
                provenance=(
                    derived_summary_provenance(
                        source_kind=SourceKind.DEPENDENCY_GRAPH,
                        source_tool="typescript",
                        evidence_summary=(
                            f"deterministic TypeScript static analysis shows `{edge['source_label']}` flows into `{edge['target_label']}`"
                        ),
                        evidence_paths=self._flow_evidence_paths(repository_rel_path, edge["path"]),
                    ),
                ),
            )
            for edge in flows_payload
        )
        flow_steps = tuple(
            ImplementationFlowStepRef(
                repository_rel_path=edge["path"],
                line_start=edge["line_start"],
                column_start=edge["column_start"],
                step_kind=ImplementationFlowStepKind(edge["step_kind"]),
                source_label=edge["source_label"],
                target_label=edge["target_label"],
                detail_label=edge["detail_label"],
                provenance=(
                    derived_summary_provenance(
                        source_kind=SourceKind.DEPENDENCY_GRAPH,
                        source_tool="typescript",
                        evidence_summary=edge["evidence_summary"],
                        evidence_paths=self._flow_evidence_paths(repository_rel_path, edge["path"]),
                    ),
                ),
            )
            for edge in implementation_flow_payload
        )
        return findings, flows, flow_steps

    @staticmethod
    def _finding_evidence_paths(
        repository_rel_path: str,
        edge: dict[str, object],
    ) -> tuple[str, ...]:
        paths = [repository_rel_path]
        for producer in edge["producer_sites"]:
            if producer["path"] not in paths:
                paths.append(producer["path"])
        return tuple(paths[:10])

    @staticmethod
    def _flow_evidence_paths(
        repository_rel_path: str,
        edge_path: str,
    ) -> tuple[str, ...]:
        if repository_rel_path == edge_path:
            return (repository_rel_path,)
        return (repository_rel_path, edge_path)

    @staticmethod
    def _producer_evidence_paths(
        repository_rel_path: str,
        producer_path: str,
    ) -> tuple[str, ...]:
        if repository_rel_path == producer_path:
            return (repository_rel_path,)
        return (repository_rel_path, producer_path)

    @staticmethod
    def _coerce_findings(value: object) -> tuple[dict[str, object], ...]:
        if value is None:
            return tuple()
        if not isinstance(value, list):
            raise ValueError("TypeScript static-analysis field `invariant_findings` must be a list")
        findings: list[dict[str, object]] = []
        seen: set[tuple[object, ...]] = set()
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("TypeScript static-analysis field `invariant_findings` must contain objects")
            path = normalize_repository_relative_path(_required_string(item.get("path"), "path"))
            access_kind = _required_string(item.get("access_kind"), "access_kind")
            line_start = _required_int(item.get("line_start"), "line_start")
            column_start = _required_int(item.get("column_start"), "column_start")
            field_name = _required_string(item.get("field_name"), "field_name")
            subject_label = _required_string(item.get("subject_label"), "subject_label")
            declared_type = item.get("declared_type")
            if declared_type is not None and not isinstance(declared_type, str):
                raise ValueError("TypeScript static-analysis field `declared_type` must be a string or null")
            producer_sites = _coerce_sites(item.get("producer_sites"))
            producer_site_key = tuple(
                (site["path"], site["line_start"], site["column_start"], site["label"])
                for site in producer_sites
            )
            key = (path, access_kind, line_start, column_start, field_name, subject_label, producer_site_key)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                {
                    "path": path,
                    "access_kind": access_kind,
                    "line_start": line_start,
                    "column_start": column_start,
                    "field_name": field_name,
                    "subject_label": subject_label,
                    "declared_type": declared_type.strip() if isinstance(declared_type, str) and declared_type.strip() else None,
                    "producer_sites": producer_sites,
                }
            )
        return tuple(findings)

    @staticmethod
    def _coerce_flow_edges(value: object) -> tuple[dict[str, object], ...]:
        if value is None:
            return tuple()
        if not isinstance(value, list):
            raise ValueError("TypeScript static-analysis field `local_flow_edges` must be a list")
        edges: list[dict[str, object]] = []
        seen: set[tuple[object, ...]] = set()
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("TypeScript static-analysis field `local_flow_edges` must contain objects")
            path = normalize_repository_relative_path(_required_string(item.get("path"), "path"))
            edge_kind = _required_string(item.get("edge_kind"), "edge_kind")
            line_start = _required_int(item.get("line_start"), "line_start")
            column_start = _required_int(item.get("column_start"), "column_start")
            source_label = _required_string(item.get("source_label"), "source_label")
            target_label = _required_string(item.get("target_label"), "target_label")
            key = (path, edge_kind, line_start, column_start, source_label, target_label)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "path": path,
                    "edge_kind": edge_kind,
                    "line_start": line_start,
                    "column_start": column_start,
                    "source_label": source_label,
                    "target_label": target_label,
                }
            )
        return tuple(edges)

    @staticmethod
    def _coerce_implementation_flow_steps(value: object) -> tuple[dict[str, object], ...]:
        if value is None:
            return tuple()
        if not isinstance(value, list):
            raise ValueError("TypeScript static-analysis field `implementation_flow_steps` must be a list")
        steps: list[dict[str, object]] = []
        seen: set[tuple[object, ...]] = set()
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("TypeScript static-analysis field `implementation_flow_steps` must contain objects")
            path = normalize_repository_relative_path(_required_string(item.get("path"), "path"))
            step_kind = _required_string(item.get("step_kind"), "step_kind")
            line_start = _required_int(item.get("line_start"), "line_start")
            column_start = _required_int(item.get("column_start"), "column_start")
            source_label = _required_string(item.get("source_label"), "source_label")
            target_label = _optional_string(item.get("target_label"), "target_label")
            detail_label = _optional_string(item.get("detail_label"), "detail_label")
            evidence_summary = _required_string(item.get("evidence_summary"), "evidence_summary")
            key = (path, step_kind, line_start, column_start, source_label, target_label, detail_label)
            if key in seen:
                continue
            seen.add(key)
            steps.append(
                {
                    "path": path,
                    "step_kind": step_kind,
                    "line_start": line_start,
                    "column_start": column_start,
                    "source_label": source_label,
                    "target_label": target_label,
                    "detail_label": detail_label,
                    "evidence_summary": evidence_summary,
                }
            )
        return tuple(steps)


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"TypeScript static-analysis field `{field_name}` must be a non-empty string")
    return value.strip()


def _required_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"TypeScript static-analysis field `{field_name}` must be a positive integer")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"TypeScript static-analysis field `{field_name}` must be a non-empty string or null")
    return value.strip()


def _coerce_sites(value: object) -> tuple[dict[str, object], ...]:
    if value is None:
        return tuple()
    if not isinstance(value, list):
        raise ValueError("TypeScript static-analysis field `producer_sites` must be a list")
    sites: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("TypeScript static-analysis field `producer_sites` must contain objects")
        path = normalize_repository_relative_path(_required_string(item.get("path"), "path"))
        line_start = _required_int(item.get("line_start"), "line_start")
        column_start = _required_int(item.get("column_start"), "column_start")
        label = _required_string(item.get("label"), "label")
        key = (path, line_start, column_start, label)
        if key in seen:
            continue
        seen.add(key)
        sites.append({"path": path, "line_start": line_start, "column_start": column_start, "label": label})
    return tuple(sites)
