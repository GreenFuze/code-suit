from __future__ import annotations

from pathlib import Path

from scripts.export_marketing_evidence import export_marketing_evidence


def test_readme_is_marketing_facing_and_links_core_docs() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "Your agent can search the repo. SuitCode asks the toolchain." in content
    assert "Stop guessing and exploring blindly. SuitCode turns repo/toolchain signals into deterministic actions." in content
    assert "suitcode-install --agent codex" in content
    assert "suitcode-install --agent claude" in content
    assert "suitcode-install --agent cursor" in content
    assert "[FEATURES.md](FEATURES.md)" in content
    assert "docs/evidence/codex-v7/README.md" in content
    assert "## Quick Proof" in content
    assert "## One End-To-End Example" in content
    assert "- Go" in content
    assert "Codex: live evaluation and passive analytics" in content
    assert "Claude Code: passive analytics" in content
    assert "Cursor: passive analytics" in content
    assert "## MCP Tools by Job" not in content


def test_features_file_exists_and_keeps_technical_catalog() -> None:
    content = Path("FEATURES.md").read_text(encoding="utf-8")

    assert "# SuitCode Features" in content
    assert "## MCP Tools by Job" in content
    assert "## Deterministic Execution Surfaces" in content
    assert "## Provenance and Trust Model" in content
    assert "- `go`" in content
    assert "Claude/Cursor passive analytics" in content
    assert "scripts/EVALUATION.md" in content


def test_example_doc_exists_and_is_linked() -> None:
    example = Path("docs/examples/bug-report-to-validation.md")
    assert example.exists()
    assert "What SuitCode surfaces" in example.read_text(encoding="utf-8")
    assert "docs/examples/bug-report-to-validation.md" in Path("README.md").read_text(encoding="utf-8")


def test_export_marketing_evidence_writes_bundle(tmp_path: Path) -> None:
    comparison_dir = Path(".suit/evaluation/codex/comparisons/2026-03-19T10-54-59Z__codex-comparison-7e510e57620f40509ee4a01f5f86094f")
    output_dir = tmp_path / "codex-v7"

    export_marketing_evidence(comparison_dir=comparison_dir, output_dir=output_dir)

    summary = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "SuitCode Evidence: Codex v7" in summary
    assert "Stable downstream A/B: SuitCode `5/5` vs baseline `2/5`" in summary
    assert "Median turns per stable headline task: SuitCode `3` vs baseline `16`" in summary
    assert "figures/01-headline-outcomes.svg" in summary
    assert (output_dir / "figures" / "01-headline-outcomes.svg").exists()
    assert (output_dir / "figures" / "03-stable-execution-matrix.svg").exists()


def test_export_marketing_evidence_is_idempotent(tmp_path: Path) -> None:
    comparison_dir = Path(".suit/evaluation/codex/comparisons/2026-03-19T10-54-59Z__codex-comparison-7e510e57620f40509ee4a01f5f86094f")
    output_dir = tmp_path / "codex-v7"

    export_marketing_evidence(comparison_dir=comparison_dir, output_dir=output_dir)
    first = (output_dir / "README.md").read_text(encoding="utf-8")
    export_marketing_evidence(comparison_dir=comparison_dir, output_dir=output_dir)
    second = (output_dir / "README.md").read_text(encoding="utf-8")

    assert first == second
