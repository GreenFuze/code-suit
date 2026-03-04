from __future__ import annotations

from enum import StrEnum

from pydantic import model_validator

from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.models.nodes import StrictModel, TestDefinition


class RelatedTestTarget(StrictModel):
    repository_rel_path: str | None = None
    owner_id: str | None = None

    @model_validator(mode="after")
    def _validate_target_mode(self) -> "RelatedTestTarget":
        has_path = self.repository_rel_path is not None
        has_owner = self.owner_id is not None
        if has_path == has_owner:
            raise ValueError("exactly one of repository_rel_path or owner_id must be provided")
        if has_path:
            self.repository_rel_path = normalize_repository_relative_path(self.repository_rel_path)
        elif self.owner_id is not None and not self.owner_id.strip():
            raise ValueError("owner_id must not be empty")
        return self


class TestDiscoveryMethod(StrEnum):
    __test__ = False
    AUTHORITATIVE_PYTEST_COLLECT = "authoritative_pytest_collect"
    AUTHORITATIVE_JEST_LIST_TESTS = "authoritative_jest_list_tests"
    HEURISTIC_MANIFEST_GLOB = "heuristic_manifest_glob"
    HEURISTIC_CONFIG_GLOB = "heuristic_config_glob"
    HEURISTIC_UNITTEST = "heuristic_unittest"


class RelatedTestMatch(StrictModel):
    test_definition: TestDefinition
    relation_reason: str
    matched_owner_id: str | None = None
    matched_repository_rel_path: str | None = None
    discovery_method: TestDiscoveryMethod
    discovery_tool: str | None = None
    is_authoritative: bool

    @model_validator(mode="after")
    def _validate_reason_and_match(self) -> "RelatedTestMatch":
        allowed = {"same_owner", "same_component", "same_package", "repository_default_suite"}
        if self.relation_reason not in allowed:
            raise ValueError(f"unsupported relation_reason: `{self.relation_reason}`")
        if self.matched_repository_rel_path is not None:
            self.matched_repository_rel_path = normalize_repository_relative_path(self.matched_repository_rel_path)
        authoritative_methods = {
            TestDiscoveryMethod.AUTHORITATIVE_PYTEST_COLLECT,
            TestDiscoveryMethod.AUTHORITATIVE_JEST_LIST_TESTS,
        }
        if self.is_authoritative != (self.discovery_method in authoritative_methods):
            raise ValueError("is_authoritative must be consistent with discovery_method")
        return self


class DiscoveredTestDefinition(StrictModel):
    test_definition: TestDefinition
    discovery_method: TestDiscoveryMethod
    discovery_tool: str | None = None
    is_authoritative: bool

    @model_validator(mode="after")
    def _validate_authoritativeness(self) -> "DiscoveredTestDefinition":
        authoritative_methods = {
            TestDiscoveryMethod.AUTHORITATIVE_PYTEST_COLLECT,
            TestDiscoveryMethod.AUTHORITATIVE_JEST_LIST_TESTS,
        }
        if self.is_authoritative != (self.discovery_method in authoritative_methods):
            raise ValueError("is_authoritative must be consistent with discovery_method")
        return self
