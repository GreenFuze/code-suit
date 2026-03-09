from __future__ import annotations

from pathlib import Path

from suitcode.core.code.models import CodeLocation, SymbolLookupTarget
from suitcode.core.code.code_intelligence import CodeIntelligence
from suitcode.core.models import EntityInfo
from suitcode.core.provenance_builders import lsp_provenance
from suitcode.core.provenance_builders import lsp_location_provenance
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.runtime_capability_models import CodeRuntimeCapabilities, RuntimeCapability, RuntimeCapabilityAvailability
from suitcode.core.provenance import SourceKind


class _FakeRepository:
    def __init__(self, providers):
        self._providers = providers

    def get_providers_for_role(self, role: ProviderRole):
        if role == ProviderRole.CODE:
            return self._providers
        return tuple()


class _CodeProvider(CodeProviderBase):
    PROVIDER_ID = "fake-code"
    DISPLAY_NAME = "fake-code"
    BUILD_SYSTEMS = ("fake",)
    PROGRAMMING_LANGUAGES = ("other",)

    @classmethod
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        return frozenset({ProviderRole.CODE})

    def __init__(self, repository, name: str, line: int) -> None:
        super().__init__(repository)
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
        )


def test_code_intelligence_concatenates_and_sorts_symbols() -> None:
    repo = _FakeRepository(
        (
            _CodeProvider(repository=None, name="Beta", line=2),  # type: ignore[arg-type]
            _CodeProvider(repository=None, name="Alpha", line=1),  # type: ignore[arg-type]
        )
    )
    intelligence = CodeIntelligence(repo)  # type: ignore[arg-type]

    assert tuple(node.name for node in intelligence.get_symbol("a")) == ("Alpha", "Beta")


def test_code_intelligence_resolves_symbol_id_for_definitions() -> None:
    repo = _FakeRepository((_CodeProvider(repository=None, name="Alpha", line=3),))  # type: ignore[arg-type]
    intelligence = CodeIntelligence(repo)  # type: ignore[arg-type]

    result = intelligence.find_definition(
        SymbolLookupTarget(symbol_id="entity:file.ts:function:Alpha:3-3")
    )

    assert result[0].repository_rel_path == "file.ts"
    assert result[0].line_start == 3
    assert result[0].provenance[0].source_kind.value == "lsp"
