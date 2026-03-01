from __future__ import annotations

from suitcode.providers.npm import NPMProvider
from tests.providers.npm.expected_npm_provider_data import (
    EXPECTED_AGGREGATOR_IDS,
    EXPECTED_COMPONENT_IDS,
    EXPECTED_EXTERNAL_PACKAGE_IDS,
    EXPECTED_TEST_IDS,
)


def test_npm_fixture_alignment_counts(npm_provider: NPMProvider) -> None:
    assert len(npm_provider.get_components()) == len(EXPECTED_COMPONENT_IDS) == 22
    assert len(npm_provider.get_aggregators()) == len(EXPECTED_AGGREGATOR_IDS) == 3
    assert len(npm_provider.get_external_packages()) == len(EXPECTED_EXTERNAL_PACKAGE_IDS) == 22


def test_npm_fixture_test_ids_are_fixture_derived_not_rig_limited(npm_provider: NPMProvider) -> None:
    assert {item.id for item in npm_provider.get_tests()} == EXPECTED_TEST_IDS
    assert len(EXPECTED_TEST_IDS) == 19
