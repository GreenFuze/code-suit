from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPARISON_DIR = PROJECT_ROOT / ".suit" / "evaluation" / "codex" / "comparisons" / "2026-03-19T10-54-59Z__codex-comparison-7e510e57620f40509ee4a01f5f86094f"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "evidence" / "codex-v7"
SELECTED_FIGURES = (
    "figures/01-headline-outcomes.svg",
    "figures/03-stable-execution-matrix.svg",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="export_marketing_evidence")
    parser.add_argument("--comparison-dir", default=str(DEFAULT_COMPARISON_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    export_marketing_evidence(
        comparison_dir=Path(args.comparison_dir),
        output_dir=Path(args.output_dir),
    )
    return 0


def export_marketing_evidence(*, comparison_dir: Path, output_dir: Path) -> None:
    comparison_dir = comparison_dir.resolve()
    output_dir = output_dir.resolve()
    comparison_json_path = comparison_dir / "comparison.json"
    comparison_md_path = comparison_dir / "comparison.md"
    if not comparison_json_path.exists():
        raise FileNotFoundError(f"comparison json not found: `{comparison_json_path}`")
    payload = json.loads(comparison_json_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    for relative_path in SELECTED_FIGURES:
        source = comparison_dir / relative_path
        if not source.exists():
            raise FileNotFoundError(f"expected figure missing: `{source}`")
        shutil.copyfile(source, figures_dir / source.name)
    summary = _render_summary(payload=payload, comparison_dir=comparison_dir, comparison_md_path=comparison_md_path)
    (output_dir / "README.md").write_text(summary, encoding="utf-8")


def _render_summary(*, payload: dict, comparison_dir: Path, comparison_md_path: Path) -> str:
    stable_suitcode = payload["stable_readonly_suitcode"]
    stable_baseline = payload["stable_readonly_baseline"]
    execution_suitcode = payload["stable_execution_suitcode"]
    execution_baseline = payload["stable_execution_baseline"]
    hero_turns = _find_metric(payload, "Median turns per stable headline task")
    hero_tokens = _find_metric(payload, "Median transcript-estimated tokens per stable headline task")
    generated_at = payload["generated_at_utc"]
    report_id = payload["report_id"]
    model = payload["model"]
    git_ref = payload["stable_readonly_suitcode_metadata"]["git_commit_hash"]
    return "\n".join(
        [
            "# SuitCode Evidence: Codex v7",
            "",
            "This page is the stable README-safe evidence export for the current Codex v7 comparison baseline.",
            "",
            "## Headline",
            "",
            f"- Stable downstream A/B: SuitCode `{stable_suitcode['task_passed']}/{stable_suitcode['task_total']}` vs baseline `{stable_baseline['task_passed']}/{stable_baseline['task_total']}`",
            f"- Median turns per stable headline task: SuitCode `{hero_turns['suitcode_value']}` vs baseline `{hero_turns['baseline_value']}`",
            f"- Stable execution A/B: SuitCode `{execution_suitcode['task_passed']}/{execution_suitcode['task_total']}` vs baseline `{execution_baseline['task_passed']}/{execution_baseline['task_total']}`",
            f"- Supporting token evidence: SuitCode `{hero_tokens['suitcode_value']}` vs baseline `{hero_tokens['baseline_value']}` transcript-estimated visible tokens per stable headline task",
            "",
            "## Figures",
            "",
            "![Headline outcomes](figures/01-headline-outcomes.svg)",
            "",
            "![Stable execution matrix](figures/03-stable-execution-matrix.svg)",
            "",
            "## Provenance",
            "",
            f"- Report id: `{report_id}`",
            f"- Generated at: `{generated_at}`",
            f"- Model: `{model}`",
            f"- Git commit: `{git_ref}`",
            f"- Full comparison markdown: `{comparison_md_path.relative_to(PROJECT_ROOT).as_posix()}`",
            f"- Full comparison directory: `{comparison_dir.relative_to(PROJECT_ROOT).as_posix()}`",
            "",
            "This export is generated from the canonical comparison artifact rather than hand-maintained.",
            "",
        ]
    )


def _find_metric(payload: dict, metric_name: str) -> dict[str, str]:
    for entry in payload.get("headline_efficiency", []):
        if entry.get("metric_name") == metric_name:
            return entry
    raise KeyError(f"headline efficiency metric not found: `{metric_name}`")


if __name__ == "__main__":
    raise SystemExit(main())
