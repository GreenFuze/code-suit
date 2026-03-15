from pathlib import Path


def test_evaluation_doc_exists_and_mentions_supported_agents() -> None:
    content = Path("scripts/EVALUATION.md").read_text(encoding="utf-8")
    assert "Current live evaluation support:" in content
    assert "- Codex CLI" in content
    assert "Current schema-level support reserved for future work:" in content
    assert "- Claude" in content
    assert "- Cursor" in content
    assert "Paper-Grade Metadata" in content
    assert "docs/evaluation/benchmark_protocol_v1.md" in content
    assert "docs/evaluation/task_schema.v1.json" in content


def test_protocol_docs_exist_and_cover_current_codex_harness() -> None:
    protocol = Path("docs/evaluation/benchmark_protocol_v1.md").read_text(encoding="utf-8")
    task_schema = Path("docs/evaluation/task_schema.v1.json").read_text(encoding="utf-8")
    failure_taxonomy = Path("docs/evaluation/failure_taxonomy.v1.json").read_text(encoding="utf-8")
    baseline_capabilities = Path("docs/evaluation/baseline_capabilities.v1.json").read_text(encoding="utf-8")
    report_template = Path("docs/evaluation/report_template.md").read_text(encoding="utf-8")

    assert "Codex only" in protocol
    assert "downstream stable read-only headline A/B" in protocol
    assert "suitcode_v6_headline.json" in protocol
    assert '"task_family"' in task_schema
    assert '"orientation"' in task_schema
    assert '"minimum_verified_change_set"' in task_schema
    assert '"answer_mismatch"' in failure_taxonomy
    assert '"usage_limit"' in failure_taxonomy
    assert '"name": "baseline"' in baseline_capabilities
    assert '"name": "treatment"' in baseline_capabilities
    assert "Baseline vs Treatment Definition" in report_template
    assert "Failure Analysis" in report_template
