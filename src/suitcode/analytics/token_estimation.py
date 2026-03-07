from __future__ import annotations

from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus, SavingsConfidence, TokenEstimate


class TokenEstimator:
    _HIGH_VALUE_TOOLS = frozenset(
        {
            "analyze_change",
            "analyze_impact",
            "describe_components",
            "describe_files",
            "describe_symbol_context",
            "describe_test_target",
            "describe_runner",
            "run_test_targets",
            "run_runner",
            "build_target",
            "build_project",
        }
    )
    _MEDIUM_VALUE_TOOLS = frozenset(
        {
            "list_components",
            "list_component_dependency_edges",
            "get_component_dependencies",
            "get_component_dependents",
            "find_symbols",
            "list_symbols_in_file",
            "find_definition",
            "find_references",
            "list_tests",
            "get_related_tests",
            "repository_summary",
        }
    )

    def estimate(self, event: AnalyticsEvent) -> TokenEstimate:
        actual_tokens = self._actual_tokens(event)
        if event.status == AnalyticsStatus.ERROR:
            return TokenEstimate(
                tool_name=event.tool_name,
                actual_tokens_estimate=actual_tokens,
                counterfactual_tokens_estimate=actual_tokens,
                estimated_tokens_saved=0,
                confidence_level=SavingsConfidence.LOW,
            )

        multiplier, confidence = self._counterfactual_multiplier(event.tool_name)
        counterfactual = max(actual_tokens, int(actual_tokens * multiplier))
        return TokenEstimate(
            tool_name=event.tool_name,
            actual_tokens_estimate=actual_tokens,
            counterfactual_tokens_estimate=counterfactual,
            estimated_tokens_saved=max(counterfactual - actual_tokens, 0),
            confidence_level=confidence,
        )

    @staticmethod
    def _actual_tokens(event: AnalyticsEvent) -> int:
        argument_chars = len(str(event.arguments_redacted))
        output_chars = event.output_payload_bytes or 0
        estimate = (argument_chars + output_chars) // 4
        if estimate < 1:
            return 1
        return estimate

    def _counterfactual_multiplier(self, tool_name: str) -> tuple[float, SavingsConfidence]:
        if tool_name in self._HIGH_VALUE_TOOLS:
            return 4.0, SavingsConfidence.HIGH
        if tool_name in self._MEDIUM_VALUE_TOOLS:
            return 2.0, SavingsConfidence.MEDIUM
        return 1.2, SavingsConfidence.LOW

