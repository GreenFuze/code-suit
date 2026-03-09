from __future__ import annotations


HIGH_VALUE_TOOLS = (
    "repository_summary",
    "describe_components",
    "describe_files",
    "describe_symbol_context",
    "analyze_change",
    "analyze_impact",
    "get_minimum_verified_change_set",
    "get_truth_coverage",
    "describe_test_target",
    "run_test_targets",
    "describe_build_target",
    "build_target",
    "build_project",
    "describe_runner",
    "run_runner",
)

HIGH_VALUE_TOOL_SET = frozenset(HIGH_VALUE_TOOLS)
