from __future__ import annotations

from pathlib import Path

from suitcode.core.code.models import CodeLocation, SymbolLookupTarget
from suitcode.core.code.code_intelligence import CodeIntelligence
from suitcode.core.models import Component
from suitcode.core.models import EntityInfo
from suitcode.core.models import FileInfo
from suitcode.core.models.graph_types import ComponentKind, ProgrammingLanguage
from suitcode.core.provenance_builders import lsp_provenance
from suitcode.core.provenance_builders import lsp_location_provenance
from suitcode.core.provenance_builders import ownership_provenance
from suitcode.core.provenance_builders import syntax_node_provenance
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.provider_metadata import ProviderAttachmentContext
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.runtime_capability_models import CodeRuntimeCapabilities, RuntimeCapability, RuntimeCapabilityAvailability
from suitcode.core.provenance import SourceKind


class _FakeRepository:
    def __init__(self, providers, files: tuple[FileInfo, ...] = tuple(), components: tuple[Component, ...] = tuple()):
        self._providers = providers
        self.arch = type("Arch", (), {"get_files": lambda _self: files, "get_components": lambda _self: components})()

    def get_providers_for_role(self, role: ProviderRole):
        if role == ProviderRole.CODE:
            return self._providers
        return tuple()

    def get_providers_for_file_role(self, repository_rel_path: str, role: ProviderRole):
        return self.get_providers_for_role(role)

    @staticmethod
    def provider_id_for_owner(owner_id: str) -> str:
        return owner_id.split(":")[1]


class _CodeProvider(CodeProviderBase):
    PROVIDER_ID = "fake-code"
    DISPLAY_NAME = "fake-code"
    BUILD_SYSTEMS = ("fake",)
    PROGRAMMING_LANGUAGES = ("other",)

    @classmethod
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        return frozenset({ProviderRole.CODE})

    @classmethod
    def discover_attachments(cls, repository_root: Path):
        return tuple()

    def __init__(self, repository, name: str, line: int) -> None:
        super().__init__(
            repository,
            ProviderAttachmentContext(
                provider_id=self.PROVIDER_ID,
                repository_root=Path("."),
                attachment_root=Path("."),
                attachment_root_rel_path="",
            ),
        )
        self._name = name
        self._line = line

    def get_symbol(self, query: str, is_case_sensitive: bool = False):
        return (
            EntityInfo(
                id=f"entity:file.ts:function:{self._name}:{self._line}-{self._line}",
                name=self._name,
                repository_rel_path="file.ts",
                entity_kind="function",
                line_start=self._line,
                line_end=self._line,
                column_start=1,
                column_end=5,
                provenance=(
                    lsp_provenance(
                        source_tool="typescript-language-server",
                        evidence_summary="discovered from fake LSP provider",
                        evidence_paths=("file.ts",),
                    ),
                ),
            ),
        )

    def list_symbols_in_file(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
        return self.get_symbol(query or self._name, is_case_sensitive=is_case_sensitive)

    def list_structural_symbols_in_file(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ):
        return (
            EntityInfo(
                id=f"entity:file.ts:function:{self._name}:{self._line}-{self._line}",
                name=self._name,
                repository_rel_path="file.ts",
                entity_kind="function",
                line_start=self._line,
                line_end=self._line,
                column_start=1,
                column_end=5,
                provenance=(
                    syntax_node_provenance(
                        source_tool="fake-parser",
                        evidence_summary="discovered from fake structural provider",
                        evidence_paths=("file.ts",),
                    ),
                ),
            ),
        )

    def find_definition(self, repository_rel_path: str, line: int, column: int):
        return (
            CodeLocation(
                repository_rel_path=repository_rel_path,
                line_start=line,
                line_end=line,
                column_start=column,
                column_end=column,
                provenance=(
                    lsp_location_provenance(
                        source_tool="typescript-language-server",
                        repository_rel_path=repository_rel_path,
                        operation="definition",
                    ),
                ),
            ),
        )

    def find_references(self, repository_rel_path: str, line: int, column: int, include_definition: bool = False):
        return (
            CodeLocation(
                repository_rel_path=repository_rel_path,
                line_start=line,
                line_end=line,
                column_start=column,
                column_end=column,
                provenance=(
                    lsp_location_provenance(
                        source_tool="typescript-language-server",
                        repository_rel_path=repository_rel_path,
                        operation="references",
                    ),
                ),
            ),
        )

    def find_implementations(self, repository_rel_path: str, line: int, column: int):
        return (
            CodeLocation(
                repository_rel_path=repository_rel_path,
                line_start=line + 1,
                line_end=line + 1,
                column_start=column,
                column_end=column,
                provenance=(
                    lsp_location_provenance(
                        source_tool="typescript-language-server",
                        repository_rel_path=repository_rel_path,
                        operation="implementation",
                    ),
                ),
            ),
        )

    def get_code_runtime_capabilities(self) -> CodeRuntimeCapabilities:
        capability = RuntimeCapability(
            capability_id="fake.code",
            availability=RuntimeCapabilityAvailability.AVAILABLE,
            source_kind=SourceKind.LSP,
            source_tool="typescript-language-server",
            provenance=(
                lsp_provenance(
                    source_tool="typescript-language-server",
                    evidence_summary="fake code capability is available",
                    evidence_paths=("file.ts",),
                ),
            ),
        )
        return CodeRuntimeCapabilities(
            symbol_search=capability,
            symbols_in_file=capability,
            definitions=capability,
            references=capability,
            implementations=capability,
        )

    def get_file_implementation_locations(self, repository_rel_path: str):
        return self.find_implementations(repository_rel_path, self._line, 1)


def test_code_intelligence_concatenates_and_sorts_symbols() -> None:
    repo = _FakeRepository(
        (
            _CodeProvider(repository=None, name="Beta", line=2),  # type: ignore[arg-type]
            _CodeProvider(repository=None, name="Alpha", line=1),  # type: ignore[arg-type]
        )
    )
    intelligence = CodeIntelligence(repo)  # type: ignore[arg-type]

    assert tuple(node.name for node in intelligence.get_symbol("a")) == ("Alpha", "Beta")


def test_code_intelligence_collects_structural_symbols_without_semantic_symbol_calls() -> None:
    class _StructuralOnlyProvider(_CodeProvider):
        def list_symbols_in_file(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
            raise AssertionError("semantic symbols must not be used for structural lookup")

    repo = _FakeRepository((_StructuralOnlyProvider(repository=None, name="Alpha", line=1),))  # type: ignore[arg-type]
    intelligence = CodeIntelligence(repo)  # type: ignore[arg-type]

    symbols = intelligence.list_structural_symbols_in_file("file.ts")

    assert tuple(item.name for item in symbols) == ("Alpha",)
    assert symbols[0].provenance[0].source_kind == SourceKind.SYNTAX


def test_code_intelligence_resolves_symbol_id_for_definitions() -> None:
    repo = _FakeRepository((_CodeProvider(repository=None, name="Alpha", line=3),))  # type: ignore[arg-type]
    intelligence = CodeIntelligence(repo)  # type: ignore[arg-type]

    result = intelligence.find_definition(
        SymbolLookupTarget(symbol_id="entity:file.ts:function:Alpha:3-3")
    )

    assert result[0].repository_rel_path == "file.ts"
    assert result[0].line_start == 3
    assert result[0].provenance[0].source_kind.value == "lsp"


def test_code_intelligence_resolves_symbol_id_when_provider_symbol_ranges_differ() -> None:
    class _DifferentRangeProvider(_CodeProvider):
        def get_symbol(self, query: str, is_case_sensitive: bool = False):
            symbol = super().get_symbol(query, is_case_sensitive=is_case_sensitive)[0]
            return (symbol.model_copy(update={"line_end": 3, "id": "entity:file.ts:function:Alpha:3-3"}),)

        def list_symbols_in_file(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
            symbol = super().get_symbol(query or self._name, is_case_sensitive=is_case_sensitive)[0]
            return (symbol.model_copy(update={"line_end": 10, "id": "entity:file.ts:function:Alpha:3-10"}),)

    repo = _FakeRepository((_DifferentRangeProvider(repository=None, name="Alpha", line=3),))  # type: ignore[arg-type]
    intelligence = CodeIntelligence(repo)  # type: ignore[arg-type]

    result = intelligence.find_references_by_symbol_id("entity:file.ts:function:Alpha:3-3")

    assert result[0].repository_rel_path == "file.ts"
    assert result[0].line_start == 3


def test_code_intelligence_collects_file_implementation_locations() -> None:
    repo = _FakeRepository((_CodeProvider(repository=None, name="Alpha", line=3),))  # type: ignore[arg-type]
    intelligence = CodeIntelligence(repo)  # type: ignore[arg-type]

    result = intelligence.get_file_implementation_locations("file.ts")

    assert result[0].repository_rel_path == "file.ts"
    assert result[0].line_start == 4
    assert result[0].provenance[0].source_kind.value == "lsp"


def test_code_intelligence_degrades_runtime_capabilities_when_symbols_are_nonfunctional() -> None:
    file_info = FileInfo(
        id="file:fake-code:file.ts",
        name="file.ts",
        repository_rel_path="file.ts",
        owner_id="component:fake-code:demo",
        language=None,
        provenance=(
            ownership_provenance(
                evidence_summary="file ownership derived from fake repository fixtures",
                evidence_paths=("file.ts",),
            ),
        ),
    )

    class _NoSymbolProvider(_CodeProvider):
        def list_symbols_in_file(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
            return tuple()

    repo = _FakeRepository((_NoSymbolProvider(repository=None, name="Alpha", line=3),), files=(file_info,))  # type: ignore[arg-type]
    intelligence = CodeIntelligence(repo)  # type: ignore[arg-type]

    capabilities = intelligence.get_runtime_capabilities()[0]

    assert capabilities.symbol_search.availability == RuntimeCapabilityAvailability.DEGRADED
    assert capabilities.symbols_in_file.availability == RuntimeCapabilityAvailability.DEGRADED
    assert capabilities.definitions.availability == RuntimeCapabilityAvailability.DEGRADED
    assert capabilities.references.availability == RuntimeCapabilityAvailability.DEGRADED
    assert "produced no symbols" in (capabilities.symbol_search.reason or "")


def test_code_intelligence_runtime_symbol_candidates_use_component_source_roots() -> None:
    source_file = FileInfo(
        id="file:fake-code:src/file.ts",
        name="src/file.ts",
        repository_rel_path="src/file.ts",
        owner_id="component:fake-code:demo",
        language=None,
        provenance=(
            ownership_provenance(
                evidence_summary="file ownership derived from fake repository fixtures",
                evidence_paths=("src/file.ts",),
            ),
        ),
    )
    artifact_file = source_file.model_copy(
        update={
            "id": "file:fake-code:dist/file.js",
            "name": "dist/file.js",
            "repository_rel_path": "dist/file.js",
        }
    )
    component = Component(
        id="component:fake-code:demo",
        name="demo",
        component_kind=ComponentKind.PACKAGE,
        language=ProgrammingLanguage.TYPESCRIPT,
        source_roots=("src",),
        artifact_paths=("dist",),
        provenance=(
            ownership_provenance(
                evidence_summary="component ownership derived from fake repository fixtures",
                evidence_paths=("src/file.ts",),
            ),
        ),
    )
    provider = _CodeProvider(repository=None, name="Alpha", line=3)  # type: ignore[arg-type]
    repo = _FakeRepository((provider,), files=(artifact_file, source_file), components=(component,))
    intelligence = CodeIntelligence(repo)  # type: ignore[arg-type]

    candidates = intelligence._candidate_files_for_provider(provider)

    assert tuple(item.repository_rel_path for item in candidates) == ("src/file.ts",)
