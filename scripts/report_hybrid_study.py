from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.analytics.token_economics import generate_token_economics_report
from suitcode.evaluation.codex.service import CodexEvaluationService
from suitcode.evaluation.hybrid_reporting import HybridStudyReporter
from suitcode.evaluation.live_study import LiveStudyManifestStore, TrackedStudyRepositoryResolver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="report_hybrid_study")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--tracked-label", default="mygamesanywhere")
    scope.add_argument("--repository-root", default=None)
    parser.add_argument("--live-manifest-path", default=None)
    parser.add_argument("--codex-transcript", default=None)
    parser.add_argument("--controlled-report-id", default=None)
    parser.add_argument("--latest-controlled", action="store_true")
    parser.add_argument("--include-failures", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    repository = TrackedStudyRepositoryResolver().resolve(tracked_label=args.tracked_label, repository_root=args.repository_root)
    repository_root = Path(repository.repository_root)
    manifest_store = LiveStudyManifestStore(repository_root)
    manifest = (
        manifest_store.load(Path(args.live_manifest_path))
        if args.live_manifest_path
        else manifest_store.load_latest()
    )
    if manifest is None:
        raise ValueError("no live-study manifest found")
    live_report = generate_token_economics_report(
        repository_root,
        include_failures=bool(args.include_failures),
        analytics_run_id=manifest.analytics_run_id,
        codex_transcript_path=(Path(args.codex_transcript) if args.codex_transcript else None),
    )
    service = CodexEvaluationService(working_directory=PROJECT_ROOT)
    controlled_report = None
    if args.controlled_report_id is not None:
        controlled_report = service.load_report(args.controlled_report_id)
    elif args.latest_controlled:
        label = manifest.tracked_repository_label or repository.label
        controlled_report = service.load_latest_report_for_tracked_repository(label)
    reporter = HybridStudyReporter()
    report = reporter.build_report(
        workspace=repository_root,
        live_report=live_report,
        controlled_report=controlled_report,
        live_manifest=manifest,
    )
    artifacts = reporter.write_artifacts(workspace=repository_root, report=report)
    if args.as_json:
        payload = report.model_dump(mode="json")
        payload["artifacts"] = artifacts.model_dump(mode="json")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"Hybrid report: {report.report_id}")
    print(f"Artifacts: {artifacts.artifact_root}")
    print("Paper-readiness summary:")
    for line in report.paper_readiness_summary:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
