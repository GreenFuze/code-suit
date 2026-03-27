from __future__ import annotations


HIGH_VALUE_TOOLS = (
    "understand_repository",
    "understand_file",
    "what_changes_if_i_edit_this",
    "what_should_i_run",
    "can_i_do_this",
    "repository_summary",
    "repository_summary_by_path",
    "describe_components",
    "describe_files",
    "describe_symbol_context",
    "analyze_change",
    "analyze_impact",
    "get_minimum_verified_change_set",
    "get_minimum_verified_change_set_by_path",
    "get_file_owner_by_path",
    "get_related_tests_by_path",
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
