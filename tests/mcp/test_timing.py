from __future__ import annotations

from suitcode.mcp.timing import request_timing_collector


def test_request_timing_collector_caps_stages_in_first_occurrence_order() -> None:
    with request_timing_collector("understand_file") as collector:
        collector.set_repository_reused(True)
        for index in range(10):
            with collector.stage(f"stage_{index}"):
                pass
        snapshot = collector.snapshot()

    assert snapshot.repository_reused is True
    assert tuple(stage.name for stage in snapshot.stages) == tuple(f"stage_{index}" for index in range(8))
    assert snapshot.truncated_stage_count == 2


def test_request_timing_collector_caps_slow_targets_and_preserves_status() -> None:
    with request_timing_collector("what_changes_if_i_edit_this") as collector:
        for index in range(7):
            repository_rel_path = f"src/{index}.ts"
            with collector.target_stage(repository_rel_path, "analyze_change"):
                pass
        collector.mark_target_status("src/0.ts", "incomplete")
        snapshot = collector.snapshot()

    assert len(snapshot.slow_targets) == 5
    assert snapshot.truncated_target_count == 2
    assert snapshot.slow_targets[0].repository_rel_path == "src/0.ts"
    assert snapshot.slow_targets[0].status == "incomplete"
    assert snapshot.slow_targets[0].dominant_stage == "analyze_change"
