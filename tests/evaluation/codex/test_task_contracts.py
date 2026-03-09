from __future__ import annotations

from suitcode.evaluation.codex.task_contracts import contract_for
from suitcode.evaluation.codex.task_models import CodexTaskFamily, default_high_value_tools, default_required_tools


def test_all_task_families_have_contracts() -> None:
    for family in CodexTaskFamily:
        contract = contract_for(family)
        assert contract.task_family == family
        assert contract.required_tools == default_required_tools(family)
        assert contract.preferred_high_value_tools == default_high_value_tools(family)

