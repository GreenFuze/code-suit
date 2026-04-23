from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.analytics.token_economics import generate_token_economics_report, write_token_economics_report_artifacts
from suitcode.evaluation.live_study import LiveStudyManifestStore, TrackedStudyRepositoryResolver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="report_live_study")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--tracked-label", default="mygamesanywhere")
    scope.add_argument("--repository-root", default=None)
    parser.add_argument("--manifest-path", default=None)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--codex-transcript", default=None)
    parser.add_argument("--include-failures", action="store_true")
    parser.add_argument("--write-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    repository = TrackedStudyRepositoryResolver().resolve(tracked_label=args.tracked_label, repository_root=args.repository_root)
    repository_root = Path(repository.repository_root)
    manifest_store = LiveStudyManifestStore(repository_root)
    if args.manifest_path:
        manifest = manifest_store.load(Path(args.manifest_path))
    else:
        manifest = manifest_store.load_latest()
    if manifest is None:
        raise ValueError("no live-study manifest found")
    report = generate_token_economics_report(
        repository_root,
        include_failures=bool(args.include_failures),
        analytics_run_id=manifest.analytics_run_id,
        codex_transcript_path=(Path(args.codex_transcript) if args.codex_transcript else None),
    )
    artifacts = write_token_economics_report_artifacts(repository_root, report) if args.write_artifacts else None
    if args.as_json:
        payload = {"manifest": manifest.model_dump(mode="json"), "report": report.model_dump(mode="json")}
        if artifacts is not None:
            payload["artifacts"] = artifacts.model_dump(mode="json")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"Live-study report for analytics run: {manifest.analytics_run_id}")
    print(f"Workspace: {report.workspace}")
    print(f"Calls: {report.total.event_count}, failures: {report.total.failure_count}, unfinished: {report.total.unfinished_count}")
    print(
        "Estimated reductions: "
        f"response_based={_fmt_pct(report.total.estimated_task_token_reduction_pct_response_based)} "
        f"evidence_lower_bound={_fmt_pct(report.total.estimated_task_token_reduction_pct_evidence_lower_bound)}"
    )
    if artifacts is not None:
        print(f"Artifacts: {artifacts.artifact_root}")


def _fmt_pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


if __name__ == "__main__":
    main()
