from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.core.change_models import ChangeImpact, QualityGateInfo, RunnerImpact, TestImpact
from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import ComponentContext, FileContext, SymbolContext
from suitcode.core.models import Component, EntityInfo, ExternalPackage, FileInfo, PackageManager, Runner, TestDefinition
from suitcode.core.provenance import ConfidenceMode, ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.provenance_summary import merge_provenance_paths, preferred_confidence_mode, preferred_source_kind, preferred_source_tool
from suitcode.core.truth_coverage_models import (
    TruthActionCapability,
    TruthAvailability,
    TruthCoverageByDomain,
    TruthCoverageDomain,
    TruthCoverageSummary,
)
from suitcode.providers.runtime_capability_models import RuntimeCapability, RuntimeCapabilityAvailability
from suitcode.providers.provider_roles import ProviderRole

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


@dataclass
class _DomainAccumulator:
    domain: TruthCoverageDomain
    total_entities: int = 0
    authoritative_count: int = 0
    derived_count: int = 0
    heuristic_count: int = 0
    unavailable_count: int = 0
    source_kind_mix: Counter[str] = field(default_factory=Counter)
    source_tool_mix: Counter[str] = field(default_factory=Counter)
    availability: TruthAvailability = TruthAvailability.UNAVAILABLE
    degraded_reason: str | None = None
    execution_available: bool | None = None
    action_capabilities: dict[str, bool] = field(default_factory=dict)
    provenance_entries: list[ProvenanceEntry] = field(default_factory=list)

    def add_provenance_item(self, provenance: tuple[ProvenanceEntry, ...]) -> None:
        self.total_entities += 1
        confidence = preferred_confidence_mode(provenance)
        if confidence == ConfidenceMode.AUTHORITATIVE:
            self.authoritative_count += 1
        elif confidence == ConfidenceMode.DERIVED:
            self.derived_count += 1
        else:
            self.heuristic_count += 1
        self.source_kind_mix[preferred_source_kind(provenance).value] += 1
        source_tool = preferred_source_tool(provenance)
        if source_tool is not None:
            self.source_tool_mix[source_tool] += 1
        for entry in provenance:
            if entry not in self.provenance_entries:
                self.provenance_entries.append(entry)

    def add_unavailable(self, count: int, *, reason: str | None = None) -> None:
        if count < 0:
            raise ValueError("unavailable count must be >= 0")
        self.total_entities += count
        self.unavailable_count += count
        if reason is not None and self.degraded_reason is None:
            self.degraded_reason = reason

    def finalize(self) -> TruthCoverageByDomain:
        return TruthCoverageByDomain(
            domain=self.domain,
            total_entities=self.total_entities,
            authoritative_count=self.authoritative_count,
            derived_count=self.derived_count,
            heuristic_count=self.heuristic_count,
            unavailable_count=self.unavailable_count,
            availability=self.availability,
            degraded_reason=self.degraded_reason,
            source_kind_mix=dict(self.source_kind_mix),
            source_tool_mix=dict(self.source_tool_mix),
            execution_available=self.execution_available,
            action_capabilities=self.action_capabilities,
        )


class TruthCoverageService:
    _CODE_OPERATION_COUNT = 4

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def repository_truth_coverage(self) -> TruthCoverageSummary:
        domains = (
            self._architecture_domain(),
            self._code_domain(),
            self._tests_domain(),
            self._quality_domain(),
            self._actions_domain(),
        )
        return self._summary(
            scope_kind="repository",
            scope_id=self._repository.id,
            domains=domains,
        )

    def change_truth_coverage(self, impact: ChangeImpact) -> TruthCoverageSummary:
        return self.change_truth_coverage_from_parts(
            target_kind=impact.target_kind,
            owner_id=impact.owner.id,
            evidence_path=(
                impact.file_context.file_info.repository_rel_path
                if impact.file_context is not None
                else (
                    impact.symbol_context.symbol.repository_rel_path
                    if impact.symbol_context is not None
                    else None
                )
            ),
            primary_component=impact.primary_component,
            component_context=impact.component_context,
            file_context=impact.file_context,
            symbol_context=impact.symbol_context,
            dependent_components=impact.dependent_components,
            reference_locations=impact.reference_locations,
            related_tests=impact.related_tests,
            related_runners=impact.related_runners,
            quality_gates=impact.quality_gates,
        )

    def change_truth_coverage_from_parts(
        self,
        *,
        target_kind: str,
        owner_id: str,
        evidence_path: str | None = None,
        primary_component: Component | None,
        component_context: ComponentContext | None,
        file_context: FileContext | None,
        symbol_context: SymbolContext | None,
        dependent_components: tuple[Component, ...],
        reference_locations: tuple[CodeLocation, ...],
        related_tests: tuple[TestImpact, ...],
        related_runners: tuple[RunnerImpact, ...],
        quality_gates: tuple[QualityGateInfo, ...],
    ) -> TruthCoverageSummary:
        architecture = _DomainAccumulator(domain=TruthCoverageDomain.ARCHITECTURE)
        for item in (
            primary_component,
            component_context,
            *dependent_components,
        ):
            if item is not None:
                architecture.add_provenance_item(item.provenance)
        architecture.availability = self._artifact_domain_availability(architecture)

        code = _DomainAccumulator(domain=TruthCoverageDomain.CODE)
        for item in (
            file_context,
            symbol_context,
            *reference_locations,
        ):
            if item is not None:
                code.add_provenance_item(item.provenance)
        code.availability = self._artifact_domain_availability(code)

        tests = _DomainAccumulator(domain=TruthCoverageDomain.TESTS)
        for item in related_tests:
            tests.add_provenance_item(item.provenance)
        tests.availability = self._artifact_domain_availability(tests)

        quality = _DomainAccumulator(domain=TruthCoverageDomain.QUALITY)
        for item in quality_gates:
            quality.add_provenance_item(item.provenance)
        quality.availability = self._artifact_domain_availability(quality)
        quality.execution_available = bool(quality_gates)

        actions = _DomainAccumulator(domain=TruthCoverageDomain.ACTIONS)
        for item in related_runners:
            actions.add_provenance_item(item.provenance)
        actions.action_capabilities = {
            TruthActionCapability.TESTS.value: False,
            TruthActionCapability.BUILDS.value: False,
            TruthActionCapability.RUNNERS.value: bool(related_runners),
        }
        actions.execution_available = bool(related_runners)
        actions.availability = self._artifact_domain_availability(actions)

        target_id = self._change_scope_id(
            target_kind=target_kind,
            owner_id=owner_id,
            evidence_path=evidence_path,
            file_context=file_context,
            symbol_context=symbol_context,
        )
        return self._summary(
            scope_kind="change",
            scope_id=target_id,
            domains=(
                architecture.finalize(),
                code.finalize(),
                tests.finalize(),
                quality.finalize(),
                actions.finalize(),
            ),
        )

    def _architecture_domain(self) -> TruthCoverageByDomain:
        accumulator = _DomainAccumulator(domain=TruthCoverageDomain.ARCHITECTURE)
        items = (
            *self._repository.arch.get_components(),
            *self._repository.arch.get_aggregators(),
            *self._repository.arch.get_runners(),
            *self._repository.arch.get_package_managers(),
            *self._repository.arch.get_external_packages(),
            *self._repository.arch.get_files(),
            *self._repository.arch.get_component_dependency_edges(),
        )
        for item in items:
            accumulator.add_provenance_item(item.provenance)
        if not self._repository.supports_role(ProviderRole.ARCHITECTURE):
            accumulator.availability = TruthAvailability.UNAVAILABLE
            accumulator.degraded_reason = "repository has no architecture provider"
        elif accumulator.total_entities == 0:
            accumulator.availability = TruthAvailability.DEGRADED
            accumulator.degraded_reason = "architecture provider exists but no architecture entities were produced"
        else:
            accumulator.availability = TruthAvailability.AVAILABLE
        return accumulator.finalize()

    def _code_domain(self) -> TruthCoverageByDomain:
        accumulator = _DomainAccumulator(domain=TruthCoverageDomain.CODE)
        if not self._repository.supports_role(ProviderRole.CODE):
            accumulator.add_unavailable(
                self._CODE_OPERATION_COUNT,
                reason="repository has no code intelligence provider",
            )
            accumulator.availability = TruthAvailability.UNAVAILABLE
            return accumulator.finalize()

        reasons: list[str] = []
        for capabilities in self._repository.code.get_runtime_capabilities():
            for capability in (
                capabilities.symbol_search,
                capabilities.symbols_in_file,
                capabilities.definitions,
                capabilities.references,
            ):
                self._apply_runtime_capability(accumulator, capability, reasons=reasons)
        if accumulator.unavailable_count == accumulator.total_entities:
            accumulator.availability = TruthAvailability.DEGRADED
        elif accumulator.unavailable_count > 0:
            accumulator.availability = TruthAvailability.DEGRADED
        else:
            accumulator.availability = TruthAvailability.AVAILABLE
        if reasons:
            accumulator.degraded_reason = "; ".join(sorted(set(reasons)))
        return accumulator.finalize()

    def _tests_domain(self) -> TruthCoverageByDomain:
        accumulator = _DomainAccumulator(domain=TruthCoverageDomain.TESTS)
        if not self._repository.supports_role(ProviderRole.TEST):
            accumulator.availability = TruthAvailability.UNAVAILABLE
            accumulator.degraded_reason = "repository has no test provider"
            return accumulator.finalize()
        reasons: list[str] = []
        runtime_capabilities = self._repository.tests.get_runtime_capabilities()
        for capabilities in runtime_capabilities:
            self._apply_runtime_capability(accumulator, capabilities.discovery, reasons=reasons)
            self._apply_runtime_capability(accumulator, capabilities.execution, reasons=reasons)
        if accumulator.total_entities == 0:
            accumulator.availability = TruthAvailability.UNAVAILABLE
            accumulator.degraded_reason = "test provider exists but exposes no runtime test capabilities"
        elif accumulator.unavailable_count > 0:
            accumulator.availability = TruthAvailability.DEGRADED
            accumulator.degraded_reason = "; ".join(sorted(set(reasons))) if reasons else "test capability is partially unavailable"
        elif accumulator.authoritative_count == 0 and accumulator.heuristic_count > 0:
            accumulator.availability = TruthAvailability.DEGRADED
            accumulator.degraded_reason = "test capability is available only through heuristic fallback"
        else:
            accumulator.availability = TruthAvailability.AVAILABLE
        return accumulator.finalize()

    def _quality_domain(self) -> TruthCoverageByDomain:
        accumulator = _DomainAccumulator(domain=TruthCoverageDomain.QUALITY)
        providers = self._repository.quality.providers
        if not providers:
            accumulator.availability = TruthAvailability.UNAVAILABLE
            accumulator.execution_available = False
            accumulator.degraded_reason = "repository has no quality provider"
            return accumulator.finalize()

        relevant_files = tuple(self._repository.arch.get_files())
        reasons: list[str] = []
        for capabilities in self._repository.quality.get_runtime_capabilities(
            tuple(file_info.repository_rel_path for file_info in relevant_files)
        ):
            self._apply_runtime_capability(accumulator, capabilities.lint, reasons=reasons)
            self._apply_runtime_capability(accumulator, capabilities.format, reasons=reasons)

        accumulator.execution_available = accumulator.unavailable_count == 0 and accumulator.total_entities > 0
        if accumulator.unavailable_count == 0:
            accumulator.availability = TruthAvailability.AVAILABLE
        else:
            accumulator.availability = TruthAvailability.DEGRADED
            accumulator.degraded_reason = "; ".join(sorted(set(reasons or [accumulator.degraded_reason or "quality capability is partially unavailable"])))
        return accumulator.finalize()

    def _actions_domain(self) -> TruthCoverageByDomain:
        accumulator = _DomainAccumulator(domain=TruthCoverageDomain.ACTIONS)
        reasons: list[str] = []
        capabilities = {
            TruthActionCapability.TESTS.value: False,
            TruthActionCapability.BUILDS.value: False,
            TruthActionCapability.RUNNERS.value: False,
        }
        runtime_snapshots = self._repository.actions.get_runtime_capabilities()
        for snapshot in runtime_snapshots:
            self._apply_runtime_capability(accumulator, snapshot.tests, reasons=reasons)
            self._apply_runtime_capability(accumulator, snapshot.builds, reasons=reasons)
            self._apply_runtime_capability(accumulator, snapshot.runners, reasons=reasons)
            capabilities[TruthActionCapability.TESTS.value] = capabilities[TruthActionCapability.TESTS.value] or (
                snapshot.tests.availability == RuntimeCapabilityAvailability.AVAILABLE
            )
            capabilities[TruthActionCapability.BUILDS.value] = capabilities[TruthActionCapability.BUILDS.value] or (
                snapshot.builds.availability == RuntimeCapabilityAvailability.AVAILABLE
            )
            capabilities[TruthActionCapability.RUNNERS.value] = capabilities[TruthActionCapability.RUNNERS.value] or (
                snapshot.runners.availability == RuntimeCapabilityAvailability.AVAILABLE
            )
        accumulator.action_capabilities = capabilities
        accumulator.execution_available = any(capabilities.values())
        if not runtime_snapshots:
            accumulator.availability = TruthAvailability.UNAVAILABLE
            accumulator.degraded_reason = "no deterministic actions were discovered"
        else:
            missing = [name for name, available in capabilities.items() if not available]
            if missing:
                accumulator.availability = TruthAvailability.DEGRADED
                accumulator.degraded_reason = "; ".join(sorted(set(reasons))) if reasons else (
                    "deterministic actions are missing for: " + ", ".join(sorted(missing))
                )
            else:
                accumulator.availability = TruthAvailability.AVAILABLE
        return accumulator.finalize()

    def _summary(
        self,
        *,
        scope_kind: str,
        scope_id: str,
        domains: tuple[TruthCoverageByDomain, ...],
    ) -> TruthCoverageSummary:
        flattened_domain_provenance: list[ProvenanceEntry] = []
        for domain in domains:
            for entry in self._domain_summary_provenance(domain):
                if entry not in flattened_domain_provenance:
                    flattened_domain_provenance.append(entry)
        if not flattened_domain_provenance:
            flattened_domain_provenance = [
                derived_summary_provenance(
                    source_kind=SourceKind.HEURISTIC,
                    evidence_summary=f"{scope_kind} truth coverage contains no provenance-bearing entities",
                    evidence_paths=tuple(),
                )
            ]

        if all(domain.availability == TruthAvailability.UNAVAILABLE for domain in domains):
            overall_availability = TruthAvailability.UNAVAILABLE
        elif any(domain.availability != TruthAvailability.AVAILABLE for domain in domains):
            overall_availability = TruthAvailability.DEGRADED
        else:
            overall_availability = TruthAvailability.AVAILABLE

        return TruthCoverageSummary(
            scope_kind=scope_kind,
            scope_id=scope_id,
            domains=domains,
            overall_authoritative_count=sum(item.authoritative_count for item in domains),
            overall_derived_count=sum(item.derived_count for item in domains),
            overall_heuristic_count=sum(item.heuristic_count for item in domains),
            overall_unavailable_count=sum(item.unavailable_count for item in domains),
            overall_availability=overall_availability,
            provenance=tuple(flattened_domain_provenance),
        )

    @staticmethod
    def _artifact_domain_availability(accumulator: _DomainAccumulator) -> TruthAvailability:
        if accumulator.total_entities == 0:
            accumulator.degraded_reason = None
            return TruthAvailability.UNAVAILABLE
        if accumulator.heuristic_count > 0:
            accumulator.degraded_reason = "artifact includes heuristic coverage in this domain"
            return TruthAvailability.DEGRADED
        return TruthAvailability.AVAILABLE

    @staticmethod
    def _domain_summary_provenance(domain: TruthCoverageByDomain) -> tuple[ProvenanceEntry, ...]:
        if domain.total_entities == 0:
            return (
                derived_summary_provenance(
                    source_kind=SourceKind.HEURISTIC,
                    evidence_summary=f"{domain.domain.value} truth coverage is {domain.availability.value}",
                    evidence_paths=tuple(),
                ),
            )
        evidence_paths = tuple()
        source_kind = SourceKind.HEURISTIC
        source_tool = None
        if domain.source_kind_mix:
            ordered_kind = max(sorted(domain.source_kind_mix), key=lambda key: domain.source_kind_mix[key])
            source_kind = SourceKind(ordered_kind)
        if domain.source_tool_mix:
            source_tool = max(sorted(domain.source_tool_mix), key=lambda key: domain.source_tool_mix[key])
        return (
            derived_summary_provenance(
                source_kind=source_kind,
                source_tool=source_tool,
                evidence_summary=f"{domain.domain.value} truth coverage summarized as {domain.availability.value}",
                evidence_paths=evidence_paths,
            ),
        )

    @staticmethod
    def _change_scope_id(
        *,
        target_kind: str,
        owner_id: str,
        evidence_path: str | None,
        file_context: FileContext | None,
        symbol_context: SymbolContext | None,
    ) -> str:
        if target_kind == "symbol":
            if symbol_context is None:
                raise ValueError("symbol change impact requires symbol_context")
            return symbol_context.symbol.id
        if target_kind == "file":
            if file_context is not None:
                return file_context.file_info.repository_rel_path
            if evidence_path is None:
                raise ValueError("file change impact requires evidence_path when file_context is unavailable")
            return evidence_path
        return owner_id

    @staticmethod
    def _apply_runtime_capability(
        accumulator: _DomainAccumulator,
        capability: RuntimeCapability,
        *,
        reasons: list[str],
    ) -> None:
        if capability.availability == RuntimeCapabilityAvailability.AVAILABLE:
            accumulator.add_provenance_item(capability.provenance)
            return
        accumulator.add_unavailable(1, reason=capability.reason)
        if capability.reason is not None:
            reasons.append(capability.reason)
