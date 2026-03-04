from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from suitcode.core.intelligence_models import (
    ComponentContext,
    FileContext,
    ImpactSummary,
    ImpactTarget,
    SymbolContext,
)
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.context_service import ContextService
from suitcode.core.impact_service import ImpactService
from suitcode.core.repository_models import FileOwnerInfo, OwnedNodeInfo
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.provider_base import ProviderBase
from suitcode.providers.provider_metadata import RepositorySupportResult
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.quality_provider_base import QualityProviderBase
from suitcode.providers.registry import BUILTIN_PROVIDER_CLASSES, detect_support_for_root, get_provider_descriptors
from suitcode.providers.test_provider_base import TestProviderBase

if TYPE_CHECKING:
    from suitcode.core.architecture.architecture_intelligence import ArchitectureIntelligence
    from suitcode.core.code.code_intelligence import CodeIntelligence
    from suitcode.core.quality.quality_intelligence import QualityIntelligence
    from suitcode.core.tests.test_intelligence import TestIntelligence
    from suitcode.core.workspace import Workspace


class Repository:
    _VC_MARKERS = (".git", ".hg", ".svn", ".bzr")
    _IDE_MARKERS = (".vscode", ".idea")

    @classmethod
    def root_candidate(cls, repository_path: Path) -> Path:
        path = Path(repository_path).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"repository path does not exist: `{repository_path}`")
        if not path.is_dir():
            raise ValueError(f"repository path is not a directory: {repository_path}")

        ancestors = [path, *path.parents]

        for candidate in ancestors:
            if any((candidate / marker).exists() for marker in cls._VC_MARKERS):
                return candidate

        for candidate in ancestors:
            if (candidate / ".suit").is_dir():
                return candidate

        for candidate in ancestors:
            if any((candidate / marker).exists() for marker in cls._IDE_MARKERS):
                return candidate

        return path

    @staticmethod
    def ensure_suit_layout(repository_root: Path) -> Path:
        suit_dir = repository_root / ".suit"
        suit_dir.mkdir(parents=True, exist_ok=True)

        config_path = suit_dir / "config.json"
        state_path = suit_dir / "state.json"
        if not config_path.exists():
            config_path.write_text("{}\n", encoding="utf-8")
        if not state_path.exists():
            state_path.write_text("{}\n", encoding="utf-8")

        return suit_dir

    @classmethod
    def support_for_path(cls, repository_directory: Path) -> RepositorySupportResult:
        repository_root = cls.root_candidate(repository_directory)
        return detect_support_for_root(repository_root)

    def __init__(self, workspace: Workspace, repository_directory: Path, repository_id: str) -> None:
        self._workspace = workspace
        self._root = self.root_candidate(repository_directory)
        self._id = repository_id
        support = self.support_for_path(self._root)
        if not support.is_supported:
            available = ", ".join(descriptor.provider_id for descriptor in get_provider_descriptors())
            raise ValueError(
                f"repository is not supported: `{self._root}`. "
                f"No registered providers matched this repository. "
                f"Available providers: {available}. "
                "Use Repository.support_for_path(...) to inspect support before construction."
            )

        self._suit_dir = self.ensure_suit_layout(self._root)
        self._providers_by_id: dict[str, ProviderBase] = {}
        self._provider_roles_by_id: dict[str, frozenset[ProviderRole]] = {}
        self._ownership_index_service: OwnershipIndex | None = None
        self._context_service: ContextService | None = None
        self._impact_service: ImpactService | None = None
        self._initialize_providers(support)

        from suitcode.core.architecture.architecture_intelligence import ArchitectureIntelligence
        from suitcode.core.code.code_intelligence import CodeIntelligence
        from suitcode.core.quality.quality_intelligence import QualityIntelligence
        from suitcode.core.tests.test_intelligence import TestIntelligence

        self._arch = ArchitectureIntelligence(self)
        self._code = CodeIntelligence(self)
        self._tests = TestIntelligence(self)
        self._quality = QualityIntelligence(self)

    def _initialize_providers(self, support: RepositorySupportResult) -> None:
        support_by_id = {item.provider_id: item for item in support.detected_providers}
        for provider_cls in BUILTIN_PROVIDER_CLASSES:
            descriptor = provider_cls.descriptor()
            detected = support_by_id.get(descriptor.provider_id)
            if detected is None:
                continue

            provider = provider_cls(self)
            self._validate_provider_roles(provider, detected.detected_roles)
            self._providers_by_id[descriptor.provider_id] = provider
            self._provider_roles_by_id[descriptor.provider_id] = detected.detected_roles

    @staticmethod
    def _validate_provider_roles(provider: ProviderBase, roles: frozenset[ProviderRole]) -> None:
        role_contracts = {
            ProviderRole.ARCHITECTURE: ArchitectureProviderBase,
            ProviderRole.CODE: CodeProviderBase,
            ProviderRole.TEST: TestProviderBase,
            ProviderRole.QUALITY: QualityProviderBase,
        }
        for role in roles:
            contract = role_contracts[role]
            if not isinstance(provider, contract):
                raise ValueError(
                    f"provider `{provider.__class__.descriptor().provider_id}` declared role `{role.value}` "
                    f"but does not implement `{contract.__name__}`"
                )

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    @property
    def id(self) -> str:
        return self._id

    @property
    def root(self) -> Path:
        return self._root

    @property
    def suit_dir(self) -> Path:
        return self._suit_dir

    @property
    def name(self) -> str:
        return self._root.name

    @property
    def providers(self) -> tuple[ProviderBase, ...]:
        return tuple(self._providers_by_id.values())

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(self._providers_by_id.keys())

    @property
    def provider_roles(self) -> Mapping[str, frozenset[ProviderRole]]:
        return self._provider_roles_by_id

    def get_provider(self, provider_id: str) -> ProviderBase:
        provider = self._providers_by_id.get(provider_id)
        if provider is None:
            raise ValueError(f"unknown provider id for repository `{self._root}`: `{provider_id}`")
        return provider

    def get_providers_for_role(self, role: ProviderRole) -> tuple[ProviderBase, ...]:
        return tuple(
            provider
            for provider_id, provider in self._providers_by_id.items()
            if role in self._provider_roles_by_id[provider_id]
        )

    def has_provider(self, provider_id: str) -> bool:
        return provider_id in self._providers_by_id

    def supports_role(self, role: ProviderRole) -> bool:
        return any(role in roles for roles in self._provider_roles_by_id.values())

    @property
    def arch(self) -> "ArchitectureIntelligence":
        return self._arch

    @property
    def code(self) -> "CodeIntelligence":
        return self._code

    @property
    def tests(self) -> "TestIntelligence":
        return self._tests

    @property
    def quality(self) -> "QualityIntelligence":
        return self._quality

    def get_file_owner(self, repository_rel_path: str) -> FileOwnerInfo:
        return self._build_ownership_index().owner_for_file(repository_rel_path)

    def list_files_by_owner(self, owner_id: str) -> tuple["FileInfo", ...]:
        return self._build_ownership_index().files_for_owner(owner_id)

    def resolve_owner(self, owner_id: str) -> OwnedNodeInfo:
        return self._build_ownership_index().owner_info(owner_id)

    def describe_components(
        self,
        component_ids: tuple[str, ...],
        file_preview_limit: int = 20,
        dependency_preview_limit: int = 20,
        dependent_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> tuple[ComponentContext, ...]:
        return self._build_context_service().describe_components(
            component_ids,
            file_preview_limit=file_preview_limit,
            dependency_preview_limit=dependency_preview_limit,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def describe_files(
        self,
        repository_rel_paths: tuple[str, ...],
        symbol_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> tuple[FileContext, ...]:
        return self._build_context_service().describe_files(
            repository_rel_paths,
            symbol_preview_limit=symbol_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def describe_symbol_context(
        self,
        symbol_id: str,
        reference_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> SymbolContext:
        return self._build_context_service().describe_symbol_context(
            symbol_id,
            reference_preview_limit=reference_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def analyze_impact(
        self,
        target: ImpactTarget,
        reference_preview_limit: int = 20,
        dependent_preview_limit: int = 20,
        test_preview_limit: int = 20,
    ) -> ImpactSummary:
        return self._build_impact_service().analyze_impact(
            target,
            reference_preview_limit=reference_preview_limit,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def _build_ownership_index(self) -> OwnershipIndex:
        if self._ownership_index_service is None:
            self._ownership_index_service = OwnershipIndex(self)
        return self._ownership_index_service

    def _build_context_service(self) -> ContextService:
        if self._context_service is None:
            self._context_service = ContextService(self, self._build_ownership_index())
        return self._context_service

    def _build_impact_service(self) -> ImpactService:
        if self._impact_service is None:
            self._impact_service = ImpactService(self, self._build_ownership_index(), self._build_context_service())
        return self._impact_service
